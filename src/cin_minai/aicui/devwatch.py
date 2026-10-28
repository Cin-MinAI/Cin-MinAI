# SPDX-License-Identifier: GPL-3.0-or-later
"""Developer mode: the project run with a watcher that writes down every error while the person plays (Ian,
2026-10-27: "an AI log watcher script so the local agent can simply log all error codes ... As soon as the run is
launched the ai is watching everything to write anything down for the correcting agent"; "When the game launches
itll say developer mode, and it will take screenshots on errors also in developer mode. But it cant be in developer
mode unless the local agents tool is on").

Only AICUI's "Run in developer mode" button starts it, never the program itself; it ends when the program does.
Everything the program prints goes to .cinminai/runs/<time>.log with the time; each error (a Python traceback, an
exception Tk caught in a callback, a C/C++ crash or error line, a non-zero exit) becomes one record in
.cinminai/run-errors.jsonl, the same error again only counted; the first time an error is seen, the program's window
is captured. Test29 (2026-10-27): Save failed inside a Tk callback and the error went to a terminal nobody saw.
"""

from __future__ import annotations

import json
import os
import re
import time

RUNS = os.path.join(".cinminai", "runs")
ERRORS = os.path.join(".cinminai", "run-errors.jsonl")
BEFORE = 30  # lines of output kept before an error, for its context
TRACE_START = re.compile(r"^Traceback \(most recent call last\):")
TK_CALLBACK = re.compile(r"^Exception in Tkinter callback")
EXC_LINE = re.compile(r"^([A-Za-z_][\w.]*(?:Error|Exception|Warning|Exit|Interrupt|Fault)|[A-Za-z_][\w.]*Error)\b:?\s?(.*)$")
FRAME = re.compile(r'^\s*File "([^"]+)", line (\d+)')
NATIVE = re.compile(r"(Segmentation fault|core dumped|terminate called|Assertion .* failed|Aborted|"
                    r"Fatal Python error|double free|stack smashing|^\S+\.(?:cpp|cc|c|h|hpp):\d+:.*\berror\b)",
                    re.IGNORECASE)


class Extractor:
    """The output, line by line, into error records: {"sig", "kind", "message", "where", "trace", "before", "count",
    "first", "last"}. A record is new the first time its signature (kind, message's first words, the deepest frame in
    the project) is seen; after that it's counted."""

    def __init__(self, root: str = "") -> None:
        self.root = os.path.realpath(root) if root else ""
        self.recent: list[str] = []
        self.trace: list[str] | None = None
        self.callback = False
        self.records: dict[str, dict] = {}

    def where(self, trace: list[str]) -> str:
        frames = [m.groups() for m in (FRAME.match(t) for t in trace) if m]
        mine = [f for f in frames if not self.root or os.path.realpath(f[0]).startswith(self.root)
                or not f[0].startswith("/")]
        f = (mine or frames or [("", "")])[-1]
        path = f[0]
        if self.root and path.startswith(self.root):
            path = os.path.relpath(path, self.root)
        return f"{path}:{f[1]}" if path else ""

    def record(self, kind: str, message: str, trace: list[str], t: float) -> tuple[dict, bool]:
        where = self.where(trace)
        sig = f"{kind}|{' '.join(message.split()[:6])}|{where}"
        r = self.records.get(sig)
        if r:
            r["count"] += 1
            r["last"] = t
            return r, False
        r = {"sig": sig, "kind": kind, "message": message.strip()[:500], "where": where, "trace": trace[-40:],
             "before": self.recent[-BEFORE:], "count": 1, "first": t, "last": t}
        self.records[sig] = r
        return r, True

    def feed(self, line: str, t: float | None = None) -> list[tuple[dict, bool]]:
        """One line of output; the records it completes, each with True when it's the first of its kind."""
        t = time.time() if t is None else t
        line = line.rstrip("\n")
        out = []
        block = self.trace is not None or bool(TK_CALLBACK.match(line) or TRACE_START.match(line))
        if self.trace is not None:
            self.trace.append(line)
            m = EXC_LINE.match(line) if not line.startswith((" ", "\t")) and len(self.trace) > 1 else None
            if m:
                kind = ("Tk callback: " if self.callback else "") + m.group(1)
                out.append(self.record(kind, m.group(2) or "", self.trace, t))
                self.trace, self.callback = None, False
            elif len(self.trace) > 400:  # a traceback that never ended: kept as it is
                out.append(self.record("Traceback", self.trace[-1], self.trace, t))
                self.trace, self.callback = None, False
        elif TK_CALLBACK.match(line):
            self.callback = True
        elif TRACE_START.match(line):
            self.trace = [line]
        elif NATIVE.search(line):
            out.append(self.record("Native", line, [line], t))
        if not block:  # the context is the program's own output, not the error's lines
            self.recent.append(line)
        if len(self.recent) > 200:
            del self.recent[:100]
        return out

    def ended(self, code: int | str, t: float | None = None) -> list[tuple[dict, bool]]:
        """The program's end: an unfinished traceback, and a non-zero exit with nothing else said."""
        t = time.time() if t is None else t
        out = []
        if self.trace:
            out.append(self.record("Traceback", self.trace[-1], self.trace, t))
            self.trace = None
        if code not in (0, "0") and not self.records:
            out.append(self.record("Exit", f"exit {code}", self.recent[-5:], t))
        return out


def summary(records: list[dict], entry: str, log: str) -> str:
    """What the correcting agent is told: each error once, with its count, place and message."""
    if not records:
        return f"Developer mode: {entry} ran with no errors recorded (its output: {log})."
    lines = [f"Developer mode: {len(records)} error(s) while the person played {entry} (records in {ERRORS}, "
             f"its whole output in {log}):"]
    for i, r in enumerate(records, 1):
        shot = f"; picture of the window: {r['picture']}" if r.get("picture") else ""
        lines.append(f"{i}. {r['kind']}: {r['message'][:200]} at {r['where'] or '?'} ({r['count']}x){shot}")
    lines.append("Fix them: each as a goal, checked by a test that reproduces it.")
    return "\n".join(lines)


def save(root: str, record: dict, run: str) -> None:
    path = os.path.join(root, ERRORS)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps({**record, "run": run}, ensure_ascii=False) + "\n")


def window_list() -> list[tuple[str, int]]:
    """Every top-level window (wmctrl -lp): its hex id and the process that says it owns it (0: not said)."""
    import subprocess
    try:
        out = subprocess.run(["wmctrl", "-lp"], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.TimeoutExpired):
        return []
    rows = []
    for ln in out.splitlines():
        parts = ln.split(None, 4)
        if len(parts) >= 3:
            rows.append((parts[0], int(parts[2]) if parts[2].lstrip("-").isdigit() else 0))
    return rows


def windows_of(pids: set[int], known: set[str] = frozenset()) -> list[str]:
    """The program's windows: those its processes own, else those opened since it started (a Tk window doesn't say
    which process it belongs to: wmctrl shows 0, 2026-10-28)."""
    rows = window_list()
    mine = [w for w, p in rows if p in pids]
    return mine or [w for w, p in rows if w not in known and p == 0]


def family(pid: int) -> set[int]:
    """pid and every process under it (run.sh starts python, python may start the engine)."""
    kids: dict[int, list[int]] = {}
    for name in os.listdir("/proc") if os.path.isdir("/proc") else []:
        if not name.isdigit():
            continue
        try:
            with open(f"/proc/{name}/stat", encoding="utf-8", errors="replace") as f:
                parent = int(f.read().rsplit(")", 1)[1].split()[1])
        except (OSError, ValueError, IndexError):
            continue
        kids.setdefault(parent, []).append(int(name))
    out, todo = set(), [pid]
    while todo:
        p = todo.pop()
        if p not in out:
            out.add(p)
            todo += kids.get(p, [])
    return out


def mark(wid: str) -> None:
    """The program's window says it's in developer mode (any program, no code of its own needed)."""
    import subprocess
    try:
        name = subprocess.run(["xprop", "-id", wid, "WM_NAME"], capture_output=True, text=True, timeout=5).stdout
        title = name.split("=", 1)[1].strip().strip('"') if "=" in name else ""
        if "DEVELOPER MODE" not in title:
            subprocess.run(["wmctrl", "-i", "-r", wid, "-T", f"{title or 'Program'} — DEVELOPER MODE"], timeout=5)
    except (OSError, subprocess.TimeoutExpired, IndexError):
        pass
