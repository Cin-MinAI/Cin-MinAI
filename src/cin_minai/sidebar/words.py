# SPDX-License-Identifier: GPL-3.0-or-later
"""What the sidebar says, in plain words (SPEC §5.5: the user never wonders what the assistant did).
No GTK here, so it can be tested anywhere. English for the Alpha; translations come with D25's UI work.
"""

from __future__ import annotations

import json

TOPICS = {
    "overview": "what kind of computer this is", "storage": "the disk space", "network": "the network",
    "updates": "the updates", "printers": "the printers", "sound": "the sound", "display": "the screens",
    "battery": "the battery", "drivers": "the drivers",
}

STATES = {  # State property -> (dot colour class, words)
    "idle": ("ok", "Ready"),
    "thinking": ("busy", "Answering…"),
    "loading": ("busy", "Getting ready…"),
    "off": ("off", "Resting (starts when you ask)"),
    "error": ("bad", "Not available"),
    "offline": ("bad", "Not running"),
}


def action(tool: str, args: dict, result: str = "") -> tuple[str, str]:
    """(icon name, words) for a tool the guide used."""
    if tool == "lookup_help":
        return "system-search-symbolic", "Looked it up in the built-in help"
    if tool == "inspect_system":
        return "computer-symbolic", f"Checked {TOPICS.get(args.get('topic', ''), 'this computer')} (changes nothing)"
    if tool == "open_app":
        try:
            opened = json.loads(result).get("opened") if result else None
        except ValueError:
            opened = None
        return ("system-run-symbolic", f"Opened {opened}") if opened else \
               ("dialog-warning-symbolic", "Tried to open a program, but couldn't")
    if tool == "request_install":
        return "dialog-information-symbolic", "Installing through the assistant comes in a later version"
    return "dialog-information-symbolic", f"Used {tool}"


def status_line(state: str, status: dict) -> tuple[str, str, str]:
    """(dot class, first line, second line) for the header."""
    dot, words = STATES.get(state, ("bad", state))
    build = status.get("build", "")
    where = {"cuda": "graphics card", "vulkan": "graphics card", "cpu": "processor"}.get(build, "")
    ctx = status.get("context", 0)
    model = status.get("model", "") or "Cin-MinAI guide"
    second = model + (f" · {where}" if where else "") + (f" · {ctx // 1024}K" if ctx else "")
    if status.get("reduced"):
        second += f"\n{status['reduced']}"
    elif state == "error" and status.get("detail"):
        second += f"\n{status['detail']}"
    return dot, words, second


def waiting(state: str, build: str) -> str:
    """What to show in an answer that hasn't started yet."""
    if state == "loading":
        return "Getting the assistant ready. The first time can take a minute or two."
    if build == "cpu":
        return "Reading your question… (on the processor this can take up to a minute)"
    return "Reading your question…"
