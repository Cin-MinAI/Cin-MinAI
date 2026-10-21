# SPDX-License-Identifier: GPL-3.0-or-later
"""An outside agent's seat at the Team Table (conference.py): an MCP server over stdio, standard library only.

    cinminai-seat --project /home/you/Documents/store --seat claude

Claude Code or Codex starts it — on this computer directly, or from another one over SSH (Ian, 2026-10-21: "secured
through the team table encryption processes from the original team table. It was over ssh at first"): the person adds
the agent's SSH key in the seat's dialog, and that key may only start this command for that seat and project
(authorized_keys `command=…,restrict`: no shell, no forwarding). Who the agent is comes from that command, never from
the agent, so a seat can't act as another.

What the seat can do: see the table (its seats, the lead, its own tasks, who has the floor), claim its next task and
finish it, read the project's files, change only the files its task holds (each change in AICUI's changelog, with
undo, under the seat's name), and talk at the table one speaker at a time. It runs no commands on this computer.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

PROTOCOL = "2025-06-18"
READ_LINES = 400
MAX_FILE = 400_000


def tool(name: str, description: str, props: dict | None = None, required: list | None = None) -> dict:
    return {"name": name, "description": description,
            "inputSchema": {"type": "object", "properties": props or {}, "required": required or []}}


S = {"type": "string"}
I = {"type": "integer"}
TOOLS = [
    tool("table_info", "The table: your seat, the lead, the other seats, your tasks, who has the floor. Start here."),
    tool("next_task", "Claim your next task (the person's requests first): its instruction and the files you may "
                      "change. One at a time: finish it before the next."),
    tool("finish_task", "Finish your task: what you did and how you checked it. verdict: done, stuck or not done.",
         {"id": I, "verdict": {"type": "string", "enum": ["done", "stuck", "not done"]}, "result": S},
         ["id", "verdict", "result"]),
    tool("list_files", "The project's files and folders under `path` (\"\" for its top).", {"path": S}),
    tool("read_file", f"A file of the project, {READ_LINES} lines from line `start`.", {"path": S, "start": I},
         ["path"]),
    tool("write_file", "Write a whole file — only one your task holds. Each change is in AICUI's changelog, with undo.",
         {"path": S, "content": S}, ["path", "content"]),
    tool("edit_file", "Replace the exact text `old` (it appears once) with `new` in a file your task holds.",
         {"path": S, "old": S, "new": S}, ["path", "old", "new"]),
    tool("say", "Say something at the table: when you have the floor, or it's free.", {"text": S}, ["text"]),
    tool("request_floor", "Ask to speak at the table: a free floor is yours now; else you wait your turn."),
    tool("pass_floor", "Give the floor to a seat (its name), or to whoever is next.", {"to": S}),
    tool("conversation", "What was said at the table after message `after_id`.", {"after_id": I}),
]


class Seat:
    def __init__(self, root: str, seat: str) -> None:
        from cin_minai import engine as engine_mod

        from .pair import project_of
        self.root = os.path.realpath(root)
        if not os.path.isdir(self.root):
            raise SystemExit(f"no project at {root}")
        self.seat = seat
        self.engine = engine_mod.Engine(project_of(self.root), self.root)
        self.member = f"{seat}.{self.engine.ns}"
        self.channel = f"table.{self.engine.ns}"
        self.current: dict | None = None

    # --- the table ---
    def seated(self) -> bool:
        return self.engine.db.member_exists(self.member)

    def table_info(self, a: dict) -> dict:
        from . import conference
        setup = conference.load(self.root)
        mine = [{"id": t["id"], "title": t["title"], "status": t["status"]} for t in self.engine.open_for(self.member)]
        try:
            floor = self.engine.db.floor(self.channel)
            floor = {"holder": (floor["holder"] or "").split(".")[0] or None,
                     "queue": [q.split(".")[0] for q in floor["queue"]], "expires_in": floor["expires_in"]}
        except Exception:
            floor = None
        return {"you": self.seat, "project": os.path.basename(self.root),
                "seated": self.seated(),
                "lead": (conference.lead_of(setup) or {}).get("name"),
                "seats": [conference.describe(s) for s in setup["seats"]],
                "your_tasks": mine, "floor": floor,
                "how": "next_task gives you your task; change only the files it holds (write_file, edit_file); "
                       "finish_task with what you did and how you checked it. You run no commands here: check what "
                       "you can by reading; the lead and the seats in AICUI run the project."
                       + ("" if self.seated() else " The table isn't sitting in AICUI right now: no tasks come until "
                                                   "it is.")}

    def next_task(self, a: dict) -> dict:
        from .pair import spec_of
        if self.current and self.engine.state(self.current["id"]) == "in_progress":
            return {"error": f"finish task {self.current['id']} first (finish_task)"}
        t = self.engine.claim(self.member)
        if t is None:
            return {"task": None, "said": "nothing for you right now: ask again later, or look at the conversation"}
        self.current = t
        s = spec_of(t)
        body = (t.get("description") or "").split("\n", 1)
        text = body[1] if len(body) > 1 else ""
        if not text.strip() and t.get("refs"):
            text = self.engine.kept(t["refs"][0])
        return {"id": t["id"], "title": t["title"], "kind": s.get("kind", ""), "instruction": text,
                "you_may_change": s.get("hold", []), "for": s.get("goal", "")}

    def finish_task(self, a: dict) -> dict:
        n = int(a.get("id") or 0)
        t = self.engine.get(n)
        if not t or t.get("assignee") != self.member:
            return {"error": f"task {n} isn't yours"}
        if t["status"] != "in_progress":
            return {"error": f"task {n} is {t['status']}"}
        self.engine.finish(t, self.member, self.seat, str(a.get("verdict", "done")), str(a.get("result", ""))[:1500])
        self.current = None
        return {"finished": n}

    # --- the project's files ---
    def path(self, rel: str) -> tuple[str, str]:
        full = os.path.realpath(os.path.join(self.root, rel or ""))
        if full != self.root and not full.startswith(self.root + os.sep):
            raise ValueError(f"{rel} isn't in the project")
        r = os.path.relpath(full, self.root).replace(os.sep, "/")
        if r.split("/")[0] in (".git", ".cinminai") or r.split("/")[0].startswith(".venv"):
            raise ValueError(f"{r} is AICUI's or git's, not the project's")
        return full, r

    def list_files(self, a: dict) -> dict:
        full, rel = self.path(str(a.get("path", "")))
        if not os.path.isdir(full):
            return {"error": f"{rel} isn't a folder"}
        out = []
        for name in sorted(os.listdir(full)):
            if name in (".git", ".cinminai") or name.startswith(".venv"):
                continue
            p = os.path.join(full, name)
            out.append(name + "/" if os.path.isdir(p) else f"{name} ({os.path.getsize(p):,} bytes)")
        return {"path": rel, "entries": out[:400]}

    def read_file(self, a: dict) -> dict:
        full, rel = self.path(str(a.get("path", "")))
        if not os.path.isfile(full):
            return {"error": f"{rel} isn't a file"}
        if os.path.getsize(full) > MAX_FILE:
            return {"error": f"{rel} is over {MAX_FILE:,} bytes"}
        with open(full, encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()
        start = max(1, int(a.get("start") or 1))
        part = lines[start - 1:start - 1 + READ_LINES]
        return {"path": rel, "lines": f"{start}-{start + len(part) - 1} of {len(lines)}",
                "text": "\n".join(f"{i:5} {x}" for i, x in enumerate(part, start))}

    def holds(self, rel: str) -> str:
        from .pair import spec_of
        t = self.current
        if not t or self.engine.state(t["id"]) != "in_progress":
            return "you have no task in progress: next_task first"
        if rel not in spec_of(t).get("hold", []):
            return f"{rel} isn't part of your task — you may change only {', '.join(spec_of(t).get('hold', [])) or 'nothing'}"
        return ""

    def change(self, rel: str, full: str, text: str, what: str) -> dict:
        from .changelog import Changelog
        log = Changelog(self.root)
        before = log.before(rel)
        os.makedirs(os.path.dirname(full) or self.root, exist_ok=True)
        with open(full + ".tmp", "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(full + ".tmp", full)
        e = log.after(rel, before, f"{self.seat} (outside agent)", f"task {self.current['id']}", what)
        return {"changed": rel, "change": e["id"], "added": e["added"], "removed": e["removed"]}

    def write_file(self, a: dict) -> dict:
        full, rel = self.path(str(a.get("path", "")))
        why = self.holds(rel)
        if why:
            return {"error": why}
        return self.change(rel, full, str(a.get("content", "")), "written whole")

    def edit_file(self, a: dict) -> dict:
        full, rel = self.path(str(a.get("path", "")))
        why = self.holds(rel)
        if why:
            return {"error": why}
        with open(full, encoding="utf-8") as f:
            text = f.read()
        old = str(a.get("old", ""))
        if not old or text.count(old) != 1:
            return {"error": f"`old` appears {text.count(old) if old else 0} times in {rel}: it must appear once"}
        return self.change(rel, full, text.replace(old, str(a.get("new", "")), 1), "edited")

    # --- talking ---
    def say(self, a: dict) -> dict:
        return self.engine.db.say(self.channel, self.member, str(a.get("text", "")))

    def request_floor(self, a: dict) -> dict:
        return self.engine.db.request_floor(self.channel, self.member)

    def pass_floor(self, a: dict) -> dict:
        to = str(a.get("to") or "")
        return self.engine.db.pass_floor(self.channel, self.member, f"{to.lower()}.{self.engine.ns}" if to else None)

    def conversation(self, a: dict) -> dict:
        return {"said": [{"id": m["id"], "who": m["sender"].split(".")[0], "said": m["content"]}
                         for m in self.engine.db.conversation(self.channel, int(a.get("after_id") or 0), 50)]}

    def call(self, name: str, args: dict) -> dict:
        if name not in {t["name"] for t in TOOLS}:
            raise KeyError(name)
        return getattr(self, name)(args or {})


def answer(seat: Seat, msg: dict) -> dict | None:
    """One JSON-RPC message in, its reply out (None for a notification)."""
    mid, method = msg.get("id"), msg.get("method", "")
    if mid is None:  # notifications (initialized, cancelled): nothing to say back
        return None
    if method == "initialize":
        asked = (msg.get("params") or {}).get("protocolVersion") or PROTOCOL
        result = {"protocolVersion": asked, "capabilities": {"tools": {}},
                  "serverInfo": {"name": "cin-minai-team-table", "version": "1"},
                  "instructions": f"You sit at the Team Table as {seat.seat}. Call table_info first."}
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif method == "tools/call":
        p = msg.get("params") or {}
        try:
            out = seat.call(str(p.get("name", "")), p.get("arguments") or {})
            failed = isinstance(out, dict) and "error" in out
        except KeyError:
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32602, "message": f"no tool {p.get('name')}"}}
        except Exception as e:  # the table's refusals and a bad path: said to the agent, the server goes on
            out, failed = {"error": getattr(e, "message", str(e))}, True
        result = {"content": [{"type": "text", "text": json.dumps(out, ensure_ascii=False)}], "isError": failed}
    else:
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"no method {method}"}}
    return {"jsonrpc": "2.0", "id": mid, "result": result}


def serve(seat: Seat, inp=sys.stdin, out=sys.stdout) -> None:
    for line in inp:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            reply = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "not JSON"}}
        else:
            reply = answer(seat, msg) if isinstance(msg, dict) else None
        if reply is not None:
            out.write(json.dumps(reply, ensure_ascii=False) + "\n")
            out.flush()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="cinminai-seat", description="An outside agent's seat at the Team Table.")
    ap.add_argument("--project", required=True)
    ap.add_argument("--seat", required=True)
    a = ap.parse_args(argv)
    from .conference import slug
    serve(Seat(a.project, slug(a.seat)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
