# SPDX-License-Identifier: GPL-3.0-or-later
"""What the sidebar says, in plain words (SPEC §5.5: the user never wonders what the assistant did).
No GTK here, so it can be tested anywhere. English for the Alpha; translations come with D25's UI work.
"""

from __future__ import annotations

import json
import re

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
        what = f"Checked {TOPICS.get(args.get('topic', ''), 'this computer')} (changes nothing)"
        n = len(_problems(result))
        if n:
            what += f" — found {n} problem{'s' if n > 1 else ''}"
        return ("dialog-warning-symbolic" if n else "computer-symbolic"), what
    if tool == "open_app":
        try:
            opened = json.loads(result).get("opened") if result else None
        except ValueError:
            opened = None
        return ("system-run-symbolic", f"Opened {opened}") if opened else \
               ("dialog-warning-symbolic", "Tried to open a program, but couldn't")
    if tool == "request_install":
        return "dialog-information-symbolic", "Installing through the assistant comes in a later version"
    if tool == "make_spreadsheet":
        try:
            made = json.loads(result).get("created") if result else None
        except ValueError:
            made = None
        if made:
            return "x-office-spreadsheet-symbolic", f"Made a new spreadsheet: {made}"
        return "dialog-warning-symbolic", "Tried to make a spreadsheet, but couldn't"
    return "dialog-information-symbolic", f"Used {tool}"


def status_line(state: str, status: dict) -> tuple[str, str, str]:
    """(dot class, first line, second line) for the header."""
    dot, words = STATES.get(state, ("bad", state))
    build = status.get("build", "")
    where = {"cuda": "graphics card", "vulkan": "graphics card", "cpu": "processor"}.get(build, "")
    ctx = status.get("context", 0)
    model = status.get("model", "") or "Cin-MinAI guide"
    second = model + (f" · {where}" if where else "") + (f" · {ctx // 1024}K" if ctx else "")
    if status.get("document"):
        second += "\n" + sees(status["document"])
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


# --- commands to copy (PLAN D53) -----------------------------------------------------------------------

FENCE = re.compile(r"```[a-z]*\n(.+?)\n?```", re.S)
INLINE = re.compile(r"`((?:sudo |systemctl |apt |dkms |uname|fsck |echo \d+ \| sudo )[^`\n]+)`")


def _problems(result: str) -> list[dict]:
    try:
        r = json.loads(result) if result else {}
    except ValueError:
        return []
    return r.get("problems_found", []) if isinstance(r, dict) else []


def commands_in_result(result: str) -> list[dict]:
    """Commands the diagnostics handed over with a tool result: {"command", "explain", "undo"}."""
    return [{"command": p["command"], "explain": p.get("command_explained", ""), "undo": p.get("undo", "")}
            for p in _problems(result) if p.get("command")]


def commands_in_text(text: str) -> list[dict]:
    """Commands the guide wrote itself: a fenced block, or a command in backticks."""
    found = [m.strip() for m in FENCE.findall(text)] + INLINE.findall(text)
    return [{"command": c, "explain": "", "undo": ""} for c in found if c]


def merge_cards(*lists: list[dict]) -> list[dict]:
    """One card per command, the first (the one with an explanation) wins."""
    out, seen = [], set()
    for card in (c for lst in lists for c in lst):
        key = " ".join(card["command"].split())
        if key not in seen:
            seen.add(key)
            out.append(card)
    return out


def card_notes(card: dict) -> list[str]:
    notes = []
    if card.get("explain"):
        notes.append(f"What it does: {card['explain']}")
    if card.get("undo"):
        notes.append(f"To undo: {card['undo']}")
    if card["command"].lstrip().startswith("sudo") or "| sudo" in card["command"]:
        notes.append("It asks for your password: that's you saying yes.")
    notes.append("Copy, then paste it in the Terminal with Ctrl+Shift+V and press Enter.")
    return notes


# --- document edits: the preview card (SPEC §7.8) ------------------------------------------------------

GRID_ROWS, GRID_COLS, CELL_CHARS = 8, 5, 14


def _cell(v) -> str:
    s = "" if v is None else str(v)
    if s.endswith(".0") and s[:-2].lstrip("-").isdigit():
        s = s[:-2]
    return s if len(s) <= CELL_CHARS else s[:CELL_CHARS - 1] + "…"


def grid(rows) -> list[list[str]]:
    """A range for the card: at most GRID_ROWS x GRID_COLS, with … where it's cut."""
    out = [[_cell(v) for v in r[:GRID_COLS]] + (["…"] if len(r) > GRID_COLS else []) for r in rows[:GRID_ROWS]]
    if len(rows) > GRID_ROWS:
        out.append(["…"])
    return out


def preview_parts(pv: dict) -> dict:
    """{"title", "kind": "text" | "grid" | "slide", "before", "after"} for the card."""
    before, after = pv.get("before"), pv.get("after")
    title = pv.get("summary", "A change to your document")
    if isinstance(after, list):
        return {"title": title, "kind": "grid", "before": grid(before or []), "after": grid(after)}
    if isinstance(after, dict):
        show = lambda d: "\n".join(x for x in ((d or {}).get("title", ""), (d or {}).get("body", "")) if x)
        return {"title": title, "kind": "slide", "before": show(before), "after": show(after)}
    return {"title": title, "kind": "text", "before": str(before or ""), "after": str(after or "")}


def decided(result: dict | None, error: str | None) -> str:
    if error:
        return f"Not changed: {error}"
    if result and result.get("applied"):
        return "Done. Press Ctrl+Z in LibreOffice to undo it in one step."
    return "Discarded. Your document is unchanged."


def sees(document: str) -> str:
    return f'Sees: document "{document}"' if document else ""


ASKED = {  # LibreOffice's Assistant menu -> the question the sidebar asks (SPEC §7.6)
    "ask-selection": None,  # the user types the question
    "rewrite-selection": "Rewrite the selected text so it reads better.",
    "explain-formula": "Explain the formula in the selected cell in simple words.",
    "summarize": "Summarize this document in a few sentences.",
}


# --- writing projects (D54) ----------------------------------------------------------------------------

PROJECT_HELLO = ("Tell me about your story: the people, the places, what happens, how it should feel. I'll keep "
                 "notes. When you're ready, click Write it up.")


def project_bar(title: str) -> str:
    return f"Writing: {title}" if title else ""


def outline_lines(outline: dict) -> list[str]:
    return [f"{i}. {s.get('title', '')}: {s.get('what_happens', '')}" for i, s in enumerate(outline.get("scenes", []), 1)]


def draft_progress(p: dict) -> str:
    return f"Writing scene {p.get('scene')} of {p.get('of')}: {p.get('title', '')}"


def draft_done(res: dict) -> str:
    pages = -(-int(res.get("lines", 0)) // 28)
    return f"Saved {res.get('shown', '')}: {res.get('words', 0)} words, about {pages} pages"


NOTE_LABELS = {"facts": "Facts", "characters": "Characters", "places": "Places", "ideas": "Ideas"}


def notes_lines(notes: dict) -> list[str]:
    out = []
    for k, label in NOTE_LABELS.items():
        if notes.get(k):
            out.append(f"{label}:")
            out += [f"  • {n}" for n in notes[k]]
    return out or ["No notes yet: tell me about your story."]
