# SPDX-License-Identifier: GPL-3.0-or-later
"""The cloud as advisor: the local models do the work, a cloud model is asked when it helps (Ian, 2026-10-13: "this
was about incorporating the local with the cloud"). The pattern of Anthropic's advisor tool, turned around: there a
cheap cloud model asks a stronger one; here the local model asks the cloud.

The lead local model (alone, team A's coder or team B's Senior) has an `advisor` tool: its question goes to the cloud
model with what it needs to answer — the request, the plan and goals, the last steps, what the checks find — and the
advice comes back as the result. AICUI also asks by itself when the work has stalled (no progress for 12 steps,
before the stuck rule stops it). A few calls a request; each one against the project's budget, its cost logged, and
shown in the chat both ways. Nothing else goes to the cloud.
"""

from __future__ import annotations

import os

MAX_USES = 5        # advisor calls in one request
STEPS_SHOWN = 8     # the last steps the advisor reads
ANSWER_TOKENS = 900

SYSTEM = """You advise a local coding model that is building a project on the person's own computer. You can't act
or see the files; you read its request, its plan and goals, its last steps and what the checks find, and answer its
question. It is smaller than you: it loses the thread, repeats steps, guesses where it should read, and stops at a
problem it could solve. Answer with what it should do next — concrete steps, the files and functions they concern,
the likely cause of an error and how to check it. Short: a few lines, at most a short code fragment where an exact
change is needed. If its approach is wrong, say so plainly and give the better one. Never ask it to call you
again.
Facts the project needs — card data, rules, names, numbers, prices — come only from the sources it has fetched
(sources/, notes/, data/, gathered records): tell it which to read or distill, or what to fetch. Never give example
data with values of your own, and never tell it to type facts from memory: a value you're not sure of is a wrong
value in its project."""


class Advisor:
    def __init__(self, agent, backend, name: str) -> None:
        self.agent, self.backend, self.name = agent, backend, name
        self.uses = 0

    def reset(self) -> None:
        """A new request: its calls start again."""
        self.uses = 0

    def ask(self, question: str, why: str = "") -> str:
        from cin_minai.inference.cloud import CloudError
        question = " ".join(str(question).split())
        if len(question) < 8:
            return "error: say what you want to know from the advisor (the question)"
        if self.uses >= MAX_USES:
            return (f"error: the advisor has answered {MAX_USES} times in this request — go on with what it said, or "
                    "ask the person")
        self.agent.event("handoff", by="coder", to="advisor", text=(f"({why}) " if why else "") + question)
        self.agent.say(f"\033[1;34m☁ Asking the cloud advisor ({self.name}){' — ' + why if why else ''}: "
                       f"{question[:200]}\033[0m")
        try:
            text, _ = self.backend.chat([{"role": "system", "content": SYSTEM},
                                         {"role": "user", "content": self.brief(question)}], max_tokens=ANSWER_TOKENS)
        except CloudError as e:
            return f"error: the cloud advisor couldn't answer ({e})"
        self.uses += 1
        text = str(text).strip() or "(no advice)"
        self.agent.event("handoff", by="advisor", to="coder", text=text)
        self.agent.say(f"\033[34m☁ The cloud advisor says:\n{text}\033[0m")
        return f"Advice from {self.name} (the cloud advisor):\n{text}"

    def brief(self, question: str) -> str:
        """What the advisor reads: the request, the plan, the last steps, the checks — as text, nothing else."""
        from .agent import REQUEST_FILE, slim
        a = self.agent
        parts = [f"The person's request: {getattr(a, 'request_text', '')[:1500]}"]
        try:
            with open(os.path.join(a.root, REQUEST_FILE), encoding="utf-8") as f:
                first = f.read().strip()
            if first and first != getattr(a, "request_text", ""):
                parts.append(f"The project's first request: {first[:1500]}")
        except OSError:
            pass
        goals = a.goals.load()
        if goals:
            parts.append("The plan's goals:\n" + "\n".join(
                f"{g['id']}. [{'x' if g['done'] else ' '}] {g['text'][:160]}"
                + (f" (files: {', '.join(g.get('files') or [])[:160]})" if g.get("files") else "") for g in goals[:30]))
        files = [r for r, d, _ in __import__("cin_minai.aicui.project", fromlist=["tree"]).tree(a.root)[:60] if not d]
        if files:
            parts.append("Its files: " + ", ".join(files))
        steps = [s for s in getattr(a, "steps", []) if isinstance(s, dict)][-STEPS_SHOWN:]
        lines = []
        for s in steps:
            if "note" in s:
                lines.append(f"- (AICUI told it) {s['note'][:300]}")
            elif s.get("did"):
                lines.append(f"- {slim(s['did'])[:400]}\n  → {str(s.get('result', ''))[:500]}")
        if lines:
            parts.append("Its last steps:\n" + "\n".join(lines))
        try:
            problems = a.problems()[:10]
        except Exception:
            problems = []
        if problems:
            parts.append("What the checks find now:\n" + "\n".join(f"- {p}" for p in problems))
        parts.append(f"Its question: {question}")
        return "\n\n".join(parts)
