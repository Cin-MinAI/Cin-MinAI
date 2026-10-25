# SPDX-License-Identifier: GPL-3.0-or-later
"""Two coders on one project — style B of the two cards (PLAN §1b, SPEC §22.5; D94-D96). Ian, 2026-10-09: "MoE
should be able to fill out a whole file structure and plan for the project then send 9b on scripts one at a time
while doing work itself in other places. If it does all the imports and classes and dependencies and binaries first,
the small model has a domain to work in and should hallucinate less and make less mistakes."

* **The Senior** (the bigger model, a MoE with its experts in RAM) works the person's request with its own judgement
  and has the final word. It lays the skeleton first, then gives the Junior one file at a time (`assign`): only a file
  that exists, so the skeleton comes first. The file is **held** for the Junior's task — the Senior can't write it
  until the task closes — and the Senior works on other files meanwhile.
* **The Junior** (the 9B coder, whole on the card) works its queue on its own thread, one task at a time, and may
  write only the files its task holds. Its result — what it did, what it changed, what the checks find now — reaches
  the Senior between its steps; the Senior accepts it or sends it back with a note (`review_task`).
* Every request is the Senior's task on the Team Table, every Junior task a child task with its verdict; the chat shows
  each exchange; Stop works on the table's tokens, as in style A.
* **The table is the backbone** (Ian, 2026-10-21): the Junior claims its next task from the table (the person's first),
  a task's number is its number there, what it holds and what attempt it is are written on it, and its instruction
  travels on it (or by reference when it's long). The table's refusals — the request's budget spent, hand-offs too
  deep, a task too big for its member — reach the Senior as its answer. A team doesn't run without the table.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import os
import threading
import time

from cin_minai import engine as engine_mod

from .project import token_of

KEEP = os.path.join(".cinminai", "keep-errands")   # AICUI: Stop the Senior only — the Junior's tasks go on
HALT = os.path.join(".cinminai", "stop-errands")   # AICUI: Stop the Junior only (when the table can't be reached)
SPEC = "aicui "    # a Junior task's first line on the table: {"kind", "rel", "hold", "attempt", "goal"} as JSON
IDLE = 5.0         # seconds the Junior's worker waits for a new task before it ends (the next task starts it again)


def spec_of(task: dict | None) -> dict:
    """What AICUI wrote on a Junior task: its kind, its file, the files it holds, its attempt, its goal."""
    first = ((task or {}).get("description") or "").split("\n", 1)[0]
    if not first.startswith(SPEC):
        return {}
    try:
        got = json.loads(first[len(SPEC):])
    except ValueError:
        return {}
    return got if isinstance(got, dict) else {}


def project_of(root: str) -> str:
    return token_of(root) or hashlib.sha1(os.path.realpath(root).encode()).hexdigest()


class Pair:
    """senior and junior: two Agents on the same project, each with its own model. `name`: the junior's name on the
    table (a crew's two contributors each have their own queue)."""

    def __init__(self, senior, junior, say=print, engine=False, where: str = "local", name: str = "junior") -> None:
        self.senior, self.junior, self.say = senior, junior, say
        senior.role, junior.role = "senior", "junior"
        if engine is False:
            engine = engine_mod.team_engine(project_of(senior.root), senior.root)
        if engine is None:
            raise RuntimeError("a team works through the Team Table, and there's none here")
        self.engine = engine
        self.lead = engine.member("senior", senior.ctx, getattr(senior, "model_name", ""), where)
        self.second = engine.member(name, junior.ctx, getattr(junior, "model_name", ""), where)
        self.models = {self.lead: getattr(senior, "model_name", ""), self.second: getattr(junior, "model_name", "")}
        self.root: dict | None = None
        self.cancel: threading.Event | None = None
        self.question_numbers = itertools.count(1)   # the junior's questions (a crew's contributors share them)
        self.lock = threading.RLock()  # the worker's claim and settle() take it, also from within each other
        self.worker: threading.Thread | None = None
        self.taken_over: set[str] = set()            # files whose corrections are the senior's now
        self.current: set[str] = set()               # the files of the task the Junior works now
        self.many = False                            # at the Team Table: a task may hold several files (`also`)
        self.stop_junior = threading.Event()
        self.delivering = 0                          # the task the Junior has claimed, until its result is delivered
        self.owed: dict[int, str] = {}               # tasks given and not answered yet: id -> what
        senior.inbox = []
        senior.junior_profile = self.profile  # the senior plans with what its junior was measured to carry
        senior.errands_pending = lambda: self.out > 0
        senior.assign_fn = self.assign
        senior.distiller = self.distill
        senior.first_reader = self.first_read  # team B: what the senior fetches, the junior reads first
        senior.planned = self.release_goals  # the plan's junior goals, once their needs are in
        senior.each_step = self.between_steps   # and, between the senior's steps, a word on a junior task that's long
        senior.follow_up_fn = self.follow_up
        senior.brief_fn = self.brief
        senior.lfd_fn = self.lfd
        senior.permit_fn = self.permit
        junior.ask_permission = self.junior_permission  # its questions: to the person and to the senior
        self.questions: dict[int, dict] = {}
        junior.inbox = []                       # the senior's direction, read at the junior's next step
        self.running: dict | None = None        # the junior's task now: {"n", "what", "since", "log0", "kinds"}
        self.pending_notes: dict[int, list[str]] = {}  # direction for a task that hasn't started
        senior.review_task_fn = self.review
        senior.may_write = self.senior_may_write
        junior.may_write = self.junior_may_write
        self.current_table: dict | None = None
        junior.halt = lambda: self.halted(self.current_table)  # Stop every step, as the Senior's own rules

    # --- the Junior's queue, as the table holds it -------------------------------------------------------------
    def open_tasks(self) -> list[dict]:
        try:
            return self.engine.open_for(self.second)
        except Exception:
            return []

    def settle(self) -> None:
        """A task stopped on the table before the Junior started it (Stop, or the Requests view) is answered all the
        same: the Senior hears it wasn't done."""
        with self.lock:  # never the task the worker has claimed: that one is answered by the worker
            for n, what in list(self.owed.items()):
                if n != self.delivering and self.engine.state(n) == "cancelled":
                    self.owed.pop(n, None)
                    self.senior.inbox.append((n, "task", f"task {n} ({what[:120]}) — not done: stopped by the person."))

    @property
    def out(self) -> int:
        """Tasks not back yet: open on the table, and the one whose result is on its way to the Senior."""
        self.settle()
        return len({t["id"] for t in self.open_tasks()} | ({self.delivering} if self.delivering else set()))

    @property
    def held(self) -> dict[str, int]:
        """file -> the Junior task that holds it (one writer per file)."""
        return {path: t["id"] for t in self.open_tasks() for path in spec_of(t).get("hold", [])}

    @property
    def listing(self) -> dict[int, dict]:
        """The tasks out, as AICUI lists them at Stop."""
        return {t["id"]: {"n": t["id"], "what": t["title"], "goal": spec_of(t).get("goal", ""), "task": t["id"]}
                for t in self.open_tasks()}

    def instruction(self, task: dict) -> str:
        """A task's instruction: on it, or under its reference when it was too long to carry."""
        body = (task.get("description") or "").split("\n", 1)
        text = body[1] if len(body) > 1 and body[0].startswith(SPEC) else (task.get("description") or "")
        if not text.strip() and task.get("refs"):
            text = self.engine.kept(task["refs"][0])
        return text

    def request_root(self) -> dict:
        """The request the Junior's tasks belong to (the Senior's work between requests gets one of its own)."""
        if self.root is None or self.engine.state(self.root["id"]) in ("done", "cancelled", "blocked"):
            self.root = self.engine.request("(the senior's own work, between requests)", self.lead)
        return self.root

    # --- the write guards ------------------------------------------------------------------------------------
    def senior_may_write(self, rel: str) -> str:
        n = self.held.get(rel)
        return f"{rel} is held by your junior's task {n} until it's done — work on another file meanwhile" if n else ""

    def junior_may_write(self, rel: str) -> str:
        return "" if rel in self.current else (f"{rel} isn't part of your task — you may change only "
                                              f"{', '.join(sorted(self.current)) or 'the files your senior names'}")

    # --- one request: the Senior's ---------------------------------------------------------------------------
    def turn(self, request: str, cancel: threading.Event | None = None) -> str:
        self.cancel = cancel or threading.Event()
        self.root = None
        if self.out == 0:
            self.stop_junior.clear()
        try:
            self.root = self.engine.request(request, self.lead)
        except Exception as e:  # the team works through the table: without the request on it, nothing starts
            said = f"The Team Table couldn't take this request ({str(e)[:200]}), so the team didn't start on it."
            self.senior.event("answer", text=said)
            return said
        try:
            out = self.senior.turn(request, self.cancel)
        except BaseException:
            self.stopped()
            raise
        if self.cancel.is_set():
            self.stopped()
        else:
            ended = getattr(self.senior, "stopped", "")
            verdict = {"answer": "done", "ask": "asks the person"}.get(ended, ended or "done")
            self.close(out, verdict)
        return out

    def close(self, text: str, verdict: str) -> None:
        if self.root:
            try:
                self.engine.finish(self.root, self.lead, self.models[self.lead], verdict, text,
                                   "done" if verdict == "done" else "blocked")
            except Exception:
                pass

    def stopped(self) -> None:
        """Stop: the Junior's tasks go on if the person chose so at Stop (AICUI's question); else all ends."""
        keep = os.path.join(self.senior.root, KEEP)
        kept = os.path.exists(keep)
        if kept:
            try:
                os.remove(keep)
            except OSError:
                pass
        if kept and self.out > 0:
            self.close("stopped by the person; the junior's tasks go on in the background", "stopped")
            return
        self.stop_junior.set()
        for root in {t["root_id"] for t in self.open_tasks() if t.get("root_id")} | ({self.root["id"]} if self.root
                                                                                    else set()):
            try:  # every request the Junior has tasks from, not only this one
                self.engine.cancel(root)
            except Exception:
                pass
        self.settle()

    def halted(self, task: dict | None) -> bool:
        halt = os.path.join(self.senior.root, HALT)
        if os.path.exists(halt):
            try:
                os.remove(halt)
            except OSError:
                pass
            self.stop_junior.set()
        if self.stop_junior.is_set():
            return True
        if task is not None:
            try:
                return self.engine.state(task["id"]) == "cancelled"
            except Exception:
                return False
        return False

    def show(self) -> None:
        self.senior.event("errands", out=sorted(self.listing.values(), key=lambda x: x["n"]))

    # --- the Senior's tools ----------------------------------------------------------------------------------
    def assign(self, path: str, task: str, kind: str = "write", attempt: int = 1, to: str = "",
               also: list | None = None) -> str:
        """One file for the Junior: it must exist (the skeleton first) and not be held already. The protocol (Ian,
        2026-10-15): the senior gives the code specifics; the junior starts each task fresh, within its limits; a
        rejected task goes back once with the corrections, and after that the senior makes the corrections itself.
        At the Team Table (`many`), `also` names more files the same task holds, new ones included (Ian, 2026-10-21:
        a lead there writes "make these five files", and a task holding one came back half done)."""
        root = os.path.realpath(self.senior.root)
        full = os.path.realpath(os.path.join(root, path))
        if not full.startswith(root + os.sep):
            return f"error: {path} isn't in the project"
        rel = os.path.relpath(full, root).replace(os.sep, "/")
        if kind == "test":  # run the program or its tests and report: nothing held, nothing changed
            if len(task.strip()) < 8:
                return "error: say what the junior should run and look for"
            return self.queue(rel if os.path.exists(full) else "", task.strip(), "test",
                              f"test {rel}: {task.strip()}"[:200], hold=[])
        later = []
        if also and not self.many:  # the first file goes ahead (2026-10-25: Haiku 5.5 sent the same call twice, was
            later, also = [f for f in also if f != rel], None  # refused twice and stopped with nothing done)
        if not os.path.isfile(full):
            return (f"error: {rel} doesn't exist yet — lay the skeleton first (the file with its imports, classes and "
                    "signatures, stubs marked TODO), then assign it")
        for f in [rel, *(also or [])]:
            if f in self.held:
                return f"error: {f} is already held by task {self.held[f]}"
        if len(task.strip()) < 8:
            return "error: say what the junior should do in this file"
        if kind == "fix" and rel in self.taken_over:
            return (f"error: your junior had its correction attempt on {rel}; the corrections there are yours now "
                    "(edit or replace_lines)")
        if kind in ("write", "fix") and attempt == 1 and len(task.split()) < DETAIL_WORDS:
            return (f"error: give your junior the code specifics ({DETAIL_WORDS} words at least): the functions or "
                    "classes with their signatures, the imports, what each must do, and how to check it")
        cap = int(getattr(self.junior, "ctx", 32768) * TASK_SHARE * 3.5)  # D95: a task is 5 % of the receiver's context
        if len(task) > cap:
            return (f"error: that task is {len(task):,} characters, over the {cap:,} your junior takes in one task (5 % "
                    "of its context): split it into tasks of one function or part each")
        out = self.queue(rel, task.strip(), kind, f"{kind} {rel}: {task.strip()}"[:200], attempt=attempt,
                         hold=[rel, *(also or [])])
        if later and not out.startswith("error"):
            out += (f" — only {rel} is in this task (one file per task here): give {', '.join(later)} their own "
                    "tasks")
        return out

    def queue(self, rel: str, task: str, kind: str, what: str, hold: list | None = None,
              goal: dict | None = None, attempt: int = 1) -> str:
        """The task onto the table for the Junior; the table's refusal, if it refuses, is the answer."""
        goal = goal or self.senior.goals.current()
        towards = f"goal {goal['id']}: {goal['text'][:120]}" if goal else "no session goal"
        spec = SPEC + json.dumps({"kind": kind, "rel": rel, "hold": list(hold if hold is not None else
                                                                          [rel] if rel else []),
                                  "attempt": attempt, "goal": towards}, ensure_ascii=False)
        try:
            root = self.request_root()
            refs = []
            body = task
            if len(what) + len(spec) + 1 + len(task) > self.engine.cap(self.second):  # the bulk by reference
                refs, body = [self.engine.keep(f"task for {self.second}: {what}", task)], ""
            table = self.engine.order(root["id"], self.lead, self.second, what[:200], f"{spec}\n{body}",
                                      {"write": "write", "distill": "read", "brief": "read"}.get(kind, "check"), refs)
        except Exception as e:  # the request's budget spent, hand-offs too deep, too big — said as the table says it
            return f"error: the Team Table refused this task: {str(e)[:300]}"
        n = table["id"]
        self.owed[n] = what
        self.show()
        with self.lock:
            if self.worker is None or not self.worker.is_alive():
                self.worker = threading.Thread(target=self.work_queue, daemon=True)
                self.worker.start()
        self.senior.event("handoff", by="senior", to="junior", text=f"task {n}: {what}")
        if kind == "goal":
            return f"task {n} given to your junior ({what}); its files are held for it until it's done."
        if kind == "brief":
            return f"task {n} given to your junior ({what}); its answer comes between your steps — work on meanwhile."
        if kind == "distill":
            return (f"task {n} given to your junior (distill" + (f" into {rel}, held for it" if rel else "") +
                    "); work on other files meanwhile; the gathered record comes between your steps.")
        return (f"task {n} given to your junior ({kind} {rel}); {rel} is held for it until it's done — work on other "
                "files meanwhile; its result comes between your steps.")

    def distill(self, sources: list, intent: str, into: str = "", fmt: str = "json") -> str:
        """The Senior's reading, to the Junior (it reads ~10x faster here): queued like a task; `into` held for it."""
        if into:
            root = os.path.realpath(self.senior.root)
            full = os.path.realpath(os.path.join(root, into))
            if not full.startswith(root + os.sep):
                return f"error: {into} isn't in the project"
            into = os.path.relpath(full, root).replace(os.sep, "/")
            if into in self.held:
                return f"error: {into} is already held by task {self.held[into]}"
        spec = json.dumps({"sources": list(sources)[:12], "intent": intent, "into": into, "format": fmt})
        hold = into.rstrip("/") + "/index.json" if into and fmt == "files" else into  # pictures: the index is written
        return self.queue(hold, spec, "distill", f"distill for: {intent}"[:200])

    def between_steps(self) -> None:
        self.release_goals()
        self.check_in()

    def check_in(self) -> None:
        """Ian, 2026-10-10: "after completing a few of its tasks it can check on Jr's progress if none has been shown
        yet. If there is progress and its just taking awhile Sr will wait. If Jr is stuck, Sr will provide further
        direction." After the Senior has moved on FOLLOW_UP times while a task is still with the Junior, a report."""
        r = self.running
        done = getattr(self.senior, "progress_total", 0)
        if not r or done - r["since"] < FOLLOW_UP:
            return
        steps = [x for x in list(getattr(self.junior, "steps", []) or []) if isinstance(x, dict) and x.get("did")]
        kinds = list(getattr(self.junior, "kinds_done", []) or [])
        entries = self.junior.log.entries() if hasattr(self.junior.log, "entries") else []
        changed = sorted({c.get("file", "") for c in entries[r["log0"]:]} - {""})
        moved = len(kinds) > r["kinds"]
        trail = "\n".join(f"- {x['did'].get('thinking', '')[:160]} → {str(x.get('result', ''))[:160]}"
                          for x in steps[-3:])
        report = (f"task {r['n']} ({r['what'][:120]}): {len(steps)} steps so far, progress {len(kinds)} times"
                  + (f" ({', '.join(kinds[-6:])})" if kinds else "") + "; changed: " + (", ".join(changed) or "nothing")
                  + f"\nIts last steps:\n{trail or '(none yet)'}\n"
                  + ("It's moving since the last word: let it work." if moved else
                     "No progress since the last word. If it's stuck or going the wrong way, direct it with follow_up "
                     f"({r['n']}, note) — what's wrong and the next small step; if it's on the right track, let it work."))
        r["since"], r["kinds"] = done, len(kinds)
        self.senior.inbox.append((r["n"], "progress", report))

    def brief(self, files: list, question: str, to: str = "") -> str:
        """The Senior asks the Junior about some files (Ian, 2026-10-10: "have your assistant scan each file and
        summarize to you"): it reads them, each in a fresh context, and answers between the Senior's steps."""
        root = os.path.realpath(self.senior.root)
        found, missing = [], []
        for f in files[:20]:
            full = os.path.realpath(os.path.join(root, str(f)))
            (found if full.startswith(root + os.sep) and os.path.isfile(full) else missing).append(
                os.path.relpath(full, root).replace(os.sep, "/") if full.startswith(root + os.sep) else str(f))
        if not found:
            return "error: none of these is a file in the project" + (f" ({', '.join(missing)})" if missing else "")
        if len(question.split()) < 3:
            return "error: say what you want to know from them (the question)"
        spec = json.dumps({"files": found, "question": question})
        said = self.queue("", spec, "brief", f"brief: {', '.join(found)[:120]} — {question}"[:200], hold=[])
        return said + (f" (not files here: {', '.join(missing)})" if missing else "")

    def run_brief(self, n: int, spec: str, table: dict | None) -> str:
        from . import lfd
        s = json.loads(spec)
        stop = lambda: self.halted(table)  # noqa: E731
        parts = []
        for rel in s["files"]:
            if stop():
                break
            self.junior.event("busy", doing=f"brief: reading {rel}", tokens=0)
            parts.append(f"## {rel}\n{lfd.summarize(self.junior, rel, s['question'], stop)}")
        os.makedirs(os.path.join(self.senior.root, ".cinminai", "briefs"), exist_ok=True)
        kept = f".cinminai/briefs/{n}.md"
        answer = "\n\n".join(parts)
        with open(os.path.join(self.senior.root, kept), "w", encoding="utf-8") as f:
            f.write(f"# {s['question']}\n\n{answer}\n")
        result = (f"task {n} (brief, by your junior) — {s['question']}\n{answer[:3500]}"
                  + (f"\n… the rest is kept in {kept}" if len(answer) > 3500 else ""))
        if table is not None and self.engine is not None:
            try:
                self.engine.finish(table, self.second, self.models[self.second], "briefed", result)
                self.engine.claim(self.lead)
            except Exception:
                pass
        return result

    def lfd(self, focus: str, ends: tuple | None = None) -> str:
        """Large File Distillation (lfd.py): both cards summarize the whole project from opposite ends; then the
        Senior's context is dumped and it plans from the summary. `ends`: the two that read (a cloud lead's two local
        contributors: its own tokens go to the plan, not the reading)."""
        from . import lfd
        focus = " ".join(focus.split()) or "what each part does and what's left to do"
        cancel = getattr(self.senior, "cancel_event", None)
        stop = lambda: self.stop_junior.is_set() or bool(cancel is not None and cancel.is_set())  # noqa: E731
        self.senior.event("handoff", by="senior", to="junior", text=f"Large File Distillation: {focus}")
        big, small = ends or (self.senior, self.junior)
        r = lfd.run(big, small, focus, stop)
        if r["stopped"]:
            return (f"Large File Distillation stopped by the person: {r['by_junior'] + r['by_senior']} of {r['files']} "
                    f"files summarized so far, in {r['path']}")
        limit = int(getattr(self.senior, "ctx", 32768) * getattr(self.senior, "cpt", 3.0) * 0.4)
        text = r["text"] if len(r["text"]) <= limit else r["text"][:limit] + f"\n… (the rest is in {r['path']})"
        self.senior.dump_context = (
            f"Large File Distillation is done: {r['files']} files, {r['by_junior']} summarized by your junior (from the "
            f"smallest), {r['by_senior']} by you (from the largest), in {r['path']}. Your earlier steps in this request "
            "are cleared, so your context is fresh. The project summary:\n\n" + text + "\n\nNow make the plan for "
            "moving forward with plan — roles for you and your assistant. The person's goals stay as they are (you tick "
            "them when they're really done, never reword or erase them); your own open goals give way to the new plan, "
            "the ticked ones stay — then work it.")
        self.senior.replan_ok = True
        return (f"Large File Distillation done: {r['files']} files in {r['seconds']} s — {r['by_junior']} by your "
                f"junior, {r['by_senior']} by you — into {r['path']}. Your context is cleared next; the summary comes "
                "with it.")

    def junior_permission(self, tool: str, show: str, about: str) -> str:
        """Ian, 2026-10-10: "If jr asks both user and sr can click yes or no." The question goes to the terminal and to
        the Senior between its steps; whichever answers first decides."""
        with self.lock:
            k = next(self.question_numbers)
        q = {"n": k, "event": threading.Event(), "answer": "", "by": ""}
        self.questions[k] = q
        self.senior.inbox.append((k, "question", f"{tool}{about}:\n{show[:800]}"))
        reply = self.terminal(f"\r\033[K\033[1m(junior) Allow {tool}{about}? [y]es / [n]o / [a]lways — or your "
                              "senior answers: \033[0m", q)
        if not q["event"].is_set():
            q["answer"], q["by"] = reply.strip().lower(), "person"
            q["event"].set()
        self.senior.event("handoff", by=q["by"], to="junior",
                          text=f"question {k}: {tool}{about} — {'yes' if q['answer'][:1] in ('y', 'a') else 'no'}")
        return q["answer"]

    def terminal(self, prompt: str, q: dict) -> str:
        """The question on screen, its answer from the keyboard — or from the senior while it waits."""
        import select
        import sys
        from .agent import ASK_LOCK, PENDING
        with ASK_LOCK:
            if q["event"].is_set():
                return q["answer"]
            if not sys.stdin.isatty():
                return self.junior.raw_ask(prompt)
            PENDING["prompt"] = prompt
            try:
                sys.stdout.write(prompt)
                sys.stdout.flush()
                while True:
                    ready, _, _ = select.select([sys.stdin], [], [], 0.5)
                    if ready:
                        return sys.stdin.readline().strip()
                    if q["event"].is_set():
                        sys.stdout.write(f"\r\033[K(the junior's question was answered by your senior: "
                                         f"{'yes' if q['answer'] == 'y' else 'no'})\n")
                        sys.stdout.flush()
                        return q["answer"]
            finally:
                PENDING["prompt"] = ""

    def permit(self, n: int, allow: bool) -> str:
        q = self.questions.get(n)
        if q is None:
            return f"error: there's no question {n} from your junior"
        if q["event"].is_set():
            return f"question {n} is answered already ({'yes' if q['answer'][:1] in ('y', 'a') else 'no'}, by the {q['by']})"
        q["answer"], q["by"] = ("y" if allow else "n"), "senior"
        q["event"].set()
        return f"told your junior: {'yes' if allow else 'no'} (question {n})"

    def follow_up(self, n: int, note: str) -> str:
        """The Senior's direction for a Junior task: read at the Junior's next step if it's working on it, or given
        with the task if it hasn't started."""
        note = " ".join(note.split())
        if len(note) < 8:
            return "error: say what the junior should do differently"
        if self.running and self.running["n"] == n:
            self.junior.inbox.append((n, "direction", note))
            self.senior.event("handoff", by="senior", to="junior", text=f"task {n}: {note}")
            return f"sent to your junior: it reads it at its next step on task {n}"
        with self.lock:
            waiting = n in self.listing
            if waiting:  # kept here until the task starts: a direction is for this session's Junior
                self.pending_notes.setdefault(n, []).append(note)
        if waiting:
            return f"task {n} hasn't started: your junior gets this with it"
        return f"error: task {n} isn't with your junior (finished, or never given) — give a new task with assign"

    def release_goals(self) -> None:
        """The plan's goals for the Junior (Ian, 2026-10-10): each goes to it once what it needs from outside is in,
        with its files held for it; one at a time per file. The Junior waits for these — it starts nothing itself."""
        for g in self.senior.goals.load():
            if g["done"] or g.get("who") not in getattr(self, "goal_whos", ("junior",)) or g.get("queued") or \
                    not self.senior.needs_met(g):
                continue
            files = list(g.get("files") or [])
            with self.lock:
                if any(f in self.held for f in files):
                    continue  # one writer per file: when they're free
            have = self.senior.needs_have(g)
            notes = sorted(os.path.join("notes", f) for f in os.listdir(os.path.join(self.senior.root, "notes"))) \
                if os.path.isdir(os.path.join(self.senior.root, "notes")) else []
            task = json.dumps({"goal": g["id"], "files": files, "text": (
                f"Goal {g['id']}: {g['text']}\n"
                + (f"Its files: {', '.join(files)}.\n" if files else "")
                + (f"What came in for it: {', '.join(f'{w} ({h})' for w, h in have)}.\n" if have else "")
                + (f"Notes kept so far: {', '.join(notes[:12])}.\n" if notes else "")
                + "Facts come from these sources only. Work the goal in small steps; when it's done, answer with what "
                  "you did and how you checked it.")})
            self.senior.goals.update(g["id"], queued=True)
            self.queue("", task, "goal", f"goal {g['id']}: {g['text']}"[:200], hold=files, goal=g)

    def first_read(self, rel: str, url: str, goal: int | None = None) -> str:
        """Ian, 2026-10-10: "Jr should do first reading and hand to senior and hold notes." A page or a PDF's text the
        Senior fetches goes to the Junior, which reads it for what the Senior was after (its thinking at that step and
        the goal) and keeps notes in notes/ — the source's own words, with where they stood; they come back between
        the Senior's steps."""
        goal = next((g for g in self.senior.goals.load() if g["id"] == goal), None) or self.senior.goals.current()
        wanted = " ".join(str(getattr(self.senior, "last_thinking", "")).split())[:300]
        intent = (f"what this source holds for: {goal['text'][:150]}" if goal else "what this source holds") + \
            (f" (your senior was after: {wanted})" if wanted else "")
        name = os.path.splitext(os.path.basename(rel))[0]
        n = 1
        into = f"notes/{name}.md"
        while into in self.held or os.path.exists(os.path.join(self.senior.root, into)):
            n += 1
            into = f"notes/{name}-{n}.md"
        said = self.distill([rel], intent, into, "text")
        return (f"Your junior reads it first and keeps notes in {into}; they come to you between steps (read {rel} "
                f"yourself only for what the notes don't hold). " + said.split("\n")[0])

    def profile(self) -> str:
        """What the senior is told each step: the junior's measured load, and this project's size against it (Ian,
        2026-10-16: "We can make that work as a task protocol and limiter for Sr. Now it knows what Jr can handle")."""
        lim = self.limits()
        if not lim["measured"]:
            return (f"Your junior isn't measured on this card yet (the Benchmark measures it): keep its tasks to about "
                    f"{lim['lines']} lines of code.")
        line = (f"Your junior, measured on this card: up to {lim['lines']:,} lines of code and {lim['steps']} steps a "
                f"task; it kept a {lim['capacity']:,}-line project working. Size each task to that.")
        size = project_lines(self.senior.root)
        if lim["capacity"] and size > lim["capacity"]:
            line += (f" This project is {size:,} lines, past what it held: give it one file at a time with exactly what "
                     "it needs from the rest (names, signatures), and check its work closely.")
        return line

    def limits(self) -> dict:
        """The junior's per-task limits: measured by the Benchmark's coding run for its model on this card, else the
        stand-ins (inference/benchmark.py)."""
        from cin_minai.inference import benchmark
        f = getattr(self.junior, "model_file", "")
        return (benchmark.coding_limits(f, getattr(self.junior, "card", "")) if f else
                {"lines": benchmark.JUNIOR_LINES, "steps": benchmark.JUNIOR_STEPS, "measured": False})

    def review(self, n: int, accept: bool, note: str = "") -> str:
        """The Senior's word on a finished task: accepted, or back to the Junior with the note."""
        table = self.engine.get(n)
        s = spec_of(table)
        if not table or table.get("assignee") != self.second or not s or table["status"] != "done":
            return f"error: task {n} isn't finished (or doesn't exist)"
        done = {"path": s.get("rel", ""), "task": self.instruction(table), "kind": s.get("kind", "write")}
        verdict = "accepted" if accept else "rejected"
        try:
            self.engine.db.update_task(n, "done", agent_name=self.lead, result=json.dumps(
                {"model": self.models[self.lead], "verdict": verdict, "note": note[:300]}, ensure_ascii=False))
        except Exception:
            pass
        self.senior.event("handoff", by="senior", to="junior", text=f"task {n} {verdict}" + (f": {note}" if note else ""))
        if accept:
            return f"task {n} accepted"
        if s.get("attempt", 1) >= 2 and done["path"]:  # its correction attempt was rejected: the senior's now
            self.taken_over.add(done["path"])
            return (f"task {n} was your junior's correction attempt and it's rejected: the corrections to "
                    f"{done['path']} are yours now — make them yourself (edit or replace_lines); the file is free")
        said = self.assign(done["path"], f"Correction of task {n} — your senior's corrections: {note}\n"
                                         f"The task was: {done['task']}", done["kind"], attempt=2,
                           also=[f for f in s.get("hold", []) if f != done["path"]] or None)
        return said if said.startswith("error") else said + " This is its one correction attempt; after it, they're yours."

    # --- the Junior ------------------------------------------------------------------------------------------
    def claim(self) -> dict | None:
        """The next task, claimed and marked as the worker's in one step (settle() never answers it too)."""
        with self.lock:
            try:
                task = self.engine.claim(self.second)
            except Exception:
                task = None
            self.delivering = task["id"] if task else 0
            return task

    def work_queue(self) -> None:
        """The Junior's next task, claimed from the table (the person's requests first, then oldest), one at a time;
        after IDLE seconds with none, the worker ends (the next task starts it again)."""
        idle = time.monotonic()
        while True:
            table = self.claim()
            if table is None:
                self.settle()
                if time.monotonic() - idle < IDLE:
                    time.sleep(0.2)
                    continue
                with self.lock:  # once more under the lock: a task queued just now isn't left without a worker
                    table = self.claim()
                    if table is None:
                        self.worker = None
                        return
            s = spec_of(table)
            n, rel, kind = table["id"], s.get("rel", ""), s.get("kind", "write")
            task = self.instruction(table)
            try:
                if self.halted(table):
                    result = "not done: stopped by the person"
                elif kind == "distill":
                    result = self.run_distill(n, rel, task, table)
                elif kind == "brief":
                    result = self.run_brief(n, task, table)
                elif kind == "goal":
                    spec = json.loads(task)
                    result = self.run_task(n, ", ".join(spec["files"]) or f"goal {spec['goal']}", spec["text"], kind,
                                           table, files=spec["files"])
                else:
                    result = self.run_task(n, rel, task, kind, table, files=s.get("hold") or None)
            except Exception as e:  # a failing task never stops the Senior
                result = f"error: the junior couldn't do it ({type(e).__name__})"
            if self.engine.state(n) == "in_progress":  # closed on the table whatever happened: its files are free
                try:
                    self.engine.finish(table, self.second, self.models[self.second], "not done", result)
                    self.engine.claim(self.lead)
                except Exception:
                    pass
            self.owed.pop(n, None)
            self.senior.inbox.append((n, "task", result))
            self.delivering = 0
            self.show()
            idle = time.monotonic()

    def run_distill(self, n: int, rel: str, spec: str, table: dict | None) -> str:
        s = json.loads(spec)
        self.current, self.current_table = ({rel} if rel else set()), table
        try:
            got = self.junior.distill_now(s["sources"], s["intent"], s["into"], s["format"])
        finally:
            self.current, self.current_table = set(), None
        result = f"task {n} (distill, by your junior) — {got}"
        if table is not None and self.engine is not None:
            try:
                self.engine.finish(table, self.second, self.models[self.second],
                                   "not done" if got.startswith(("error", "not done")) else "distilled", result)
                self.engine.claim(self.lead)
            except Exception:
                pass
        return result

    def verified(self, changes: list[dict]) -> str:
        """What the task changed and whether the program still starts, by AICUI, for the Senior to judge from in one
        step (2026-10-25: Haiku 5.5 re-checked each result by hand, compile, start, read, search, ~20 of its 38 paid
        calls on test16)."""
        log = self.junior.log
        diff = "\n".join(log.diff(c) for c in changes if hasattr(log, "diff"))
        diff = "\n".join(line for line in diff.splitlines() if not line.startswith(("diff --git", "index ")))
        if len(diff) > DIFF_CHARS:
            diff = diff[:DIFF_CHARS] + f"\n… ({len(diff) - DIFF_CHARS:,} more characters: read the file for the rest)"
        out = "\nWhat changed:\n" + (diff.strip() or "(no difference)")
        from .agent import entry_point
        entry = entry_point(self.junior.root)
        if entry and not entry.endswith((".html", ".htm")) and callable(getattr(self.junior, "execute", None)):
            how = f"./{entry}" if entry.endswith(".sh") else f"python3 {entry}"
            code, printed = self.junior.execute(f"timeout 5 {how}", 30, self.junior.bwrap)
            out += (f"\nStarted by AICUI ({entry}, 5 s): " + ("still running after 5 s" if code == 124 else
                    "finished" if code == 0 else f"STOPPED (exit {code})\n" + (printed or "")[-600:]))
        return out

    def run_task(self, n: int, rel: str, task: str, kind: str, table: dict | None, files: list | None = None) -> str:
        self.current = set() if kind == "test" else set(files) if files is not None else {rel}
        self.current_table = table
        before = len(self.junior.log.entries()) if hasattr(self.junior.log, "entries") else 0
        self.running = {"n": n, "what": f"{kind} {rel}", "since": getattr(self.senior, "progress_total", 0),
                        "log0": before, "kinds": 0}
        notes = self.pending_notes.pop(n, [])
        if notes:
            task += "\nYour senior adds: " + " ".join(notes)
        may = ("Change no file: run what's needed and report what works and what fails, with the errors as they "
               "were printed." if kind == "test" else f"You may change only {', '.join(sorted(self.current))}.")
        if kind == "fix":  # Ian, 2026-10-25: "the Senior reads, assigns edits, then the junior does them and verifies
            # the edits before dumping and moving on" (on test16 every whole-file rewrite stalled; small edits all held)
            may += ("\nThis is a fix: change only the lines your senior named, with edit or replace_lines (read them "
                    "first) — never rewrite the whole file. Then verify: compile it (python3 -m py_compile for Python), "
                    "start the program for a few seconds if it has one (timeout 5), and read the changed lines back. "
                    "Answer with what you changed (file:lines) and what each check showed.")
        lim = self.limits()
        may += (f"\nThis task's limits: {lim['steps']} steps" + ("" if kind == "test" else
                f", {lim['lines']} lines of code written or changed") + ("" if lim["measured"] else
                " (not measured for this model yet)") + ". At a limit, answer with what's done and what's left.")
        # every task starts fresh: only its instruction, nothing from earlier tasks (Ian, 2026-10-15: "dumping context
        # from task to task, only keeping what it needs for its specific detailed instruction from senior")
        self.junior.history = []
        self.junior.__dict__.pop("resumed", None)
        self.junior.task_lines, self.junior.line_limit = 0, (0 if kind == "test" else lim["lines"])
        steps_were, self.junior.max_steps = self.junior.max_steps, lim["steps"]
        self.junior.edits_only = kind == "fix"
        try:
            said = self.junior.work(f"[{kind}] Task {n} from your senior: {task}\n{may}", self.stop_junior)
        finally:
            self.current, self.current_table, self.running = set(), None, None
            self.junior.inbox.clear()
            self.junior.max_steps, self.junior.line_limit = steps_were, 0
            self.junior.edits_only = False
            self.junior.history = []  # accepted or not, the next task starts fresh
        changes = self.junior.log.entries()[before:] if hasattr(self.junior.log, "entries") else []
        changed = sorted({c.get("file", "") for c in changes} - {""})
        found = [p for p in self.senior.problems() if any(p.startswith(f + ":") for f in (files or [rel]))]
        ended = getattr(self.junior, "stopped", "")
        verdict = {"answer": "done", "ask": "asks the senior"}.get(ended, ended or "done")
        checks = "\nThe checks on " + rel + ": " + ("; ".join(found) or "nothing found")
        if changes and kind in ("fix", "write"):
            checks += self.verified(changes)
        if ended in ("stuck", "limit", "error", "ask"):  # its stuck point goes up (Ian: "gets stuck, sends to sr…")
            last = [s for s in getattr(self.junior, "steps", []) if isinstance(s, dict) and s.get("did")][-3:]
            trail = "\n".join(f"- {s['did'].get('thinking', '')[:200]} → {str(s.get('result', ''))[:200]}" for s in last)
            result = (f"task {n} ({kind} {rel}) — STUCK POINT from your junior ({verdict}). It said: {said[:700]}\n"
                      f"Its last steps:\n{trail or '(none)'}\nChanged: " + (", ".join(changed) or "nothing") + checks
                      + "\nDistill its next step: a smaller, exact task (assign, naming the lines or the function and "
                      "what's wrong) — or patch this one mechanism yourself.")
        elif ended == "stopped":
            result = f"task {n} ({kind} {rel}) — not done: stopped by the person."
        else:
            result = (f"task {n} ({kind} {rel}) — {verdict}. It said: {said[:900]}\nChanged: "
                      + (", ".join(changed) or "nothing") + checks + "\nAccept it, or send it back, with review_task.")
        if table is not None and self.engine is not None:
            try:
                self.engine.finish(table, self.second, self.models[self.second], verdict, result)
                self.engine.claim(self.lead)
            except Exception:
                pass
        return result


class Crew:
    """The cloud leads; two local contributors work for it (Ian, 2026-10-12: "turn the 2 local models into tool calls
    locally to conserve tokens. Fetch this, write that, test this, correct that with this."). The coder (the bigger
    local model) writes, fixes, checks and tests; the reader (the faster one) fetches, distills and briefs; Large File
    Distillation is theirs, from both ends. Each is a Pair with the same lead: one numbering, one listing at Stop, and
    each task, question and review goes to the one that holds it."""

    def __init__(self, lead, coder, reader, say=print, engine=False) -> None:
        if engine is False:
            engine = engine_mod.team_engine(project_of(lead.root), lead.root)
        self.lead, self.say = lead, say
        # each contributor its own queue on the table; task numbers are the table's, so they never collide
        self.reader = Pair(lead, reader, say, engine, name="reader")
        self.coder = Pair(lead, coder, say, engine, name="coder")  # second: the lead's hooks are the coder's, set below
        self.reader.question_numbers = self.coder.question_numbers
        self.reader.request_root = self.coder.request_root  # the reader's tasks belong to the request the lead works
        self.pairs = (self.coder, self.reader)
        for p in self.pairs:
            p.show = self.show
        lead.inbox = []
        lead.junior_profile = lambda: " ".join(f"({p.junior.model_name}) {p.profile()}" for p in self.pairs)
        lead.errands_pending = lambda: self.out > 0
        lead.assign_fn = self.coder.assign
        lead.distiller = self.reader.distill
        lead.first_reader = self.reader.first_read
        lead.brief_fn = self.reader.brief
        lead.planned = self.coder.release_goals
        lead.each_step = self.between_steps
        lead.follow_up_fn = lambda n, note: self.holder(n).follow_up(n, note)
        lead.review_task_fn = lambda n, accept, note="": self.holder(n).review(n, accept, note)
        lead.permit_fn = lambda n, allow: next((p for p in self.pairs if n in p.questions), self.coder).permit(n, allow)
        lead.lfd_fn = lambda focus: self.coder.lfd(focus, ends=(coder, reader))
        lead.may_write = lambda rel: self.coder.senior_may_write(rel) or self.reader.senior_may_write(rel)

    @property
    def out(self) -> int:
        return sum(p.out for p in self.pairs)

    def holder(self, n: int) -> Pair:
        """The contributor with task n: the one it's assigned to on the table."""
        who = (self.coder.engine.get(n) or {}).get("assignee")
        return next((p for p in self.pairs if p.second == who), self.coder)

    def show(self) -> None:
        out = [x for p in self.pairs for x in p.listing.values()]
        self.lead.event("errands", out=sorted(out, key=lambda x: x["n"]))

    def between_steps(self) -> None:
        self.coder.release_goals()
        for p in self.pairs:
            p.check_in()

    def turn(self, request: str, cancel: threading.Event | None = None) -> str:
        cancel = cancel or threading.Event()
        if self.reader.out == 0:
            self.reader.stop_junior.clear()
        try:  # the lead works the request; the coder's Pair keeps it on the Team Table (the reader's tasks go by Stop)
            return self.coder.turn(request, cancel)
        except BaseException:
            self.reader.stopped()
            raise
        finally:
            if cancel.is_set():
                self.reader.stopped()

    def stopped(self) -> None:
        for p in self.pairs:
            p.stopped()


DETAIL_WORDS = 20  # a write or fix task names the code specifics (Ian, 2026-10-15: "Sr gives detail on code specifics")
DIFF_CHARS = 2500  # a result's diff for the Senior: enough for a fix, a pointer to the file beyond it
TASK_SHARE = 0.05  # D95: a task is at most 5 % of the receiving model's context
FOLLOW_UP = 3   # the Senior's steps of progress while a task is with the Junior before a word on how it's going
TEAM = os.path.join(".cinminai", "team.json")   # {"team": "solo" | "A" | "B"} — chosen in AICUI's top bar
TEAMS = ("solo", "A", "B", "table")             # solo: one local model, the coder alone (Ian, 2026-10-14);
#   table: the Team Table, the seats the person set (conference.py)
JUNIOR_FILE = "Qwen3.5-9B-Q4_K_M.gguf"          # the 9B coder, whole on the card
SENIOR_FILE = "Qwen3.6-35B-A3B-Q4_K_M.gguf"     # the MoE Senior, its experts in RAM (Flash-Next comes second)


CODE_EXT = {".py", ".js", ".ts", ".html", ".css", ".c", ".cc", ".cpp", ".h", ".hpp", ".rs", ".go", ".java", ".sh"}


def project_lines(root: str) -> int:
    """The project's own code, in lines (not what came in from outside, not AICUI's folders)."""
    from . import intake
    from .project import tree
    total = 0
    for rel, is_dir, _ in tree(root):
        if is_dir or os.path.splitext(rel)[1].lower() not in CODE_EXT or intake.came_in(root, rel):
            continue
        try:
            with open(os.path.join(root, rel), encoding="utf-8", errors="replace") as f:
                total += sum(1 for line in f if line.strip())
        except OSError:
            pass
    return total


def team_of(root: str) -> str:
    try:
        with open(os.path.join(root, TEAM), encoding="utf-8") as f:
            team = json.load(f).get("team")
            return team if team in TEAMS else "A"
    except (OSError, ValueError):
        return "A"


def pair_backends(say=print):
    """The two models of style B, placed together (matcher.pair_plan): the Junior whole on the card, loaded first; the
    Senior beside it, with its picture reader when that's in the model store. (senior, senior_name, junior,
    junior_name, reads_pictures); RuntimeError with the reason when a model is missing or the pair doesn't fit."""
    import time

    from cin_minai.daemon import config
    from cin_minai.daemon.models import CODING_DRAFT, ModelStore, backend_cfg
    from cin_minai.inference import matcher
    from cin_minai.inference.llamacpp import LlamaCppBackend

    from .agent import unload_guide
    store = ModelStore()
    models = {m.file: m for ms in matcher.CATALOG.values() for m in ms}
    junior, senior = models.get(JUNIOR_FILE), models.get(SENIOR_FILE)
    missing = [f for f in (JUNIOR_FILE, SENIOR_FILE) if not store.has(f)]
    if missing or junior is None or senior is None:
        raise RuntimeError("team B needs " + " and ".join(missing or [JUNIOR_FILE, SENIOR_FILE]) +
                           " in the model store (the Models view brings them in)")
    unload_guide()
    machine = matcher.read_machine(models_dir=store.root)
    from cin_minai.inference import contextfit
    prefs = contextfit.load()  # the sizes the person chose (AICUI's Context button): the Junior first, the Senior second
    from cin_minai.inference import benchmark
    sizes, plan = contextfit.fit_pair(junior, senior, machine, prefs)
    key = benchmark.setup_key([JUNIOR_FILE, SENIOR_FILE], benchmark.card_of(machine))
    kept, why = benchmark.cap(list(sizes), key)
    if why:  # sizes that failed here when measured (the Benchmark button, or a crash at work) aren't used again
        say(f"\033[33m{why}: {kept[0] // 1024}K and {kept[1] // 1024}K.\033[0m")
        sizes, plan = tuple(kept), matcher.pair_plan(junior, senior, machine, *kept)
    if plan is None and prefs["choice"] != "default":
        say(f"\033[33m{sizes[0] // 1024}K and {sizes[1] // 1024}K of context don't fit this computer together; "
            "the sizes Cin-MinAI picks instead.\033[0m")
        plan = matcher.pair_plan(junior, senior, machine)
    if plan is None:
        raise RuntimeError("the two models don't fit this computer together (the card, or the RAM for the experts)")
    log_path = os.path.join(os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache"), "cinminai",
                            "code-server.log")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)

    def log(msg: str) -> None:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")
    base = config.load()["inference"]
    jcfg = backend_cfg(base, plan["junior"], store.path(JUNIOR_FILE))
    jcfg["socket_name"], jcfg["draft"] = "llama-code.sock", CODING_DRAFT
    scfg = backend_cfg(base, plan["senior"], store.path(SENIOR_FILE))
    scfg["socket_name"], scfg["draft"] = "llama-senior.sock", CODING_DRAFT
    projector = matcher.PROJECTORS.get(SENIOR_FILE)
    sees = bool(projector and store.has(projector.file))
    if sees:  # looks: the Senior answers the picture question (kept off the card: room is the Junior's)
        scfg["extra_args"] = list(scfg.get("extra_args", [])) + ["--mmproj", store.path(projector.file),
                                                                 "--no-mmproj-offload"]
    for who in ("junior", "senior"):
        p = plan[who]
        log(f"team B {who}: {p['model']} | {p['mode']} | {' '.join(p.get('args', []))}")
    say(f"\033[2mTeam B: {plan['senior']['model']} (Senior, {plan['senior']['context'] // 1024}K context, "
        f"{plan['senior']['mode']}) and {plan['junior']['model']} (Junior, {plan['junior']['context'] // 1024}K "
        f"context, {plan['junior']['mode']}), loading…\033[0m")
    jcfg["fallback_context"] = scfg["fallback_context"] = contextfit.DEFAULT  # a crash steps down to 32K, not 4K
    jb = LlamaCppBackend(jcfg, log)
    sb = LlamaCppBackend(scfg, log)
    from .agent import crash_recorder
    jb.on_crash = sb.on_crash = crash_recorder([JUNIOR_FILE, SENIOR_FILE], machine)
    jb.model_file, jb.card = JUNIOR_FILE, benchmark.card_of(machine)  # the junior's measured limits (benchmark.py)
    sb.model_file, sb.card = SENIOR_FILE, benchmark.card_of(machine)
    jb.chat([{"role": "user", "content": "ok"}], max_tokens=1)  # the Junior first: it's placed whole on the card
    return sb, plan["senior"]["model"], jb, plan["junior"]["model"], sees
