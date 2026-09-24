"""Persistent PTY-backed shell session (M0 spike).

Owns the child process and the PTY master fd. Knows nothing about rendering.
"""

from __future__ import annotations

import asyncio
import errno
import fcntl
import os
import pty
import signal
import struct
import termios
from typing import Callable


class PtySession:
    def __init__(self, argv: list[str] | None = None, cwd: str | None = None) -> None:
        self.argv = argv or [os.environ.get("SHELL", "/bin/bash"), "-i"]
        self.cwd = cwd
        self.pid: int | None = None
        self.fd: int | None = None
        self.exit_status: int | None = None
        self._pending = bytearray()
        self._on_output: Callable[[bytes], None] | None = None
        self._on_exit: Callable[[int], None] | None = None

    @property
    def alive(self) -> bool:
        return self.fd is not None

    def start(
        self,
        cols: int,
        rows: int,
        on_output: Callable[[bytes], None],
        on_exit: Callable[[int], None],
    ) -> None:
        self._on_output = on_output
        self._on_exit = on_exit
        pid, fd = pty.fork()
        if pid == 0:  # child
            try:
                if self.cwd:
                    os.chdir(self.cwd)
                env = dict(os.environ)
                env["TERM"] = "xterm-256color"
                env.pop("COLUMNS", None)
                env.pop("LINES", None)
                os.execvpe(self.argv[0], self.argv, env)
            finally:
                os._exit(127)
        self.pid, self.fd = pid, fd
        self.resize(cols, rows)
        os.set_blocking(fd, False)
        asyncio.get_running_loop().add_reader(fd, self._readable)

    def _readable(self) -> None:
        assert self.fd is not None
        try:
            data = os.read(self.fd, 65536)
        except BlockingIOError:
            return
        except OSError as e:
            if e.errno != errno.EIO:  # EIO == slave side closed
                raise
            data = b""
        if data:
            self._on_output(data)
        else:
            self._closed()

    def write(self, data: bytes) -> None:
        if self.fd is None:
            return
        self._pending += data
        self._flush_pending()

    def _flush_pending(self) -> None:
        loop = asyncio.get_running_loop()
        try:
            while self._pending:
                n = os.write(self.fd, self._pending)
                del self._pending[:n]
        except BlockingIOError:
            loop.add_writer(self.fd, self._flush_pending)
            return
        except OSError:
            self._pending.clear()
        loop.remove_writer(self.fd)

    def resize(self, cols: int, rows: int) -> None:
        if self.fd is not None:
            # Kernel delivers SIGWINCH to the foreground process group.
            fcntl.ioctl(self.fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))

    def interrupt(self) -> None:
        # Through the line discipline, exactly like a real Ctrl-C keypress.
        self.write(b"\x03")

    def _closed(self) -> None:
        loop = asyncio.get_running_loop()
        loop.remove_reader(self.fd)
        loop.remove_writer(self.fd)
        os.close(self.fd)
        self.fd = None
        self.exit_status = self._reap()
        if self._on_exit:
            self._on_exit(self.exit_status)

    def _reap(self) -> int:
        try:
            _, status = os.waitpid(self.pid, 0)
            return os.waitstatus_to_exitcode(status)
        except ChildProcessError:
            return -1

    def close(self) -> None:
        if self.fd is None:
            return
        try:
            os.kill(self.pid, signal.SIGHUP)
        except ProcessLookupError:
            pass
        self._closed()
