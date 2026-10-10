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
        self.count = 0
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
        if not os.path.isfile(full):
            return (f"error: {rel} doesn't exist yet — lay the skeleton first (the file with its imports, classes and "
                    "signatures, stubs marked TODO), then assign it")
        if rel in self.held:
            return f"error: {rel} is already held by task {self.held[rel]}"
        if len(task.strip()) < 8:
            return "error: say what the junior should do in this file"
        return self.queue(rel, task.strip(), kind, f"{kind} {rel}: {task.strip()}"[:200])

    def queue(self, rel: str, task: str, kind: str, what: str) -> str:
        goal = self.senior.goals.current()
        towards = f"goal {goal['id']}: {goal['text'][:120]}" if goal else "no session goal"
        table = None
        if self.engine is not None and self.root:
            try:
                table = self.engine.order(self.root["id"], self.lead, self.second, what, f"{what}\nfor {towards}",
                                          {"write": "write", "distill": "read"}.get(kind, "check"))
            except Exception:
                table = None
        with self.lock:
            self.count += 1
            self.out += 1
            n = self.count
            if rel:
                self.held[rel] = n
            self.listing[n] = {"n": n, "what": what, "goal": towards, "task": table["id"] if table else None}
        self.show()
        self.tasks.put((n, rel, task, kind, table))
        if self.worker is None or not self.worker.is_alive():
            self.worker = threading.Thread(target=self.work_queue, daemon=True)
            self.worker.start()
        self.senior.event("handoff", by="senior", to="junior", text=f"task {n}: {what}")
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

    def first_read(self, rel: str, url: str) -> str:
        """Ian, 2026-10-10: "Jr should do first reading and hand to senior and hold notes." A page or a PDF's text the
        Senior fetches goes to the Junior, which reads it for what the Senior was after (its thinking at that step and
        the goal) and keeps notes in notes/ — the source's own words, with where they stood; they come back between
        the Senior's steps."""
        goal = self.senior.goals.current()
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
                else:
                    result = self.run_task(n, rel, task, kind, table)
            except Exception as e:  # a failing task never stops the Senior
                result = f"error: the junior couldn't do it ({type(e).__name__})"
            with self.lock:
                self.held.pop(rel, None)
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

    def run_task(self, n: int, rel: str, task: str, kind: str, table: dict | None) -> str:
        if table is not None and self.engine is not None:
            try:
                self.engine.db.claim_task(table["id"], self.second)
            except Exception:
                pass
        self.current, self.current_table = {rel}, table
        before = len(self.junior.log.entries()) if hasattr(self.junior.log, "entries") else 0
        try:
            said = self.junior.work(f"[{kind}] Task {n} from your senior: {task}\nYou may change only {rel}.",
                                    self.stop_junior)
        finally:
            self.current, self.current_table = set(), None
        changes = self.junior.log.entries()[before:] if hasattr(self.junior.log, "entries") else []
        changed = sorted({c.get("file", "") for c in changes} - {""})
        found = [p for p in self.senior.problems() if p.startswith(rel + ":")]
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


TEAM = os.path.join(".cinminai", "team.json")   # {"team": "A" | "B"} — chosen in AICUI's top bar
JUNIOR_FILE = "Qwen3.5-9B-Q4_K_M.gguf"          # the 9B coder, whole on the card
SENIOR_FILE = "Qwen3.6-35B-A3B-Q4_K_M.gguf"     # the MoE Senior, its experts in RAM (Flash-Next comes second)


def team_of(root: str) -> str:
    try:
        with open(os.path.join(root, TEAM), encoding="utf-8") as f:
            return "B" if json.load(f).get("team") == "B" else "A"
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
    say(f"\033[2mTeam B: {plan['senior']['model']} (Senior, {plan['senior']['mode']}) and {plan['junior']['model']} "
        f"(Junior, {plan['junior']['mode']}), loading…\033[0m")
    jb = LlamaCppBackend(jcfg, log)
    jb.chat([{"role": "user", "content": "ok"}], max_tokens=1)  # the Junior first: it's placed whole on the card
    sb = LlamaCppBackend(scfg, log)
    return sb, plan["senior"]["model"], jb, plan["junior"]["model"], sees
