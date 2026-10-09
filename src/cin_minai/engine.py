# SPDX-License-Identifier: GPL-3.0-or-later
"""The multi-model engine (SPEC §22.4-22.5, PLAN D95): the Team Table drives the models, it doesn't only record them.
Ian, 2026-10-09: "team table was the multi model engine" — and "you and any other cloud model can work at team table
also, for 3 agents at the project".

* **Members** are whoever works the project — a local model, a cloud model through an API or sign-in the person
  allowed, an outside agent through Team Table's MCP server on the same file — each with its context size: a task for a
  member is at most 5 % of it (the table enforces it). Names carry the project ("coder.4182ec9f"), so two projects
  don't share a queue. Nothing here assumes a member is local.
* **A request** from the person is a root task (origin "person", served first), assigned to the organizer (or the
  senior).
* **Every move is a child task:** a work order — one kind of action (write, delete or check), the step, what it acts
  on, what proves it — or the organizer's own gathering (look, fetch). While a child is open the request waits (the
  table's own rule); when it closes, the organizer claims the request again and chooses the next move.
* **References are made by code:** the organizer names files or lines; the engine puts their content in shared context
  under its own key and the task carries the key — the bulk travels by reference, the order stays small.
* **Results** say which model did it and the verdict; a child always closes as done (a "blocked" child would hold its
  request for ever) and its verdict says how it went. Stop cancels the request and everything under it.

Everything is in ~/.local/share/cinminai/table.db beside the assistant's own requests, so the Requests view shows it.
"""

from __future__ import annotations

import json
import os
import re
import uuid

from cin_minai.daemon.turns import PERSON, path as table_path

KINDS = ("write", "delete", "check")              # a work order's one kind of action (the four kinds, for code)
GATHER = ("look", "fetch", "search")              # the organizer's own: gathering, not progress
REF_LINES = re.compile(r"^(?P<file>[^:\s]+):(?P<first>\d+)(?:-(?P<last>\d+))?$")
REF_CHARS = 12_000                                # one reference's content at most (a few hundred lines)
ENGINE = "engine"                                 # who keeps the references (its keys are its own: "engine/…")
MAX_REFS = 4                                      # references a work order carries (the table counts 30 writes a minute)


class EngineError(Exception):
    pass


class Engine:
    def __init__(self, project: str, root_dir: str = "", db_path: str | None = None, budget: int = 100) -> None:
        from pathlib import Path

        from team_table.config import Config
        from team_table.db import Database
        self.db = Database(Config(db_path=Path(db_path or table_path()), require_tokens=False))
        self.ns = re.sub(r"[^a-zA-Z0-9]", "", project)[:8] or "local"
        self.root_dir, self.budget = root_dir, budget
        self.db.register(PERSON, role="person")
        self.db.register(ENGINE, role="agent")

    # --- members ---------------------------------------------------------------------------------------------
    def member(self, role: str, context_tokens: int = 0, model: str = "", where: str = "local") -> str:
        """Whoever works the project, as "<role>.<project>": its context (the 5 % cap follows it), its model and
        where it runs ("local", "cloud:anthropic", "mcp", …)."""
        name = f"{role}.{self.ns}"
        caps = [c[:64] for c in (f"model:{model}" if model else "", f"where:{where}") if c]
        self.db.register(name, role="agent", capabilities=caps, context_tokens=int(context_tokens or 0))
        return name

    def cap(self, member: str) -> int:
        """A task's size limit for a member, in characters (as the table counts it)."""
        from team_table.db import CHARS_PER_TOKEN, TOKEN_SHARE
        row = self.db._get_conn().execute("SELECT context_tokens FROM members WHERE name=?", (member,)).fetchone()
        tokens = row["context_tokens"] if row is not None and row["context_tokens"] else 0
        return int(tokens * TOKEN_SHARE * CHARS_PER_TOKEN) if tokens else 10**9

    def close_stale(self) -> int:
        """This project's tasks left open by an earlier run (AICUI closed mid-request): closed with the reason."""
        conn = self.db._get_conn()
        rows = conn.execute("SELECT id FROM tasks WHERE parent_id IS NULL AND assignee LIKE ? AND status IN "
                            "('pending', 'in_progress', 'awaiting_review')", (f"%.{self.ns}",)).fetchall()
        for row in rows:
            self.db.cancel_task(row["id"], PERSON)
        return len(rows)

    # --- requests and moves -----------------------------------------------------------------------------------
    def request(self, text: str, organizer: str) -> dict:
        """The person's request: a root task for the organizer, claimed by it. Longer than its cap: by reference."""
        text = text.strip() or "(empty)"
        title = text.splitlines()[0][:200]
        refs = []
        description = text if len(title) + len(text) <= self.cap(organizer) else ""
        if not description:
            refs.append(self.keep(f"the person's request, whole: {title}", text))
        task = self.db.create_task(title, PERSON, description, organizer, origin="person", kind="request",
                                   refs=refs, budget_tasks=self.budget)
        claimed = self.db.claim_task(task["id"], organizer)
        if not claimed or "error" in claimed:
            raise EngineError((claimed or {}).get("error", "the request couldn't be claimed"))
        return claimed

    def keep(self, label: str, content: str) -> str:
        """Bulk into shared context, by code; returns its key (what a task carries instead)."""
        key = f"{ENGINE}/{self.ns}/{uuid.uuid4().hex[:10]}"
        self.db.share_context(key, f"{label}\n{content}"[:50_000], ENGINE)
        return key

    def reference(self, ref: str) -> str:
        """A file or lines the organizer named — "game.py:40-62" or "game.py" — as a key, its content as it is now."""
        ref = ref.strip().strip("`'\"")
        m = REF_LINES.match(ref)
        rel = m.group("file") if m else ref
        root = os.path.realpath(self.root_dir) if self.root_dir else ""
        full = os.path.realpath(os.path.join(root, rel)) if root else ""
        if not root or not full.startswith(root + os.sep) or not os.path.isfile(full):
            raise EngineError(f"{ref} isn't a file in the project")
        with open(full, encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()
        first = int(m.group("first")) if m else 1
        last = min(int(m.group("last") or m.group("first")) if m else len(lines), len(lines))
        if first < 1 or first > max(last, 1):
            raise EngineError(f"{ref}: {rel} has {len(lines)} lines")
        body = "\n".join(f"{i:5} {line}" for i, line in enumerate(lines[first - 1:last], first))
        if len(body) > REF_CHARS:
            body = body[:REF_CHARS] + "\n… (cut here: name a narrower range)"
        return self.keep(f"{os.path.relpath(full, root)} lines {first}-{last}, as they were when the task was given",
                         body)

    def references(self, said: str) -> list[str]:
        """Every file or line range named in what a move acts on, made into references (the rest stays words)."""
        keys = []
        for word in re.split(r"[\s,;]+", said or ""):
            word = word.strip("`'\"()[].")
            if word and ("/" in word or "." in word):
                try:
                    keys.append(self.reference(word))
                except Exception:  # not a file here, or the table's rate limit: the words still say it
                    pass
            if len(keys) >= MAX_REFS:
                break
        return keys

    def order(self, root: int, creator: str, assignee: str, title: str, description: str, kind: str,
              refs: list[str] | None = None) -> dict:
        """A child of the request — a work order (write / delete / check) or gathering (look / fetch) — and the
        request goes back to waiting on it."""
        from team_table.validation import ValidationError
        if kind not in KINDS + GATHER:
            raise EngineError(f"a task is one of {', '.join(KINDS + GATHER)}, not {kind!r}")
        try:
            task = self.db.create_task(title.strip()[:200] or kind, creator, description, assignee, parent_id=root,
                                       kind=kind, refs=list(refs or [])[:20])
        except ValidationError as e:  # too big for its member, the request's budget spent: the organizer hears why
            raise EngineError(str(e)) from e
        self.db.update_task(root, "pending", agent_name=creator)
        return task

    def claim(self, member: str) -> dict | None:
        """The member's next task (the person's requests first; a request waits while its children are open)."""
        return self.db.next_task(member)

    def content(self, task: dict, limit: int = 10**9) -> str:
        """A task as its member reads it: its own words, then each reference's content — together at most `limit`
        characters (a member's context holds the task and its work)."""
        parts = [task.get("description") or task.get("title", "")]
        room = limit
        for ref in task.get("refs") or []:
            got = self.db.get_shared_context(ref)
            if isinstance(got, dict) and got.get("value") and room > 200:
                value = got["value"] if len(got["value"]) <= room else got["value"][:room] + "\n… (cut: no more room)"
                parts.append(f"--- {value}")
                room -= len(value)
        return "\n\n".join(parts)

    def finish(self, task: dict, member: str, model: str, verdict: str, outcome: str, state: str = "done") -> None:
        """Close a task with its result: which model, the verdict (pass, fail, declined, changed nothing, …), how it
        went."""
        result = json.dumps({"model": model, "verdict": verdict, "note": outcome[:1500]}, ensure_ascii=False)
        self.db.update_task(task["id"], state, result=result[:4800], agent_name=member)

    def cancel(self, root: int) -> int:
        out = self.db.cancel_task(root, PERSON) or {}
        return int(out.get("cancelled", 0)) if isinstance(out, dict) else 0

    def summary(self, root: int, limit: int = 500) -> list[dict]:
        """The request's children so far, as the organizer reads them."""
        out = []
        for c in (self.db.task_tree(root) or {}).get("children", []):
            try:
                r = json.loads(c.get("result") or "{}")
            except ValueError:
                r = {"note": c.get("result") or ""}
            r = r if isinstance(r, dict) else {"note": str(r)}
            out.append({"id": c["id"], "task": c["title"], "kind": c.get("kind", ""), "status": c["status"],
                        "who": c.get("assignee") or "", "model": r.get("model", ""),
                        "verdict": r.get("verdict", ""), "outcome": str(r.get("note", ""))[:limit]})
        return out


def open_engine(project: str, root_dir: str = "", **kw) -> Engine | None:
    """The engine, or None when the table can't be opened (AICUI then works the request without a record)."""
    try:
        return Engine(project, root_dir, **kw)
    except Exception:
        return None
