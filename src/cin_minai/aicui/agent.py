# SPDX-License-Identifier: GPL-3.0-or-later
"""cinminai-code, the coding agent that runs in AICUI's terminal (PLAN D61, SPEC §21).

    python3 -m cin_minai.aicui.agent [--auto | --no-permissions] [--admin] [FOLDER]

It talks in the terminal like any coding agent: you type, it works, and before it changes a file or runs a command
it asks there ([y]es / [n]o / [a]lways this session) — unless the user chose auto mode or no permissions at all.
Every file it changes goes into the changelog (shadow git, undo exact). It writes small event lines to
.cinminai/events.jsonl, which AICUI turns into the chat history (its thinking as collapsible bubbles), the changelog
and the session goals.

The model answers in schema-constrained JSON (D6): its thinking, then one action. Local by default: the system
matcher's coding model (D60); cloud backends come in a later slice.
"""

from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time

from .changelog import Changelog
from .project import Goals, project_root, tree

MAX_STEPS = 30
READ_LINES = 80        # a read fits one result (OBS_CHARS) with its "more lines" note
OBS_CHARS = 3000       # what one tool result may add to the context (8K on an 11 GB card)
RUN_TIMEOUT = 120
ANSWER_TOKENS = 1800   # room for one step's answer (thinking + an action; a written file can be long)

STR = {"type": "string"}
ACTIONS = [
    {"tool": "read", "path": STR, "start": {"type": "integer"}},
    {"tool": "list", "path": STR},
    {"tool": "search", "pattern": STR},
    {"tool": "edit", "path": STR, "old": STR, "new": STR},
    {"tool": "write", "path": STR, "content": STR},
    {"tool": "run", "command": STR},
    {"tool": "goal_add", "text": STR},
    {"tool": "goal_done", "id": {"type": "integer"}},
    {"tool": "ask", "question": STR},
    {"tool": "answer", "text": STR},
]
OPTIONAL = {"start"}


def schema() -> dict:
    variants = []
    for a in ACTIONS:
        props = {k: ({"const": v} if k == "tool" else v) for k, v in a.items()}
        variants.append({"type": "object", "additionalProperties": False, "properties": props,
                         "required": [k for k in a if k not in OPTIONAL]})
    return {"type": "object", "additionalProperties": False, "required": ["thinking", "action"],
            "properties": {"thinking": {"type": "string", "maxLength": 1500}, "action": {"anyOf": variants}}}


SYSTEM = """You are the coding agent in AICUI, working in the project folder {root} on the user's own computer.
You work step by step. Each step: your thinking (short), then exactly one action:
- read (a file, from line `start`), list (a folder), search (a regex over the project's files)
- edit (replace the exact text `old` with `new` in a file; `old` must appear once), write (a whole new file)
- run (a shell command in the project folder{sandbox})
- goal_add / goal_done (the session goals: add one, or tick goal `id` when it's really done)
- ask (a question for the user), answer (tell the user something; ends your turn)
Rules: read before you edit; make the smallest change that does the job; after a change, check it (run the tests or
the program) before you call it done. Paths are relative to the project folder. Never invent file contents you
haven't read. At the start of a new project, ask about its goals and scope and write them as goals; once work
starts, work the goals as your to-do list. Answer in the user's language.

The project's files (first lines):
{files}

Session goals:
{goals}"""


def slim(step: dict) -> dict:
    """A step as it's sent again later: file contents shortened to what they were (the file itself is on disk)."""
    a = dict(step.get("action", {}))
    if a.get("tool") == "write":
        a["content"] = f"<{len(str(a.get('content', '')).splitlines())} lines written>"
    for k in ("old", "new"):
        if len(str(a.get(k, ""))) > 300:
            a[k] = str(a[k])[:300] + " …"
    return {"thinking": str(step.get("thinking", ""))[:300], "action": a}


def brief(step: dict) -> str:
    a = step.get("action", {})
    what = a.get("path") or a.get("command") or a.get("pattern") or a.get("text") or ""
    return f"{a.get('tool', '?')} {str(what)[:80]}"


class Agent:
    def __init__(self, root: str, chat, model_name: str, mode: str = "ask", admin: bool = False,
                 ask=input, say=print, ctx: int = 8192) -> None:
        self.root, self.chat, self.model_name, self.ctx = root, chat, model_name, ctx
        self.mode, self.admin, self.ask, self.say = mode, admin, ask, say
        self.always: set[str] = set()   # tools the user said "always" to this session
        self.goals, self.log = Goals(root), Changelog(root)
        self.history: list[dict] = []   # earlier turns: the user's message and the final answer
        self.events = os.path.join(root, ".cinminai", "events.jsonl")
        self.sandbox = shutil.which("bwrap") is not None and mode != "none"

    # --- events for AICUI's panes --------------------------------------------------------------------------
    def event(self, kind: str, **data) -> None:
        os.makedirs(os.path.dirname(self.events), exist_ok=True)
        with open(self.events, "a", encoding="utf-8") as f:
            f.write(json.dumps({"t": time.time(), "kind": kind, **data}, ensure_ascii=False) + "\n")

    # --- the loop -------------------------------------------------------------------------------------------
    def system(self) -> str:
        files = "\n".join("  " + r +("/" if d else "") for r, d, _ in tree(self.root)[:80])
        goals = "\n".join(f"  {g['id']}. [{'x' if g['done'] else ' '}] {g['text']}" for g in self.goals.load()) or "  (none yet)"
        return SYSTEM.format(root=self.root, files=files or "  (empty)", goals=goals,
                             sandbox=", sandboxed without network" if self.sandbox else "")

    def messages(self, text: str, steps: list[dict], full: int = 4) -> list[dict]:
        """What the model is sent: the system text, earlier turns, this request, and this turn's steps — the last
        `full` in full, older ones as one line each. A step's file contents are never sent again (2026-10-02: the
        blackjack run overflowed 8K by resending every written file in every step); the file is on disk to read."""
        messages = [{"role": "system", "content": self.system()}]
        for h in self.history[-6:]:
            messages += [{"role": "user", "content": h["user"]}, {"role": "assistant", "content": h["answer"][:600]}]
        messages.append({"role": "user", "content": text})
        older = steps[:-full] if full else steps
        if older:
            messages.append({"role": "user", "content": "Earlier in this task:\n" + "\n".join(
                f"- {brief(s['did'])} → {s['result'][:100]}" for s in older)})
        for s in steps[len(older):]:
            messages.append({"role": "assistant", "content": json.dumps(slim(s["did"]), ensure_ascii=False)})
            messages.append({"role": "user", "content": "Result: " + s["result"]})
        return messages

    def fit(self, text: str, steps: list[dict]) -> list[dict]:
        """The messages, shrunk until they fit the context with room for the answer (~3.3 characters a token)."""
        budget = (self.ctx - ANSWER_TOKENS - 300) * 3.3
        for full in (4, 3, 2, 1, 0):
            m = self.messages(text, steps, full)
            if sum(len(x["content"]) for x in m) <= budget:
                return m
        return m

    def turn(self, text: str, cancel: threading.Event | None = None) -> str:
        self.event("user", text=text)
        steps: list[dict] = []
        for _ in range(MAX_STEPS):
            try:
                raw, _ = self.chat(self.fit(text, steps), schema=schema(), max_tokens=ANSWER_TOKENS, cancel=cancel)
            except Exception as e:  # too long after all, or the server failed: compact harder once, else say so
                try:
                    raw, _ = self.chat(self.messages(text, steps[-1:], 0), schema=schema(), max_tokens=ANSWER_TOKENS,
                                       cancel=cancel)
                except Exception:
                    msg = (f"I couldn't go on ({str(e)[:160]}). What's done is saved and in the changelog; tell me to "
                           "continue and I'll pick up from the files and the goals.")
                    self.event("answer", text=msg)
                    self.say(msg)
                    self.history.append({"user": text, "answer": msg})
                    return msg
            try:
                step = json.loads(raw)
                act = step["action"]
            except (ValueError, KeyError, TypeError):
                steps.append({"did": {"thinking": "", "action": {"tool": "answer", "text": raw[:200]}},
                              "result": "That wasn't valid JSON; answer with one action."})
                continue
            if step.get("thinking"):
                self.event("thinking", text=step["thinking"])
                self.say(f"\033[2m{step['thinking']}\033[0m")
            if act["tool"] in ("answer", "ask"):
                msg = act.get("text") or act.get("question") or ""
                self.event("answer", text=msg)
                self.say(msg)
                self.history.append({"user": text, "answer": msg})
                return msg
            result = self.do(act)
            steps.append({"did": step, "result": result[:OBS_CHARS]})
        msg = "I stopped after many steps without finishing. Tell me how to go on."
        self.event("answer", text=msg)
        self.say(msg)
        return msg

    # --- the tools ------------------------------------------------------------------------------------------
    def path(self, rel: str) -> str:
        full = os.path.realpath(os.path.join(self.root, rel))
        if not (full == os.path.realpath(self.root) or full.startswith(os.path.realpath(self.root) + os.sep)):
            raise ValueError(f"{rel} is outside the project folder")
        if os.sep + ".cinminai" in full[len(os.path.realpath(self.root)):] + os.sep:
            raise ValueError("the .cinminai folder is AICUI's own")
        return full

    def allowed(self, tool: str, show: str) -> bool:
        """Ask in the terminal, as coding agents do — unless auto mode, no permissions, or "always" for this tool."""
        if self.mode in ("auto", "none") or tool in self.always:
            return True
        self.say(show)
        reply = self.ask(f"\033[1mAllow {tool}? [y]es / [n]o / [a]lways this session: \033[0m").strip().lower()
        if reply.startswith("a"):
            self.always.add(tool)
        return reply[:1] in ("y", "a")

    def do(self, a: dict) -> str:
        try:
            t = a["tool"]
            if t == "read":
                with open(self.path(a["path"]), encoding="utf-8", errors="replace") as f:
                    lines = f.read().splitlines()
                start = max(1, int(a.get("start") or 1))
                part = lines[start - 1:start - 1 + READ_LINES]
                more = f"\n… {len(lines) - (start - 1 + len(part))} more lines (read from line {start + len(part)})" \
                    if start - 1 + len(part) < len(lines) else ""
                return "\n".join(f"{start + i:5} {line}" for i, line in enumerate(part)) + more
            if t == "list":
                p = self.path(a.get("path") or ".")
                return "\n".join(sorted(e + ("/" if os.path.isdir(os.path.join(p, e)) else "") for e in os.listdir(p)
                                        if e != ".cinminai")) or "(empty)"
            if t == "search":
                rx, hits = re.compile(a["pattern"]), []
                for rel, is_dir, _ in tree(self.root):
                    if is_dir or len(hits) >= 60:
                        continue
                    try:
                        with open(os.path.join(self.root, rel), encoding="utf-8") as f:
                            hits += [f"{rel}:{n}: {line.strip()[:160]}" for n, line in enumerate(f, 1) if rx.search(line)]
                    except (OSError, UnicodeDecodeError):
                        pass
                return "\n".join(hits[:60]) or "no matches"
            if t in ("edit", "write"):
                return self.change(a)
            if t == "run":
                return self.run(a["command"])
            if t == "goal_add":
                g = self.goals.add(a["text"], by="ai")
                self.event("goals")
                return f"goal {g['id']} added"
            if t == "goal_done":
                self.goals.set_done(int(a["id"]), True)
                self.event("goals")
                return f"goal {a['id']} ticked"
            return f"unknown tool {t}"
        except (OSError, ValueError, re.error, KeyError, StopIteration) as e:
            return f"error: {e}"

    def change(self, a: dict) -> str:
        rel = os.path.relpath(self.path(a["path"]), self.root)
        full = os.path.join(self.root, rel)
        old = open(full, encoding="utf-8").read() if os.path.exists(full) else ""
        if a["tool"] == "edit":
            if old.count(a["old"]) != 1:
                return f"error: the text to replace appears {old.count(a['old'])} times in {rel}, not once"
            new = old.replace(a["old"], a["new"], 1)
        else:
            new = a["content"]
        diff = "".join(difflib.unified_diff(old.splitlines(True), new.splitlines(True), f"a/{rel}", f"b/{rel}"))
        colored = "\n".join(("\033[32m" if l.startswith("+") else "\033[31m" if l.startswith("-") else "") + l.rstrip("\n")
                            + "\033[0m" for l in diff.splitlines())
        if not self.allowed(a["tool"], colored or f"(no change to {rel})"):
            return "the user said no to this change"
        before = self.log.before(rel)
        os.makedirs(os.path.dirname(full) or self.root, exist_ok=True)
        with open(full, "w", encoding="utf-8", newline="") as f:
            f.write(new)
        open_goal = next((g["text"] for g in self.goals.load() if not g["done"]), "")
        e = self.log.after(rel, before, model=self.model_name, goal=open_goal,
                           what=f"{a['tool']} {rel}")
        self.event("change", id=e["id"], file=rel, added=e["added"], removed=e["removed"])
        return f"{rel} changed (+{e['added']} -{e['removed']}), logged as change {e['id']}"

    def run(self, command: str) -> str:
        if not self.admin and re.match(r"\s*(sudo|pkexec|su)\b", command):
            return "error: administrator commands aren't allowed in this session (no admin)"
        if not self.allowed("run", f"\033[36m$ {command}\033[0m"):
            return "the user said no to this command"
        argv = ["bash", "-lc", command]
        if self.sandbox:
            argv = ["bwrap", "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc", "--tmpfs", "/tmp",
                    "--bind", self.root, self.root, "--unshare-net", "--die-with-parent", "--chdir", self.root, *argv]
        try:
            r = subprocess.run(argv, cwd=self.root, capture_output=True, text=True, timeout=RUN_TIMEOUT)
        except subprocess.TimeoutExpired:
            return f"error: still running after {RUN_TIMEOUT} s, stopped"
        out = (r.stdout + r.stderr).strip()
        self.say(out[-3000:])
        tail = out[-OBS_CHARS:] if len(out) > OBS_CHARS else out
        return f"exit {r.returncode}\n{tail}"


# --- the model -------------------------------------------------------------------------------------------------
def local_backend(say=print):
    """The matcher's coding model from the user's model store; the daemon's guide is unloaded first (one card)."""
    from cin_minai.daemon import config
    from cin_minai.daemon.models import ModelStore, backend_cfg
    from cin_minai.inference import matcher
    from cin_minai.inference.llamacpp import LlamaCppBackend
    store = ModelStore()
    machine = matcher.read_machine(models_dir=store.root)
    plan = store.in_use("coding") or matcher.match(machine).get("coding")
    if not plan:
        raise SystemExit("No coding model in our list runs on this computer.")
    if not store.has(plan["file"]):  # the best one you already have that runs here, and say what else there is
        have = [(m, p) for m in matcher.CATALOG["coding"] if store.has(m.file)
                for p in [matcher.plan(m, machine, matcher.CONTEXT["coding"])] if p]
        if not have:
            raise SystemExit(f"The coding model for this computer is {plan['model']} ({plan['size'] / 2**30:.1f} GB). "
                             "It isn't downloaded yet: AICUI's model selection will offer it.")
        say(f"[2m(The best fit here would be {plan['model']}, not downloaded; using the one you have.)[0m")
        m, p = have[0]
        plan = {"model": m.name, "file": m.file, **p, "context": matcher.CONTEXT["coding"],
                "reserve_mib": matcher.margin_mib(machine.cards[0]) if machine.cards else 0}
    subprocess.run(["gdbus", "call", "--session", "--dest", "org.cinminai.Assistant1", "--object-path",
                    "/org/cinminai/Assistant1", "--method", "org.cinminai.Assistant1.Unload"],
                   capture_output=True, timeout=20)
    cfg = backend_cfg(config.load()["inference"], plan, store.path(plan["file"]))
    cfg["socket_name"] = "llama-code.sock"
    say(f"\033[2mModel: {plan['model']} ({plan['mode']}), loading…\033[0m")
    return LlamaCppBackend(cfg, lambda m: None), plan["model"]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="cinminai-code", description="The coding agent in AICUI's terminal.")
    ap.add_argument("folder", nargs="?", default=os.getcwd())
    ap.add_argument("--auto", action="store_true", help="work without asking (approved for this session)")
    ap.add_argument("--no-permissions", action="store_true",
                    help="no questions and no sandbox — strongly advised against until the model is tested")
    ap.add_argument("--admin", action="store_true", help="allow administrator commands")
    a = ap.parse_args(argv)
    mode = "none" if a.no_permissions else "auto" if a.auto else "ask"
    root = project_root(a.folder)
    if mode == "none":
        print("\033[1;31mNo permissions: the AI changes files and runs commands without asking, outside the sandbox. "
              "Don't risk anything you aren't willing to lose.\033[0m")
    backend, name = local_backend()
    agent = Agent(root, backend.chat, name, mode, a.admin, ctx=int(backend.cfg.get("context", 8192)))
    print(f"cinminai-code in {root} — {name}, mode: {mode}{', admin' if a.admin else ''}. Type your request; "
          "Ctrl+D to leave.")
    try:
        while True:
            try:
                text = input("\033[1;34myou>\033[0m ").strip()
            except EOFError:
                break
            if text:
                cancel = threading.Event()
                try:
                    agent.turn(text, cancel)
                except KeyboardInterrupt:
                    cancel.set()
                    print("(stopped)")
    finally:
        backend.unload()
    return 0


if __name__ == "__main__":
    sys.exit(main())
