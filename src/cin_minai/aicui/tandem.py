# SPDX-License-Identifier: GPL-3.0-or-later
"""Two models on one project (SPEC §22.5, PLAN D94-D96; slice 3): the guide (the 4B, on the processor) organizes, the
coding model (on the graphics card) codes. Ian, 2026-10-08: "If I hit continue on AICUI it should feed it to the
small bot to scan piece by piece and place things to look at and do… letting the smaller bot do most of the
organization except crucial stuff that needs to be done by the bigger bot, and information retrieval. Then they
bounce back and forth until the project is finished… the small bot would suggest the hint, if the error were honest
and there was nothing else to do."

* **Code scans** — the project's map and the problems the checks find are made from the code (agent.project_map):
  the 4B reads prompts at ~35 tokens a second on the processor (the 27B ~250 on the card), so it never reads code.
* **The organizer (4B)** picks the next move from the map, the problems, the goals and short summaries of what the
  coder did: a scoped task for the coder, a page to fetch (asked first, D86), a question for the person, or done.
* **The coder (27B)** does each task with its own steps and checks (Agent.work); what it did comes back as a summary.
* **Stuck:** one hint from the organizer, then the person. An honest "I can't know this" goes to the person at once.
* Every task is a turn token on the coder (D95): at most 5 % of its context.
"""

from __future__ import annotations

import json
import os
import re
import threading

MAX_ROUNDS = 20          # tasks per request before the organizer hands back to the person
SUMMARY_CHARS = 500      # what the organizer hears of each task's outcome
JUNIOR_CONTEXT = 8192

SYSTEM = """You organize the work in AICUI, a coding workspace. A bigger model, the coder, writes and fixes the code;
you choose what it does next, one task at a time. You never write code yourself.
You get the person's request, the goals, the problems the checks find in the files and the project's map — both
made from the code, so trust them — and what the coder did so far.
Your reply: a short thinking (a sentence), then one move:
- coder: one task for the coder: what to do, in which file and lines, and how to check it. Concrete and small; name
  the lines from the map or the problems. At most {cap} characters.
- fetch: a web page the work needs (a source the person named), saved as a file in the project for the coder.
- ask: a question only the person can answer (a choice, a source, a fact nobody here can know).
- done: the goals are met and the checks find no problems, or nothing more can be done now: say what was done and
  what's left.
Every task is a change to make — never only to review, check or verify (the checks already do that, by code).
When the checks find nothing, the task is the next concrete piece of the first open goal: which file, what to add.
Rules: problems the checks find come first (a build error first of all); ask for the smallest change that fixes
each — a call to a name that exists nowhere usually means something was renamed: point the call at the name in the
map. Several blocks to remove
from one file: list them bottom first (lines above a removed block keep their numbers). Never give the same task
twice in a row: change it, or ask. If the coder said honestly that it can't know something, ask the person — don't
work around it. Reply in the person's language."""

HINT = """The coder stopped without finishing this task: it spent its steps without changing anything. Give it one
hint that gets it to act. Never tell it to read more — reading is what it was stuck in. Point it to a change it can
make now: the exact lines from the problems or the map, and the tool — replace_lines to delete or redo lines by
number (several blocks in one file: bottom first), edit to change a short exact text, write for a new file. If it
said honestly that it can't know something or needs the person, ask the person instead. At most 400 characters."""


def plan_schema(cap: int) -> dict:
    move = lambda name, **props: {  # noqa: E731
        "type": "object", "additionalProperties": False, "required": ["move", *props],
        "properties": {"move": {"const": name}, **props}}
    s = {"type": "string"}
    return {"type": "object", "additionalProperties": False, "required": ["thinking", "next"], "properties": {
        "thinking": {"type": "string", "maxLength": 400},
        "next": {"anyOf": [move("coder", task={"type": "string", "maxLength": cap}),
                           move("fetch", url=s, save_as=s), move("ask", question=s), move("done", summary=s)]}}}


HINT_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["next"], "properties": {"next": {"anyOf": [
    {"type": "object", "additionalProperties": False, "required": ["move", "hint"],
     "properties": {"move": {"const": "hint"}, "hint": {"type": "string", "maxLength": 400}}},
    {"type": "object", "additionalProperties": False, "required": ["move", "question"],
     "properties": {"move": {"const": "ask"}, "question": {"type": "string"}}}]}}}


REVIEW = re.compile(r"^\W*(?:please\s+)?(?:review|check|verify|ensure|inspect|examine|look\s+(?:at|over|through)|"
                    r"go\s+through|read|analy[sz]e|make\s+sure|confirm|audit)\b", re.I)


def is_review(task: str) -> bool:
    """A task that only asks for reading and judging (2026-10-08: "Review the code…", "Review the implementation of
    the Engine class… ensure…" — the coder read every file and changed nothing). The checks review, by code."""
    return bool(REVIEW.match(task))


def goal_task(goals: list[dict], root: str) -> str:
    """The next move made by code when the organizer only offers reviews: a change toward the first open goal — a
    test first if the project has none, since a goal is ticked only when its tests pass."""
    goal = next((g for g in goals if not g["done"]), None)
    if goal is None:
        return ""
    has_tests = any(f.startswith("test_") and f.endswith(".py") for _, _, fs in os.walk(root) for f in fs)
    if not has_tests:
        return (f"Goal {goal['id']}: {goal['text'][:300]}\nThe project has no tests, so no goal can be ticked yet. "
                "Write test_" + re.sub(r"\W+", "_", goal["text"].split()[0].lower() if goal["text"] else "goal")[:20]
                + ".py with a few tests of what this goal promises (they may fail at first), run them, and fix what "
                "fails, one change at a time.")
    return (f"Goal {goal['id']}: {goal['text'][:300]}\nPick the next missing piece of this goal, make that change, "
            "and check it (build, run, or the tests). One piece; then say what's next.")


def token_cap(coder_ctx: int) -> int:
    """A task's size limit: 5 % of the coder's context (D95), in characters (~3 a token)."""
    return int(coder_ctx * 0.05 * 3)


class Tandem:
    """One request worked by the organizer and the coder in turns. agent: the coder's Agent; junior: the organizer's
    chat (messages, schema=, max_tokens=, cancel=) -> (text, timings)."""

    def __init__(self, agent, junior, say=print) -> None:
        self.agent, self.junior, self.say = agent, junior, say
        self.cap = token_cap(agent.ctx)

    # --- the organizer ------------------------------------------------------------------------------------------
    def situation(self, request: str, rounds: list[dict]) -> str:
        goals = "\n".join(f"  {g['id']}. [{'x' if g['done'] else ' '}] {g['text']}"
                          for g in self.agent.goals.load()) or "  (none)"
        done = "\n".join(f"  {i}. {r['task'][:200]} → {r['outcome'][:SUMMARY_CHARS]}"
                         for i, r in enumerate(rounds, 1)) or "  (nothing yet)"
        return (f"The person's request: {request}\n\nGoals:\n{goals}{self.agent.project_map()}\n\n"
                f"Done so far in this request:\n{done}")

    def ask_junior(self, system: str, user: str, schema: dict, cancel) -> dict | None:
        try:
            raw, _ = self.junior([{"role": "system", "content": system}, {"role": "user", "content": user}],
                                 schema=schema, max_tokens=500, cancel=cancel)
            return json.loads(raw)
        except Exception as e:  # the organizer failing never loses the request: the coder works it alone
            self.agent.event("note", text=f"The organizer didn't answer ({type(e).__name__}); the coder goes on alone.")
            return None

    def next_move(self, request: str, rounds: list[dict], cancel) -> dict | None:
        out = self.ask_junior(SYSTEM.format(cap=self.cap), self.situation(request, rounds), plan_schema(self.cap),
                              cancel)
        if out and out.get("thinking"):
            self.agent.event("thinking", text=f"(organizer) {out['thinking']}")
        return out and out.get("next")

    def hint(self, request: str, rounds: list[dict], stopped: str, cancel) -> dict | None:
        user = self.situation(request, rounds) + f"\n\nThe coder's stop:\n{stopped[:1200]}"
        out = self.ask_junior(HINT, user, HINT_SCHEMA, cancel)
        return out and out.get("next")

    # --- the moves -----------------------------------------------------------------------------------------------
    def coder(self, request: str, task: str, cancel) -> str:
        self.agent.event("handoff", by="organizer", to="coder", text=task)
        self.say(f"\033[36m(organizer → coder) {task}\033[0m")
        return self.agent.work(f"A task from the organizer, part of the person's request \"{request[:200]}\":\n{task}",
                               cancel)

    def fetch(self, url: str, save_as: str) -> str:
        name = re.sub(r"[^\w.-]+", "-", os.path.basename(save_as or "page")).strip("-.") or "page"
        if not name.endswith((".txt", ".md", ".json", ".csv")):
            name += ".txt"
        self.agent.event("handoff", by="organizer", to="fetch", text=url)
        text = self.agent.fetch(url)  # asks the person first, always (D86)
        if text.startswith(("error", "the user said no")):
            return text
        os.makedirs(os.path.join(self.agent.root, "sources"), exist_ok=True)
        rel = os.path.join("sources", name)
        with open(os.path.join(self.agent.root, rel), "w", encoding="utf-8") as f:
            f.write(text)
        return f"saved {url} as {rel} ({len(text.splitlines())} lines) for the coder"

    def finish(self, text: str) -> str:
        self.agent.event("answer", text=text)
        self.say(text)
        return text

    # --- one request ---------------------------------------------------------------------------------------------
    def turn(self, request: str, cancel: threading.Event | None = None) -> str:
        cancel = cancel or threading.Event()
        self.agent.event("user", text=request)
        try:
            return self.work(request, cancel)
        finally:
            self.agent.event("idle")

    def work(self, request: str, cancel: threading.Event) -> str:
        rounds: list[dict] = []
        hinted = False
        for _ in range(MAX_ROUNDS):
            if cancel.is_set():
                return self.finish("Stopped. What's done is saved and in the changelog.")
            move = self.next_move(request, rounds, cancel)
            if move is None:  # the organizer is out: the coder takes the request as it is
                return self.agent.work(request, cancel)
            kind = move.get("move")
            if kind == "done":
                return self.finish(move.get("summary") or "Done.")
            if kind == "ask":
                self.agent.event("handoff", by="organizer", to="person", text=move.get("question", ""))
                return self.finish(move.get("question") or "What should happen next?")
            if kind == "fetch":
                rounds.append({"task": f"fetch {move.get('url', '')}",
                               "outcome": self.fetch(move.get("url", ""), move.get("save_as", ""))})
                continue
            task = move.get("task", "").strip() if kind == "coder" else ""
            if task and is_review(task):  # once back to the organizer, then a task made by code
                self.agent.event("note", text="The organizer's task was a review; it was asked for a change instead.")
                again = self.next_move(request + "\n(Your last task only asked for a review. The checks review, by "
                                       "code: give a change to make.)", rounds, cancel)
                if (again or {}).get("move") == "ask":
                    return self.finish(again.get("question") or "What should happen next?")
                task = (again or {}).get("task", "").strip() if (again or {}).get("move") == "coder" else ""
                if not task or is_review(task):
                    task = goal_task(self.agent.goals.load(), self.agent.root)
            if not task:  # nothing the coder could do
                return self.finish("The organizer had no next task, so I've stopped here. Tell me how to go on.")
            if rounds and task == rounds[-1]["task"]:  # a loop between the two: the person decides
                return self.finish("The organizer gave the coder the same task twice in a row, so I've stopped here. "
                                   f"The task was: {task}\nTell me how to go on.")
            outcome = self.coder(request, task, cancel)
            if self.agent.stopped in ("ask", "error"):  # the coder needs the person, or couldn't go on: theirs now
                return outcome
            stopped = self.agent.stopped == "stuck"
            if stopped and not hinted:  # one hint, then the person
                problems = self.agent.problems()
                if problems:  # the checks name what to fix: the hint comes from them, by code (the 4B's varied)
                    hint = {"move": "hint", "hint": "Act on what the checks find now, with replace_lines (bottom first) "
                            "or edit — don't read further: " + "; ".join(problems)[:600]}
                else:
                    hint = self.hint(request, rounds + [{"task": task, "outcome": outcome}], outcome, cancel)
                if hint and hint.get("move") == "hint" and hint.get("hint"):
                    hinted = True
                    self.agent.event("handoff", by="organizer", to="coder", text=f"Hint: {hint['hint']}")
                    outcome = self.coder(request, f"Hint from the organizer: {hint['hint']}\n(The task it's for: "
                                         f"{task[:400]} — its line numbers may have moved since; the problems and "
                                         "the map above are current.)", cancel)
                    stopped = self.agent.stopped == "stuck"
                elif hint and hint.get("move") == "ask":
                    return self.finish(hint.get("question") or outcome)
            if stopped:
                return self.finish(outcome)
            rounds.append({"task": task, "outcome": outcome})
        return self.finish(f"I've stopped after {MAX_ROUNDS} tasks for this request; what's done is saved. "
                           "Tell me to continue and the organizer picks up from the files and the goals.")


def junior_backend(log=None):
    """The guide on the processor, beside the coding model on the card: its own server and socket; it never takes
    the card (the processor is its only rung)."""
    from cin_minai.daemon import config
    from cin_minai.inference.llamacpp import LlamaCppBackend
    cfg = dict(config.load()["inference"])
    if not cfg.get("model") or not os.path.isfile(cfg["model"]):
        return None
    cfg.update(build="cpu", context=JUNIOR_CONTEXT, cpu_context=JUNIOR_CONTEXT, cache_type="q8_0",
               socket_name="llama-junior.sock", model_name="Cin-MinAI guide (organizer)", extra_args=[])
    return LlamaCppBackend(cfg, log or (lambda m: None))
