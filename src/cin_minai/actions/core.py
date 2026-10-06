# SPDX-License-Identifier: GPL-3.0-or-later
"""One path for every action (PLAN D67, D85; SPEC §8).

    Γ   what this state allows: the fixed walls (below) and, inside them, the boundary chooser
    d   the choice: the model or a tool proposes; the person decides when it's theirs to decide
    T_d the action's own realize(): the only code that changes anything
    w   the action's check() on the result
    R   the record: every step, in order, append-only

The walls are fixed and never learned (D85):
  * every action is shown in plain words and recorded — nothing happens out of sight;
  * an irreversible action always asks — no setting turns that off;
  * an admin action always asks here, and the root mechanism asks for the password (polkit) — the assistant is not the
    admin.
Inside the walls the boundary chooser decides whether to ask. It can only narrow: whatever it says, a wall wins. The
mode is the person's: "ask" (the default) asks for everything; "auto" lets reversible actions run on their own — they
are shown, recorded, and can be undone.

A reversible action declares the paths it touches; before it runs, those are copied to the undo store, and undo puts
them back and proves it (the hashes must match what was there before). An action is reversible only if it says so
*and* can be undone that way; when an undo of a kind has ever failed, the chooser asks for that kind again.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from .record import Record

LANES = ("sandboxed", "user", "user_approved", "admin")
MODES = ("ask", "auto")


class ActionError(RuntimeError):
    pass


@dataclass(frozen=True)
class Kind:
    """A kind of action the assistant may take. realize() is the only code that changes anything."""
    name: str
    lane: str
    reversible: bool
    summary: Callable[[dict], str]                      # plain words for the card and the record (no content)
    realize: Callable[[dict], Any]
    check: Callable[[dict, Any], bool] = lambda args, result: True
    touches: Callable[[dict], list[str]] = lambda args: []   # paths a reversible action may change
    destructive: bool = False                            # the stronger dialog (SPEC §8.3)

    def __post_init__(self):
        if self.lane not in LANES:
            raise ValueError(f"unknown lane {self.lane}")
        if self.lane == "admin" and self.reversible:
            raise ValueError("admin actions count as irreversible here")


@dataclass
class Proposal:
    id: str
    kind: Kind
    args: dict
    by: str
    reason: str
    state: str = "proposed"     # proposed / waiting / denied / done / failed / undone
    result: Any = None
    undo: str | None = None
    asked: bool = False
    manifest: list = field(default_factory=list)


class SimpleBoundary:
    """The boundary chooser, inside the walls (M4's own; PLAN D85). Says "auto" or "ask"."""

    def decide(self, kind: Kind, args: dict, mode: str, record: Record) -> str:
        if mode != "auto":
            return "ask"
        if any(e.get("event") == "undo-failed" and e.get("kind") == kind.name for e in record.entries):
            return "ask"            # its way back has failed before: ask again for this kind
        return "auto"


def _sha(path: str) -> str | None:
    if not os.path.lexists(path):
        return None
    if os.path.isdir(path):
        raise ActionError(f"{path} is a folder; an undoable action names files")
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def default_undo_dir() -> str:
    base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return os.path.join(base, "cinminai", "undo")


class Actions:
    def __init__(self, record: Record | None = None, undo_dir: str | None = None, mode: str = "ask",
                 boundary=None, notify: Callable[[str, Proposal], None] | None = None):
        self.record = record or Record()
        self.undo_dir = undo_dir or default_undo_dir()
        os.makedirs(self.undo_dir, mode=0o700, exist_ok=True)
        self.mode = mode if mode in MODES else "ask"
        self.boundary = boundary or SimpleBoundary()
        self.notify = notify or (lambda event, p: None)
        self.kinds: dict[str, Kind] = {}
        self.open: dict[str, Proposal] = {}
        self._lock = threading.Lock()

    def register(self, kind: Kind) -> None:
        self.kinds[kind.name] = kind

    # -- Γ: the walls, then the chooser -----------------------------------------------------------------------------
    def gate(self, kind: Kind, args: dict) -> str:
        if kind.lane == "admin" or not kind.reversible:
            return "ask"                                     # walls: no setting, no chooser can change these
        decision = self.boundary.decide(kind, args, self.mode, self.record)
        return "auto" if decision == "auto" and self.mode == "auto" else "ask"

    # -- d: propose; the person answers when it's theirs to answer ---------------------------------------------------
    def propose(self, name: str, args: dict, by: str = "assistant", reason: str = "") -> Proposal:
        kind = self.kinds.get(name)
        if kind is None:
            raise ActionError(f"no such action: {name}")
        p = Proposal(uuid.uuid4().hex[:12], kind, dict(args), by, reason)
        self.record.add("proposed", id=p.id, kind=name, lane=kind.lane, reversible=kind.reversible, by=by,
                        summary=kind.summary(args), reason=reason[:300])
        if self.gate(kind, args) == "auto":
            self.record.add("auto", id=p.id, kind=name, mode=self.mode)
            self._run(p)
        else:
            p.state, p.asked = "waiting", True
            with self._lock:
                self.open[p.id] = p
            self.notify("waiting", p)
        return p

    def answer(self, action_id: str, allow: bool) -> Proposal:
        with self._lock:
            p = self.open.pop(action_id, None)
        if p is None:
            raise ActionError("no such action is waiting")
        if not allow:
            p.state = "denied"
            self.record.add("denied", id=p.id, kind=p.kind.name)
            self.notify("denied", p)
            return p
        self.record.add("allowed", id=p.id, kind=p.kind.name)
        self._run(p)
        return p

    # -- T_d, then w ---------------------------------------------------------------------------------------------------
    def _run(self, p: Proposal) -> None:
        if p.kind.reversible:
            p.undo = self._snapshot(p)
        try:
            p.result = p.kind.realize(p.args)
            ok = bool(p.kind.check(p.args, p.result))
        except Exception as e:                                # noqa: BLE001 — every failure is recorded, not raised on
            p.state = "failed"
            self.record.add("failed", id=p.id, kind=p.kind.name, error=str(e)[:300])
            if p.undo:
                self.undo(p.id, reason="the action failed")
            self.notify("failed", p)
            return
        if not ok:
            p.state = "failed"
            self.record.add("check-failed", id=p.id, kind=p.kind.name)
            if p.undo:
                self.undo(p.id, reason="its check failed")
            self.notify("failed", p)
            return
        p.state = "done"
        self.record.add("done", id=p.id, kind=p.kind.name, undo=bool(p.undo))
        self.notify("done", p)

    # -- the way back ---------------------------------------------------------------------------------------------------
    def _snapshot(self, p: Proposal) -> str:
        d = os.path.join(self.undo_dir, p.id)
        os.makedirs(d, mode=0o700)
        manifest = []
        for n, path in enumerate(p.kind.touches(p.args)):
            path = os.path.abspath(path)
            before = _sha(path)
            copy = None
            if before is not None:
                copy = os.path.join(d, str(n))
                shutil.copy2(path, copy)
            manifest.append({"path": path, "before": before, "copy": copy})
        p.manifest = manifest
        self.record.add("snapshot", id=p.id, kind=p.kind.name,
                        files=[{"path": m["path"], "before": m["before"]} for m in manifest])
        return d

    def undo(self, action_id: str, reason: str = "asked") -> bool:
        """Put back what a reversible action changed, and prove it: every file's hash must match what was there."""
        entries = self.record.of(action_id)
        snap = next((e for e in entries if e["event"] == "snapshot"), None)
        if snap is None:
            raise ActionError("this action can't be undone")
        if any(e["event"] == "undone" for e in entries):
            raise ActionError("already undone")
        d = os.path.join(self.undo_dir, action_id)
        ok = True
        for n, f in enumerate(snap["files"]):
            path, before = f["path"], f["before"]
            try:
                if before is None:
                    if os.path.lexists(path):
                        os.remove(path)
                else:
                    os.makedirs(os.path.dirname(path), exist_ok=True)
                    shutil.copy2(os.path.join(d, str(n)), path)
            except OSError:
                ok = False
            ok = ok and _sha(path) == before
        kind = snap["kind"]
        if ok:
            self.record.add("undone", id=action_id, kind=kind, reason=reason)
        else:
            self.record.add("undo-failed", id=action_id, kind=kind, reason=reason)
        return ok

    def prune(self, keep_days: float = 30, keep_bytes: int = 2 << 30) -> int:
        """Drop the oldest undo copies past 30 days or 2 GB; the record notes that their undo is gone."""
        dirs = sorted((os.path.getmtime(os.path.join(self.undo_dir, x)), x) for x in os.listdir(self.undo_dir))
        total = sum(_size(os.path.join(self.undo_dir, x)) for _, x in dirs)
        cutoff, dropped = time.time() - keep_days * 86400, 0
        for mtime, x in dirs:
            if mtime >= cutoff and total <= keep_bytes:
                break
            path = os.path.join(self.undo_dir, x)
            total -= _size(path)
            shutil.rmtree(path, ignore_errors=True)
            self.record.add("undo-expired", id=x)
            dropped += 1
        return dropped


def _size(path: str) -> int:
    return sum(os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(path) for f in fs)
