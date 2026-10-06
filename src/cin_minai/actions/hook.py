# SPDX-License-Identifier: GPL-3.0-or-later
"""Putting the daemon's existing actions on the one path (M4 slice 2).

    value, action_id = hook.run("make_document", lambda: odt.write(...), "a new document in Documents",
                                created=lambda path: [path])

Something the person clicked runs at once (theirs to decide) and is recorded as theirs, with its undo where it creates
or changes files. Something the assistant decides on its own (person=False) goes through the gate: in Ask mode it
waits for the person, and run() returns (None, id) with nothing changed. With no action path installed (tests, command
line tools) the function simply runs, as before.
"""

from __future__ import annotations

from typing import Any, Callable

from .core import Actions, Kind

_actions: Actions | None = None


def install(actions: Actions | None) -> None:
    global _actions
    _actions = actions


def installed() -> Actions | None:
    return _actions


def _kind(name: str, lane: str, reversible: bool, private: bool) -> Kind:
    def realize(args):
        value = args["fn"]()
        return {"value": value, "created": list(args["created"](value) or [])}
    return Kind(name, lane, reversible, summary=lambda a: a["summary"], realize=realize, private_paths=private)


def run(name: str, fn: Callable[[], Any], summary: str, created: Callable[[Any], list] = lambda v: [],
        person: bool = True, lane: str = "user", reversible: bool = True, private: bool = True,
        reason: str = "") -> tuple[Any, str | None]:
    """Run fn as the action `name`. Returns (fn's value, the action's id); raises what fn raised."""
    if _actions is None:
        return fn(), None
    if name not in _actions.kinds:
        _actions.register(_kind(name, lane, reversible, private))
    args = {"fn": fn, "summary": summary, "created": created}
    p = _actions.perform(name, args, reason=reason) if person else _actions.propose(name, args, reason=reason)
    if p.state == "waiting":
        return None, p.id
    if p.state == "failed" and p.error is not None:
        raise p.error
    return (p.result or {}).get("value"), p.id
