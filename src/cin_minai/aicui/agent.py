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
import shlex
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
ANSWER_TOKENS = 1800   # room for one step's answer at 8K (thinking + an action); 16K gets 4096 (see Agent)
TOKENS_A_LINE = 25     # a code line in a JSON string, escapes included: the size of one write part
TICK_S = 1.5           # how often the progress of a step goes to AICUI (busy events)

STR = {"type": "string"}
ACTIONS = [
    {"tool": "read", "path": STR, "start": {"type": "integer"}},
    {"tool": "list", "path": STR},
    {"tool": "search", "pattern": STR},
    {"tool": "edit", "path": STR, "old": STR, "new": STR},
    {"tool": "write", "path": STR, "content": STR},
    {"tool": "append", "path": STR, "content": STR},
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
- edit (replace the exact text `old` with `new` in a file; `old` must appear once), write (a whole new file),
  append (add `content` to the end of a file)
- run (a shell command in the project folder{sandbox})
- goal_add / goal_done (the session goals: add one, or tick goal `id` when it's really done)
- ask (a question for the user), answer (tell the user something; ends your turn)
Rules: read before you edit; make the smallest change that does the job; after a change, check it (run the tests or
the program) before you call it done. Paths are relative to the project folder. Never invent file contents you
haven't read. At the start of a new project, ask about its goals and scope and write them as goals; once work
starts, work the goals as your to-do list. Answer in the user's language.
One step holds about {answer_tokens} tokens: a file longer than about {write_lines} lines is written in parts — write
the first part, then append the rest, one part per step, each under {write_lines} lines.
You can't see the screen: graphical programs run here without a window (SDL's dummy video and audio drivers) and web
pages aren't shown. Check your work with tests, `python3 -m py_compile`, or `timeout 5` around a program with a main
loop; the user opens the program or the page to try it.{venv}

The project's files (first lines):
{files}

Session goals:
{goals}"""


def slim(step: dict) -> str:
    """A step as it's sent again later. A write or a long edit becomes a plain sentence — never an action with
    stand-in content: shown `"content": "<219 lines written>"`, the model copied that into a real write and
    gui.py became one line of placeholder (2026-10-02). Other actions stay as they were."""
    a = dict(step.get("action", {}))
    thinking = str(step.get("thinking", ""))[:300]
    if a.get("tool") in ("write", "append"):
        n = len(str(a.get("content", "")).splitlines())
        did = "wrote" if a["tool"] == "write" else "added to the end of"
        return f"{thinking}\n(Earlier I {did} {a.get('path', '')}, {n} lines; it's on disk — read it if I need it.)"
    if a.get("tool") == "edit" and len(str(a.get("old", "")) + str(a.get("new", ""))) > 600:
        return f"{thinking}\n(Earlier I edited {a.get('path', '')}: replaced {len(str(a.get('old', '')).splitlines())} " \
               f"lines with {len(str(a.get('new', '')).splitlines())}; it's on disk.)"
    return json.dumps({"thinking": thinking, "action": a}, ensure_ascii=False)


PLACEHOLDER = re.compile(r"^\s*(<[^<>\n]{0,60}>|\.\.\.|…|# ?\.\.\.|TODO)?\s*$")


def brief(step: dict) -> str:
    a = step.get("action", {})
    what = a.get("path") or a.get("command") or a.get("pattern") or a.get("text") or ""
    return f"{a.get('tool', '?')} {str(what)[:80]}"


ESCAPE = re.compile(r'\\.|[^\\]', re.S)


def salvage(raw: str) -> tuple[str, str, str] | None:
    """A write or append cut off by the step's token limit: (tool, path, the content up to its last whole line), so
    the work isn't lost — 2026-10-03, a pygame GUI cut off at 1,800 tokens three times over, ~3½ minutes each."""
    tool = re.search(r'"tool"\s*:\s*"(write|append)"', raw)
    path = re.search(r'"path"\s*:\s*"((?:[^"\\]|\\.)*)"', raw)
    start = re.search(r'"content"\s*:\s*"', raw)
    if not (tool and path and start):
        return None
    body, end = raw[start.end():], 0
    for m in ESCAPE.finditer(body):
        if m.group() == '"':
            return None  # the content was complete: something else was cut
        if m.group() == "\\n":
            end = m.end()
    try:
        content, rel = json.loads('"' + body[:end] + '"'), json.loads('"' + path.group(1) + '"')
    except ValueError:
        return None
    return (tool.group(1), rel, content) if content.count("\n") >= 5 else None


def doing(raw: str) -> str:
    """What a step being generated is about, from its first tokens (for the progress indicator)."""
    tool = re.search(r'"tool"\s*:\s*"(\w+)"', raw)
    if not tool:
        return "thinking"
    what = re.search(r'"(?:path|command|pattern)"\s*:\s*"((?:[^"\\]|\\.){0,60})', raw)
    verb = {"write": "writing", "append": "writing", "edit": "editing", "read": "reading", "run": "running",
            "list": "looking in", "search": "searching", "answer": "answering", "ask": "asking"}.get(tool.group(1),
                                                                                                    tool.group(1))
    return f"{verb} {what.group(1)}" if what else verb


def venv_of(root: str) -> str | None:
    """The project's own Python environment (.venv or venv), as made with `python3 -m venv`."""
    for name in (".venv", "venv"):
        if os.path.exists(os.path.join(root, name, "bin", "python")):
            return os.path.join(root, name)
    return None


def venv_packages(venv: str) -> list[str]:
    found = []
    for lib in sorted(os.listdir(os.path.join(venv, "lib"))) if os.path.isdir(os.path.join(venv, "lib")) else []:
        site = os.path.join(venv, "lib", lib, "site-packages")
        for d in sorted(os.listdir(site)) if os.path.isdir(site) else []:
            if d.endswith(".dist-info"):
                name, _, version = d[:-10].partition("-")
                if name.lower() not in ("pip", "setuptools", "wheel"):
                    found.append(f"{name} {version}")
    return found[:20]


class Agent:
    def __init__(self, root: str, chat, model_name: str, mode: str = "ask", admin: bool = False,
                 ask=input, say=print, ctx: int = 8192, tick=None) -> None:
        self.root, self.chat, self.model_name, self.ctx = root, chat, model_name, ctx
        self.read_lines = READ_LINES * max(1, ctx // 8192) + (40 if ctx >= 16384 else 0)  # 8K: 80, 16K: 200
        self.obs_chars = OBS_CHARS * max(1, ctx // 8192)
        self.reads: dict = {}  # (file, from line, modified) -> the steps that read it in this task
        self.steps: list[dict] = []  # this task's steps so far (the loop guard sees which reads are still in view)
        self.cut, self.sys, self.cpt = 0, "", 3.0  # this task: steps summarized, its system text, characters a token
        self.max_steps = min(60, MAX_STEPS * max(1, ctx // 8192))  # 8K: 30 steps, 16K: 60
        # the answer limit grows with the context (it stayed at 1,800 when coding went to 16K: writes were cut off)
        self.answer_tokens = ANSWER_TOKENS if ctx < 16384 else 4096  # 8K: 1800, 16K and up: 4096 (more: a write could take 16 min)
        self.write_lines = self.answer_tokens // TOKENS_A_LINE // 10 * 10           # 8K: 70 lines, 16K: 160
        self.venv = venv_of(root)
        self.mode, self.admin, self.ask, self.say = mode, admin, ask, say
        self.tick = tick  # tick(text): the terminal's progress line while a step is generated
        self.goals, self.log = Goals(root), Changelog(root)
        self.history: list[dict] = []   # earlier turns: the user's message and the final answer
        self.events = os.path.join(root, ".cinminai", "events.jsonl")
        self.bwrap = shutil.which("bwrap") is not None
        self.sandbox = self.bwrap and mode != "none"

    # --- events for AICUI's panes --------------------------------------------------------------------------
    def event(self, kind: str, **data) -> None:
        os.makedirs(os.path.dirname(self.events), exist_ok=True)
        with open(self.events, "a", encoding="utf-8") as f:
            f.write(json.dumps({"t": time.time(), "kind": kind, **data}, ensure_ascii=False) + "\n")

    # --- the loop -------------------------------------------------------------------------------------------
    def system(self) -> str:
        files = "\n".join("  " + r +("/" if d else "") for r, d, _ in tree(self.root)[:80])
        goals = "\n".join(f"  {g['id']}. [{'x' if g['done'] else ' '}] {g['text']}" for g in self.goals.load()) or "  (none yet)"
        venv = ""
        if self.venv:
            pkgs = ", ".join(venv_packages(self.venv)) or "nothing yet"
            venv = (f"\nThe project's Python environment {os.path.basename(self.venv)}/ is active in your commands "
                    f"(`python3` and `python` are its own; installed: {pkgs}). Installing more needs the network: "
                    "ask the user to do it.")
        return SYSTEM.format(root=self.root, files=files or "  (empty)", goals=goals, venv=venv,
                             answer_tokens=self.answer_tokens, write_lines=self.write_lines,
                             sandbox=", sandboxed without network" if self.sandbox else "")

    def messages(self, text: str, steps: list[dict], cut: int = 0) -> list[dict]:
        """What the model is sent: the system text, earlier turns, this request, and this turn's steps — the first
        `cut` as one line each, the rest in full. A step's file contents are never sent again (2026-10-02: the
        blackjack run overflowed 8K by resending every written file in every step); the file is on disk to read."""
        messages = [{"role": "system", "content": self.sys or self.system()}]
        for h in self.history[-6:]:
            messages += [{"role": "user", "content": h["user"]}, {"role": "assistant", "content": h["answer"][:600]}]
        messages.append({"role": "user", "content": text})
        older = steps[:cut]
        if older:
            messages.append({"role": "user", "content": "Earlier in this task:\n" + "\n".join(
                f"- (note) {s['note'][:100]}" if "note" in s else f"- {brief(s['did'])} → {s['result'][:100]}"
                for s in older)})
        for s in steps[len(older):]:
            if "note" in s:  # a step that went wrong: said as it was, never as an action the model might copy
                messages.append({"role": "user", "content": s["note"]})
                continue
            messages.append({"role": "assistant", "content": slim(s["did"])})
            messages.append({"role": "user", "content": "Result: " + s["result"]})
        return messages

    def fit(self, text: str, steps: list[dict]) -> list[dict]:
        """The messages, shrunk to fit the context with room for the answer. Every step that fits is kept in full
        (a fixed 4 made it re-read in a loop). When they don't fit, the oldest go to one line each — enough of them
        to come down to ~60 % of the room, and that boundary then stays put: moved one step at a time, the summary
        changed every step and the server re-read the whole prompt each time (2026-10-03, 75 s a step at 12.8K)."""
        budget = (self.ctx - self.answer_tokens - 300) * self.cpt

        def size(m):
            return sum(len(x["content"]) for x in m)
        m = self.messages(text, steps, self.cut)
        if size(m) <= budget:
            return m
        for cut in range(self.cut + 1, len(steps) + 1):
            m = self.messages(text, steps, cut)
            if size(m) <= budget * 0.6:
                break
        self.cut = cut
        return m

    def generate(self, messages: list[dict], n: int, cancel) -> tuple[str, dict]:
        """One step from the model, with its progress to AICUI (busy events) and the terminal (tick) as it comes."""
        parts: list[str] = []
        last = [time.time()]

        def on_text(piece: str) -> None:
            parts.append(piece)
            if time.time() - last[0] >= TICK_S:
                last[0] = time.time()
                what = doing("".join(parts))
                self.event("busy", step=n, of=self.max_steps, doing=what, tokens=len(parts))
                if self.tick:
                    self.tick(f"step {n} · {what} · {len(parts)} tokens")
        self.event("busy", step=n, of=self.max_steps, doing="reading the request", tokens=0)
        t0 = time.time()
        raw, timings = self.chat(messages, schema=schema(), max_tokens=self.answer_tokens, cancel=cancel,
                                 on_text=on_text)
        t = timings if isinstance(timings, dict) else {}
        tokens = (t.get("prompt_n") or 0) + (t.get("cache_n") or 0)
        if tokens > 500:  # characters a token, as the server counted this prompt (code in JSON: ~2.9, not 3.3)
            self.cpt = min(3.3, max(2.0, 0.95 * sum(len(x["content"]) for x in messages) / tokens))
        self.event("timing", seconds=round(time.time() - t0, 1), prompt_n=t.get("prompt_n"),  # for diagnosis
                   cache_n=t.get("cache_n"), prompt_tps=round(t.get("prompt_per_second") or 0),
                   gen_n=t.get("predicted_n"), gen_tps=round(t.get("predicted_per_second") or 0, 1))
        return raw, t

    def unfinished(self, raw: str, cut: bool) -> str:
        """A reply that isn't a whole step: save what a cut-off write holds, and tell the model plainly what happened."""
        if not cut:
            return "Your last reply wasn't valid JSON, so nothing was done. Reply with your thinking and one action."
        limit = (f"Your last reply was cut off: one step holds about {self.answer_tokens} tokens, and it was longer. "
                 f"Write long files in parts of under {self.write_lines} lines: write the first part, then append the "
                 "rest, one part per step.")
        part = salvage(raw)
        if not part:
            return limit + " Nothing was saved."
        tool, rel, content = part
        result = self.change({"tool": tool, "path": rel, "content": content})
        if "logged as change" not in result:
            return f"{limit} The part that came through couldn't be saved ({result})."
        with open(self.path(rel), encoding="utf-8") as f:
            lines = f.read().splitlines()
        tail = "\n".join(f"{i:5} {line}" for i, line in enumerate(lines, 1))
        tail = "\n".join(tail.splitlines()[-6:])
        return (f"{limit} What came through was saved: {rel} now has {len(lines)} lines ({result}). It ends with:\n"
                f"{tail}\nContinue with append from there — don't write those lines again.")

    def turn(self, text: str, cancel: threading.Event | None = None) -> str:
        self.event("user", text=text)
        try:
            return self.work(text, cancel)
        finally:
            self.event("idle")  # AICUI's indicator goes away, also after Stop (Ctrl+C) or an error

    def work(self, text: str, cancel: threading.Event | None) -> str:
        steps: list[dict] = []
        self.reads, self.cut, self.steps = {}, 0, steps
        # the system text stays as it was at the start of the task: the file list in it changed with every new file,
        # and the server re-read the whole prompt (the model knows the files it made from its own steps)
        self.sys = self.system()
        for n in range(1, self.max_steps + 1):
            try:
                raw, t = self.generate(self.fit(text, steps), n, cancel)
            except Exception as e:  # too long after all, or the server failed: compact harder once, else say so
                try:
                    raw, t = self.generate(self.messages(text, steps[-1:], 1), n, cancel)
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
                cut = (t.get("predicted_n") or 0) >= self.answer_tokens - 2
                note = self.unfinished(raw, cut)
                self.event("note", text=note)
                self.say(f"\033[33m{note.splitlines()[0]}\033[0m")
                steps.append({"note": note})
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
            self.event("busy", step=n, of=self.max_steps, doing=doing(raw), tokens=0)
            result = self.do(act)
            steps.append({"did": step, "result": result[:self.obs_chars]})
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

    # --- the session's permissions: AICUI's choices, read again before every question ------------------------
    def session_path(self) -> str:
        return os.path.join(self.root, ".cinminai", "session.json")

    def refresh(self) -> None:
        """Ask / auto / none and admin as AICUI's choices say now. They used to restart the agent by typing Ctrl+D and
        a new command into its terminal: mid-task the keys went nowhere, or into an answer (2026-10-03)."""
        try:
            with open(self.session_path(), encoding="utf-8") as f:
                s = json.load(f)
        except (OSError, ValueError):
            return
        if s.get("mode") in ("ask", "auto", "none"):
            self.mode = s["mode"]
        self.admin = bool(s.get("admin", self.admin))
        self.sandbox = self.bwrap and self.mode != "none"

    def save_session(self) -> None:
        os.makedirs(os.path.dirname(self.session_path()), exist_ok=True)
        with open(self.session_path() + ".tmp", "w", encoding="utf-8") as f:
            json.dump({"mode": self.mode, "admin": self.admin}, f)
        os.replace(self.session_path() + ".tmp", self.session_path())
        self.event("session", mode=self.mode, admin=self.admin)

    def allowed(self, tool: str, show: str) -> bool:
        """Ask in the terminal, as coding agents do — unless auto mode or no permissions. "Always" means what it says:
        no more questions this session (it was per tool, and the next kind of action asked again)."""
        self.refresh()
        if self.mode in ("auto", "none"):
            return True
        self.say(show)
        self.event("busy", doing="waiting for your answer in the terminal")
        reply = self.ask(f"\033[1mAllow {tool}? [y]es / [n]o / [a]lways (auto from now on): \033[0m").strip().lower()
        if reply.startswith("a"):
            self.mode = "auto"
            self.save_session()  # AICUI's permission choice follows
        return reply[:1] in ("y", "a")

    def do(self, a: dict) -> str:
        try:
            t = a["tool"]
            if t == "read":
                full = self.path(a["path"])
                with open(full, encoding="utf-8", errors="replace") as f:
                    lines = f.read().splitlines()
                start = max(1, int(a.get("start") or 1))
                key = (full, start, os.path.getmtime(full))
                earlier = self.reads.setdefault(key, [])  # the steps that read this, unchanged since
                in_view = [i for i in earlier if i >= self.cut]  # still sent in full (not compacted away)
                earlier.append(len(self.steps))
                # the loop guard (2026-10-02: it re-read the same seven files for 9 minutes) — but only while the
                # earlier reads are still in view: once compaction removed them, refusing left the model without
                # the file it needed, and it asked again and again (2026-10-03, goal 5 "Combine")
                if len(in_view) >= 2:
                    return (f"You've already read {a['path']} from line {start} {len(in_view)} times in this "
                            "task, and it hasn't changed — it's above. Stop reading it: act on what you know (edit, "
                            "write, run), or ask the user.")
                part = lines[start - 1:start - 1 + self.read_lines]
                more = f"\n… {len(lines) - (start - 1 + len(part))} more lines (read from line {start + len(part)})" \
                    if start - 1 + len(part) < len(lines) else ""
                note = ("" if len(earlier) < 3 else
                        f"(You've read this {len(earlier)} times in this task: not every file fits in view at once. "
                        "Work on one file at a time, and make the change you read it for in your next step.)\n")
                return note + "\n".join(f"{start + i:5} {line}" for i, line in enumerate(part)) + more
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
            if t in ("edit", "write", "append"):
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
        elif a["tool"] == "append":
            new = old + ("\n" if old and not old.endswith("\n") else "") + a["content"]
        else:
            new = a["content"]
        text = a.get("new", "") if a["tool"] == "edit" else a["content"]
        if a["tool"] in ("write", "append") and PLACEHOLDER.match(text):  # never a stand-in for real code (see slim)
            return (f"error: that isn't file content ({text.strip()[:40]!r}). Write the complete, real contents of "
                    f"{rel}.")
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
        self.refresh()
        if not self.admin and re.match(r"\s*(sudo|pkexec|su)\b", command):
            return "error: administrator commands aren't allowed in this session (no admin)"
        if not self.allowed("run", f"\033[36m$ {command}\033[0m"):
            return "the user said no to this command"
        # the project's venv first on the path (after bash -l's profile, which may set PATH), and no window: the AI
        # can't see one, and a program waiting on a window it can't close would hold the step until the timeout
        prefix = f"export VIRTUAL_ENV={shlex.quote(self.venv)} PATH={shlex.quote(self.venv + '/bin')}:$PATH; " \
            if self.venv else ""
        argv = ["bash", "-lc", prefix + command]
        if self.sandbox:
            argv = ["bwrap", "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc", "--tmpfs", "/tmp",
                    "--bind", self.root, self.root, "--unshare-net", "--die-with-parent", "--chdir", self.root, *argv]
        env = {**os.environ, "SDL_VIDEODRIVER": "dummy", "SDL_AUDIODRIVER": "dummy",
               "PYGAME_HIDE_SUPPORT_PROMPT": "1"}
        try:
            r = subprocess.run(argv, cwd=self.root, capture_output=True, text=True, timeout=RUN_TIMEOUT, env=env)
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
    log_path = os.path.join(os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache"), "cinminai",
                            "code-server.log")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)

    def log(msg: str) -> None:  # the backend's messages (load profile, failures), for diagnosing a stall
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")
    log(f"plan: {plan['model']} | {plan['mode']} | {' '.join(plan.get('args', []))}")
    return LlamaCppBackend(cfg, log), plan["model"]


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
    def tick(text: str) -> None:  # one progress line, rewritten in place; anything said after it starts clean
        sys.stdout.write(f"\r\033[2m… {text}\033[0m\033[K")
        sys.stdout.flush()

    agent = Agent(root, backend.chat, name, mode, a.admin, ctx=int(backend.cfg.get("context", 8192)),
                  say=lambda s: print(f"\r\033[K{s}"), tick=tick)
    agent.save_session()  # this session starts as chosen, not as a session.json left from an earlier one
    print(f"cinminai-code in {root} — {name}, mode: {mode}{', admin' if a.admin else ''}. Type your request; "
          "Ctrl+C stops the AI, Ctrl+D leaves.")
    try:
        while True:
            try:
                text = input("\033[1;34myou>\033[0m ").strip()
            except EOFError:
                break
            except KeyboardInterrupt:  # Stop while nothing runs: a fresh prompt, not the end of the agent
                print()
                continue
            if text:
                cancel = threading.Event()
                try:
                    agent.turn(text, cancel)
                except KeyboardInterrupt:  # AICUI's Stop button sends Ctrl+C; the server stops when we hang up
                    cancel.set()
                    print("\r\033[K(stopped — what's done is saved and in the changelog)")
                    agent.event("answer", text="Stopped. What's done is saved and in the changelog.")
    finally:
        backend.unload()
    return 0


if __name__ == "__main__":
    sys.exit(main())
