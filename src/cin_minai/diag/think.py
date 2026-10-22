# SPDX-License-Identifier: GPL-3.0-or-later
"""Think it through (PLAN D7): past the end of the diagnostic trees — no rule recognises the fault, its cause is
unknown, or the tree's fixes are used up — the person may ask the model to reason over what the checks recorded.
Offered, never automatic (Rule 9). The answer is plain text, not a tool call: thinking doesn't meet the schema the
tool calls are held to (D6), and nothing is run — the person decides, as everywhere (SPEC §20.1 principle 5).

This module is the request itself, so the measurement (training/eval/guide/think_eval.py) measures what ships.
Measured 2026-10-21 on the 4070: the 27B coding model thinking got the cause right 13 of 14 times and cited the
evidence, in 1-3 minutes; plain, 14 of 14 in 6 s but surer than the evidence allows; the 4B guide can't finish a
thought (0 of 18), so without a coding model the guide answers plainly. The thinking budget keeps the longest from
running out of room (one ran past 6144 tokens and never answered).
"""

from __future__ import annotations

SYSTEM = """You help a person who is new to Linux Mint find out why their computer has a problem. The built-in \
checks recorded what they could, but no fixed rule explains it, so you reason it through from the evidence below.

Answer in plain words, for someone who isn't technical:
1. The likeliest cause, in one or two sentences, and which lines of the evidence point to it.
2. The one next step that is safe to try first: the way without the terminal if there is one. A command only if it \
only reads, and say what it does.
3. What would tell them it worked.
If the evidence isn't enough to tell, say so and say what to look at next. Never suggest reinstalling the system, \
deleting files, formatting a disk or removing packages. Never claim more certainty than the evidence gives. Keep it \
under 180 words, in the person's language."""


BUDGET = 4096  # thinking tokens; then the server tells it to answer
BUDGET_MESSAGE = " That is enough thinking; time to write the answer."
ANSWER_TOKENS = 800
SAMPLING = {"temperature": 0.6, "top_p": 0.95, "top_k": 20}  # Qwen's advice for thinking (greedy can loop)
EVIDENCE_CHARS = 12000  # the report is ~3-6K; a long one is cut, not the request
MIN_BUDGET = 2048  # less isn't worth the wait: measured answers thought 600-4300 tokens
CHARS_PER_TOKEN = 3  # a cautious guess for English and logs (Japanese runs denser: still within the margin)


def budget(context: int, msgs: list[dict]) -> int:
    """The thinking budget that fits: the prompt, the thinking and the answer in the model's context. Under
    MIN_BUDGET (the ladder stepped down far) it's 0: a plain answer, not one cut off mid-thought."""
    prompt = sum(len(m["content"]) for m in msgs) // CHARS_PER_TOKEN + 64
    room = min(BUDGET, context - prompt - ANSWER_TOKENS)
    return room if room >= MIN_BUDGET else 0


def evidence(rep_markdown: str, found: str = "") -> str:
    """What the checks recorded: the topic's own reading (inspect_system's result), then the full report."""
    text = (f"## What the assistant's check read\n\n{found}\n\n" if found else "") + rep_markdown
    return text if len(text) <= EVIDENCE_CHARS else text[:EVIDENCE_CHARS] + "\n\n(cut here: the report goes on)"


def messages(question: str, evidence: str) -> list[dict]:
    """The request: the person's words and what the checks recorded (the report's Markdown, or the part of it the
    trees couldn't explain)."""
    return [{"role": "system", "content": SYSTEM},
            {"role": "user", "content": f"What the person said: {question}\n\nWhat the checks recorded:\n\n{evidence}"}]
