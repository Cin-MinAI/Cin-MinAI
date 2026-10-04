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
    if tool == "terminal":
        return "utilities-terminal-symbolic", "Looked at your terminal (changes nothing)"
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
INLINE = re.compile(r"`((?:sudo |systemctl |apt |dkms |uname|fsck |echo \d+ \| sudo "
                    # M3: ordinary shell commands, now that answers can be about the person's terminal
                    r"|python3? |pip3? |\.venv/bin/|source |\. \.venv|cd |chmod |ls\b|pwd\b|mkdir |git |make\b|gcc |"
                    r"bash |\./)[^`\n]*)`")


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
    """The plan by the story circle's steps (D56): each step's name, then its scenes."""
    out, step = [], None
    for i, s in enumerate(outline.get("scenes", []), 1):
        if s.get("step_name") and s["step_name"] != step:
            step = s["step_name"]
            out.append(f"{step}:")
        out.append(f"{'  ' if step else ''}{i}. {s.get('title', '')}: {s.get('what_happens', '')}")
    return out


# --- the story circle (D56) ------------------------------------------------------------------------------

SHAPES = ["A story in one chapter"] + [f"A story over {n} chapters" for n in range(2, 9)]


def shape_index(info: dict) -> int:
    return 0 if info.get("shape") != "chapters" else max(0, min(7, int(info.get("chapters", 4)) - 1))


def shape_settings(index: int) -> dict:
    return {"shape": "chapter"} if index <= 0 else {"shape": "chapters", "chapters": index + 1}


def circle_lines(info: dict) -> list[str]:
    circle = info.get("circle", {})
    out = ["The story circle (Dan Harmon's):"]
    for i, s in enumerate(info.get("steps", []), 1):
        out.append(f"  {i}. {s['name']} ({s['means']}): " + (" ".join(circle.get(s["key"], [])) or "not yet"))
    return out


STEP_NAMES = {"you": "You", "need": "Need", "go": "Go", "search": "Search", "find": "Find", "take": "Take",
              "return": "Return", "change": "Change"}
QUOTES = "\"'“”„«» "  # the model's own quote marks around a quote (2026-10-01: ""Elena, the founder…"")
STATUS_MARKS = {"written": "✓", "partly written": "◐", "planned": "·", "missing": "○"}


def review_title(review: dict) -> str:
    if review.get("chapter"):
        return f"Before chapter {review['chapter']} of {review.get('of')}: where the story is"
    return "Before writing: where the story is"


def review_step(k: str, s: dict) -> str:
    shown = f' — "{s["evidence"].strip(QUOTES)}"' if s.get("status") in ("written", "partly written") and s.get("evidence") else ""
    return f"{STEP_NAMES.get(k, k)} ({s.get('status', '')}): {s.get('what', '')}{shown}"


def review_steps(review: dict) -> list[tuple[str, str, bool]]:
    """The card's tick boxes (D57): (step, its line, ticked = the review found it written). The writer's ticks
    decide where the chapter starts."""
    return [(k, review_step(k, s), s.get("status") == "written") for k, s in review.get("steps", {}).items()]


def would_cover(review: dict, ticked) -> list[str]:
    """Where the chapter starts with these ticks: the first step not ticked, the steps left paced over the chapters
    left — the same rule as the daemon's (writer.next_steps; a test keeps them equal)."""
    order = list(STEP_NAMES)
    chapter, of = review.get("chapter"), review.get("of") or 1
    if not chapter:
        return order
    start = next((i for i, k in enumerate(order) if k not in ticked), len(order))
    left = order[start:] or order[-1:]
    return left[:-(-len(left) // max(1, of - chapter + 1))]


def cover_line(review: dict, steps: list[str]) -> str:
    if not review.get("chapter"):
        return ""
    return f"Chapter {review['chapter']} would cover: " + ", ".join(STEP_NAMES.get(k, k) for k in steps) + "."


def review_lines(review: dict, steps: bool = True) -> list[str]:
    """The review before a chapter (D57), in the order a writer reads it; steps=False leaves out the circle and
    the chapter line (the card shows them as tick boxes and a line that follows them)."""
    out = []
    if steps:
        out.append("The story circle:")
        out += [f"  {STATUS_MARKS.get(s.get('status'), '·')} {review_step(k, s)}" for k, s in review.get("steps", {}).items()]
    if review.get("characters"):
        out.append("The characters:")
        out += [f"  • {c.get('name', '')}, at {STEP_NAMES.get(c.get('step'), c.get('step', ''))}: {c.get('where', '')}"
                for c in review["characters"]]
    if review.get("missing"):
        out.append("Still missing:")
        out += [f"  • {m}" for m in review["missing"]]
    if review.get("questions"):
        out.append("Questions for you:")
        out += [f"  • {q}" for q in review["questions"]]
    nxt = review.get("next_steps", [])
    if steps and review.get("chapter") and nxt:
        out.append(cover_line(review, nxt))
    return out


# --- the manuscript (D58) ---------------------------------------------------------------------------------

MANUSCRIPT_TIP = "Your chapters as they are now, in the format agents and publishers expect (.odt and Word)."
MANUSCRIPT_INTRO = ("This puts your chapters, as they are now (your own edits included), into one new document in "
                    "standard manuscript format: a title page, double spacing, a page header with your name, each "
                    "chapter on a new page. You get it as a LibreOffice file and as a Word file, which most agents "
                    "and publishers ask for. Your drafts stay as they are.")


def manuscript_done(res: dict) -> str:
    import os
    name = os.path.basename(res.get("odt", ""))[:-4]
    n = res.get("chapters", 0)
    return (f"Your manuscript is ready: {n} chapter{'s' if n != 1 else ''}, {res.get('words', 0):,} words, "
            f"{res.get('paper', '')} paper. It's open in Writer and saved in the project folder as \"{name}\", "
            ".odt and .docx (for Word).")


# --- a bigger model for writing (D60) ---------------------------------------------------------------------

def offer_title(o: dict) -> str:
    return "Your computer can run a stronger writing model"


def offer_lines(o: dict) -> list[str]:
    lo, hi = o.get("tok_s", [0, 0])
    lines = [f"{o.get('model', '')}: {o.get('why', '')}.",
             f"Here it would run {o.get('mode', '')}, about {lo * 45:.0f}-{hi * 45:.0f} words a minute."]
    if o.get("downloaded"):
        lines.append("It's already downloaded.")
    elif o.get("parked_on"):
        lines.append(f"It's on {o['parked_on']}: it'll be copied back to this computer and checked, no download needed.")
    else:
        lines.append(f"The download is {o.get('size', 0) / 2**30:.1f} GB from Hugging Face, checked against its checksum "
                     "before it's used. Nothing is sent or fetched until you click Download.")
    if not o.get("space_ok", True):
        lines.append("There isn't enough free disk space for it right now.")
    return lines


def download_progress(p: dict) -> str:
    if p.get("testing"):
        return f"Checked. Testing {p.get('model', '')} on this computer…"
    return f"Downloading {p.get('model', '')}: {p.get('have_gb', '0')} of {p.get('total_gb', '?')} GB"


def download_done(p: dict) -> str:
    return f"{p.get('model', '')} is ready: {p.get('measured', 0):.0f} tokens a second here."


def model_line(in_use: dict | None) -> str:
    if not in_use:
        return "Writing uses the built-in guide."
    m = in_use.get("measured")
    return f"Writing uses {in_use.get('model', '')}" + (f" ({m:.0f} tokens a second here)." if m else ".")


def next_chapter_line(info: dict) -> str:
    if info.get("shape") != "chapters":
        return "Write it up reviews your notes, then plans the whole circle in one chapter."
    return (f"Write it up reads the story so far, shows where it is on the circle, then plans chapter "
            f"{info.get('next_chapter')} of {info.get('chapters')}.")


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


# --- the journal (D55) -----------------------------------------------------------------------------------

JOURNAL_HELLO = "How was your day? Tell me whatever you'd like to remember. I'll only ask, never judge."


def entry_label(e: dict) -> str:
    when = e.get("when", "").replace("T", " ")[:16]
    return f"🔒 {when}  (private)" if e.get("private") else f"{when}  {e.get('title', '')}"


def journal_written(e: dict) -> str:
    return ("Entry written and locked" if e.get("private") else f"Entry written: {e.get('title', '')}") + \
        f" ({e.get('words', 0)} words)"


# --- web search (D55, SPEC §7.5) ---------------------------------------------------------------------------

def search_note(offer: dict) -> str:
    if not offer.get("online", True):
        return "This computer is offline. Connect to the internet first; nothing is sent until you click Search."
    return (f"Only these words are sent, to {offer.get('provider', 'the search engine')}. The pages it finds are "
            "read to answer you. Nothing about you or this computer is sent.")


def source_line(s: dict) -> str:
    import urllib.parse
    host = urllib.parse.urlsplit(s.get("url", "")).hostname or ""
    return f"[{s.get('n')}] {s.get('title', '')} — {host}"


# --- "Put in Writer" ------------------------------------------------------------------------------------

def worth_a_document(text: str) -> bool:
    """A real answer (a poem, steps, the PC's specs), not a one-liner or an offer the user still has to click."""
    t = text.strip()
    if len(t.split()) < 25:
        return False
    return not t.startswith(("I can look that up", "I'd need to look that up", "I've prepared this change"))


def document_title(first_line: str) -> str:
    t = first_line.strip().strip("#*:").strip()
    words_ = t.split()
    return " ".join(words_[:8]).rstrip(",.;:") if words_ else "From the assistant"


# --- the bigger model for an unusual terminal error (M3) ---------------------------------------------------------
def bigger_offer(offer: dict) -> str:
    return f"This error isn't in the built-in help. Ask {offer.get('model') or 'the bigger model'}?"


def bigger_note(offer: dict) -> str:
    return ("It's the larger model already on this computer. Loading it takes about a minute, and the assistant is "
            "back to normal with your next question. Nothing leaves this computer.")


def bigger_running(args: dict) -> str:
    return f"Loading {args.get('model') or 'the bigger model'}…"


def bigger_done(result: dict) -> str:
    return f"Answered by {result.get('model') or 'the bigger model'}; the assistant comes back with your next question"


def sent_to_terminal(reply: dict) -> str:
    """What happened after "To terminal" (M3)."""
    if reply.get("ok"):
        warn = "; ".join(reply.get("warnings") or [])
        return "It's at your prompt: check it, then press Enter in the terminal to run it." + (f" Careful: {warn}." if warn else "")
    return f"Not sent: {reply.get('error') or 'the terminal didn’t accept it'}."
