# SPDX-License-Identifier: GPL-3.0-or-later
"""Two models on one project, the coder leading (SPEC §22.5, PLAN D94-D96). Ian, 2026-10-09: "flip the tandem".

The coding model (on the graphics card) works the person's request with its own judgement, exactly as it does alone.
The guide (the 4B, on the processor) is its helper, for the jobs that would spend the coder's context or that need a
second model — never deciding what the coder does:

* **read** — a long file (a kept page, a document) read for one question, in parts; the answer is kept under
  `.cinminai/helper/` and the coder gets its beginning and where the rest is (the bulk stays out of its context:
  "more information per cubic unit").
* **review** — before a goal is ticked, a model other than the one that did the work says whether the facts cover
  every part of the goal (D94, D96).
* **pictures** — a look's one question (look.py), when the guide has its picture reader.

Every request is a task on the Team Table for the coder, every helper job a child task for the helper, with its
verdict; Stop cancels the tree (cin_minai.engine).
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

READ = """You read part {n} of {total} of the file {source} for the coding model. Answer only from this part: {question}
Copy names and numbers exactly as they are here. If this part has nothing for the question, answer: nothing here."""

REVIEW = """You review whether a session goal is met, from facts code collected: the goal, the checks' results, the
project's files and its tests. Say covered only when every part the goal names is shown by these facts. If a part
isn't (a feature, a kind of data, files the goal promises), name it in one sentence with what's missing. Don't judge
style or ask for more than the goal says."""

REVIEW_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["covered", "missing"], "properties": {
    "covered": {"type": "boolean"}, "missing": {"type": "string", "maxLength": 300}}}


class Tandem:
    """The coder (agent: the Agent) leads; the helper (junior: chat(messages, schema=, max_tokens=, cancel=) ->
    (text, timings)) takes the jobs above. engine: the Team Table (opened for the project when not given; None when
    it can't be — the work goes on unrecorded)."""

    def __init__(self, agent, junior, say=print, engine=False, junior_model: str = "Cin-MinAI guide",
                 where: str = "local") -> None:
        self.agent, self.junior, self.say = agent, junior, say
        if engine is False:
            project = token_of(agent.root) or hashlib.sha1(os.path.realpath(agent.root).encode()).hexdigest()
            engine = engine_mod.open_engine(project, agent.root)
            if engine is not None:
                engine.close_stale()
        self.engine = engine
        self.lead, self.helper_name = "coder", "helper"
        if engine is not None:
            self.lead = engine.member("coder", agent.ctx, getattr(agent, "model_name", ""), where)
            self.helper_name = engine.member("helper", JUNIOR_CONTEXT, junior_model, "local")
        self.models = {self.lead: getattr(agent, "model_name", ""), self.helper_name: junior_model}
        self.root: dict | None = None
        self.cancel: threading.Event | None = None
        agent.helper = self.read        # the coder's ask_helper tool
        agent.reviewer = self.review_goal

    # --- one request: the coder's ----------------------------------------------------------------------------
    def turn(self, request: str, cancel: threading.Event | None = None) -> str:
        self.cancel = cancel or threading.Event()
        self.root = None
        if self.engine is not None:
            try:
                self.root = self.engine.request(request, self.lead)
            except Exception as e:  # the record failing never loses the request
                self.agent.event("note", text=f"The Team Table couldn't take this request ({str(e)[:160]}).")
        try:
            out = self.agent.turn(request, self.cancel)
        except BaseException:  # Stop (Ctrl+C) or a failure: the request's tree is cancelled, not left open
            self.close_cancelled()
            raise
        if self.cancel.is_set():
            self.close_cancelled()
        else:
            ended = getattr(self.agent, "stopped", "")
            verdict = {"answer": "done", "ask": "asks the person", "declined": "declined"}.get(ended, ended or "done")
            self.close(out, verdict)
        return out

    def close(self, text: str, verdict: str) -> None:
        if self.engine is not None and self.root:
            state = "done" if verdict == "done" else "blocked"
            try:
                self.engine.finish(self.root, self.lead, self.models[self.lead], verdict, text, state)
            except Exception:
                pass

    def close_cancelled(self) -> None:
        if self.engine is not None and self.root:
            try:
                self.engine.cancel(self.root["id"])
            except Exception:
                pass

    # --- the helper's jobs, each a child task on the table ---------------------------------------------------
    def job(self, kind: str, title: str, text: str, run) -> str:
        """Give the helper a job under the current request and run it: run() -> (result, verdict)."""
        task = None
        if self.engine is not None and self.root:
            try:
                task = self.engine.order(self.root["id"], self.lead, self.helper_name, title, text, kind)
                self.engine.claim(self.helper_name)
            except Exception:
                task = None
        self.agent.event("handoff", by="coder", to="helper", text=title)
        try:
            result, verdict = run()
        except Exception as e:  # the helper failing never stops the coder
            result, verdict = f"error: the helper couldn't do it ({type(e).__name__}: {str(e)[:160]})", "error"
        if task is not None:
            try:
                self.engine.finish(task, self.helper_name, self.models[self.helper_name], verdict, result)
                self.engine.claim(self.lead)  # the request again: its child is closed
            except Exception:
                pass
        self.agent.event("handoff", by="helper", to="coder", text=result[:300])
        return result

    def ask(self, system: str, user: str, schema: dict | None = None, max_tokens: int = 600) -> str:
        raw, _ = self.junior([{"role": "system", "content": system}, {"role": "user", "content": user}],
                             schema=schema, max_tokens=max_tokens, cancel=self.cancel)
        return str(raw)

    def read(self, source: str, question: str) -> str:
        """ask_helper: the helper reads a long file for one question, part by part; the answer is kept."""
        full = os.path.realpath(os.path.join(self.agent.root, source))
        root = os.path.realpath(self.agent.root)
        if not full.startswith(root + os.sep) or not os.path.isfile(full):
            return f"error: {source} isn't a file in the project"
        if not question.strip():
            return "error: ask the helper a question about the file"
        rel = os.path.relpath(full, root).replace(os.sep, "/")

        def run() -> tuple[str, str]:
            with open(full, encoding="utf-8", errors="replace") as f:
                text = f.read()
            parts = [text[i:i + PART_CHARS] for i in range(0, len(text), PART_CHARS)] or [""]
            cut = len(parts) > MAX_PARTS
            parts = parts[:MAX_PARTS]
            found = []
            for n, part in enumerate(parts, 1):
                if self.cancel is not None and self.cancel.is_set():
                    break
                self.agent.event("busy", doing=f"the helper is reading {rel}, part {n} of {len(parts)}", tokens=0)
                said = self.ask(READ.format(n=n, total=len(parts), source=rel, question=question), part).strip()
                if said and not said.lower().startswith("nothing here"):
                    found.append(f"## part {n}\n{said}")
            os.makedirs(os.path.join(root, ".cinminai", "helper"), exist_ok=True)
            kept = f".cinminai/helper/{time.strftime('%Y%m%d-%H%M%S')}.md"
            answer = "\n\n".join(found) or "nothing in the file answers it"
            with open(os.path.join(root, kept), "w", encoding="utf-8") as f:
                f.write(f"# {rel}: {question}\n\n{answer}\n")
            note = f" (only its first {MAX_PARTS} parts: the file is longer)" if cut else ""
            return (f"the helper read {rel} in {len(parts)} parts{note} for: {question}\nIts answer is kept in {kept} "
                    f"({answer.count(chr(10)) + 1} lines); it begins:\n{answer[:1500]}"), "answered"
        return self.job("read", f"read {rel}: {question}"[:200], f"{rel}\n{question}", run)

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
