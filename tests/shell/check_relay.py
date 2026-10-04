#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Terminal relay checks (M3; the M0 spike's suite, now against cin_minai.shell). Run on Linux from the repo root:

    python3 tests/shell/check_relay.py [-k name]

Plays the terminal emulator: each shell runs in an outer pty whose output is rendered with pyte.
Identity checks run every scenario twice (plain `bash --rcfile hooks.bash` vs. the relay) and
compare what the user would see. The rest checks segmentation, privacy rules, send-to-prompt,
the ◆ marker, latency and throughput through the relay.
"""

from __future__ import annotations

import fcntl
import glob
import hashlib
import os
import pty
import select
import shutil
import signal
import statistics
import struct
import sys
import tempfile
import termios
import time

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src")
sys.path.insert(0, SRC)

import pyte  # noqa: E402

from cin_minai.shell.ctl import request  # noqa: E402
from cin_minai.shell.emulator import AltScreen  # noqa: E402

HOOKS = os.path.join(SRC, "cin_minai", "shell", "hooks.bash")
RELAY_CMD = f"{sys.executable} -P -m cin_minai.shell.relay"
TMP = tempfile.mkdtemp(prefix="relay-check-")
HOME = os.path.join(TMP, "home")
RUN = os.path.join(TMP, "run")
os.makedirs(HOME)
os.makedirs(RUN, mode=0o700)
with open(os.path.join(HOME, ".bashrc"), "w") as f:
    f.write("PS1='\\u@test:\\w\\$ '\nHISTCONTROL=ignoreboth\nHISTFILE=/dev/null\n")
with open(os.path.join(HOME, "notes.txt"), "w") as f:
    f.write("".join(f"line {i}\n" for i in range(1, 201)))
# A stand-in for Mint's sudo: pwfeedback prompt (echo off, character mode, signals on, '*' per
# key), then relaying the command's output in full raw mode (use_pty). Named "sudo" so that
# /proc/<pid>/comm says sudo.
FAKEBIN = os.path.join(TMP, "bin")
os.makedirs(FAKEBIN)
with open(os.path.join(FAKEBIN, "sudo"), "w") as f:
    f.write(f"""#!{sys.executable}
import os, sys, termios, tty
fd = sys.stdin.fileno()
old = termios.tcgetattr(fd)
new = termios.tcgetattr(fd)
new[3] &= ~(termios.ECHO | termios.ICANON)
termios.tcsetattr(fd, termios.TCSANOW, new)
os.write(1, b"[sudo] password for user: ")
while (ch := os.read(fd, 1)) not in (b"\\r", b"\\n"):
    os.write(1, b"*")
os.write(1, b"\\r\\n")
tty.setraw(fd)
os.write(1, b"relayed output: " + " ".join(sys.argv[1:]).encode() + b"\\r\\n")
termios.tcsetattr(fd, termios.TCSANOW, old)
""")
os.chmod(os.path.join(FAKEBIN, "sudo"), 0o755)

ENV = {
    "HOME": HOME, "PATH": os.environ["PATH"], "TERM": "xterm-256color", "LANG": "C.UTF-8",
    "USER": os.environ.get("USER", "user"), "XDG_RUNTIME_DIR": RUN, "SHELL": "/bin/bash",
    "PYTHONPATH": os.path.abspath(SRC),
}
PLAIN = ["bash", "--rcfile", HOOKS, "-i"]
RELAYED = [sys.executable, "-P", "-m", "cin_minai.shell.relay"]

results: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""), flush=True)


class Term:
    """An outer pty + pyte screen: what the user's terminal emulator would show."""

    def __init__(self, argv: list[str], cols: int = 100, rows: int = 30, render: bool = True):
        self.render = render
        self.raw = bytearray()
        self.pid, self.fd = pty.fork()
        if self.pid == 0:
            fcntl.ioctl(0, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
            os.chdir(HOME)
            os.execvpe(argv[0], argv, ENV)
        self.screen = AltScreen(cols, rows)
        self.stream = pyte.ByteStream(self.screen)
        self.status = None

    def pump(self, timeout: float = 0.05) -> int:
        got = 0
        end = time.monotonic() + timeout
        while True:
            left = end - time.monotonic()
            r, _, _ = select.select([self.fd], [], [], max(left, 0))
            if not r:
                return got
            try:
                data = os.read(self.fd, 1 << 20)
            except OSError:
                data = b""
            if not data:
                return got
            got += len(data)
            self.raw += data
            if self.render:
                self.stream.feed(data)

    def send(self, data: bytes | str) -> None:
        os.write(self.fd, data.encode() if isinstance(data, str) else data)

    def text(self) -> str:
        return "\n".join(self.screen.line_text(y) for y in range(self.screen.lines)).rstrip()

    def wait(self, needle: str, timeout: float = 10.0) -> bool:
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if needle in self.text():
                return True
            self.pump(0.05)
        return needle in self.text()

    def settle(self, quiet: float = 0.4, timeout: float = 10.0) -> None:
        end = time.monotonic() + timeout
        while time.monotonic() < end and self.pump(quiet):
            pass

    def run(self, line: str, settle: float = 0.4) -> None:
        self.send(line + "\r")
        self.settle(settle)

    def resize(self, cols: int, rows: int) -> None:
        fcntl.ioctl(self.fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
        self.screen.resize(rows, cols)

    def close(self) -> int | None:
        try:
            os.kill(self.pid, signal.SIGHUP)
        except ProcessLookupError:
            pass
        return self.reap()

    def reap(self, timeout: float = 5.0) -> int | None:
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            self.pump(0.05)
            pid, st = os.waitpid(self.pid, os.WNOHANG)
            if pid:
                self.status = os.waitstatus_to_exitcode(st)
                break
        try:
            os.close(self.fd)
        except OSError:
            pass
        return self.status


def sockets() -> list[str]:
    return glob.glob(os.path.join(RUN, "cinminai", "relay-*.sock"))


def ctl(term_pid: int, req: dict) -> dict:
    return request(os.path.join(RUN, "cinminai", f"relay-{term_pid}.sock"), req)


def last(term: Term, n: int = 1) -> list[dict]:
    return ctl(term.pid, {"cmd": "history", "n": n})["commands"]


# --- identity: the same keys give the same screen, with and without the relay -----------------

def sc_basic(t: Term) -> list[str]:
    t.run("echo hello; printf '\\e[31mred\\e[0m \\e[1mbold\\e[0m\\n'; ls /usr")
    return [t.text()]


def sc_vim(t: Term) -> list[str]:
    t.run("vim -u NONE -N scratch.txt", 1.0)
    t.send("ihello from vim\x1b")
    t.settle(0.5)
    shot = t.text()
    t.send(":wq\r")
    t.settle(0.5)
    t.run("cat scratch.txt; rm scratch.txt")
    return [shot, t.text()]


def sc_less(t: Term) -> list[str]:
    t.run("less notes.txt", 0.6)
    t.send(" ")
    t.settle(0.4)
    shot = t.text()
    t.send("q")
    t.settle(0.4)
    return [shot, t.text()]


def sc_htop(t: Term) -> list[str]:
    t.run("htop", 1.5)
    ok = "PID" in t.text() or "CPU" in t.text()
    t.send("q")
    t.settle(0.5)
    return [f"htop drew: {ok}", t.text()]  # htop's numbers change; compare after it exits


def sc_tmux(t: Term) -> list[str]:
    t.run("tmux -f /dev/null -L relaycheck new-session", 1.0)
    t.run("echo inside-tmux", 0.6)
    inside = "inside-tmux" in t.text()
    t.run("exit", 1.0)
    return [f"tmux shell works: {inside}", t.text()]


def sc_python(t: Term) -> list[str]:
    t.run("python3 -q", 0.8)
    t.run("print(6 * 7)")
    t.run("exit()", 0.6)
    return [t.text()]


def sc_ctrl_c(t: Term) -> list[str]:
    t.run("sleep 30", 0.3)
    start = time.monotonic()
    t.send("\x03")
    t.wait("$ ", 3)
    t.settle(0.3)
    return [f"interrupted in <2s: {time.monotonic() - start < 2}", t.text()]


def sc_ctrl_z(t: Term) -> list[str]:
    t.run("sleep 30", 0.3)
    t.send("\x1a")
    t.settle(0.4)
    t.run("jobs")
    t.run("kill %1")
    t.run("true")
    return [t.text()]


def sc_resize(t: Term) -> list[str]:
    t.resize(120, 40)
    t.settle(0.3)
    t.run("echo cols=$(tput cols) lines=$(tput lines)")
    return [t.text()]


SCENARIOS = [sc_basic, sc_vim, sc_less, sc_htop, sc_tmux, sc_python, sc_ctrl_c, sc_ctrl_z, sc_resize]


def identity() -> None:
    for sc in SCENARIOS:
        shots = {}
        for mode, argv in (("plain", PLAIN), ("relay", RELAYED)):
            t = Term(argv)
            t.wait("$ ")
            t.settle(0.3)
            shots[mode] = sc(t)
            t.close()
        # The ◆ marker is the one intended difference: it shows only where something listens (the relay).
        shots = {m: [x.replace("◆ ", "") for x in v] for m, v in shots.items()}
        same = shots["plain"] == shots["relay"]
        detail = ""
        if not same:
            for a, b in zip(shots["plain"], shots["relay"]):
                if a != b:
                    detail = f"\n--- plain ---\n{a}\n--- relay ---\n{b}"
                    break
        record(f"identity: {sc.__name__[3:]}", same, detail)


# --- segmentation and privacy ------------------------------------------------------------------

def segmentation() -> None:
    t = Term(RELAYED)
    t.wait("$ ")
    t.settle(0.3)

    st = ctl(t.pid, {"cmd": "status"})
    record("status: socket + foreground shell", st["foreground"].get("comm") == "bash",
           f"tty={st['tty']} fg={st['foreground'].get('comm')}")
    record("prompt shows sharing indicator", "◆ " in t.text())
    record("the very first prompt already shows it (socket opened before the shell)",
           "◆ " in next((l for l in t.text().split("\n") if l.rstrip().endswith("$")), ""))

    t.run("echo hello")
    r = last(t)[0]
    record("command text + output + exit 0",
           (r["cmd"], r["output"], r["exit"], r["cmd_source"]) == ("echo hello", "hello", 0, "hook"),
           f"{r['cmd']!r} -> {r['output']!r} exit {r['exit']}")

    t.run("ls /nonexistent-dir")
    r = last(t)[0]
    record("failing command: exit code + stderr", r["exit"] == 2 and "No such file" in (r["output"] or ""),
           f"exit {r['exit']}")

    t.run("echo hello")
    t.run("echo hello")
    r = last(t)[0]
    record("repeated command (ignoredups) taken from screen",
           (r["cmd"], r["cmd_source"], r["output"]) == ("echo hello", "screen", "hello"),
           f"{r['cmd']!r} via {r['cmd_source']}")

    t.run(" echo hidden-secret")
    r = last(t)[0]
    record("space-prefixed command (ignorespace) stays private",
           r["cmd"] is None and r["output"] is None and r["cmd_source"] == "hidden")

    t.run("cd /tmp")
    t.run("true")
    r = last(t)[0]
    record("cwd from OSC 7", r["cwd"] == "/tmp", f"{r['cwd']}")
    t.run("cd ~")

    t.run("seq 1 3000", 1.0)
    r = last(t)[0]
    out = (r["output"] or "").split("\n")
    record("long output kept past the screen (3000 lines)",
           len(out) == 3000 and out[0] == "1" and out[-1] == "3000" and not r["truncated"],
           f"{len(out)} lines")

    t.send("for i in 1 2; do\r")
    t.send("echo L$i\r")
    t.run("done")
    r = last(t)[0]
    record("multi-line command", "for i in 1 2" in (r["cmd"] or "") and r["output"] == "L1\nL2",
           f"{r['cmd']!r} -> {r['output']!r}")

    t.run("vim -u NONE -N", 1.0)
    t.send(":q\r")
    t.settle(0.5)
    r = last(t)[0]
    record("full-screen program flagged, no redraw noise captured",
           r["fullscreen"] and not r["output"], f"output={r['output']!r}")

    # Echo-off rule: password prompts.
    t.send("read -s -p 'Password: ' pw; echo; echo len=${#pw}\r")
    t.wait("Password:")
    t.settle(0.3)
    st = ctl(t.pid, {"cmd": "status"})
    refused = ctl(t.pid, {"cmd": "send", "text": "oops", "force": True})
    t.send("hunter2\r")
    t.settle(0.4)
    r = last(t)[0]
    everywhere = str(ctl(t.pid, {"cmd": "history", "n": 50})) + str(ctl(t.pid, {"cmd": "screen"}))
    record("password prompt detected (echo off, canonical)", st["secret"] is True)
    record("send refused at a password prompt", refused.get("ok") is False, refused.get("error", ""))
    record("typed secret never captured", "hunter2" not in everywhere and r["secret"])

    t.send(f"{FAKEBIN}/sudo apt update\r")
    t.wait("password for")
    t.settle(0.3)
    st = ctl(t.pid, {"cmd": "status"})
    t.send("s3cret\r")
    t.settle(0.4)
    r = last(t)[0]
    record("sudo pwfeedback prompt (character mode) detected", st["secret"] is True)
    record("sudo's relayed command output still captured",
           r["secret"] and "relayed output: apt update" in (r["output"] or ""), repr(r["output"]))

    # Send to prompt: typed, not executed.
    n_before = ctl(t.pid, {"cmd": "status"})["commands"]
    rep = ctl(t.pid, {"cmd": "send", "text": "echo injected\n"})
    t.settle(0.5)
    n_after = ctl(t.pid, {"cmd": "status"})["commands"]
    record("send puts text at the prompt without running it",
           rep.get("ok") and "echo injected" in t.text() and n_after == n_before, str(rep))
    t.send("\r")
    t.settle(0.4)
    r = last(t)[0]
    record("sent command runs when the user presses Enter",
           (r["cmd"], r["output"]) == ("echo injected", "injected"), f"{r['cmd']!r}")

    t.send("sleep 2\r")
    t.settle(0.2)
    rep = ctl(t.pid, {"cmd": "send", "text": "echo nope"})
    record("send refused while a program runs", rep.get("ok") is False, rep.get("error", ""))
    time.sleep(2)
    t.settle(0.4)

    # ai off / on.
    t.run("ai off")
    no_ind = "◆" not in t.text().split("\n")[-1]
    t.run("echo private-stuff")
    t.run("ai on")
    t.run("echo public-stuff")
    hist = str(ctl(t.pid, {"cmd": "history", "n": 50}))
    record("ai off: nothing captured, indicator gone",
           no_ind and "private-stuff" not in hist and "public-stuff" in hist)

    # Nesting guard.
    before = len(sockets())
    t.run(RELAY_CMD, 0.8)
    nested = len(sockets())
    t.run("exit", 0.5)
    record("nested relay execs the shell instead", nested == before, f"sockets {before}->{nested}")

    # Analyzer dies -> pass-through continues.
    apid = ctl(t.pid, {"cmd": "status"})["analyzer_pid"]
    os.kill(apid, signal.SIGKILL)
    time.sleep(0.2)
    t.run("echo still-alive")
    record("relay keeps working when the analyzer dies", "still-alive" in t.text().split("\n")[-2])
    t.run("true")
    record("with the analyzer gone, the ◆ marker disappears (nothing is listening)",
           "◆" not in t.text().split("\n")[-1], t.text().split("\n")[-1])

    t.send("exit 3\r")
    code = t.reap()
    record("shell exit status passed through", code == 3, f"status {code}")


# --- latency and throughput ----------------------------------------------------------------

def echo_latency(argv: list[str], n: int = 400) -> list[float]:
    t = Term(argv, render=False)
    t.pump(1.0)
    t.settle(0.3)
    samples = []
    for i in range(n):
        key = b"x" if i % 2 == 0 else b"\x7f"
        start = time.perf_counter()
        t.send(key)
        select.select([t.fd], [], [], 2.0)  # first byte of the echo
        samples.append((time.perf_counter() - start) * 1000)
        t.raw += os.read(t.fd, 65536)
        t.settle(0.005, timeout=0.05)
    t.close()
    return samples


def latency() -> None:
    res = {}
    for mode, argv in (("plain", PLAIN), ("relay", RELAYED)):
        s = sorted(echo_latency(argv))
        res[mode] = (statistics.median(s), s[int(len(s) * 0.95)], s[int(len(s) * 0.99)])
    add = res["relay"][0] - res["plain"][0]
    record("keystroke echo latency added by relay < 2 ms (median)", add < 2.0,
           " | ".join(f"{m}: median {a:.2f} p95 {b:.2f} p99 {c:.2f} ms" for m, (a, b, c) in res.items()))


def throughput() -> None:
    big = os.path.join(TMP, "big.txt")
    with open(big, "w") as f:
        for start in range(0, 12_000_000, 100_000):
            f.write("\n".join(map(str, range(start, start + 100_000))) + "\n")
    size = os.path.getsize(big)
    res = {}
    for mode, argv in (("plain", PLAIN), ("relay", RELAYED)):
        t = Term(argv, render=False)
        t.pump(1.0)
        t.settle(0.3)
        mark = len(t.raw)
        start = time.perf_counter()
        t.send(f"cat {big}; echo __DO''NE__\r")
        while b"\n__DONE__" not in t.raw[-4096:]:
            t.pump(1.0)
        dt = time.perf_counter() - start
        t.settle(0.5)
        body = bytes(t.raw[mark:])
        res[mode] = (dt, hashlib.sha256(body[: body.rindex(b"\n__DONE__")]).hexdigest())
        if mode == "relay":
            st = ctl(t.pid, {"cmd": "status"})
            h = last(t, 2)
            t.run("echo after-flood")
            after = last(t)[0]
        t.close()
    mb = size / 1e6
    record(f"throughput: cat {mb:.0f} MB",
           res["relay"][0] < res["plain"][0] * 1.5 + 0.5,
           f"plain {mb / res['plain'][0]:.0f} MB/s, relay {mb / res['relay'][0]:.0f} MB/s")
    record("pass-through is byte-exact under load", res["plain"][1] == res["relay"][1])
    record("analyzer dropped instead of blocking (gap recorded)", st["gaps"] > 0 and h[0]["truncated"],
           f"gaps={st['gaps']}")
    record("segmentation recovers after the flood",
           (after["cmd"], after["output"]) == ("echo after-flood", "after-flood"), f"{after['cmd']!r}")


def main() -> int:
    groups = {"identity": identity, "segmentation": segmentation, "latency": latency,
              "throughput": throughput}
    only = sys.argv[sys.argv.index("-k") + 1] if "-k" in sys.argv else None
    try:
        for name, fn in groups.items():
            if only and only != name:
                continue
            print(f"== {name}", flush=True)
            try:
                fn()
            except Exception as e:  # keep going; report as a failure
                import traceback
                traceback.print_exc()
                record(f"{name}: crashed", False, repr(e))
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks pass")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
