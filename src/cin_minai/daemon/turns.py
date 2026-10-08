# SPDX-License-Identifier: GPL-3.0-or-later
"""Turn tokens on the computer (SPEC §22.4, PLAN D95): the daemon keeps a Team Table (Ian's team-table, the
cinminai-table package) and every request becomes a task on it — the person's questions, searches, the scheduled
watches. The person is a member with the operator-granted "person" role, so their requests go first; the guide is a
member with its context size, so a task for it is at most 5 % of that (the bulk goes in shared context, by reference).
Stop cancels a request with everything under it. The table is the record of who asked what, when, and how it ended.

The table lives in ~/.local/share/cinminai/table.db (owner-only). The daemon is its operator: it uses the database
layer directly, so no tokens or network are involved (the MCP server is an optional extra for outside agents).
If team-table isn't installed, the daemon works as before and records nothing here.
"""

from __future__ import annotations

import os
import uuid

PERSON = "person"
GUIDE = "guide"
SCHEDULE = "schedule"
TITLE = 200
RESULT = 500


def path() -> str:
    base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return os.path.join(base, "cinminai", "table.db")


class Turns:
    def __init__(self, db_path: str | None = None, guide_context: int = 8192) -> None:
        from pathlib import Path

        from team_table.config import Config
        from team_table.db import Database
        self.db = Database(Config(db_path=Path(db_path or path()), require_tokens=False))
        self.db.register(PERSON, role="person")
        self.db.register(SCHEDULE, role="agent")
        self.guide_context(guide_context)

    def guide_context(self, tokens: int) -> None:
        """The guide's context changes with where it runs (8K on the card, 4K on the processor)."""
        self.db.register(GUIDE, role="agent", context_tokens=int(tokens or 0))

    def request(self, text: str, by: str = PERSON, kind: str = "ask") -> int:
        """A new request for the guide; returns its task id. Longer than the guide's cap: the whole text goes in
        shared context and the task points to it."""
        text = text.strip() or "(empty)"
        title = text.splitlines()[0][:TITLE]
        cap = self.cap()
        refs: list[str] = []
        description = text if len(title) + len(text) <= cap else ""
        if not description and len(text) > len(title):
            key = f"{by}/{kind}-{uuid.uuid4().hex[:10]}"
            self.db.share_context(key, text, by)
            refs.append(key)
        task = self.db.create_task(title, by, description, GUIDE, origin="person" if by == PERSON else "agent",
                                   kind=kind, refs=refs)
        return task["id"]

    def cap(self) -> int:
        from team_table.db import CHARS_PER_TOKEN, TOKEN_SHARE
        row = self.db._get_conn().execute("SELECT context_tokens FROM members WHERE name=?", (GUIDE,)).fetchone()
        tokens = row["context_tokens"] if row is not None and row["context_tokens"] else 0
        return int(tokens * TOKEN_SHARE * CHARS_PER_TOKEN) if tokens else 10**9

    def next(self) -> int | None:
        """The guide's next queued request (the person's first): claimed, its id."""
        task = self.db.next_task(GUIDE)
        return task["id"] if task else None

    def start(self, task_id: int) -> None:
        self.db.claim_task(task_id, GUIDE)

    def finish(self, task_id: int, state: str, summary: str = "") -> None:
        """state: done | failed | cancelled."""
        if state == "cancelled":
            self.db.cancel_task(task_id, PERSON)
            return
        status = "done" if state == "done" else "blocked"
        self.db.update_task(task_id, status, summary[:RESULT] or None, agent_name=GUIDE)

    def cancel(self, task_id: int) -> int:
        out = self.db.cancel_task(task_id, PERSON) or {}
        return int(out.get("cancelled", 0))

    def close_stale(self) -> int:
        """Requests left open by a previous run (the daemon stopped or restarted mid-answer): closed with the
        reason, so they don't wait for ever."""
        conn = self.db._get_conn()
        rows = conn.execute("SELECT id FROM tasks WHERE assignee=? AND status IN ('pending', 'in_progress')",
                            (GUIDE,)).fetchall()
        for row in rows:
            self.db.update_task(row["id"], "blocked", "the assistant restarted before this was answered",
                                agent_name=GUIDE)
        return len(rows)

    def recent(self, n: int = 20) -> list[dict]:
        """The last n requests, each with its tree (for the view)."""
        rows = self.db._get_conn().execute(
            "SELECT id FROM tasks WHERE parent_id IS NULL ORDER BY id DESC LIMIT ?", (n,)).fetchall()
        return [t for t in (self.db.task_tree(r["id"]) for r in rows) if t]


def open_table(guide_context: int = 8192) -> Turns | None:
    """The table, or None when team-table isn't installed or the file can't be opened (the daemon goes on)."""
    try:
        return Turns(guide_context=guide_context)
    except Exception:  # ImportError, sqlite3 errors: never stop the assistant over its record
        return None
