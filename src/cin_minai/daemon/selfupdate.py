# SPDX-License-Identifier: GPL-3.0-or-later
"""The daemon restarts itself after an update (PLAN D59): installing a package doesn't restart a running user
service, and logging out isn't always enough (2026-10-01: other sessions kept it alive; a broken update crash-looped
into systemd's start limit and stayed down).

Every check compares the daemon's own code files (this package's .py files and the program that started it) with
how they were at start. Once they've changed and then held still for a check (an install takes a moment), and the
daemon is idle, the new code is first loaded in a separate process: if it doesn't load, the running version keeps
going and says why (once per version). Otherwise the model server is stopped and the daemon exits with code 75;
systemd (Restart=on-failure) starts the new version, which reopens the writing project that was open.
"""

from __future__ import annotations

import os
import subprocess
import sys

PACKAGE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # .../cin_minai
REOPEN = "CINMINAI_REOPEN_PROJECT"


def code_files(package: str = PACKAGE) -> list[str]:
    out = []
    for root, dirs, files in os.walk(package):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        out += [os.path.join(root, f) for f in files if f.endswith(".py")]
    starter = os.path.abspath(sys.argv[0]) if sys.argv and sys.argv[0] else ""
    if starter and os.path.isfile(starter) and not starter.startswith(package):
        out.append(starter)
    return sorted(out)


def signature(files: list[str]) -> tuple:
    sig = []
    for f in files:
        try:
            st = os.stat(f)
            sig.append((f, st.st_mtime_ns, st.st_size))
        except OSError:
            sig.append((f, None, None))
    return tuple(sig)


class Watcher:
    """check() -> "same" (as at start), "changing" (changed since the last check) or "ready" (changed, then still)."""

    def __init__(self, package: str = PACKAGE) -> None:
        self.package = package
        self.start = self.seen = signature(code_files(package))
        self.refused: tuple | None = None  # a version whose test load failed: not tried again

    def check(self) -> str:
        now = signature(code_files(self.package))
        if now == self.start:
            self.seen = now
            return "same"
        if now != self.seen:
            self.seen = now
            return "changing"
        return "ready"


def loads(timeout: int = 60) -> tuple[bool, str]:
    """Does the installed code load? In a separate process, with the same Python and environment (-P: not whatever
    the current folder holds)."""
    try:
        r = subprocess.run([sys.executable, "-P", "-c", "import cin_minai.daemon.service, cin_minai.daemon.__main__"],
                           capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as e:
        return False, str(e)
    return r.returncode == 0, (r.stderr.strip().splitlines() or [""])[-1]


RESTART_CODE = 75  # EX_TEMPFAIL: the unit's Restart=on-failure starts the new version 5 s later


def state_file() -> str:
    return os.path.join(os.environ.get("XDG_RUNTIME_DIR") or "/tmp", "cinminai", "reopen-project")


def updated_file() -> str:
    return os.path.join(os.path.dirname(state_file()), "updated")


def take_updated() -> bool:
    """Did this start come from an update restart? (read once, then gone): the sidebar says so (round 3, 2026-10-07:
    the update restarted quietly while Ian was in the terminal, and nothing told him it had)."""
    try:
        os.remove(updated_file())
        return True
    except OSError:
        return False


def take_reopen() -> str:
    """The project that was open before an update restart (read once, then gone)."""
    path = state_file()
    try:
        with open(path, encoding="utf-8") as f:
            folder = f.read().strip()
        os.remove(path)
        return folder
    except OSError:
        return os.environ.pop(REOPEN, "")


def restart(project_folder: str | None = None) -> None:
    """Leave for the new version: note the open project, exit with RESTART_CODE, and systemd starts the new code.
    Not exec in place: the unit is Type=dbus, and dropping the bus name during an exec made systemd mark the
    service dead and leave it stopped (first real update, 2026-10-02)."""
    os.makedirs(os.path.dirname(state_file()), exist_ok=True)
    with open(updated_file(), "w", encoding="utf-8") as f:
        f.write("1")
    if project_folder:
        with open(state_file(), "w", encoding="utf-8") as f:
            f.write(project_folder)
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(RESTART_CODE)
