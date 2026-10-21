# SPDX-License-Identifier: GPL-3.0-or-later
"""Two models on one project — style A of the two cards (PLAN §1b, SPEC §22.5; D94-D96): the coder holds the Senior
card, the guide (the 4B, on the processor) the Junior card, as an errand intern. Ian, 2026-10-09: "4b is an
assistant and doesnt have to be used, but will be used when it will make things go faster."

The coder works the person's request with its own judgement and has the final word. It gives the Junior errands only
when it has other work meanwhile; they stack in the Junior's queue and run one at a time while the coder works, and
each answer reaches the coder between its steps (before it finishes, it waits for any still out):

* **read** — a long file (a kept page, a document) read in parts for one question; the answer is kept under
  `.cinminai/helper/` and the coder gets its beginning and where the rest is.
* **look** — the program looked at (look.py), the question answered.
* **review** — before a goal is ticked, the Junior says whether the facts cover every part of it: a flag for the
  coder, who decides (a second goal_done ticks it); the person is above both.

Every request is the coder's task on the Team Table, every Junior job a child task with its verdict; the chat shows
each exchange. **Stop works on the table's tokens** (Ian, 2026-10-09: "It falls back to team tables tokens. Stop
both or just one?"): every errand is a task from the moment it's queued; at Stop, AICUI lists them with their session
goals and the person stops both, the coder only (the errands go on; their answers come at the next request), or the
helper only (its tasks are cancelled on the table, the coder goes on). The helper obeys the table: a cancelled task is
skipped, or stopped between its parts — from AICUI or from the sidebar's Requests view alike.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time

from cin_minai import engine as engine_mod

from .project import token_of

JUNIOR_CONTEXT = 8192
PART_CHARS = 9000        # what the helper reads at a time (its 8K context holds a part, the question and its answer)
MAX_PARTS = 24           # a file longer than this many parts is read from its start (the helper says so)
KEEP = os.path.join(".cinminai", "keep-errands")   # AICUI: Stop the coder only — the errands go on
HALT = os.path.join(".cinminai", "stop-errands")   # AICUI: Stop the helper only (when the table can't be reached)
ERRAND = "errand "  # a queued errand's description on the table: {"kind", "source", "question", "goal"} as JSON
IDLE = 5.0          # seconds the helper's worker waits for a new errand before it ends

READ = """You read part {n} of {total} of the file {source} for the coding model. Answer only from this part: {question}
Copy names and numbers exactly as they are here. If this part has nothing for the question, answer: nothing here."""

REVIEW = """You review whether a session goal is met, from facts code collected: the goal, the checks' results, the
project's files and its tests. Say covered only when every part the goal names is shown by these facts. If a part
isn't (a feature, a kind of data, files the goal promises), name it in one sentence with what's missing. Don't judge
style or ask for more than the goal says."""

REVIEW_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["covered", "missing"], "properties": {
    "covered": {"type": "boolean"}, "missing": {"type": "string", "maxLength": 300}}}


def errand_of(task: dict | None) -> dict:
    """What the coder wrote on a queued errand (empty for a job run on the spot)."""
    d = (task or {}).get("description") or ""
    if not d.startswith(ERRAND):
        return {}
    try:
        got = json.loads(d[len(ERRAND):].split("\n", 1)[0])
    except ValueError:
        return {}
    return got if isinstance(got, dict) else {}


class Tandem:
    """The coder (agent: the Agent) leads; the helper (junior: chat(messages, schema=, max_tokens=, cancel=) ->
    (text, timings)) takes the jobs above. engine: the Team Table (opened for the project when not given). The table is
    the backbone (Ian, 2026-10-21): the helper claims its errands from it, an errand's number is its number there, and
    the table's refusals reach the coder; without the table there's no tandem (the coder works alone and says why)."""

    def __init__(self, agent, junior, say=print, engine=False, junior_model: str = "Cin-MinAI guide",
                 where: str = "local") -> None:
        self.agent, self.junior, self.say = agent, junior, say
        if engine is False:
            project = token_of(agent.root) or hashlib.sha1(os.path.realpath(agent.root).encode()).hexdigest()
            engine = engine_mod.team_engine(project, agent.root)
        if engine is None:
            raise RuntimeError("the tandem works through the Team Table, and there's none here")
        self.engine = engine
        self.lead = engine.member("coder", agent.ctx, getattr(agent, "model_name", ""), where)
        self.helper_name = engine.member("helper", JUNIOR_CONTEXT, junior_model, "local")
        self.models = {self.lead: getattr(agent, "model_name", ""), self.helper_name: junior_model}
        self.root: dict | None = None
        self.cancel: threading.Event | None = None
        self.lock = threading.RLock()  # the worker's claim and settle() take it, also from within each other
        self.worker: threading.Thread | None = None
        self.delivering = 0                          # the errand claimed, until its answer is in the coder's inbox
        self.owed: dict[int, str] = {}               # errands given and not answered yet: id -> kind
        self.errand_stop = threading.Event()         # the errands' own stop (Stop may leave them running)
        agent.inbox = []                             # answers waiting for the coder's next step
        agent.errand = self.errand                   # the coder's errand tool
        agent.errands_pending = lambda: self.out > 0
        agent.reviewer = self.review_goal

    # --- the helper's queue, as the table holds it -------------------------------------------------------------
    def open_errands(self) -> list[dict]:
        try:
            return [t for t in self.engine.open_for(self.helper_name) if errand_of(t)]
        except Exception:
            return []

    def settle(self) -> None:
        """An errand stopped on the table before the helper started it (Stop, or the Requests view) is answered all the
        same: the coder hears it wasn't done."""
        with self.lock:  # never the errand the worker has claimed: that one is answered by the worker
            for n, kind in list(self.owed.items()):
                if n != self.delivering and self.engine.state(n) == "cancelled":
                    self.owed.pop(n, None)
                    self.agent.inbox.append((n, kind, "not done: stopped by the person"))

    @property
    def out(self) -> int:
        """Errands not answered yet: open on the table, and the one whose answer is on its way."""
        self.settle()
        return len({t["id"] for t in self.open_errands()} | ({self.delivering} if self.delivering else set()))

    @property
    def listing(self) -> dict[int, dict]:
        """The errands out, as AICUI lists them at Stop."""
        return {t["id"]: {"n": t["id"], "what": t["title"], "goal": errand_of(t).get("goal", ""), "task": t["id"]}
                for t in self.open_errands()}

    def request_root(self) -> dict:
        """The request an errand belongs to (the coder's work between requests gets one of its own)."""
        if self.root is None or self.engine.state(self.root["id"]) in ("done", "cancelled", "blocked"):
            self.root = self.engine.request("(the coder's own work, between requests)", self.lead)
        return self.root

    # --- one request: the coder's ----------------------------------------------------------------------------
    def turn(self, request: str, cancel: threading.Event | None = None) -> str:
        self.cancel = cancel or threading.Event()
        self.root = None
        if self.out == 0:
            self.errand_stop.clear()
        try:
            self.root = self.engine.request(request, self.lead)
        except Exception as e:  # the tandem works through the table: without the request on it, nothing starts
            said = f"The Team Table couldn't take this request ({str(e)[:200]}), so the work didn't start."
            self.agent.event("answer", text=said)
            return said
        try:
            out = self.agent.turn(request, self.cancel)
        except BaseException:  # Stop (Ctrl+C) or a failure: the coder's part ends; errands as the person chose
            self.stopped()
            raise
        if self.cancel.is_set():
            self.stopped()
        else:
            ended = getattr(self.agent, "stopped", "")
            verdict = {"answer": "done", "ask": "asks the person", "declined": "declined"}.get(ended, ended or "done")
            self.close(out, verdict)
        return out

    def close(self, text: str, verdict: str) -> None:
        if self.root:
            state = "done" if verdict == "done" else "blocked"
            try:
                self.engine.finish(self.root, self.lead, self.models[self.lead], verdict, text, state)
            except Exception:
                pass

    def stopped(self) -> None:
        """Stop: errands still out keep going if the person chose so at Stop (AICUI's question); else all ends."""
        keep = os.path.join(self.agent.root, KEEP)
        kept = os.path.exists(keep)
        if kept:
            try:
                os.remove(keep)
            except OSError:
                pass
        if kept and self.out > 0:
            self.close("stopped by the person; the helper's errands go on in the background", "stopped")
            self.agent.event("note", text="Stopped. Your helper's errands go on in the background; their answers come "
                                          "at your next request.")
            return
        self.errand_stop.set()
        self.close_cancelled()

    def show_errands(self) -> None:
        """What the helper has out, for AICUI's question at Stop."""
        self.agent.event("errands", out=sorted(self.listing.values(), key=lambda x: x["n"]))

    def close_cancelled(self) -> None:
        for root in {t["root_id"] for t in self.open_errands() if t.get("root_id")} | ({self.root["id"]} if self.root
                                                                                      else set()):
            try:  # every request the helper has errands from, not only this one
                self.engine.cancel(root)
            except Exception:
                pass
        self.settle()

    # --- the helper's jobs, each a child task on the table ---------------------------------------------------
    def errand(self, kind: str, source: str, question: str, goal: int | None = None) -> str:
        """The coder's errand tool: queued for the Junior, answered between the coder's steps."""
        if kind not in ("read", "look"):
            return "error: an errand is read (a long file, for a question) or look (the program, for a question)"
        if not question.strip():
            return "error: give the errand a question"
        if kind == "read":
            full = os.path.realpath(os.path.join(self.agent.root, source))
            if not full.startswith(os.path.realpath(self.agent.root) + os.sep) or not os.path.isfile(full):
                return f"error: {source} isn't a file in the project"
        goals = self.agent.goals.load()
        g = next((x for x in goals if x["id"] == goal), None) or next((x for x in goals if not x["done"]), None)
        what = f"{kind} {source}: {question}"[:200] if kind == "read" else f"look at the program: {question}"[:200]
        towards = f"goal {g['id']}: {g['text'][:120]}" if g else "no session goal"
        spec = ERRAND + json.dumps({"kind": kind, "source": source, "question": question, "goal": towards},
                                   ensure_ascii=False)
        try:  # a token on the table from now: the person can stop it; the table may refuse it (budget, size)
            task = self.engine.order(self.request_root()["id"], self.lead, self.helper_name, what, spec, kind)
        except Exception as e:
            return f"error: the Team Table refused this errand: {str(e)[:300]}"
        n = task["id"]
        self.owed[n] = kind
        self.show_errands()
        with self.lock:
            if self.worker is None or not self.worker.is_alive():
                self.worker = threading.Thread(target=self.work_queue, daemon=True)
                self.worker.start()
        return (f"errand {n} given to your helper ({kind}{' ' + source if kind == 'read' else ''}: {question}); its "
                "answer comes between your steps — go on with other work meanwhile.")

    def claim(self) -> dict | None:
        """The next errand, claimed and marked as the worker's in one step (settle() never answers it too)."""
        with self.lock:
            try:
                task = self.engine.claim(self.helper_name)
            except Exception:
                task = None
            self.delivering = task["id"] if task else 0
            return task

    def work_queue(self) -> None:
        """The Junior: its next errand claimed from the table, one at a time, while the coder works; after IDLE
        seconds with none, the worker ends (the next errand starts it again)."""
        idle = time.monotonic()
        while True:
            task = self.claim()
            if task is None:
                self.settle()
                if time.monotonic() - idle < IDLE:
                    time.sleep(0.2)
                    continue
                with self.lock:  # once more under the lock: an errand given just now isn't left without a worker
                    task = self.claim()
                    if task is None:
                        self.worker = None
                        return
            e = errand_of(task)
            if not e:  # a job the coder runs right now (a goal's review): its own, not the queue's
                self.delivering = 0
                continue
            n, kind, source, question = task["id"], e.get("kind", "read"), e.get("source", ""), e.get("question", "")
            try:
                if self.halted(task):
                    result = "not done: stopped by the person"
                    self.agent.event("handoff", by="helper", to="coder", text=f"errand {n}: {result}")
                elif kind == "read":
                    result = self.read(source, question, task=task)
                else:
                    result = self.job("look", f"look at the program: {question}"[:200], question,
                                      lambda: (self.agent.look("program", question, ""), "looked"), task=task)
            except Exception as e:  # a failing errand never stops the coder
                result = f"error: the helper couldn't do it ({type(e).__name__})"
            if self.engine.state(n) == "in_progress":  # closed on the table whatever happened
                try:
                    self.engine.finish(task, self.helper_name, self.models[self.helper_name], "not done", result)
                except Exception:
                    pass
            self.owed.pop(n, None)
            self.agent.inbox.append((n, kind, result))
            self.delivering = 0
            self.show_errands()
            idle = time.monotonic()

    def halted(self, task: dict | None) -> bool:
        """Is this errand stopped — all of the helper's work (Stop both, or the helper only), or its own token?"""
        halt = os.path.join(self.agent.root, HALT)
        if os.path.exists(halt):
            try:
                os.remove(halt)
            except OSError:
                pass
            self.errand_stop.set()
        if self.errand_stop.is_set():
            return True
        if task is not None:
            try:
                return self.engine.state(task["id"]) == "cancelled"
            except Exception:
                return False
        return False

    def job(self, kind: str, title: str, text: str, run, root: dict | None = None, task: dict | None = None) -> str:
        """Run a Junior job — its task given (an errand, queued earlier) or made now under the request: run() ->
        (result, verdict)."""
        if task is None:  # a job run now: its own task, claimed by id (never the queue's next errand)
            try:
                root = root if root is not None else self.request_root()
                task = self.engine.order(root["id"], self.lead, self.helper_name, title, text, kind)
                self.engine.db.claim_task(task["id"], self.helper_name)
            except Exception as e:  # the table refused it (budget, size): said, and the job isn't run
                result = f"not done: the Team Table refused it ({str(e)[:200]})"
                self.agent.event("handoff", by="helper", to="coder", text=result)
                return result
        self.agent.event("handoff", by="coder", to="helper", text=title)
        try:
            result, verdict = run()
        except Exception as e:  # the helper failing never stops the coder
            result, verdict = f"error: the helper couldn't do it ({type(e).__name__}: {str(e)[:160]})", "error"
        if not self.halted(task):
            try:
                self.engine.finish(task, self.helper_name, self.models[self.helper_name], verdict, result)
                self.engine.claim(self.lead)  # the request again: its child is closed
            except Exception:
                pass
        self.agent.event("handoff", by="helper", to="coder", text=result[:300])
        return result

    def ask(self, system: str, user: str, schema: dict | None = None, max_tokens: int = 600,
            cancel: threading.Event | None = None) -> str:
        raw, _ = self.junior([{"role": "system", "content": system}, {"role": "user", "content": user}],
                             schema=schema, max_tokens=max_tokens, cancel=cancel or self.cancel)
        return str(raw)

    def read(self, source: str, question: str, root: dict | None = None, task: dict | None = None) -> str:
        """A read errand: the Junior reads a long file for one question, part by part; the answer is kept."""
        full = os.path.realpath(os.path.join(self.agent.root, source))
        base = os.path.realpath(self.agent.root)  # the project folder (root is the request)
        if not full.startswith(base + os.sep) or not os.path.isfile(full):
            return f"error: {source} isn't a file in the project"
        if not question.strip():
            return "error: ask the helper a question about the file"
        rel = os.path.relpath(full, base).replace(os.sep, "/")

        def run() -> tuple[str, str]:
            with open(full, encoding="utf-8", errors="replace") as f:
                text = f.read()
            parts = [text[i:i + PART_CHARS] for i in range(0, len(text), PART_CHARS)] or [""]
            cut = len(parts) > MAX_PARTS
            parts = parts[:MAX_PARTS]
            found = []
            for n, part in enumerate(parts, 1):
                if self.halted(task):  # stopped by the person, as a whole or this one token
                    break
                self.agent.event("helper", doing=f"reading {rel}, part {n} of {len(parts)}")  # not the coder's status
                said = self.ask(READ.format(n=n, total=len(parts), source=rel, question=question), part,
                                cancel=self.errand_stop).strip()
                if said and not said.lower().startswith("nothing here"):
                    found.append(f"## part {n}\n{said}")
            os.makedirs(os.path.join(base, ".cinminai", "helper"), exist_ok=True)
            kept = f".cinminai/helper/{time.strftime('%Y%m%d-%H%M%S')}.md"
            answer = "\n\n".join(found) or "nothing in the file answers it"
            with open(os.path.join(base, kept), "w", encoding="utf-8") as f:
                f.write(f"# {rel}: {question}\n\n{answer}\n")
            if self.halted(task):  # stopped while it read (between parts, or during the last one)
                return (f"not done: stopped by the person — what it found before is kept in {kept}" if found else
                        "not done: stopped by the person"), "stopped"
            note = f" (only its first {MAX_PARTS} parts: the file is longer)" if cut else ""
            return (f"the helper read {rel} in {len(parts)} parts{note} for: {question}\nIts answer is kept in {kept} "
                    f"({answer.count(chr(10)) + 1} lines); it begins:\n{answer[:1500]}"), "answered"
        return self.job("read", f"read {rel}: {question}"[:200], f"{rel}\n{question}", run, root, task)

    def review_goal(self, goal: dict, report: str) -> tuple[bool, str] | None:
        """Before a tick: do the facts cover every part of the goal? (2026-10-09: a goal for "the set's cards with
        card images" was ticked on 7 cards and no images, because its tests passed.) None: no answer, the checks
        decide."""
        from .project import tree
        files = [rel for rel, is_dir, _ in tree(self.agent.root)[:120] if not is_dir]
        tests = []
        for rel in files:
            if os.path.basename(rel).startswith("test_") and rel.endswith(".py"):
                try:
                    with open(os.path.join(self.agent.root, rel), encoding="utf-8", errors="replace") as f:
                        tests += [f"{rel}: {n}" for n in re.findall(r"^\s*def (test_\w+)", f.read(), re.M)]
                except OSError:
                    pass
        user = (f"The goal: {goal['text']}\n\nThe checks:\n{report[:1500]}\n\nThe project's files:\n"
                + "\n".join(files[:120]) + "\n\nIts tests:\n" + ("\n".join(tests[:60]) or "(none)"))
        verdict: list = []

        def run() -> tuple[str, str]:
            out = json.loads(self.ask(REVIEW, user, REVIEW_SCHEMA, 300))
            verdict.append((bool(out.get("covered")), str(out.get("missing", ""))))
            return ("covered" if verdict[0][0] else f"not covered yet — {verdict[0][1]}"), \
                ("covered" if verdict[0][0] else "not covered")
        self.job("review", f"review goal {goal['id']}: {goal['text']}"[:200], goal["text"], run)
        return verdict[0] if verdict else None


def guide_projector() -> str:
    """The guide's picture reader in the model store ("" when it isn't there)."""
    from cin_minai.daemon.models import ModelStore
    from cin_minai.inference import matcher
    proj = matcher.PROJECTORS.get(matcher.CATALOG["help"][0].file)
    store = ModelStore()
    return store.path(proj.file) if proj and store.has(proj.file) else ""


def reads_pictures() -> bool:
    try:
        return bool(guide_projector())
    except Exception:
        return False


def junior_backend(log=None):
    """The guide on the processor, beside the coding model on the card: its own server and socket; it never takes
    the card (the processor is its only rung). With its picture reader when that's here (look.py's questions)."""
    from cin_minai.daemon import config
    from cin_minai.inference.llamacpp import LlamaCppBackend
    cfg = dict(config.load()["inference"])
    if not cfg.get("model") or not os.path.isfile(cfg["model"]):
        return None
    projector = guide_projector()
    cfg.update(build="cpu", context=JUNIOR_CONTEXT, cpu_context=JUNIOR_CONTEXT, cache_type="q8_0",
               socket_name="llama-junior.sock", model_name="Cin-MinAI guide (helper)",
               extra_args=["--mmproj", projector, "--no-mmproj-offload"] if projector else [])
    return LlamaCppBackend(cfg, log or (lambda m: None))
