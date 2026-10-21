# SPDX-License-Identifier: GPL-3.0-or-later
"""The master Stop (Ian, 2026-10-21: "killing all aicui related processes including inferences actively running, shells
actively running, searches actively running, all activity about the session is to stop immediately").

Stop (Ctrl+C) asks the agent to stop, and the agent stops what it runs; a model in the middle of an answer, a command in
its own process group, a server loading or a search waiting doesn't hear it. This stops them from the outside: every
process under the session's roots is frozen first (so none can exit and leave a child to the system, or start another),
then all are killed together. Linux /proc only; nothing outside the roots' trees is touched.
"""

from __future__ import annotations

import os
import signal


def children() -> dict[int, list[int]]:
    """parent pid -> its children's pids, as /proc shows them now."""
    out: dict[int, list[int]] = {}
    for name in os.listdir("/proc"):
        if not name.isdigit():
            continue
        try:
            with open(f"/proc/{name}/stat", encoding="utf-8", errors="replace") as f:
                stat = f.read()
        except OSError:
            continue
        # "pid (comm) state ppid …": comm may hold spaces and brackets, so the fields count from its last ")"
        rest = stat[stat.rfind(")") + 2:].split()
        if len(rest) > 1 and rest[1].isdigit():
            out.setdefault(int(rest[1]), []).append(int(name))
    return out


def tree(roots: list[int], keep: set[int] | None = None) -> list[int]:
    """The roots and everything under them, parents first; `keep` (and what's under it) left out."""
    keep = keep or set()
    kids = children()
    found, todo = [], [r for r in roots if r and r not in keep]
    while todo:
        pid = todo.pop(0)
        if pid in found or pid in keep:
            continue
        found.append(pid)
        todo += kids.get(pid, [])
    return found


def alive(pid: int) -> bool:
    try:
        with open(f"/proc/{pid}/stat", encoding="utf-8", errors="replace") as f:
            stat = f.read()
    except OSError:
        return False
    return stat[stat.rfind(")") + 2:].split()[0] != "Z"  # a zombie has ended: it only waits to be collected


def stop_all(roots: list[int], keep: set[int] | None = None) -> int:
    """Freeze every process under the roots until no new one appears, then kill them all. Returns how many ended."""
    frozen: list[int] = []
    for _ in range(10):  # a process that was starting a child as we looked: look again until the tree holds still
        new = [p for p in tree(roots, keep) if p not in frozen]
        if not new:
            break
        for pid in new:
            try:
                os.kill(pid, signal.SIGSTOP)
                frozen.append(pid)
            except OSError:
                pass  # ended already
        roots = roots + new
    for pid in frozen:
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
    return len(frozen)
