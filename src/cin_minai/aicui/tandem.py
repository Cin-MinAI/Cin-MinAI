# SPDX-License-Identifier: GPL-3.0-or-later
"""Two models on one project (SPEC §22.5, PLAN D94-D96; slice 3): the guide (the 4B, on the processor) organizes, the
coding model (on the graphics card) codes. Ian, 2026-10-08: "If I hit continue on AICUI it should feed it to the
small bot to scan piece by piece and place things to look at and do… letting the smaller bot do most of the
organization except crucial stuff that needs to be done by the bigger bot, and information retrieval. Then they
bounce back and forth until the project is finished… the small bot would suggest the hint, if the error were honest
and there was nothing else to do."

* **Code scans** — the project's map, the problems the checks find and each goal's cycle (fetched, structured,
  checked, used, reviewed) are made from the code; the 4B reads prompts at ~35 tokens a second on the processor (the
  27B ~250 on the card), so it never reads code.
* **The move contract** (PLAN §1b closure 1; Ian: "We can't just auto code what to do. This has to be generalized
  for function"). Every move says what it acts on, and a task for the coder also what proves it's done. Code checks
  the contract, not the wording:
  - what the person just gave — a link, a project file, pasted material — is used first: a move that uses none of it
    goes back to the organizer once, then to the person;
  - a task must change something: one that changed nothing (a review, a no-op) comes back as "changed nothing";
  - the coder may decline a task with its reason; the organizer revises it;
  - the same task twice in a row, or twice "changed nothing" or "declined", goes to the person.
* **Stuck:** one hint (made by code from the problems when the checks name any), then the person. The coder's own
  question and an honest "I can't know this" go to the person at once.
* Every task is a turn token on the coder (D95): at most 5 % of its context.
"""

from __future__ import annotations

import json
import os
import threading

from . import intake
from .project import goal_stages

MAX_ROUNDS = 20          # tasks per request before the organizer hands back to the person
SUMMARY_CHARS = 500      # what the organizer hears of each task's outcome
JUNIOR_CONTEXT = 8192

SYSTEM = """You organize the work in AICUI, a coding workspace. A bigger model, the coder, writes and fixes the code;
you choose what it does next, one task at a time. You never write code yourself.
You get the person's request (and anything they gave with it), the goals with where each stands, the problems the
checks find in the files and the project's map — all made from the code, so trust them — and what the coder did.
Your reply: a short thinking (a sentence), then one move:
- coder: one task: `task` (what to change, in which file and lines — concrete and small, at most {cap} characters),
  `acts_on` (the files, lines or the person's input it works on) and `proof` (what shows it's done: a build, a test,
  a run, a source's count).
- fetch: a web page or file the work needs (one the person named first); it's kept in the project for the coder.
- look: see the program running (target "program"), a page ("page", with its `address`) or the person's screen
  ("screen", asked first) — facts read by code, and your one `question` answered by a picture model.
- ask: a question only the person can answer (a choice, a source, a fact nobody here can know).
- done: the goals are met and the checks find no problems, or nothing more can be done now: say what was done and
  what's left.
Rules: use what the person just gave first. Every task changes something — the checks already review, by code; with
nothing to fix, take the next piece of the first open goal (a goal without a passing test needs one). Problems the
checks find come first (a build error first of all), each with the smallest change that fixes it — a call to a name
that exists nowhere usually means something was renamed. Several blocks to remove from one file: bottom first. If the
coder declines a task or it changed nothing, give a different one or ask. If the coder said honestly that it can't
know something, ask the person. Reply in the person's language."""

HINT = """The coder stopped without finishing this task: it spent its steps without changing anything. Give it one
hint that gets it to act. Never tell it to read more — reading is what it was stuck in. Point it to a change it can
make now: the exact lines from the problems or the map, and the tool — replace_lines to delete or redo lines by
number (several blocks in one file: bottom first), edit to change a short exact text, write for a new file. If it
said honestly that it can't know something or needs the person, ask the person instead. At most 400 characters."""


def plan_schema(cap: int) -> dict:
    move = lambda name, **props: {  # noqa: E731
        "type": "object", "additionalProperties": False, "required": ["move", *props],
        "properties": {"move": {"const": name}, **props}}
    s, said = {"type": "string"}, {"type": "string", "minLength": 2, "maxLength": 300}
    return {"type": "object", "additionalProperties": False, "required": ["thinking", "next"], "properties": {
        "thinking": {"type": "string", "maxLength": 400},
        "next": {"anyOf": [move("coder", task={"type": "string", "minLength": 8, "maxLength": cap}, acts_on=said,
                                proof=said),
                           move("fetch", url=s), move("look", target={"enum": ["program", "page", "screen"]},
                                                      question=s, address=s),
                           move("ask", question=s), move("done", summary=s)]}}}


HINT_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["next"], "properties": {"next": {"anyOf": [
    {"type": "object", "additionalProperties": False, "required": ["move", "hint"],
     "properties": {"move": {"const": "hint"}, "hint": {"type": "string", "maxLength": 400}}},
    {"type": "object", "additionalProperties": False, "required": ["move", "question"],
     "properties": {"move": {"const": "ask"}, "question": {"type": "string"}}}]}}}


def token_cap(coder_ctx: int) -> int:
    """A task's size limit: 5 % of the coder's context (D95), in characters (~3 a token)."""
    return int(coder_ctx * 0.05 * 3)


def uses(move: dict, given: dict) -> bool:
    """Does a move work on something the person gave? A link by its address, a file by its path."""
    said = " ".join(str(move.get(k, "")) for k in ("url", "address", "task", "acts_on", "question"))
    return given["value"] in said or (given["kind"] == "link" and move.get("url", "").rstrip("/") ==
                                      given["value"].rstrip("/"))


class Tandem:
    """One request worked by the organizer and the coder in turns. agent: the coder's Agent; junior: the organizer's
    chat (messages, schema=, max_tokens=, cancel=) -> (text, timings)."""

    def __init__(self, agent, junior, say=print) -> None:
        self.agent, self.junior, self.say = agent, junior, say
        self.cap = token_cap(agent.ctx)

    # --- what the organizer sees --------------------------------------------------------------------------------
    def situation(self, request: str, rounds: list[dict], given: list[dict]) -> str:
        goals = []
        for g in self.agent.goals.load():
            goals.append(f"  {g['id']}. [{'x' if g['done'] else ' '}] {g['text']}")
            goals += [f"       {line}" for line in goal_stages(self.agent.root, g)["lines"]]
        done = "\n".join(f"  {i}. {r['task'][:200]} → {r['outcome'][:SUMMARY_CHARS]}"
                         for i, r in enumerate(rounds, 1)) or "  (nothing yet)"
        brought = "".join(f"\n  - {'a link' if x['kind'] == 'link' else 'a file'}: {x['value']}" for x in given)
        return (f"The person's request: {request}" + (f"\nWhat they gave, not used yet:{brought}" if given else "")
                + "\n\nGoals:\n" + ("\n".join(goals) or "  (none)") + self.agent.project_map()
                + f"\n\nDone so far in this request:\n{done}")

    def ask_junior(self, system: str, user: str, schema: dict, cancel) -> dict | None:
        try:
            raw, _ = self.junior([{"role": "system", "content": system}, {"role": "user", "content": user}],
                                 schema=schema, max_tokens=500, cancel=cancel)
            return json.loads(raw)
        except Exception as e:  # the organizer failing never loses the request: the coder works it alone
            self.agent.event("note", text=f"The organizer didn't answer ({type(e).__name__}); the coder goes on alone.")
            return None

    def next_move(self, request: str, rounds: list[dict], given: list[dict], cancel) -> dict | None:
        out = self.ask_junior(SYSTEM.format(cap=self.cap), self.situation(request, rounds, given),
                              plan_schema(self.cap), cancel)
        if out and out.get("thinking"):
            self.agent.event("thinking", text=f"(organizer) {out['thinking']}")
        return out and out.get("next")

    def hint(self, request: str, rounds: list[dict], stopped: str, cancel) -> dict | None:
        user = self.situation(request, rounds, []) + f"\n\nThe coder's stop:\n{stopped[:1200]}"
        out = self.ask_junior(HINT, user, HINT_SCHEMA, cancel)
        return out and out.get("next")

    # --- the moves -----------------------------------------------------------------------------------------------
    def state(self) -> tuple:
        """What a task can change, as code sees it: the changelog, the kept sources and files, the goals, the
        environment's header."""
        def count(folder: str) -> int:
            try:
                return len(os.listdir(os.path.join(self.agent.root, folder)))
            except OSError:
                return 0
        try:
            changes = len(self.agent.log.entries())
        except Exception:
            changes = 0
        goals = tuple((g["id"], g["done"]) for g in self.agent.goals.load())
        venv = os.path.join(self.agent.root, ".venv", "cinminai-env.json")
        return changes, count("sources"), count("assets"), goals, os.path.getmtime(venv) if os.path.exists(venv) else 0

    def coder(self, request: str, move: dict, cancel) -> str:
        task = move["task"].strip()
        text = task + (f"\nWorks on: {move['acts_on']}" if move.get("acts_on") else "") + \
            (f"\nDone when: {move['proof']}" if move.get("proof") else "")
        self.agent.event("handoff", by="organizer", to="coder", text=text)
        self.say(f"\033[36m(organizer → coder) {task}\033[0m")
        return self.agent.work(f"A task from the organizer, part of the person's request \"{request[:200]}\":\n{text}\n"
                               "If it doesn't apply (it's already done, or it can't be done here), decline it with "
                               "your reason.", cancel)

    def fetch(self, url: str) -> str:
        self.agent.event("handoff", by="organizer", to="fetch", text=url)
        return self.agent.fetch(url)  # asks the person first, always (D86); kept whole under sources/ or assets/

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
        hinted, refused, idle = False, 0, 0
        given = []  # what the person brought: links and project files to use first; pasted material kept as a source
        for item in intake.person_inputs(request, self.agent.root):
            if item["kind"] == "pasted":
                item = {"kind": "file", "value": intake.keep_pasted(self.agent.root, item["value"])}
            given.append(item)
        for _ in range(MAX_ROUNDS):
            if cancel.is_set():
                return self.finish("Stopped. What's done is saved and in the changelog.")
            move = self.next_move(request, rounds, given, cancel)
            if move is None:  # the organizer is out: the coder takes the request as it is
                return self.agent.work(request, cancel)
            kind = move.get("move")
            if kind == "done":
                return self.finish(move.get("summary") or "Done.")
            if kind == "ask":
                self.agent.event("handoff", by="organizer", to="person", text=move.get("question", ""))
                return self.finish(move.get("question") or "What should happen next?")
            if given and not any(uses(move, g) for g in given):  # the contract: the person's input comes first
                refused += 1
                what = ", ".join(g["value"] for g in given)
                if refused > 1:
                    return self.finish(f"The organizer didn't use what you gave ({what}), so I've stopped here. Tell "
                                       "me what to do with it.")
                rounds.append({"task": f"{kind}: {move.get('task') or move.get('url', '')}"[:300],
                               "outcome": f"not done: the person gave {what} — use it first"})
                self.agent.event("note", text=f"The organizer's move didn't use what you gave ({what}); asked again.")
                continue
            given = [g for g in given if not uses(move, g)]
            if kind == "look":
                self.agent.event("handoff", by="organizer", to="look", text=f"{move.get('target')}: "
                                                                         f"{move.get('question', '')}")
                rounds.append({"task": f"look at the {move.get('target', 'program')}: {move.get('question', '')}",
                               "outcome": self.agent.look(move.get("target", "program"), move.get("question", ""),
                                                          move.get("address", ""))})
                continue
            if kind == "fetch":
                url = move.get("url", "").strip()
                if not url.startswith("https://"):  # the contract: a fetch acts on a web address (the 4B "fetched"
                    # gui.py, then asked the person for "the correct URL")
                    outcome = (f"not done: {url or 'that'} isn't a web address — files in the project are the coder's "
                               "to read and change: give the coder a task")
                else:
                    outcome = self.fetch(url)
                rounds.append({"task": f"fetch {url}", "outcome": outcome})
                continue
            task = (move.get("task") or "").strip()
            if rounds and task == rounds[-1]["task"]:  # a loop between the two: the person decides
                return self.finish("The organizer gave the coder the same task twice in a row, so I've stopped here. "
                                   f"The task was: {task}\nTell me how to go on.")
            before = self.state()
            outcome = self.coder(request, move, cancel)
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
                    outcome = self.coder(request, {"task": f"Hint from the organizer: {hint['hint']}\n(The task it's "
                                                           f"for: {task[:400]} — its line numbers may have moved "
                                                           "since; the problems and the map above are current.)"},
                                         cancel)
                    stopped = self.agent.stopped == "stuck"
                elif hint and hint.get("move") == "ask":
                    return self.finish(hint.get("question") or outcome)
            if stopped:
                return self.finish(outcome)
            if self.agent.stopped == "declined":
                outcome = f"declined by the coder — {outcome}"
            elif self.state() == before:  # the contract: a task changes something
                outcome = f"changed nothing (no file, source, goal or environment): {outcome}"
            if outcome.startswith(("declined", "changed nothing")):
                idle += 1
                if idle > 1:
                    return self.finish(f"Two tasks in a row changed nothing, so I've stopped here.\nThe last: {task}\n"
                                       f"{outcome[:600]}\nTell me how to go on.")
            else:
                idle = 0
            rounds.append({"task": task, "outcome": outcome})
        return self.finish(f"I've stopped after {MAX_ROUNDS} tasks for this request; what's done is saved. "
                           "Tell me to continue and the organizer picks up from the files and the goals.")


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
               socket_name="llama-junior.sock", model_name="Cin-MinAI guide (organizer)",
               extra_args=["--mmproj", projector, "--no-mmproj-offload"] if projector else [])
    return LlamaCppBackend(cfg, log or (lambda m: None))
