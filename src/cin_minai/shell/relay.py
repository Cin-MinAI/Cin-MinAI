# SPDX-License-Identifier: GPL-3.0-or-later
"""Terminal relay (M3, SPEC §6.2; from the M0 spike, docs/spikes.md "Terminal relay").

    terminal emulator <-> relay (pty master) <-> shell (pty slave)
                            |
                            +-- pipe --> analyzer process (analyzer.py): markers, pyte, control socket

The relay loop only copies bytes. A copy of the shell's output goes to the analyzer through a
non-blocking pipe; if the analyzer falls behind (or dies) the relay drops data and records a
gap instead of waiting. Usage:  cinminai-relay [shell argv...]   (default: bash with hooks.bash)

Started from start.bash, which the person's ~/.bashrc sources only once they turned terminal sharing on (D77).
"""

from __future__ import annotations

import errno
import fcntl
import os
import re
import select
import signal
import struct
import sys
import termios
import tty

HERE = os.path.dirname(os.path.abspath(__file__))
HOOKS = os.path.join(HERE, "hooks.bash")

# Frames relay -> analyzer: 1-byte type, 4-byte length, payload.
F_DATA, F_GAP, F_SECRET, F_SIZE = b"D", b"G", b"S", b"W"
MAX_PENDING = 4 << 20          # bytes of unsent frames before we start dropping
PIPE_SIZE = 1 << 20            # analyzer pipe capacity (F_SETPIPE_SZ)
F_SETPIPE_SZ = 1031
MARKER_RE = re.compile(rb"\x1b\](?:133|7|7717);[^\x07\x1b]*(?:\x07|\x1b\\)")


def frame(kind: bytes, payload: bytes = b"") -> bytes:
    return kind + struct.pack("<I", len(payload)) + payload


def get_winsize(fd: int) -> bytes:
    return fcntl.ioctl(fd, termios.TIOCGWINSZ, b"\0" * 8)


PASSWORD_PROGRAMS = {"sudo", "su", "ssh", "passwd", "pkexec", "doas", "gpg", "login",
                     "pinentry-curses", "pinentry-tty", "sshpass"}
_comm_cache: dict[int, str] = {}


def foreground_comm(fd: int) -> str:
    pgid = os.tcgetpgrp(fd)
    if pgid not in _comm_cache:
        try:
            with open(f"/proc/{pgid}/comm") as f:
                _comm_cache.clear()
                _comm_cache[pgid] = f.read().strip()
        except OSError:
            return ""
    return _comm_cache[pgid]


def is_secret(fd: int) -> bool:
    """Is the terminal at a password prompt? (On Linux, tcgetattr on the pty master reports
    the slave's settings.)

    - Echo off in canonical mode: ssh, su, read -s, sudo without pwfeedback.
    - Echo off in character mode with signals on, and a password program in the foreground:
      sudo with pwfeedback (Mint's default), which reads keys one by one to print '*'.
      Readline and full-screen programs also run with echo off in character mode, but they
      aren't password programs; sudo/ssh relaying a session use full raw mode (signals off).
    """
    lflag = termios.tcgetattr(fd)[3]
    if lflag & termios.ECHO:
        return False
    if lflag & termios.ICANON:
        return True
    return bool(lflag & termios.ISIG) and foreground_comm(fd) in PASSWORD_PROGRAMS


def socket_path(pid: int) -> str:
    base = os.environ.get("XDG_RUNTIME_DIR") or f"/tmp/cinminai-{os.getuid()}"
    return os.path.join(base, "cinminai", f"relay-{pid}.sock")


def write_all(fd: int, data: bytes | memoryview) -> None:
    view = memoryview(data)
    while view:
        try:
            view = view[os.write(fd, view):]
        except InterruptedError:
            pass
        except BlockingIOError:
            select.select([], [fd], [])


def main() -> int:
    argv = default_argv()
    # No terminal, or already inside a relay: be the shell, nothing else.
    if not os.isatty(0) or not os.isatty(1) or os.environ.get("CINMINAI_RELAY"):
        os.execvp(argv[0], argv)

    master, slave = os.openpty()
    termios.tcsetattr(slave, termios.TCSANOW, termios.tcgetattr(0))
    fcntl.ioctl(slave, termios.TIOCSWINSZ, get_winsize(0))
    sock = socket_path(os.getpid())
    try:
        from cin_minai.shell.analyzer import listen
        listener = listen(sock)  # not inherited by the shell (Python sockets are close-on-exec)
    except Exception:  # no pyte, no runtime dir: relay anyway, record nothing
        listener = None

    shell_pid = os.fork()
    if shell_pid == 0:
        os.setsid()
        fcntl.ioctl(slave, termios.TIOCSCTTY, 0)
        for fd in (0, 1, 2):
            os.dup2(slave, fd)
        os.close(slave)
        os.close(master)
        os.environ["CINMINAI_RELAY"] = "1"
        os.environ["CINMINAI_SOCK"] = sock
        try:
            os.execvp(argv[0], argv)
        finally:
            os._exit(127)
    os.close(slave)

    if listener is None:  # nothing to feed: be a plain relay
        analyzer_pid, rpipe, wpipe = 0, *os.pipe()
        os.close(rpipe)
    else:
        rpipe, wpipe = os.pipe()
        analyzer_pid = os.fork()
    if listener is not None and analyzer_pid == 0:
        os.close(wpipe)
        os.setpgid(0, 0)  # keep out of the outer terminal's job control
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        try:
            from cin_minai.shell import analyzer
            analyzer.run(rpipe, master, shell_pid, listener, sock, os.getppid())
        finally:
            os._exit(0)  # never return into the relay's loop
    if listener is not None:
        os.close(rpipe)
        listener.close()  # the analyzer has its own copy
    try:
        fcntl.fcntl(wpipe, F_SETPIPE_SZ, PIPE_SIZE)
    except OSError:
        pass
    os.set_blocking(wpipe, False)

    wake_r, wake_w = os.pipe()
    os.set_blocking(wake_r, False)
    os.set_blocking(wake_w, False)
    signal.set_wakeup_fd(wake_w)
    signal.signal(signal.SIGWINCH, lambda *_: None)
    signal.signal(signal.SIGCHLD, lambda *_: None)

    pending = bytearray()
    feeding = True  # False once the analyzer is gone
    gap_open = False
    secret = is_secret(master)
    size = get_winsize(0)

    def queue(kind: bytes, payload: bytes = b"") -> None:
        nonlocal gap_open
        if not feeding:
            return
        if kind == F_DATA and len(pending) + len(payload) > MAX_PENDING:
            if not gap_open:
                pending.extend(frame(F_GAP))
                gap_open = True
            # Still forward the shell's markers so command boundaries survive a flood.
            if b"\x1b]" in payload:
                marks = b"".join(MARKER_RE.findall(payload))
                if marks:
                    pending.extend(frame(F_DATA, marks))
            return
        if kind == F_DATA:
            gap_open = False
        pending.extend(frame(kind, payload))

    queue(F_SIZE, size)
    queue(F_SECRET, b"1" if secret else b"0")

    saved = termios.tcgetattr(0)
    tty.setraw(0)
    os.environ["CINMINAI_RELAY_STARTED"] = "1"  # from here on the shell runs under us: no fallback exec
    status = 0
    try:
        while True:
            wlist = [wpipe] if pending and feeding else []
            try:
                r, w, _ = select.select([0, master, wake_r], wlist, [])
            except InterruptedError:
                continue

            if wake_r in r:
                try:
                    os.read(wake_r, 512)
                except BlockingIOError:
                    pass
                new = get_winsize(0)
                if new != size:
                    size = new
                    fcntl.ioctl(master, termios.TIOCSWINSZ, size)
                    queue(F_SIZE, size)
                if analyzer_pid and os.waitpid(analyzer_pid, os.WNOHANG)[0]:
                    analyzer_pid = 0  # reaped; the relay carries on without it
                    try:
                        os.unlink(sock)  # nothing listens any more: the next prompt drops the ◆ marker
                    except OSError:
                        pass
                # Like a terminal emulator, stop when the shell exits, even if a
                # background job still holds the pty open.
                pid, st = os.waitpid(shell_pid, os.WNOHANG)
                if pid:
                    status = os.waitstatus_to_exitcode(st)
                    shell_pid = 0
                    drain(master)
                    break

            if master in r:
                try:
                    data = os.read(master, 65536)
                except OSError as e:
                    if e.errno != errno.EIO:
                        raise
                    data = b""
                if not data:
                    break  # every slave fd is closed: the shell is gone
                write_all(1, data)
                now = is_secret(master)
                if now != secret:
                    secret = now
                    queue(F_SECRET, b"1" if secret else b"0")
                queue(F_DATA, data)

            if 0 in r:
                data = os.read(0, 65536)
                if not data:
                    break
                write_all(master, data)

            if wpipe in w:
                try:
                    n = os.write(wpipe, pending[: 1 << 20])
                    del pending[:n]
                except BlockingIOError:
                    pass
                except BrokenPipeError:
                    feeding = False  # analyzer died: keep relaying, record nothing
                    pending.clear()
    finally:
        termios.tcsetattr(0, termios.TCSAFLUSH, saved)
        # Closing our ends hangs up the shell (the analyzer closes its copy of the
        # master when it sees EOF on the pipe).
        os.close(wpipe)
        os.close(master)
        if shell_pid:
            try:
                _, st = os.waitpid(shell_pid, 0)
                status = os.waitstatus_to_exitcode(st)
            except ChildProcessError:
                pass
    return status if status >= 0 else 128 - status


def drain(master: int) -> None:
    """Copy whatever the shell wrote just before exiting."""
    os.set_blocking(master, False)
    try:
        while data := os.read(master, 65536):
            write_all(1, data)
    except OSError:
        pass


def default_argv() -> list[str]:
    return sys.argv[1:] or ["bash", "--rcfile", HOOKS, "-i"]


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        # A relay that fails must never cost the person their terminal: they'd have no way to fix it. Before the
        # loop runs (the usual place for a surprise), fall back to the plain shell.
        if not os.environ.get("CINMINAI_RELAY_STARTED"):
            os.execvp(default_argv()[0], default_argv())
        raise
