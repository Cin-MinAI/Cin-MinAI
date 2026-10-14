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
"""

from __future__ import annotations

import hashlib
import itertools
import json
import os
import queue
import threading

from cin_minai import engine as engine_mod

from .project import token_of

KEEP = os.path.join(".cinminai", "keep-errands")   # AICUI: Stop the Senior only — the Junior's tasks go on
HALT = os.path.join(".cinminai", "stop-errands")   # AICUI: Stop the Junior only (when the table can't be reached)


class Pair:
    """senior and junior: two Agents on the same project, each with its own model."""

    def __init__(self, senior, junior, say=print, engine=False, where: str = "local") -> None:
        self.senior, self.junior, self.say = senior, junior, say
        senior.role, junior.role = "senior", "junior"
        if engine is False:
            project = token_of(senior.root) or hashlib.sha1(os.path.realpath(senior.root).encode()).hexdigest()
            engine = engine_mod.open_engine(project, senior.root)
            if engine is not None:
                engine.close_stale()
        self.engine = engine
        self.lead, self.second = "senior", "junior"
        if engine is not None:
            self.lead = engine.member("senior", senior.ctx, getattr(senior, "model_name", ""), where)
            self.second = engine.member("junior", junior.ctx, getattr(junior, "model_name", ""), where)
        self.models = {self.lead: getattr(senior, "model_name", ""), self.second: getattr(junior, "model_name", "")}
        self.root: dict | None = None
        self.cancel: threading.Event | None = None
        self.tasks: queue.Queue = queue.Queue()     # the Junior's queue: tasks stack, done one at a time
        self.out = 0
        self.numbers = itertools.count(1)            # task numbers (a crew's contributors share them)
        self.question_numbers = itertools.count(1)   # the junior's questions, numbered the same way
        self.lock = threading.Lock()
        self.worker: threading.Thread | None = None
        self.listing: dict[int, dict] = {}           # tasks out, as AICUI lists them at Stop
        self.held: dict[str, int] = {}               # file -> the Junior task that holds it
        self.current: set[str] = set()               # the files of the task the Junior works now
        self.done: dict[int, dict] = {}              # finished tasks, for review_task
        self.stop_junior = threading.Event()
        senior.inbox = []
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
        if self.engine is not None:
            try:
                self.root = self.engine.request(request, self.lead)
            except Exception as e:  # the record failing never loses the request
                self.senior.event("note", text=f"The Team Table couldn't take this request ({str(e)[:160]}).")
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
        if self.engine is not None and self.root:
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
        if self.engine is not None and self.root:
            try:
                self.engine.cancel(self.root["id"])
            except Exception:
                pass

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
        if task is not None and self.engine is not None:
            try:
                return self.engine.state(task["id"]) == "cancelled"
            except Exception:
                return False
        return False

    def show(self) -> None:
        self.senior.event("errands", out=sorted(self.listing.values(), key=lambda x: x["n"]))

    # --- the Senior's tools ----------------------------------------------------------------------------------
    def assign(self, path: str, task: str, kind: str = "write") -> str:
        """One file for the Junior: it must exist (the skeleton first) and not be held already."""
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
        if not os.path.isfile(full):
            return (f"error: {rel} doesn't exist yet — lay the skeleton first (the file with its imports, classes and "
                    "signatures, stubs marked TODO), then assign it")
        if rel in self.held:
            return f"error: {rel} is already held by task {self.held[rel]}"
        if len(task.strip()) < 8:
            return "error: say what the junior should do in this file"
        return self.queue(rel, task.strip(), kind, f"{kind} {rel}: {task.strip()}"[:200])

    def queue(self, rel: str, task: str, kind: str, what: str, hold: list | None = None,
              goal: dict | None = None) -> str:
        goal = goal or self.senior.goals.current()
        towards = f"goal {goal['id']}: {goal['text'][:120]}" if goal else "no session goal"
        table = None
        if self.engine is not None and self.root:
            try:
                table = self.engine.order(self.root["id"], self.lead, self.second, what, f"{what}\nfor {towards}",
                                          {"write": "write", "distill": "read", "brief": "read"}.get(kind, "check"))
            except Exception:
                table = None
        with self.lock:
            self.out += 1
            n = next(self.numbers)
            for path in (hold if hold is not None else [rel] if rel else []):
                self.held[path] = n
            self.listing[n] = {"n": n, "what": what, "goal": towards, "task": table["id"] if table else None}
        self.show()
        self.tasks.put((n, rel, task, kind, table))
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

    def brief(self, files: list, question: str) -> str:
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
            "moving forward with plan — roles for you and your assistant; the open goals give way to it, the ticked ones "
            "stay — then work it.")
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
            if waiting:
                self.pending_notes.setdefault(n, []).append(note)
        if waiting:
            return f"task {n} hasn't started: your junior gets this with it"
        return f"error: task {n} isn't with your junior (finished, or never given) — give a new task with assign"

    def release_goals(self) -> None:
        """The plan's goals for the Junior (Ian, 2026-10-10): each goes to it once what it needs from outside is in,
        with its files held for it; one at a time per file. The Junior waits for these — it starts nothing itself."""
        for g in self.senior.goals.load():
            if g["done"] or g.get("who") != "junior" or g.get("queued") or not self.senior.needs_met(g):
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

    def review(self, n: int, accept: bool, note: str = "") -> str:
        """The Senior's word on a finished task: accepted, or back to the Junior with the note."""
        done = self.done.get(n)
        if not done:
            return f"error: task {n} isn't finished (or doesn't exist)"
        verdict = "accepted" if accept else "rejected"
        if done.get("table") is not None and self.engine is not None:
            try:
                self.engine.db.update_task(done["table"]["id"], "done", agent_name=self.lead, result=json.dumps(
                    {"model": self.models[self.lead], "verdict": verdict, "note": note[:300]}, ensure_ascii=False))
            except Exception:
                pass
        self.senior.event("handoff", by="senior", to="junior", text=f"task {n} {verdict}" + (f": {note}" if note else ""))
        if accept:
            return f"task {n} accepted"
        return self.assign(done["path"], f"Rework of task {n} — your senior's note: {note}\nThe task was: {done['task']}",
                           done["kind"])

    # --- the Junior ------------------------------------------------------------------------------------------
    def work_queue(self) -> None:
        while True:
            try:
                n, rel, task, kind, table = self.tasks.get(timeout=5)
            except queue.Empty:
                return
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
                    result = self.run_task(n, rel, task, kind, table)
            except Exception as e:  # a failing task never stops the Senior
                result = f"error: the junior couldn't do it ({type(e).__name__})"
            with self.lock:
                for path in [p for p, m in self.held.items() if m == n]:
                    self.held.pop(path, None)
                self.listing.pop(n, None)
                self.done[n] = {"path": rel, "task": task, "kind": kind, "table": table}
                self.out -= 1
            self.senior.inbox.append((n, "task", result))
            self.show()

    def run_distill(self, n: int, rel: str, spec: str, table: dict | None) -> str:
        s = json.loads(spec)
        if table is not None and self.engine is not None:
            try:
                self.engine.db.claim_task(table["id"], self.second)
            except Exception:
                pass
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

    def run_task(self, n: int, rel: str, task: str, kind: str, table: dict | None, files: list | None = None) -> str:
        if table is not None and self.engine is not None:
            try:
                self.engine.db.claim_task(table["id"], self.second)
            except Exception:
                pass
        self.current = set() if kind == "test" else set(files) if files is not None else {rel}
        self.current_table = table
        before = len(self.junior.log.entries()) if hasattr(self.junior.log, "entries") else 0
        self.running = {"n": n, "what": f"{kind} {rel}", "since": getattr(self.senior, "progress_total", 0),
                        "log0": before, "kinds": 0}
        notes = self.pending_notes.pop(n, [])
        if notes:
            task += "\nYour senior adds: " + " ".join(notes)
        may = ("Change no file: run what's needed and report what works and what fails, with the errors as they "
               "were printed." if kind == "test" else f"You may change only {rel}.")
        try:
            said = self.junior.work(f"[{kind}] Task {n} from your senior: {task}\n{may}", self.stop_junior)
        finally:
            self.current, self.current_table, self.running = set(), None, None
            self.junior.inbox.clear()
        changes = self.junior.log.entries()[before:] if hasattr(self.junior.log, "entries") else []
        changed = sorted({c.get("file", "") for c in changes} - {""})
        found = [p for p in self.senior.problems() if any(p.startswith(f + ":") for f in (files or [rel]))]
        ended = getattr(self.junior, "stopped", "")
        verdict = {"answer": "done", "ask": "asks the senior"}.get(ended, ended or "done")
        checks = "\nThe checks on " + rel + ": " + ("; ".join(found) or "nothing found")
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
            project = token_of(lead.root) or hashlib.sha1(os.path.realpath(lead.root).encode()).hexdigest()
            engine = engine_mod.open_engine(project, lead.root)
            if engine is not None:
                engine.close_stale()
        self.lead, self.say = lead, say
        self.reader = Pair(lead, reader, say, engine)
        self.coder = Pair(lead, coder, say, engine)   # second: the lead's own hooks are the coder's, then set below
        self.reader.numbers, self.reader.question_numbers = self.coder.numbers, self.coder.question_numbers
        self.pairs = (self.coder, self.reader)
        for p in self.pairs:
            p.show = self.show
        lead.inbox = []
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
        """The contributor with task n: working on it, waiting with it, or finished with it."""
        for p in self.pairs:
            if n in p.listing or n in p.done or (p.running and p.running["n"] == n):
                return p
        return self.coder

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


FOLLOW_UP = 3   # the Senior's steps of progress while a task is with the Junior before a word on how it's going
TEAM = os.path.join(".cinminai", "team.json")   # {"team": "solo" | "A" | "B"} — chosen in AICUI's top bar
TEAMS = ("solo", "A", "B")                      # solo: one local model, the coder alone (Ian, 2026-10-14)
JUNIOR_FILE = "Qwen3.5-9B-Q4_K_M.gguf"          # the 9B coder, whole on the card
SENIOR_FILE = "Qwen3.6-35B-A3B-Q4_K_M.gguf"     # the MoE Senior, its experts in RAM (Flash-Next comes second)


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
    from cin_minai.daemon.models import ModelStore, backend_cfg
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
    sizes, plan = contextfit.fit_pair(junior, senior, machine, prefs)
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
    jcfg["socket_name"] = "llama-code.sock"
    scfg = backend_cfg(base, plan["senior"], store.path(SENIOR_FILE))
    scfg["socket_name"] = "llama-senior.sock"
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
    jb = LlamaCppBackend(jcfg, log)
    jb.chat([{"role": "user", "content": "ok"}], max_tokens=1)  # the Junior first: it's placed whole on the card
    sb = LlamaCppBackend(scfg, log)
    return sb, plan["senior"]["model"], jb, plan["junior"]["model"], sees
