# SPDX-License-Identifier: GPL-3.0-or-later
"""The writing partner and the write-up (PLAN D54): gather, then outline, then a rough draft scene by scene.

Built on the probe of 2026-09-30 (the guide wrote a usable scene, but ran ahead of its outline and drifted
from a fact): every scene is written with the project's notes as fixed facts, the whole outline, and a short
summary of what's already written, and is told to stay inside its own scene. The model only ever writes
prose or fills a JSON schema; files are written by our code (odt.py), never overwriting anything.

Stories follow Dan Harmon's Story Circle (PLAN D56): the partner asks about the circle's next empty step, the
notes keep what each step holds, the outline is the steps of this chapter (all eight for a story in one chapter,
a piece of the circle for a story over chapters), each with its scenes, and every scene is told its step. A
chapter of a story over chapters is told what the earlier chapters did (their summaries).

`chat(messages, schema=None, max_tokens=..., cancel=..., sampling=...) -> (text, timings)` is the backend's.
"""

from __future__ import annotations

import json
import re
import threading
from typing import Callable

from cin_minai.inference.backend import Cancelled

from . import odt
from .projects import CIRCLE, NOTE_KEYS, STEP, STEPS, Project

# prose: a little randomness, and llama.cpp's DRY sampler against loops (2026-10-01 "Grandman Stan": scene 1
# repeated whole paragraphs three times with repeat_penalty alone)
WRITE = {"temperature": 0.7, "top_p": 0.9, "repeat_penalty": 1.05, "presence_penalty": 0.3,
         "dry_multiplier": 0.8, "dry_base": 1.75, "dry_allowed_length": 2,
         "dry_penalty_last_n": 1024}  # -1 ("all") is refused by llama-server v0.5.0's request check: a scene is <1,200
CJK = re.compile(r"[぀-ヿ㐀-鿿가-힯＀-￯]+")
# a number the model put in its chapter title, in the v1 languages (D25)
CHAPTER_WORD = re.compile(r"^\s*(chapter|cap[íi]tulo|chapitre|kapitel|第)\s*\w{1,6}\s*(章)?\s*[:.\-–—]?\s*", re.I)


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
MAX_SCENES = 8
WORDS_PER_SCENE = 650          # 8 scenes ~ 5,200 words ~ 520 lines ~ 18 A5 pages (odt.py)
MAX_LINES = 600                # Ian: "600 lines max"

# Dan Harmon's Story Circle (PLAN D56): the whole circle, as every prompt that plans or writes is shown it
CIRCLE_TEXT = "\n".join(f"{i}. {name}: {means}." for i, (_, name, means, _) in enumerate(CIRCLE, 1))

PARTNER = """You are a writing partner built into this computer, helping the user with their own story, "{title}". \
Right now you are only gathering: the user tells you ideas, characters, places and things that happen, and you \
listen. Reply in one to three short sentences, in the user's language: say what you understood, then ask one \
question that helps the story. Don't write the story yet, don't make up details they didn't give, and never \
judge the ideas. When they're ready, they press "Write it up".

The story is built on Dan Harmon's Story Circle:
{circle}
{next_step}
What you know so far:
{notes}"""

NOTES_SCHEMA = {"type": "object", "additionalProperties": False, "required": [*NOTE_KEYS, "circle"],
                "properties": {**{k: {"type": "array", "items": {"type": "string"}, "maxItems": 8} for k in NOTE_KEYS},
                               "circle": {"type": "object", "additionalProperties": False, "required": list(STEPS),
                                          "properties": {k: {"type": "array", "items": {"type": "string"}, "maxItems": 2}
                                                         for k in STEPS}}}}
NOTES_PROMPT = """Take notes for a writer. The user is the writer: what they say about themselves or their \
plans ("I want to write a book", "chapter one") is not part of the story. From the user's latest message only, \
list what's NEW for the story, in short sentences, in the user's language: facts (things that are true in the \
story's world), characters (name, who they are, and whose side they're on), places, ideas (things they want in \
it, and how it should feel: tone, mood, humour). Then "circle": if the message says something for a step of the \
story's circle, put it under that step too:
{circle}
Leave a list empty when the message has nothing for it. Don't repeat what's already noted, and don't invent \
anything.

Already noted:
{notes}"""

OUTLINE_PROMPT = """Plan {what} of the user's story "{title}", in the user's language. The story follows Dan \
Harmon's Story Circle, eight steps:
{circle}
{scope} For each step, give {per_step}: a short title and two or three sentences on what happens in it. Use \
the writer's notes: every fact in them stays true, and every character keeps who they are and whose side \
they're on. Each scene moves the story forward; never retell what an earlier scene or chapter already told.

{notes}
{so_far}{wish}"""

SCENE_PROMPT = """You are writing a rough first draft of the user's story "{title}", {chapter_line}, in the \
language of their notes. The story follows Dan Harmon's Story Circle (You, Need, Go, Search, Find, Take, \
Return, Change).

{notes}

{plan_head}:
{plan}

The story so far:
{so_far}
{last}
Now write scene {n} of {total}, "{scene}", in full: about {words} words of story prose. This scene is the \
circle's step "{step}": {means}. Write only what happens in this scene ({what}); stop at its end and don't \
start on later scenes. Continue from exactly where the story is now: don't repeat or retell anything the \
reader already knows. Keep every fact above true, and every character who they are and on their side. No \
headings, no notes, no title — just the prose."""

SUMMARY_PROMPT = """Summarize this scene in two sentences for the writer's memory: what happened and how it \
ended. Same language as the scene.

{scene}"""

CHAPTER_SUMMARY_PROMPT = """Summarize this chapter in three sentences for the writer's memory: what happened, \
where each main character stands at its end, and what is still open. Same language as the scenes.

{scenes}"""


def outline_schema(steps: tuple[str, ...], lo: int, hi: int) -> dict:
    """The plan as the circle's steps, in order, each with its scenes: no step can be left out."""
    scene = {"type": "object", "additionalProperties": False, "required": ["title", "what_happens"],
             "properties": {"title": {"type": "string"}, "what_happens": {"type": "string"}}}
    return {"type": "object", "additionalProperties": False, "required": ["chapter_title", "steps"],
            "properties": {"chapter_title": {"type": "string"},
                           "steps": {"type": "object", "additionalProperties": False, "required": list(steps),
                                     "properties": {k: {"type": "array", "minItems": lo, "maxItems": hi, "items": scene}
                                                    for k in steps}}}}


def scenes_per_step(steps: int) -> tuple[int, int]:
    """6 to 8 scenes a chapter when the steps allow it: one step each for the whole circle, 3-4 for two steps."""
    hi = max(1, MAX_SCENES // steps)
    return min(-(-6 // steps), hi), hi


def _last_paragraph(text: str) -> str:
    """Where the story is now (2026-10-01: with only a summary, scene 4 found the bottle scene 3 had found)."""
    paras = odt.paragraphs(text)
    return paras[-1][-700:] if paras else ""


def plan_text(outline: dict) -> str:
    return "\n".join(f"{i}. [{STEP[s['step']]['name']}] {s['title']}: {s['what_happens']}" if s.get("step") in STEP
                     else f"{i}. {s['title']}: {s['what_happens']}" for i, s in enumerate(outline["scenes"], 1))


def _names(steps) -> str:
    return ", ".join(STEP[k]["name"] for k in steps)


class Writer:
    def __init__(self, chat: Callable) -> None:
        self.chat = chat

    # --- gathering ----------------------------------------------------------------------------------------
    def reply(self, project: Project, text: str, on_text: Callable[[str], None], cancel: threading.Event) -> str:
        """One gathering turn: a short reply that keeps the conversation going, then the notes it gave."""
        history = project.data["messages"][-12:]
        step = project.open_step()
        next_step = (f'The circle\'s next empty step is "{STEP[step]["name"]}" ({STEP[step]["means"]}). When the '
                     f'user\'s message doesn\'t call for another question, ask about it: {STEP[step]["ask"]}\n'
                     if step else "")
        messages = [{"role": "system", "content": PARTNER.format(title=project.title, circle=CIRCLE_TEXT,
                                                                 next_step=next_step, notes=project.notes_text())},
                    *history, {"role": "user", "content": text}]
        out, _ = self.chat(messages, max_tokens=200, on_text=on_text, cancel=cancel, sampling=WRITE)
        project.remember("user", text)
        project.remember("assistant", out.strip())
        self.take_notes(project, text, cancel)
        return out.strip()

    def take_notes(self, project: Project, text: str, cancel: threading.Event | None = None) -> int:
        raw, _ = self.chat([{"role": "system", "content": NOTES_PROMPT.format(circle=CIRCLE_TEXT,
                                                                             notes=project.notes_text())},
                            {"role": "user", "content": text}], schema=NOTES_SCHEMA, max_tokens=600, cancel=cancel)
        try:
            return project.add_notes(json.loads(raw))
        except (ValueError, TypeError):
            return 0

    # --- the write-up -------------------------------------------------------------------------------------
    def outline(self, project: Project, wish: str = "", cancel: threading.Event | None = None) -> dict:
        """The plan for the next chapter: the circle's steps it covers, each with its scenes. Returned flat
        ("scenes", each with its "step") so the draft and the sidebar walk one list."""
        chapter, steps = project.this_chapter()
        lo, hi = scenes_per_step(len(steps))
        if chapter is None:
            what, scope = "the user's story as one chapter", "This chapter is the whole story: all eight steps, in order."
        else:
            n = project.data["chapters"]
            done, later = STEPS[:STEPS.index(steps[0])], STEPS[STEPS.index(steps[-1]) + 1:]
            what = f"chapter {chapter} of {n}"
            scope = (f"The story runs over {n} chapters, and this is chapter {chapter}: it covers the steps "
                     f"{_names(steps)}." + (f" Earlier chapters covered {_names(done)}." if done else "") +
                     (f" Later chapters will cover {_names(later)}: don't get there yet." if later else
                      " This is the last chapter: the circle closes here."))
        per_step = f"{lo} scene" if lo == hi == 1 else f"{lo} scenes" if lo == hi else f"{lo} to {hi} scenes"
        prompt = OUTLINE_PROMPT.format(what=what, title=project.title, circle=CIRCLE_TEXT, scope=scope,
                                       per_step=per_step, notes=project.notes_text(),
                                       so_far=self.chapters_so_far(project, chapter),
                                       wish=f"\nWhat the writer asked for: {wish}" if wish else "")
        raw, _ = self.chat([{"role": "user", "content": prompt}], schema=outline_schema(steps, lo, hi),
                           max_tokens=1400, cancel=cancel)
        plan = json.loads(raw)
        if chapter:  # we number the chapters: "Chapter 1: The Warning" became "Chapter 1 — Chapter 1 The Warning"
            plan["chapter_title"] = CHAPTER_WORD.sub("", plan["chapter_title"]).strip() or plan["chapter_title"]
        scenes = [{**s, "step": k, "step_name": STEP[k]["name"]} for k in steps for s in plan["steps"].get(k, [])]
        return {"chapter_title": plan["chapter_title"], "chapter": chapter, "of": project.data["chapters"] if chapter else None,
                "steps": list(steps), "scenes": scenes[:MAX_SCENES]}

    @staticmethod
    def chapters_so_far(project: Project, chapter: int | None) -> str:
        if not chapter:
            return ""
        before = project.chapters_before(chapter)
        if not before:
            return ""
        return "The story so far, chapter by chapter:\n" + "\n".join(
            f"Chapter {d['chapter']}, \"{d['title']}\" ({_names(d.get('steps', []))}): {d.get('summary') or '(no summary)'}"
            for d in before) + "\n"

    def draft(self, project: Project, outline: dict, on_progress: Callable[[int, int, str], None],
              cancel: threading.Event) -> dict:
        """Write the chapter scene by scene into a new .odt in the project folder. on_progress(n, total, what)."""
        scenes, summaries = [], []
        cleanup: dict[str, int] = {}
        cjk_ok = bool(CJK.search(project.notes_text() + project.title))  # a Japanese story keeps its script
        total = len(outline["scenes"])
        chapter = outline.get("chapter")
        chapter_line = (f"chapter {chapter} of {outline.get('of')}, \"{outline['chapter_title']}\"" if chapter
                        else f"\"{outline['chapter_title']}\" (the whole story in one chapter)")
        earlier = self.chapters_so_far(project, chapter)
        budget = MAX_LINES
        for n, s in enumerate(outline["scenes"], 1):
            if cancel.is_set():
                break
            words = min(WORDS_PER_SCENE, max(150, (budget * odt.WORDS_PER_LINE) // max(1, total - n + 1)))
            on_progress(n, total, s["title"])
            step = STEP.get(s.get("step"), {"name": "", "means": "the next part of the story"})
            this_chapter = "\n".join(f"Scene {i}: {t}" for i, t in enumerate(summaries, 1))
            prompt = SCENE_PROMPT.format(title=project.title, chapter_line=chapter_line, notes=project.notes_text(),
                                         plan_head="This chapter's plan, by the circle's steps",
                                         plan=plan_text(outline), n=n, total=total, scene=s["title"],
                                         step=step["name"], means=step["means"], what=s["what_happens"], words=words,
                                         so_far=(earlier + ("In this chapter:\n" + this_chapter if this_chapter else ""))
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
            if (n < total or chapter) and not cancel.is_set():  # a chapter's last summary goes into its own
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
        name = f"Chapter {chapter} — {outline['chapter_title']}" if chapter else outline["chapter_title"]
        path = odt.write(project.folder, name, name, scenes, header=f"Rough draft — {project.title}")
        words = sum(len(t.split()) for t in scenes)
        summary = ""
        if chapter and summaries and not cancel.is_set():  # what the next chapter is told about this one
            try:
                summary, _ = self.chat([{"role": "user", "content": CHAPTER_SUMMARY_PROMPT.format(
                    scenes="\n".join(summaries))}], max_tokens=200, cancel=cancel)
            except Cancelled:
                pass
            summary = summary.strip() or " ".join(summaries)
        project.add_draft(path, outline["chapter_title"], words, chapter=chapter, steps=outline.get("steps", ()),
                          summary=summary, finished=len(scenes) == total and not cancel.is_set())
        return {"file": path, "scenes": len(scenes), "of": total, "words": words, "lines": odt.estimate_lines(scenes),
                "stopped": cancel.is_set(), "chapter": chapter, **cleanup}
