# SPDX-License-Identifier: GPL-3.0-or-later
"""The Team Table as a conference table (Ian, 2026-10-21: "a conference table Claude, Codex, Grok, and Gemini could sit
at and build something together… If I wanted to run 6 agents with 4 clouds and 2 local, well lets do it. Its all up to
the user and the limitations of the systems").

* **Seats**, two to start, as many as the person adds. Each seat is a **local** model from the model store, a **cloud**
  model by the person's key, or an **outside** agent (Claude Code, Codex) that joins over SSH through the seat server
  (seatmcp.py). One seat wears the **crown**: the lead, chosen by the person, plans and accepts or rejects the others'
  work. The setup is the project's: `.cinminai/table.json`.
* **The paper** in the middle is the session goals; each can be assigned to a seat (a goal's `who` is the seat's name).
* **Running** (`Table`): every seat is a member on the Team Table. A local or cloud seat is an Agent working its
  queue in AICUI (a Pair per seat, as team B's Junior); an outside seat claims its tasks through its MCP server and its
  results come back to the lead the same way. One writer per file across all seats.
* **Talking**: beside the tasks, the seats share the table's conversation, one speaker at a time (the floor, in Team
  Table: say, pass_floor, request_floor); the person and the lead can always speak and take the floor.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import threading

TABLE = os.path.join(".cinminai", "table.json")
KINDS = ("local", "cloud", "outside")
OUTSIDE_AGENTS = ("Claude Code", "Codex")
NAME = re.compile(r"^[A-Za-z][A-Za-z0-9 _-]{0,23}$")
KEYS = os.path.expanduser("~/.ssh/authorized_keys")
MARK = "cinminai-seat:"       # the comment on an outside seat's key line: what AICUI may remove
SEAT_COMMAND = "/usr/bin/cinminai-seat"


# --- the setup --------------------------------------------------------------------------------------------------------
def default() -> dict:
    return {"seats": [{"name": "Lead", "kind": "", "lead": True}, {"name": "Seat 2", "kind": ""}]}


def load(root: str) -> dict:
    try:
        with open(os.path.join(root, TABLE), encoding="utf-8") as f:
            got = json.load(f)
        if isinstance(got, dict) and isinstance(got.get("seats"), list) and got["seats"]:
            return got
    except (OSError, ValueError):
        pass
    return default()


def save(root: str, table: dict) -> None:
    path = os.path.join(root, TABLE)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        json.dump(table, f, indent=1, ensure_ascii=False)
    os.replace(path + ".tmp", path)


def slug(name: str) -> str:
    """A seat's name on the Team Table (letters, digits, dashes)."""
    return re.sub(r"[^a-z0-9-]+", "-", name.strip().lower()).strip("-")[:24] or "seat"


def lead_of(table: dict) -> dict | None:
    return next((s for s in table["seats"] if s.get("lead")), None)


def problems(table: dict) -> list[str]:
    """What stops this table from sitting down, in plain words (empty: it can)."""
    out = []
    seats = table.get("seats") or []
    if len(seats) < 2:
        out.append("a table needs two seats at least")
    names = [slug(s.get("name", "")) for s in seats]
    for s in seats:
        if not NAME.match(s.get("name", "")):
            out.append(f"\"{s.get('name', '')}\": a seat's name is a word or two (letters, digits, spaces)")
        if s.get("kind") not in KINDS:
            out.append(f"{s.get('name', 'a seat')} is empty: choose who sits there")
        elif s["kind"] in ("local", "cloud") and not s.get("model"):
            out.append(f"{s['name']}: choose its model")
        elif s["kind"] == "outside" and s.get("agent") not in OUTSIDE_AGENTS:
            out.append(f"{s['name']}: choose the outside agent")
    if len(set(names)) != len(names):
        out.append("two seats have the same name")
    leads = [s for s in seats if s.get("lead")]
    if len(leads) != 1:
        out.append("one seat wears the crown: the lead")
    elif leads[0].get("kind") == "outside":
        out.append("the lead is a local or cloud seat (an outside agent works from its own place, not AICUI's)")
    return out


def describe(seat: dict) -> str:
    """One seat, as the lead and the person read it."""
    from cin_minai.inference import cloud as cloud_mod
    kind = seat.get("kind")
    if kind == "local":
        return f"{seat['name']} (local: {os.path.splitext(seat.get('model', ''))[0]})"
    if kind == "cloud":
        return f"{seat['name']} (cloud: {cloud_mod.label(seat.get('model', ''))})"
    if kind == "outside":
        return f"{seat['name']} (outside agent: {seat.get('agent', '')}, joins over SSH)"
    return f"{seat.get('name', 'a seat')} (empty)"


def fit(setup: dict, machine=None) -> dict:
    """{seat name: how its local model runs here, or "doesn't fit beside the seats before it"} (matcher.seats_plan)."""
    from cin_minai.daemon.models import ModelStore
    from cin_minai.inference import matcher
    store = ModelStore()
    local = [s for s in setup["seats"] if s.get("kind") == "local" and s.get("model")]
    if not local:
        return {}
    machine = machine or matcher.read_machine(models_dir=store.root)
    models = []
    for s in local:
        m = next((m for ms in matcher.CATALOG.values() for m in ms if m.file == s["model"]), None)
        if m is None and store.has(s["model"]):
            try:
                m = matcher.model_from_gguf(store.path(s["model"]))
            except Exception:
                m = None
        models.append(m)
    plans = matcher.seats_plan([m for m in models if m is not None], machine)
    out, it = {}, iter(plans)
    for s, m in zip(local, models):
        p = next(it) if m is not None else None
        out[s["name"]] = (f"{p['mode']}, {p['context'] // 1024}K" if p else "doesn't fit beside the seats before it",
                          p, m)
    return out


def backends(root: str, setup: dict, say=print) -> dict:
    """Each local and cloud seat's model, started: {seat name: (backend, its label)}. Local seats go on the card in
    seat order (the lead's first); RuntimeError with the reason when one can't start."""
    import time

    from cin_minai.daemon import config
    from cin_minai.daemon.models import CODING_DRAFT, ModelStore, backend_cfg
    from cin_minai.inference import cloud as cloud_mod
    from cin_minai.inference.llamacpp import LlamaCppBackend

    from .agent import unload_guide
    out = {}
    ordered = sorted(setup["seats"], key=lambda s: not s.get("lead"))
    if any(s.get("kind") == "local" for s in ordered):
        unload_guide()  # one card: the assistant's guide steps aside while the table sits
        placed = fit({"seats": ordered})
        store = ModelStore()
        base = config.load()["inference"]
        log_path = os.path.join(os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache"), "cinminai",
                                "code-server.log")
        os.makedirs(os.path.dirname(log_path), exist_ok=True)

        def log(msg: str) -> None:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")
        for s in ordered:
            if s.get("kind") != "local":
                continue
            how, plan, model = placed.get(s["name"], ("", None, None))
            if plan is None:
                raise RuntimeError(f"{s['name']}'s model ({s.get('model')}) " + (
                    "isn't in the model store" if model is None else "doesn't fit beside the seats before it"))
            cfg = backend_cfg(base, plan, store.path(s["model"]))
            cfg["socket_name"], cfg["draft"] = f"llama-seat-{slug(s['name'])}.sock", CODING_DRAFT
            log(f"table seat {s['name']}: {plan['model']} | {plan['mode']} | {' '.join(plan.get('args', []))}")
            say(f"\033[2m{s['name']}: {plan['model']} ({how}), loading…\033[0m")
            b = LlamaCppBackend(cfg, log)
            b.model_file = s["model"]
            b.chat([{"role": "user", "content": "ok"}], max_tokens=1)  # in seat order: each takes its room now
            out[s["name"]] = (b, plan["model"])
    for s in ordered:
        if s.get("kind") == "cloud":
            out[s["name"]] = (cloud_mod.backend(root, s.get("provider") or cloud_mod.provider_of(s["model"]),
                                                s["model"]), cloud_mod.label(s["model"]) + " (cloud)")
    return out


def describe_all(setup: dict) -> str:
    return ", ".join(describe(s) for s in setup["seats"] if not s.get("lead")) or "no other seats"


# --- outside seats: a key that may only reach its seat -------------------------------------------------------------
KEY = re.compile(r"^(ssh-ed25519|ssh-rsa|ecdsa-sha2-nistp(256|384|521)|sk-ssh-ed25519@openssh\.com) [A-Za-z0-9+/=]{40,}"
                 r"( .*)?$")


def key_line(root: str, seat: str, public_key: str) -> str:
    """The authorized_keys line for an outside seat: its key can only start that seat's server for this project — no
    shell, no forwarding, no terminal (`restrict`)."""
    public_key = " ".join(public_key.strip().split())
    if not KEY.match(public_key):
        raise ValueError("that isn't an SSH public key (it starts with ssh-ed25519, ssh-rsa or ecdsa-…; copy the .pub "
                         "file's one line)")
    kind, body = public_key.split()[:2]
    if any(c in root for c in "\"\\'\n"):
        raise ValueError("the project's folder name has a quote or a backslash: rename it to seat an outside agent")
    command = f"{SEAT_COMMAND} --project {shlex.quote(root)} --seat {slug(seat)}"
    return f'command="{command}",restrict {kind} {body} {MARK}{slug(seat)}@{os.path.basename(root)}'


def add_key(root: str, seat: str, public_key: str, path: str = KEYS) -> None:
    line = key_line(root, seat, public_key)
    remove_key(root, seat, path)
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    os.chmod(path, 0o600)


def remove_key(root: str, seat: str, path: str = KEYS) -> bool:
    """The seat's key line gone (only lines AICUI wrote for this seat and project)."""
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError:
        return False
    mark = f"{MARK}{slug(seat)}@{os.path.basename(root)}"
    kept = [x for x in lines if not x.rstrip().endswith(mark)]
    if len(kept) == len(lines):
        return False
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        f.write("\n".join(kept) + ("\n" if kept else ""))
    os.chmod(path + ".tmp", 0o600)
    os.replace(path + ".tmp", path)
    return True


def connect_lines(seat: dict, root: str, where: str) -> dict:
    """What the person gives the outside agent: the line that adds this table to it. `where`: user@host of this
    computer (from another one), or "" on this computer."""
    if where:
        cmd, args = "ssh", ["-T", where]
    else:
        cmd, args = SEAT_COMMAND, ["--project", root, "--seat", slug(seat["name"])]
    return {"Claude Code": "claude mcp add team-table -- " + " ".join([cmd, *args]),
            "Codex": "[mcp_servers.team-table]\ncommand = " + json.dumps(cmd) + "\nargs = " + json.dumps(args)}


# --- running: the lead, the seats in AICUI, the outside seats ---------------------------------------------------
class OutsideSeat:
    """An outside agent's seat: its tasks are put on the table for it; it claims them through its seat server and
    finishes them there; the results reach the lead between its steps, as a seat's in AICUI do."""

    def __init__(self, table: "Table", seat: dict) -> None:
        self.table, self.seat = table, seat
        self.name = seat["name"]
        self.second = table.engine.member(slug(seat["name"]), 200_000, seat.get("agent", ""), "mcp")
        self.owed: dict[int, str] = {}
        self.lock = threading.RLock()

    def open_tasks(self) -> list[dict]:
        try:
            return self.table.engine.open_for(self.second)
        except Exception:
            return []

    @property
    def held(self) -> dict[str, int]:
        from .pair import spec_of
        return {p: t["id"] for t in self.open_tasks() for p in spec_of(t).get("hold", [])}

    @property
    def out(self) -> int:
        self.settle()
        return len(self.open_tasks())

    @property
    def listing(self) -> dict[int, dict]:
        from .pair import spec_of
        return {t["id"]: {"n": t["id"], "what": f"({self.name}) {t['title']}", "goal": spec_of(t).get("goal", ""),
                          "task": t["id"]} for t in self.open_tasks()}

    def queue(self, rel: str, task: str, kind: str, what: str, hold: list | None = None, attempt: int = 1,
              goal: str = "") -> str:
        from .pair import SPEC
        e = self.table.engine
        spec = SPEC + json.dumps({"kind": kind, "rel": rel, "hold": list(hold if hold is not None else
                                                                          [rel] if rel else []),
                                  "attempt": attempt, "goal": goal or "no session goal"}, ensure_ascii=False)
        try:
            refs, body = [], task
            if len(what) + len(spec) + 1 + len(task) > e.cap(self.second):
                refs, body = [e.keep(f"task for {self.second}: {what}", task)], ""
            t = e.order(self.table.request_root()["id"], self.table.lead_member, self.second, what[:200],
                        f"{spec}\n{body}", {"write": "write", "fix": "write"}.get(kind, "check"), refs)
        except Exception as ex:
            return f"error: the Team Table refused this task: {str(ex)[:300]}"
        self.owed[t["id"]] = what
        self.table.show()
        self.table.lead.event("handoff", by="senior", to=slug(self.name), text=f"task {t['id']}: {what}")
        return (f"task {t['id']} put on the table for {self.name} ({kind} {rel or ''}); {self.name} works from its own "
                "place and its result comes between your steps.")

    def settle(self) -> None:
        """Its finished or stopped tasks, to the lead."""
        with self.lock:
            for n, what in list(self.owed.items()):
                t = self.table.engine.get(n)
                if not t or t["status"] in ("pending", "in_progress"):
                    continue
                self.owed.pop(n, None)
                if t["status"] == "cancelled":
                    text = f"task {n} ({what[:120]}) — not done: stopped by the person."
                else:
                    try:
                        r = json.loads(t.get("result") or "{}")
                    except ValueError:
                        r = {"note": t.get("result") or ""}
                    r = r if isinstance(r, dict) else {"note": str(r)}
                    text = (f"task {n} ({what[:120]}) — {r.get('verdict', 'done')}, by {self.name}. It said: "
                            f"{str(r.get('note', ''))[:1200]}\nAccept it, or send it back, with review_task.")
                self.table.lead.inbox.append((n, "task", text))

    def review(self, n: int, accept: bool, note: str = "") -> str:
        from .pair import spec_of
        t = self.table.engine.get(n)
        if not t or t.get("assignee") != self.second or t["status"] != "done":
            return f"error: task {n} isn't finished (or isn't {self.name}'s)"
        verdict = "accepted" if accept else "rejected"
        try:
            self.table.engine.db.update_task(n, "done", agent_name=self.table.lead_member, result=json.dumps(
                {"model": self.seat.get("agent", ""), "verdict": verdict, "note": note[:300]}, ensure_ascii=False))
        except Exception:
            pass
        if accept:
            return f"task {n} accepted"
        s = spec_of(t)
        return self.queue(s.get("rel", ""), f"Correction of task {n} — the lead's corrections: {note}\nThe task was: "
                                            f"{t['title']}", s.get("kind", "write"), f"fix {s.get('rel', '')}: {note}"
                          [:200], hold=s.get("hold"), attempt=2)


class Table:
    """The lead (an Agent) and the seats: local or cloud Agents (a Pair each, so each works its own queue on the
    table) and outside seats. The lead's assign and brief take `to`, a seat's name; goals assigned on the paper go to
    their seat once their needs are in."""

    def __init__(self, lead, seats: dict, setup: dict, say=print, engine=False) -> None:
        from cin_minai import engine as engine_mod

        from .pair import Pair, project_of
        self.lead, self.setup, self.say = lead, setup, say
        if engine is False:
            engine = engine_mod.team_engine(project_of(lead.root), lead.root)
        if engine is None:
            raise RuntimeError("the table works through the Team Table, and there's none here")
        self.engine = engine
        crowned = lead_of(setup) or {"name": "Lead"}
        self.lead_name = crowned["name"]
        self.pairs: dict[str, Pair] = {}
        self.outside: dict[str, OutsideSeat] = {}
        first = None
        for s in setup["seats"]:
            if s.get("lead"):
                continue
            if s.get("kind") == "outside":
                self.outside[s["name"]] = None  # made once the lead's member is known (below)
            elif s["name"] in seats:
                p = Pair(lead, seats[s["name"]], say, engine, name=slug(s["name"]))
                p.many = True  # a task here may hold several files (the lead's `also`)
                p.goal_whos = (s["name"],) if first is not None else ("junior", s["name"])  # its goals; a
                #   plan's "junior" goals go to the first seat in AICUI
                if first is not None:
                    p.question_numbers = first.question_numbers
                    p.request_root = first.request_root
                first = first or p
                self.pairs[s["name"]] = p
        if first is None:  # only outside seats: a Pair-less lead still needs its request on the table
            self.lead_member = engine.member("senior", lead.ctx, getattr(lead, "model_name", ""), "local")
            self._root = None
            self.request_root = self._own_root
        else:
            self.lead_member = first.lead
            self.request_root = first.request_root
        for name in list(self.outside):
            self.outside[name] = OutsideSeat(self, next(s for s in setup["seats"] if s["name"] == name))
        self.first = first
        self.channel = f"table.{engine.ns}"
        self.talk_seen = 0
        self.open_floor()
        lead.inbox = []
        lead.table_seats = self.seats_text()
        lead.junior_profile = lambda: " ".join(f"{n}: {p.profile()}" for n, p in self.pairs.items())
        lead.errands_pending = lambda: self.out > 0
        lead.assign_fn = self.assign
        lead.brief_fn = self.brief
        lead.distiller = lambda *a, **k: (first.distill(*a, **k) if first else
                                          "error: no seat in AICUI to distill for you (only outside seats)")
        lead.first_reader = first.first_read if first else None
        lead.planned = self.release_goals
        lead.each_step = self.between_steps
        lead.follow_up_fn = lambda n, note: (self.holder(n).follow_up(n, note) if hasattr(self.holder(n), "follow_up")
                                             else f"error: task {n} is with an outside seat; say it at the table")
        lead.review_task_fn = lambda n, accept, note="": self.holder(n).review(n, accept, note)
        lead.permit_fn = lambda n, allow: next((p for p in self.pairs.values() if n in p.questions),
                                               first).permit(n, allow) if first else f"error: no question {n}"
        lead.lfd_fn = (lambda focus: first.lfd(focus)) if first else (lambda focus: "error: no seat in AICUI for lfd")
        from .pair import within
        lead.may_write = lambda rel: next((f"{rel} is held by {n}'s task {h[k]} until it's done — work on another "
                                           "file meanwhile" for n, h in ((n, x.held) for n, x in self.seats().items())
                                           for k in h if within(rel, k)), "")  # a folder holds its files too
        lead.table_fn = lambda tool, a: self.talk(self.lead_member, tool, a)
        for name, p in self.pairs.items():
            p.junior.table_fn = (lambda tool, a, who=p.second: self.talk(who, tool, a))
            p.show = self.show

    def _own_root(self) -> dict:
        if self._root is None or self.engine.state(self._root["id"]) in ("done", "cancelled", "blocked"):
            self._root = self.engine.request("(the lead's own work, between requests)", self.lead_member)
        return self._root

    def seats(self) -> dict:
        return {**self.pairs, **self.outside}

    def seats_text(self) -> str:
        return ", ".join(describe(s) for s in self.setup["seats"] if not s.get("lead"))

    @property
    def out(self) -> int:
        return sum(x.out for x in self.seats().values())

    def show(self) -> None:
        listed = [x for s in self.seats().values() for x in s.listing.values()]
        self.lead.event("errands", out=sorted(listed, key=lambda x: x["n"]))

    def seat_for(self, to: str):
        """The seat a lead names (its name, any case), or the first seat in AICUI."""
        if to:
            for name, s in self.seats().items():
                if slug(name) == slug(to):
                    return s
            return None
        return self.first or next(iter(self.outside.values()), None)

    def holder(self, n: int):
        who = (self.engine.get(n) or {}).get("assignee")
        return next((s for s in self.seats().values() if s.second == who), self.first)

    # --- the lead's tools -------------------------------------------------------------------------------------------
    def assign(self, path: str, task: str, kind: str = "write", attempt: int = 1, to: str = "",
               also: list | None = None) -> str:
        """`also`: more files the same task holds, new ones included; none may be held by another task."""
        seat = self.seat_for(to)
        if seat is None:
            return f"error: there's no seat \"{to}\" at the table — the seats: {self.seats_text()}"
        root = os.path.realpath(self.lead.root)
        main = os.path.relpath(os.path.realpath(os.path.join(root, path)), root).replace(os.sep, "/")
        held = "" if kind == "test" else self.lead.may_write(main)  # held by any seat's task, not only this one's
        if held:
            return f"error: {held}"
        more = []
        for f in [] if kind == "test" else also or []:
            full = os.path.realpath(os.path.join(root, str(f)))
            if not full.startswith(root + os.sep) or os.path.isdir(full):
                return f"error: {f} isn't a file in the project"
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            held = self.lead.may_write(rel)
            if held:
                return f"error: {held}"
            if rel != main and rel not in more:
                more.append(rel)
        if isinstance(seat, OutsideSeat):
            root = os.path.realpath(self.lead.root)
            full = os.path.realpath(os.path.join(root, path))
            if not full.startswith(root + os.sep):
                return f"error: {path} isn't in the project"
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            held = self.lead.may_write(rel)
            if kind != "test" and held:
                return f"error: {held}"
            if kind != "test" and not os.path.isfile(full):
                return (f"error: {rel} doesn't exist yet — lay the skeleton first (the file with its imports, classes "
                        "and signatures, stubs marked TODO), then assign it")
            return seat.queue(rel, task.strip(), kind, f"{kind} {rel}: {task.strip()}"[:200],
                              hold=[] if kind == "test" else [rel, *more], attempt=attempt)
        return seat.assign(path, task, kind, attempt, also=more or None)

    def brief(self, files: list, question: str, to: str = "") -> str:
        seat = self.seat_for(to) if to else self.first
        if seat is None or isinstance(seat, OutsideSeat):
            return "error: brief goes to a seat in AICUI (a local or cloud seat)"
        return seat.brief(files, question)

    def release_goals(self) -> None:
        for p in self.pairs.values():
            p.release_goals()
        for name, seat in self.outside.items():
            for g in self.lead.goals.load():
                if g["done"] or g.get("who") != name or g.get("queued") or not self.lead.needs_met(g):
                    continue
                files = list(g.get("files") or [])
                if any(f in s.held for s in self.seats().values() for f in files):
                    continue
                self.lead.goals.update(g["id"], queued=True)
                seat.queue(", ".join(files), f"Goal {g['id']}: {g['text']}" + (f"\nIts files: {', '.join(files)}."
                                                                             if files else ""),
                           "goal", f"goal {g['id']}: {g['text']}"[:200], hold=files, goal=f"goal {g['id']}")

    def between_steps(self) -> None:
        self.release_goals()
        for p in self.pairs.values():
            p.check_in()
        for s in self.outside.values():
            s.settle()
        self.news()

    # --- the conversation ------------------------------------------------------------------------------------------
    def open_floor(self) -> None:
        from cin_minai.daemon.turns import PERSON
        order = [self.lead_member] + [s.second for s in self.seats().values()]
        try:
            self.engine.db.open_floor(self.channel, order, [PERSON, self.lead_member], PERSON)
        except Exception as e:
            self.say(f"(the table's conversation couldn't open: {e})")

    def talk(self, who: str, tool: str, a: dict) -> str:
        db = self.engine.db
        try:
            if tool == "say":
                db.say(self.channel, who, str(a.get("text", "")))
                return "said at the table"
            if tool == "pass_floor":
                to = str(a.get("to", "") or "")
                target = self.seat_for(to) if to else None
                state = db.pass_floor(self.channel, who, target.second if target else (None if not to else to))
                return f"the floor is {state['holder'] or 'free'}'s now"
            if tool == "request_floor":
                state = db.request_floor(self.channel, who)
                return ("you have the floor: say what you need" if state["holder"] == who else
                        f"{state['holder']} has the floor; you're number {state['queue'].index(who) + 1} to speak next")
        except Exception as e:
            return f"error: {getattr(e, 'message', str(e))}"
        return "error: say, pass_floor or request_floor"

    def news(self) -> None:
        """What was said at the table since the lead last heard, to the lead (capped: a long conversation can't
        flood its context)."""
        try:
            said = self.engine.db.conversation(self.channel, self.talk_seen, 30)
        except Exception:
            return
        if not said:
            return
        self.talk_seen = said[-1]["id"]
        lines = [f"{m['sender'].split('.')[0]}: {m['content']}" for m in said if m["sender"] != self.lead_member]
        if lines:
            cap = int(getattr(self.lead, "ctx", 32768) * 3 * 0.05)
            text = "\n".join(lines)
            self.lead.inbox.append((0, "talk", text[-cap:]))

    # --- one request ----------------------------------------------------------------------------------------------
    def turn(self, request: str, cancel: threading.Event | None = None) -> str:
        cancel = cancel or threading.Event()
        if self.first is not None:
            try:
                return self.first.turn(request, cancel)
            finally:
                if cancel.is_set():
                    self.stopped()
        try:
            self._root = self.engine.request(request, self.lead_member)
        except Exception as e:
            return f"The Team Table couldn't take this request ({str(e)[:200]}), so the table didn't start on it."
        try:
            return self.lead.turn(request, cancel)
        finally:
            if cancel.is_set():
                self.stopped()

    def stopped(self) -> None:
        for p in self.pairs.values():
            p.stopped()
        try:
            self.engine.close_stale()
        except Exception:
            pass
        for s in self.outside.values():
            s.settle()
