# SPDX-License-Identifier: GPL-3.0-or-later
"""Relay analyzer (M3, from the M0 spike): runs in a child process of the relay.

Reads framed output from the relay, splits it into commands using the OSC 133 / OSC 7 / OSC 7717
markers from hooks.bash, renders text with pyte, and answers requests on a unix socket
(one JSON object per line):

    {"cmd": "status"}                      relay, shell, state, cwd, foreground process
    {"cmd": "history", "n": 5}             last n commands with their output as plain text
    {"cmd": "screen"}                      what the terminal shows now
    {"cmd": "send", "text": "...", "force": false}
                                           put text at the prompt, as if typed, without Enter
"""

from __future__ import annotations

import collections
import fcntl
import json
import os
import selectors
import socket
import struct
import termios
import time
from urllib.parse import unquote, urlparse

import pyte

from .emulator import BRACKETED_PASTE, AltScreen, CaptureScreen

OSC_MAX = 64 * 1024
TIOCGPTN = 0x80045430  # not exported by the termios module
BEHIND = 256 * 1024     # one pipe read this big means we're behind the shell
TAIL = 64 * 1024        # then emulate only this much of it


class OscScanner:
    """Splits a byte stream into ('text', bytes) and ('osc', payload) events across chunks."""

    def __init__(self) -> None:
        self.hold = b""  # an incomplete OSC, or a trailing ESC that may start one
        self.in_osc = False

    def reset(self) -> None:
        self.hold = b""
        self.in_osc = False

    def feed(self, data: bytes):
        data = self.hold + data
        self.hold = b""
        pos = 0
        while pos < len(data):
            if not self.in_osc:
                start = data.find(b"\x1b]", pos)
                if start < 0:
                    end = len(data) - 1 if data.endswith(b"\x1b") else len(data)
                    if end > pos:
                        yield "text", data[pos:end]
                    self.hold = data[end:]
                    return
                if start > pos:
                    yield "text", data[pos:start]
                self.in_osc = True
                pos = start + 2
            bel = data.find(b"\x07", pos)
            st = data.find(b"\x1b\\", pos)
            ends = [(i, n) for i, n in ((bel, 1), (st, 2)) if i >= 0]
            if not ends:
                if len(data) - pos > OSC_MAX:  # not a real OSC; give up on it
                    self.in_osc = False
                    continue
                self.hold = b"\x1b]" + data[pos:]
                self.in_osc = False
                return
            end, n = min(ends)
            yield "osc", data[pos:end]
            self.in_osc = False
            pos = end + n


class Analyzer:
    def __init__(self, master: int, shell_pid: int, relay_pid: int) -> None:
        self.master = master
        self.shell_pid = shell_pid
        self.relay_pid = relay_pid
        self.screen = AltScreen(80, 24)
        self.stream = pyte.ByteStream(self.screen)
        self.scanner = OscScanner()
        self.state = "unknown"      # prompt | input | running | done
        self.segmented = False      # seen shell hooks at least once
        self.on = True              # `ai on|off`
        self.secret = False         # echo off in canonical mode (password prompt)
        self.cwd = None
        self.gaps = 0
        self.history: collections.deque = collections.deque(maxlen=50)
        self.count = 0
        self.cur = None             # command being run
        self.cap = None             # its CaptureScreen
        self.cap_stream = None
        self.hook_cmd = None        # ('text', str) | ('unrecorded', None) from the hooks
        self.input_at = None        # (y, x, scrolls) at the end of the prompt

    # --- relay frames ---------------------------------------------------------------------
    def batch(self, frames: list[tuple[bytes, bytes]]) -> None:
        """Handle what one pipe read delivered. If that is a lot, we are behind (a flood):
        markers are still processed in order, but only the last TAIL bytes of text go through
        pyte, since emulation is what's slow. The skipped part counts as a gap."""
        total = sum(len(p) for k, p in frames if k == b"D")
        skip = total - TAIL if total > BEHIND else 0
        if skip:
            self.gaps += 1
            if self.cur:
                self.cur["truncated"] = True
        for kind, payload in frames:
            if kind != b"D":
                self.frame(kind, payload)
                continue
            for what, data in self.scanner.feed(payload):
                if what == "osc":
                    self.osc(data)
                elif skip >= len(data):
                    skip -= len(data)
                else:
                    self.text(data[skip:])
                    skip = 0

    def frame(self, kind: bytes, payload: bytes) -> None:
        if kind == b"D":
            self.batch([(kind, payload)])
        elif kind == b"W":
            rows, cols = struct.unpack("HHHH", payload)[:2]
            self.screen.resize(rows, cols)
            if self.cap:
                self.cap.resize(rows, cols)
        elif kind == b"S":
            self.secret = payload == b"1"
            if self.secret and self.cur:
                self.cur["secret"] = True
        elif kind == b"G":
            self.gaps += 1
            self.scanner.reset()
            if self.cur:
                self.cur["truncated"] = True

    def text(self, data: bytes) -> None:
        if not self.on:
            return
        self.stream.feed(data)
        # Output shown during a password prompt is never captured.
        if self.cap and not self.secret:
            self.cap_stream.feed(data)

    def osc(self, p: bytes) -> None:
        if p.startswith(b"7717;ai="):
            self.on = p.endswith(b"on")
            if not self.on:
                self.cur = self.cap = self.cap_stream = None
                self.state = "unknown"
            return
        if not self.on:
            return
        if p.startswith(b"133;"):
            self.segmented = True
            mark = p[4:5]
            if mark == b"A":
                self.state = "prompt"
            elif mark == b"B":
                self.state = "input"
                c = self.screen.cursor
                self.input_at = (c.y, c.x, self.screen.scrolls)
            elif mark == b"C":
                self.start_command()
            elif mark == b"D":
                code = p[6:].decode(errors="replace")
                self.end_command(int(code) if code.lstrip("-").isdigit() else None)
        elif p.startswith(b"7;"):
            self.cwd = unquote(urlparse(p[2:].decode(errors="replace")).path)
        elif p.startswith(b"7717;cmd="):
            self.hook_cmd = ("text", unquote(p[9:].decode(errors="replace")))
        elif p == b"7717;unrecorded":
            self.hook_cmd = ("unrecorded", None)

    # --- segmentation ---------------------------------------------------------------------
    def screen_command(self) -> str | None:
        """The command line as the user saw it: from the end of the prompt up to the cursor."""
        if not self.input_at:
            return None
        y, x, scrolls = self.input_at
        y -= self.screen.scrolls - scrolls
        if y < 0:
            y, x = 0, 0
        end = self.screen.cursor.y
        lines = [self.screen.line_text(row, x if row == y else 0) for row in range(y, max(end, y + 1))]
        return "\n".join(lines)

    def start_command(self) -> None:
        if self.cur:  # never saw its end (lost in a gap, or a shell without hooks)
            self.cur["truncated"] = True
            self.end_command(None)
        on_screen = self.screen_command()
        kind, text = self.hook_cmd or ("unrecorded", None)
        if kind == "text":
            cmd, source = text, "hook"
        elif on_screen and not on_screen[:1].isspace():
            cmd, source = on_screen, "screen"  # a repeat that ignoredups kept out of history
        else:
            cmd, source = None, "hidden"       # " cmd" with ignorespace: keep it private
        self.hook_cmd = None
        self.count += 1
        self.cur = {
            "id": self.count, "cmd": cmd, "cmd_source": source, "screen_cmd": on_screen,
            "cwd": self.cwd, "start": time.time(), "end": None, "exit": None, "output": None,
            "lines": 0, "truncated": False, "secret": self.secret, "fullscreen": False,
        }
        self.state = "running"
        if source == "hidden":
            self.cap = self.cap_stream = None
        else:
            self.cap = CaptureScreen(self.screen.columns, self.screen.lines)
            self.cap_stream = pyte.ByteStream(self.cap)

    def end_command(self, code: int | None) -> None:
        self.state = "done"
        if not self.cur:
            return  # D before the first prompt, or for an empty line
        rec, self.cur = self.cur, None
        rec["end"] = time.time()
        rec["exit"] = code
        if self.cap:
            rec["output"] = self.cap.text()
            rec["lines"] = rec["output"].count("\n") + 1 if rec["output"] else 0
            rec["fullscreen"] = self.cap.alt_used
            rec["truncated"] |= self.cap.dropped > 0
        self.cap = self.cap_stream = None
        self.history.append(rec)

    # --- requests -------------------------------------------------------------------------
    def foreground(self) -> dict:
        try:
            pgid = os.tcgetpgrp(self.master)
            with open(f"/proc/{pgid}/comm") as f:
                comm = f.read().strip()
            with open(f"/proc/{pgid}/status") as f:
                uid = next(int(l.split()[1]) for l in f if l.startswith("Uid:"))
            with open(f"/proc/{pgid}/cmdline", "rb") as f:
                argv = [a.decode(errors="replace") for a in f.read().split(b"\0") if a]
        except (OSError, StopIteration):
            return {}
        return {"pid": pgid, "comm": comm, "uid": uid, "argv": argv}

    def status(self) -> dict:
        ptn = struct.unpack("I", fcntl.ioctl(self.master, TIOCGPTN, b"\0" * 4))[0]
        return {
            "relay_pid": self.relay_pid, "analyzer_pid": os.getpid(), "shell_pid": self.shell_pid,
            "tty": f"/dev/pts/{ptn}", "state": self.state, "segmented": self.segmented,
            "ai": self.on, "secret": self.secret, "cwd": self.cwd, "gaps": self.gaps,
            "size": [self.screen.columns, self.screen.lines], "commands": self.count,
            "foreground": self.foreground(),
        }

    def send(self, text: str, force: bool = False) -> dict:
        if not self.on:
            return {"ok": False, "error": "sharing is off in this terminal (ai on)"}
        if self.secret:
            return {"ok": False, "error": "the terminal is at a password prompt"}
        fg = self.foreground()
        warnings = []
        if fg.get("uid") == 0:
            warnings.append("this terminal is root")
        if fg.get("comm") == "ssh":
            host = next((a for a in fg["argv"][1:] if not a.startswith("-")), "?")
            warnings.append(f"this terminal is ssh to {host}")
        at_prompt = self.state == "input" and fg.get("pid") == self.shell_pid
        if not at_prompt and not force:
            return {"ok": False, "error": f"not at a shell prompt (running: {fg.get('comm')})",
                    "warnings": warnings}
        # Typed input only: no escape sequences, no Enter.
        text = "".join(ch for ch in text if ch == "\n" or ch == "\t" or ch >= " ").strip("\n")
        if BRACKETED_PASTE in self.screen.mode:
            data = b"\x1b[200~" + text.encode() + b"\x1b[201~"  # readline won't run it
        elif "\n" in text:
            return {"ok": False, "error": "multi-line text needs bracketed paste"}
        else:
            data = text.encode()
        os.write(self.master, data)
        return {"ok": True, "warnings": warnings}

    def handle(self, req: dict) -> dict:
        cmd = req.get("cmd")
        if cmd == "status":
            return self.status()
        if cmd == "history":
            return {"commands": list(self.history)[-int(req.get("n", 10)):]}
        if cmd == "screen":
            return {"lines": [self.screen.line_text(y) for y in range(self.screen.lines)],
                    "cursor": [self.screen.cursor.x, self.screen.cursor.y],
                    "fullscreen": self.screen.in_alt}
        if cmd == "send":
            return self.send(str(req.get("text", "")), bool(req.get("force")))
        return {"error": f"unknown cmd {cmd!r}"}


def listen(sock_path: str) -> socket.socket:
    """The analyzer's control socket, user-only. The relay opens it before the shell starts, so the first prompt
    already sees it (the ◆ marker), and hands it to the analyzer."""
    os.makedirs(os.path.dirname(sock_path), mode=0o700, exist_ok=True)
    try:
        os.unlink(sock_path)
    except FileNotFoundError:
        pass
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    old = os.umask(0o177)
    try:
        listener.bind(sock_path)
    finally:
        os.umask(old)
    listener.listen(8)
    return listener


def run(rfd: int, master: int, shell_pid: int, listener: socket.socket, sock_path: str, relay_pid: int) -> None:
    an = Analyzer(master, shell_pid, relay_pid)
    listener.setblocking(False)

    sel = selectors.DefaultSelector()
    sel.register(rfd, selectors.EVENT_READ, "pipe")
    sel.register(listener, selectors.EVENT_READ, "listen")
    buf = bytearray()
    try:
        while True:
            for key, _ in sel.select():
                if key.data == "pipe":
                    chunk = os.read(rfd, 1 << 20)
                    if not chunk:
                        return  # relay is gone
                    buf += chunk
                    frames, pos = [], 0
                    while len(buf) - pos >= 5:
                        n = struct.unpack_from("<I", buf, pos + 1)[0]
                        if len(buf) - pos < 5 + n:
                            break
                        frames.append((bytes(buf[pos:pos + 1]), bytes(buf[pos + 5:pos + 5 + n])))
                        pos += 5 + n
                    del buf[:pos]
                    an.batch(frames)
                elif key.data == "listen":
                    conn, _ = listener.accept()
                    conn.setblocking(False)
                    sel.register(conn, selectors.EVENT_READ, bytearray())
                else:
                    conn, pending = key.fileobj, key.data
                    try:
                        chunk = conn.recv(65536)
                    except OSError:
                        chunk = b""
                    pending += chunk
                    if not chunk or b"\n" in pending:
                        sel.unregister(conn)
                        if b"\n" in pending:
                            line = pending.split(b"\n", 1)[0]
                            try:
                                reply = an.handle(json.loads(line))
                            except Exception as e:  # a bad request must not take the terminal's analyzer down
                                reply = {"error": repr(e)}
                            conn.setblocking(True)
                            conn.sendall(json.dumps(reply).encode() + b"\n")
                        conn.close()
    finally:
        try:
            os.unlink(sock_path)
        except OSError:
            pass
