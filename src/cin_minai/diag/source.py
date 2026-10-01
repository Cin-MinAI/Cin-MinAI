# SPDX-License-Identifier: GPL-3.0-or-later
"""Where the evidence comes from: the running system, or a recorded case (a fixture, SPEC §20.7).

Probes only call run() and read(); a LiveSource answers from the machine, a FixtureSource from a JSON file
of the same answers ({"cmd": {"journalctl -k -b X ...": "..."}, "file": {"/proc/modules": "..."}}). Every
real case is recorded with capture(), so a fault rule is tested on exactly what the machine said.
Everything here reads: nothing changes the system and nothing goes on the network.
"""

from __future__ import annotations

import glob
import json
import os
import re
import socket
import subprocess


class LiveSource:
    def run(self, argv: list[str], timeout: float = 20) -> str:
        try:
            return subprocess.run(argv, capture_output=True, text=True, timeout=timeout,
                                  env={**os.environ, "LC_ALL": "C.UTF-8"}).stdout
        except (OSError, subprocess.SubprocessError):
            return ""

    def read(self, path: str) -> str:
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                return f.read()
        except OSError:
            return ""

    def glob(self, pattern: str) -> list[str]:
        return sorted(glob.glob(pattern))


class FixtureSource:
    """Answers from a recorded case. A command or file the case doesn't have reads as empty, like a
    missing tool on a real machine."""

    def __init__(self, path: str) -> None:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        self.cmds, self.files = data.get("cmd", {}), data.get("file", {})
        self.note = data.get("note", "")

    def run(self, argv: list[str], timeout: float = 20) -> str:
        return self.cmds.get(" ".join(argv), "")

    def read(self, path: str) -> str:
        return self.files.get(path, "")

    def glob(self, pattern: str) -> list[str]:
        rx = re.compile("^" + re.escape(pattern).replace(r"\*", "[^/]*") + "$")
        return sorted(p for p in self.files if rx.match(p))


class Recorder:
    """A LiveSource that keeps every answer: `cinminai-diag capture FILE` writes them as a fixture.
    Kernel logs are cut to the lines the probes look at (they'd be megabytes otherwise)."""

    def __init__(self, keep_line) -> None:
        self.live, self.keep_line = LiveSource(), keep_line
        self.host = socket.gethostname()
        self.cmds: dict[str, str] = {}
        self.files: dict[str, str] = {}

    def run(self, argv: list[str], timeout: float = 20) -> str:
        out = self.live.run(argv, timeout)
        if argv[:1] == ["journalctl"] and "--list-boots" not in argv:
            # only the lines a probe reads: no log-ins, addresses or programs' messages in a test case
            out = "".join(l for l in out.splitlines(keepends=True) if self.keep_line(l))
        out = out.replace(self.host, "HOST") if self.host else out
        self.cmds[" ".join(argv)] = out
        return out

    def read(self, path: str) -> str:
        out = self.live.read(path)
        self.files[path] = out.replace(self.host, "HOST") if self.host else out
        return out

    def glob(self, pattern: str) -> list[str]:
        found = self.live.glob(pattern)
        for p in found:
            self.files.setdefault(p, "")
        return found

    def save(self, path: str, note: str) -> None:
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            json.dump({"note": note, "cmd": self.cmds, "file": self.files}, f, indent=1, ensure_ascii=False)
            f.write("\n")
