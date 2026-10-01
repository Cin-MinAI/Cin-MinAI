# SPDX-License-Identifier: GPL-3.0-or-later
"""The writing partner and the write-up (PLAN D54): gather, then outline, then a rough draft scene by scene.

Built on the probe of 2026-09-30 (the guide wrote a usable scene, but ran ahead of its outline and drifted
from a fact): every scene is written with the project's notes as fixed facts, the whole outline, and a short
summary of what's already written, and is told to stay inside its own scene. The model only ever writes
prose or fills a JSON schema; files are written by our code (odt.py), never overwriting anything.

`chat(messages, schema=None, max_tokens=..., cancel=..., sampling=...) -> (text, timings)` is the backend's.
"""

from __future__ import annotations

import json
import re
import threading
from typing import Callable

from cin_minai.inference.backend import Cancelled

from . import odt
from .projects import NOTE_KEYS, Project

# prose: a little randomness, and llama.cpp's DRY sampler against loops (2026-10-01 "Grandman Stan": scene 1
# repeated whole paragraphs three times with repeat_penalty alone)
WRITE = {"temperature": 0.7, "top_p": 0.9, "repeat_penalty": 1.05, "presence_penalty": 0.3,
         "dry_multiplier": 0.8, "dry_base": 1.75, "dry_allowed_length": 2,
         "dry_penalty_last_n": 1024}  # -1 ("all") is refused by llama-server v0.5.0's request check: a scene is <1,200
CJK = re.compile(r"[぀-ヿ㐀-鿿가-힯＀-￯]+")


def _words(p: str) -> set[str]:
    return set(re.findall(r"\w+", p.lower()))


def _same(a: str, b: str) -> bool:
    """Two paragraphs that say the same thing: equal, or 85 % of the same words."""
    wa, wb = _words(a), _words(b)
    if not wa or not wb:
        return a.strip() == b.strip()
    return len(wa & wb) / max(len(wa), len(wb)) >= 0.85


def clean_scene(text: str, previous_end: str, cjk_ok: bool) -> tuple[str, dict]:
    """What the model wrote, without its loops: paragraphs that repeat an earlier one (or the previous scene's
    ending, which it was shown) are dropped, and stray Chinese characters in a non-CJK story are removed
    ("sharp and清脆 like glass", 2026-10-01)."""
    kept, dropped, cjk = [], 0, 0
    for p in odt.paragraphs(text):
        if not cjk_ok and CJK.search(p):
            cjk += len(CJK.findall(p))
            p = re.sub(r"\s{2,}", " ", CJK.sub(" ", p)).replace(" ,", ",").replace(" .", ".").strip()
        if (previous_end and _same(p, previous_end)) or any(_same(p, k) for k in kept):
            dropped += 1
            continue
        if p:
            kept.append(p)
    return "\n\n".join(kept), {"repeats_dropped": dropped, "cjk_removed": cjk}
SCENES = (6, 8)
WORDS_PER_SCENE = 650          # 8 scenes ~ 5,200 words ~ 520 lines ~ 18 A5 pages (odt.py)
MAX_LINES = 600                # Ian: "600 lines max"

PARTNER = """You are a writing partner built into this computer, helping the user with their own story, "{title}". \
Right now you are only gathering: the user tells you ideas, characters, places and things that happen, and you \
listen. Reply in one to three short sentences, in the user's language: say what you understood, then ask one \
question that helps the story (who, where, why, what happens next, how it should feel). Don't write the story \
yet, don't make up details they didn't give, and never judge the ideas. When they're ready, they press \
"Write it up".

What you know so far:
{notes}"""

NOTES_SCHEMA = {"type": "object", "additionalProperties": False, "required": list(NOTE_KEYS),
                "properties": {k: {"type": "array", "items": {"type": "string"}, "maxItems": 8} for k in NOTE_KEYS}}
NOTES_PROMPT = """Take notes for a writer. The user is the writer: what they say about themselves or their \
plans ("I want to write a book", "chapter one") is not part of the story. From the user's latest message only, \
list what's NEW for the story, in short sentences, in the user's language: facts (things that are true in the \
story's world), characters (name and who they are), places, ideas (things they want in it, and how it should \
feel: tone, mood, humour). Leave a list empty when the message has nothing for it. Don't repeat what's \
already noted, and don't invent anything.

Already noted:
{notes}"""

OUTLINE_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["chapter_title", "scenes"],
                  "properties": {"chapter_title": {"type": "string"},
                                 "scenes": {"type": "array", "minItems": SCENES[0], "maxItems": SCENES[1],
                                            "items": {"type": "object", "additionalProperties": False,
                                                      "required": ["title", "what_happens"],
                                                      "properties": {"title": {"type": "string"},
                                                                     "what_happens": {"type": "string"}}}}}}
OUTLINE_PROMPT = """Plan one chapter of the user's story "{title}" as {lo} to {hi} scenes, in the user's \
language. Use their notes; every fact in them stays true. Each scene: a short title and two or three sentences \
on what happens in it. Spread the events out: each scene moves the story one step.

{notes}
{wish}"""

SCENE_PROMPT = """You are writing a rough first draft of the user's story "{title}", chapter "{chapter}", in the \
language of their notes.

{notes}

The chapter's plan:
{plan}

The story so far:
{so_far}
{last}
Now write scene {n} of {total}, "{scene}", in full: about {words} words of story prose. Write only what \
happens in this scene ({what}); stop at its end and don't start on later scenes. Continue from exactly where \
the story is now: don't repeat anything that already happened. Keep every fact above true. No headings, no \
notes, no title — just the prose."""

SUMMARY_PROMPT = """Summarize this scene in two sentences for the writer's memory: what happened and how it \
ended. Same language as the scene.

{scene}"""


def _last_paragraph(text: str) -> str:
    """Where the story is now (2026-10-01: with only a summary, scene 4 found the bottle scene 3 had found)."""
    paras = odt.paragraphs(text)
    return paras[-1][-700:] if paras else ""


def plan_text(outline: dict) -> str:
    return "\n".join(f"{i}. {s['title']}: {s['what_happens']}" for i, s in enumerate(outline["scenes"], 1))


class Writer:
    def __init__(self, chat: Callable) -> None:
        self.chat = chat

    # --- gathering ----------------------------------------------------------------------------------------
    def reply(self, project: Project, text: str, on_text: Callable[[str], None], cancel: threading.Event) -> str:
        """One gathering turn: a short reply that keeps the conversation going, then the notes it gave."""
        history = project.data["messages"][-12:]
        messages = [{"role": "system", "content": PARTNER.format(title=project.title, notes=project.notes_text())},
                    *history, {"role": "user", "content": text}]
        out, _ = self.chat(messages, max_tokens=200, on_text=on_text, cancel=cancel, sampling=WRITE)
        project.remember("user", text)
        project.remember("assistant", out.strip())
        self.take_notes(project, text, cancel)
        return out.strip()

    def take_notes(self, project: Project, text: str, cancel: threading.Event | None = None) -> int:
        raw, _ = self.chat([{"role": "system", "content": NOTES_PROMPT.format(notes=project.notes_text())},
                            {"role": "user", "content": text}], schema=NOTES_SCHEMA, max_tokens=400, cancel=cancel)
        try:
            return project.add_notes(json.loads(raw))
        except (ValueError, TypeError):
            return 0

    # --- the write-up -------------------------------------------------------------------------------------
    def outline(self, project: Project, wish: str = "", cancel: threading.Event | None = None) -> dict:
        prompt = OUTLINE_PROMPT.format(title=project.title, lo=SCENES[0], hi=SCENES[1], notes=project.notes_text(),
                                       wish=f"What the writer asked for: {wish}" if wish else "")
        raw, _ = self.chat([{"role": "user", "content": prompt}], schema=OUTLINE_SCHEMA, max_tokens=1100, cancel=cancel)
        return json.loads(raw)

    def draft(self, project: Project, outline: dict, on_progress: Callable[[int, int, str], None],
              cancel: threading.Event) -> dict:
        """Write the chapter scene by scene into a new .odt in the project folder. on_progress(n, total, what)."""
        scenes, summaries = [], []
        cleanup: dict[str, int] = {}
        cjk_ok = bool(CJK.search(project.notes_text() + project.title))  # a Japanese story keeps its script
        total = len(outline["scenes"])
        budget = MAX_LINES
        for n, s in enumerate(outline["scenes"], 1):
            if cancel.is_set():
                break
            words = min(WORDS_PER_SCENE, max(150, (budget * odt.WORDS_PER_LINE) // max(1, total - n + 1)))
            on_progress(n, total, s["title"])
            prompt = SCENE_PROMPT.format(title=project.title, chapter=outline["chapter_title"], notes=project.notes_text(),
                                         plan=plan_text(outline), n=n, total=total, scene=s["title"],
                                         what=s["what_happens"], words=words,
                                         so_far="\n".join(f"Scene {i}: {t}" for i, t in enumerate(summaries, 1))
                                         or "(this is the first scene)",
                                         last=(f'\nThe story so far ends with these words — already written; begin '
                                               f'right after them and don\'t repeat them:\n"{_last_paragraph(scenes[-1])}"\n'
                                               if scenes else ""))
            try:
                text, _ = self.chat([{"role": "user", "content": prompt}], max_tokens=int(words * 1.8), cancel=cancel,
                                    sampling=WRITE)
            except Cancelled:  # Stop mid-scene: keep the scenes already written
                break
            text, fixed = clean_scene(text, _last_paragraph(scenes[-1]) if scenes else "", cjk_ok)
            for k, v in fixed.items():
                cleanup[k] = cleanup.get(k, 0) + v
            scenes.append(text)
            budget -= odt.estimate_lines([text])
            if n < total and not cancel.is_set():
                try:
                    summary, _ = self.chat([{"role": "user", "content": SUMMARY_PROMPT.format(scene=text)}],
                                           max_tokens=120, cancel=cancel)
                except Cancelled:
                    break
                summaries.append(summary.strip())
            if budget <= 0:
                break
        if not scenes:
            return {"file": None, "scenes": 0}
        path = odt.write(project.folder, outline["chapter_title"], outline["chapter_title"], scenes,
                         header=f"Rough draft — {project.title}")
        words = sum(len(t.split()) for t in scenes)
        project.add_draft(path, outline["chapter_title"], words)
        return {"file": path, "scenes": len(scenes), "of": total, "words": words, "lines": odt.estimate_lines(scenes),
                "stopped": cancel.is_set(), **cleanup}
