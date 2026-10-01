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
import os
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


def _letters(p: str) -> str:
    """The text without spaces or punctuation: a repeat with its words glued together is still a repeat."""
    return re.sub(r"[\W_]+", "", p.lower())


def _same(a: str, b: str) -> bool:
    """Two paragraphs that say the same thing: equal, 85 % of the same words, or the same letters once spaces
    are taken out. DRY blocks a repeated word sequence, and the model got round it by dropping the spaces:
    "their eyes filledwith determination … readytohelphimfindwhatheneeded" ("Grandman Stan", 2026-10-01)."""
    wa, wb = _words(a), _words(b)
    if not wa or not wb:
        return a.strip() == b.strip()
    if len(wa & wb) / max(len(wa), len(wb)) >= 0.85:
        return True
    la, lb = _letters(a), _letters(b)
    short, long_ = sorted((la, lb), key=len)
    return len(short) >= 40 and len(short) >= 0.85 * len(long_) and short in long_  # a part: the sentence check


SENTENCE = re.compile(r"(?<=[.!?…])\s+|(?<=[.!?…][\"'”’»)])\s+")  # the closing quote stays with its sentence
LONG = re.compile(r"[^\W\d_]{16,}")  # a long run of letters: glued words, or a real long word (German compounds)


def glued(run: str, vocab: set[str]) -> bool:
    """A run of letters that splits entirely into 3+ words the story already uses ("readytohelphimfind…"); a
    real long word ("Donaudampfschifffahrtsgesellschaft") doesn't."""
    run = run.lower()
    best = [0] + [None] * len(run)  # best[i]: fewest words that make run[:i]
    for i in range(1, len(run) + 1):
        for j in range(max(0, i - 20), i):
            if best[j] is not None and run[j:i] in vocab and (best[i] is None or best[j] + 1 < best[i]):
                best[i] = best[j] + 1
    return best[-1] is not None and best[-1] >= 3


def clean_scene(text: str, previous_end: str, cjk_ok: bool, earlier: list[str] = ()) -> tuple[str, dict]:
    """What the model wrote, without its loops: paragraphs that repeat an earlier one (in this scene, in the
    chapter's earlier scenes, or the previous scene's ending, which it was shown) are dropped; so are sentences
    that repeat an earlier sentence letter for letter (glued or not); text from a run of glued words to the end
    of its sentence is cut; stray Chinese characters in a non-CJK story are removed ("sharp and清脆 like glass")."""
    kept, dropped, sentences, cut, cjk = [], 0, 0, 0, 0
    before = [p for p in earlier if p] + ([previous_end] if previous_end else [])
    seen = {_letters(s) for p in before for s in SENTENCE.split(p) if len(_letters(s)) >= 30}
    vocab = {w for p in [*before, text] for w in re.findall(r"[^\W\d_]+", p.lower())
             if 2 <= len(w) < 16 or w in ("a", "i")}  # the long runs themselves are what's being checked
    for p in odt.paragraphs(text):
        if not cjk_ok and CJK.search(p):
            cjk += len(CJK.findall(p))
            p = re.sub(r"\s{2,}", " ", CJK.sub(" ", p)).replace(" ,", ",").replace(" .", ".").strip()
        if any(_same(p, k) for k in before) or any(_same(p, k) for k in kept):
            dropped += 1
            continue
        out = []
        for s in SENTENCE.split(p):
            m = next((m for m in LONG.finditer(s) if glued(m.group(), vocab)), None)
            if m and not cjk_ok:
                cut += 1
                s = s[:m.start()].rstrip(" ,;:—-")
                s = s + "." if s and s[-1] not in ".!?…\"'”" else s
            letters = _letters(s)
            if len(letters) >= 30 and letters in seen:
                sentences += 1
                continue
            if letters:
                seen.add(letters)
                out.append(s)
        p = " ".join(out).strip()
        if p and len(_letters(p)) >= 3:
            kept.append(p)
    return "\n\n".join(kept), {"repeats_dropped": dropped, "sentences_dropped": sentences, "glued_cut": cut,
                               "cjk_removed": cjk}
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
they're on, unless the writer changes it. Each scene moves the story forward; never retell what an earlier scene \
or chapter already told.

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
circle's step "{step}": {means}.{not_yet} Write only what happens in this scene ({what}); stop at its end \
and don't start on later scenes. Continue from exactly where the story is now: don't repeat or retell anything the \
reader already knows. Keep every fact above true, and every character who they are and on their side unless \
the writer changed it. No headings, no notes, no title — just the prose."""

SUMMARY_PROMPT = """Summarize this scene in two sentences for the writer's memory: what happened and how it \
ended. Same language as the scene.

{scene}"""


# the review before every chapter (PLAN D57): the story as it is now, against the circle and the notes
STATUSES = ("written", "partly written", "planned", "missing")
REVIEW_SCHEMA = {"type": "object", "additionalProperties": False,
                 "required": ["steps", "characters", "missing", "questions"],
                 "properties": {
                     "steps": {"type": "object", "additionalProperties": False, "required": list(STEPS),
                               # the evidence first: the status is chosen after the model looked for the words
                               "properties": {k: {"type": "object", "additionalProperties": False,
                                                  "required": ["evidence", "status", "what"],
                                                  "properties": {"evidence": {"type": "string"},
                                                                 "status": {"enum": list(STATUSES)},
                                                                 "what": {"type": "string"}}} for k in STEPS}},
                     "characters": {"type": "array", "maxItems": 4, "items": {
                         "type": "object", "additionalProperties": False, "required": ["name", "step", "where"],
                         "properties": {"name": {"type": "string"}, "step": {"enum": list(STEPS)},
                                        "where": {"type": "string"}}}},
                     "missing": {"type": "array", "maxItems": 4, "items": {"type": "string"}},
                     "questions": {"type": "array", "maxItems": 4, "items": {"type": "string"}}}}
READ_WORDS = 1500  # a chapter is read in parts this long (the context is 8K on the card)
READ_PROMPT = """Summarize this part of chapter {n} of the user's story "{title}" in three or four sentences for \
the writer's memory: what happens, who does what, and anything that changes for a character (a new side, a new \
goal, an injury, a death). Same language as the text. Only what's in the text.

{text}"""
REVIEW_PROMPT = """You are reviewing the user's story "{title}" before {next} is planned. The story follows Dan \
Harmon's Story Circle; a step has happened only when this is true of the main character:
{tests}

For each step, first "evidence": copy, word for word, the words from the chapters below that show the step \
happening (one sentence or part of one, each step its own), or "" if there are none. Then the status: \
"written" only with evidence, "partly written" if the evidence shows it starting but not finished, "planned" \
if only the writer's notes have it, "missing" if nothing has it yet; and in one sentence what it is, or what's \
missing. A goal someone takes on is Need, not Find, Take or Change. For up to four main \
characters: their name, the step of their own circle they're at, and one sentence on where they are now. Then \
what the story is still missing that a reader would need, and questions for the writer where the chapters and \
the notes disagree, or where a character acts against who they were — ask, don't judge: the writer may want \
it. Use only the writer's notes and the chapters below; don't invent. In the writer's language.

The writer's notes:
{notes}

{chapters}"""


# what has to be true for a step to have happened (D57: "Take: she has taken on the goal" passed as written)
STEP_TESTS = {
    "you": "the main character is shown in their ordinary life before the trouble starts",
    "need": "the main character wants something of their own, shown or said",
    "go": "they leave their familiar world for an unfamiliar situation",
    "search": "out there they struggle and adapt, tested more than once",
    "find": "they get the thing they wanted",
    "take": "they pay a heavy price for it: a loss, a wound, a sacrifice",
    "return": "they go back to where they started",
    "change": "they are shown to be different from who they were at the start",
}
REVIEW_TESTS = "\n".join(f"{i}. {STEP[k]['name']}: {STEP_TESTS[k]}." for i, k in enumerate(STEPS, 1))


def _tokens(s: str) -> list[str]:
    return re.findall(r"\w+", s.lower())


def found_in(evidence: str, source: list[str], min_words: int = 4) -> bool:
    """The evidence is really in the text (D57): at least min_words words, and 80 % of them as one run in the
    source (a quote, give or take a word the model smoothed)."""
    import difflib
    ev = _tokens(evidence)
    if len(ev) < min_words:
        return False
    m = difflib.SequenceMatcher(None, ev, source, autojunk=False).find_longest_match(0, len(ev), 0, len(source))
    return m.size >= max(min_words, int(0.8 * len(ev)))


def check_evidence(review: dict, source_text: str, circle: dict) -> list[str]:
    """A step is written only with its own words from the chapters: without them (or with another step's), it's
    "planned" if the notes have it, else "missing". Returns the steps it took back."""
    source, used, taken = _tokens(source_text), [], []
    for k in STEPS:
        s = review["steps"].get(k)
        if not s or s["status"] not in ("written", "partly written"):
            continue
        ev = s.get("evidence", "")
        if not found_in(ev, source) or any(_same(ev, u) for u in used):
            s["status"] = "planned" if circle.get(k) else "missing"
            taken.append(k)
        else:
            used.append(ev)
    return taken


def _parts(paras: list[str], words: int = READ_WORDS) -> list[str]:
    parts, cur, n = [], [], 0
    for p in paras:
        cur.append(p)
        n += len(p.split())
        if n >= words:
            parts.append("\n\n".join(cur))
            cur, n = [], 0
    if cur:
        parts.append("\n\n".join(cur))
    return parts


def next_steps(review: dict, chapter: int | None, chapters: int) -> tuple[str, ...]:
    """Where the next chapter starts: the first step the review doesn't find written (D57); the steps left are
    paced over the chapters left. A story in one chapter is always the whole circle."""
    if chapter is None:
        return STEPS
    st = review.get("steps", {})
    start = next((i for i, k in enumerate(STEPS) if st.get(k, {}).get("status") != "written"), len(STEPS))
    left = STEPS[start:] or STEPS[-1:]  # all written but chapters left: the last step goes on
    return left[:-(-len(left) // max(1, chapters - chapter + 1))]


def outline_schema(steps: tuple[str, ...], lo: int, hi: int) -> dict:
    """The plan as the circle's steps, in order, each with its scenes: no step can be left out."""
    scene = {"type": "object", "additionalProperties": False, "required": ["title", "what_happens"],
             "properties": {"title": {"type": "string"}, "what_happens": {"type": "string"}}}
    return {"type": "object", "additionalProperties": False, "required": ["chapter_title", "steps"],
            "properties": {"chapter_title": {"type": "string"},
                           "steps": {"type": "object", "additionalProperties": False, "required": list(steps),
                                     "properties": {k: {"type": "array", "minItems": lo, "maxItems": hi, "items": scene}
                                                    for k in steps}}}}


def scenes_per_step(steps: int, whole: bool = False) -> tuple[int, int]:
    """The whole circle in one chapter: one scene a step. A piece of it per chapter: 2-3 scenes a step — with 3-4
    the plan ran ahead into the next steps to fill them (2026-10-01: "Grandman Stan" ended after 3 of 4 chapters)."""
    if whole:
        return 1, max(1, MAX_SCENES // steps)
    hi = min(3, max(1, MAX_SCENES // steps))
    return min(2, hi), hi


def _last_paragraph(text: str) -> str:
    """Where the story is now (2026-10-01: with only a summary, scene 4 found the bottle scene 3 had found)."""
    paras = odt.paragraphs(text)
    return paras[-1][-700:] if paras else ""


def plan_text(outline: dict) -> str:
    return "\n".join(f"{i}. [{STEP[s['step']]['name']}] {s['title']}: {s['what_happens']}" if s.get("step") in STEP
                     else f"{i}. {s['title']}: {s['what_happens']}" for i, s in enumerate(outline["scenes"], 1))


def _names(steps) -> str:
    return ", ".join(STEP[k]["name"] for k in steps)


def review_text(review: dict | None) -> str:
    """The review, as the plan is told it (D57)."""
    if not review:
        return ""
    lines = ["Where the story is (the review before this chapter):"]
    lines += [f"- {STEP[k]['name']}: {s['status']}: {s['what']}" for k, s in review.get("steps", {}).items() if k in STEP]
    if review.get("characters"):
        lines.append("Where the main characters are: " + "; ".join(
            f"{c['name']} ({STEP.get(c['step'], {}).get('name', c['step'])}): {c['where']}" for c in review["characters"]))
    if review.get("missing"):
        lines.append("Still missing: " + "; ".join(review["missing"]))
    return "\n".join(lines) + "\n"


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
    def read_chapters(self, project: Project, chapter: int | None, cancel: threading.Event | None = None) -> list[dict]:
        """The chapters before this one as the files are now, the writer's own edits included (D57): each read
        in parts and summarized, cached until the file changes. A chapter whose file is gone is left out."""
        out = []
        for d in project.chapters_before(chapter) if chapter else []:
            path = os.path.join(project.folder, d["file"])
            try:
                st = os.stat(path)
                key = f"{st.st_mtime_ns}:{st.st_size}"
                if d.get("read", {}).get("key") != key:
                    paras = odt.read(path)[1:]  # without the title
                    sums = [self.chat([{"role": "user", "content": READ_PROMPT.format(
                        n=d["chapter"], title=project.title, text=part)}], max_tokens=220, cancel=cancel)[0].strip()
                        for part in _parts(paras)]
                    d["read"] = {"key": key, "summary": " ".join(s for s in sums if s)}
                    project.save()
            except (OSError, KeyError, ValueError):  # gone, renamed, or not an .odt any more
                continue
            out.append(d)
        return out

    def review(self, project: Project, cancel: threading.Event | None = None) -> dict:
        """Before every chapter (D57): where the story stands on the circle, where each main character is, what's
        missing, and questions where the written story and the notes disagree. Kept with the project."""
        chapter, _ = project.this_chapter()
        read = self.read_chapters(project, chapter, cancel)
        chapters = ("The chapters written so far, as they are now:\n" + "\n".join(
            f"Chapter {d['chapter']}, \"{d['title']}\": {d['read']['summary']}" for d in read)) if read else \
            "No chapters are written yet: nothing is \"written\" or \"partly written\"."
        nxt = (f"chapter {chapter} of {project.data['chapters']}" if chapter else
               "the story (the whole circle in one chapter)")
        raw, _ = self.chat([{"role": "user", "content": REVIEW_PROMPT.format(
            title=project.title, next=nxt, tests=REVIEW_TESTS, notes=project.notes_text(), chapters=chapters)}],
            schema=REVIEW_SCHEMA, max_tokens=1400, cancel=cancel)
        review = json.loads(raw)
        for k in ("missing", "questions"):  # the same question four times (2026-10-01)
            review[k] = [q for i, q in enumerate(review[k]) if not any(_same(q, p) for p in review[k][:i])]
        # written only with the chapters' own words (D57); before chapter 1 there are none, so nothing is
        review["taken_back"] = check_evidence(review, chapters if read else "", project.circle)
        review.update({"chapter": chapter, "of": project.data["chapters"] if chapter else None,
                       "chapters_read": [d["chapter"] for d in read],
                       "next_steps": list(next_steps(review, chapter, project.data["chapters"]))})
        project.data["review"] = review
        project.save()
        return review

    @staticmethod
    def set_written(project: Project, review: dict, written) -> dict:
        """The writer's own call on the review card (D57): the steps they tick are written, the others aren't
        (an unticked "partly written" stays partly). Where the next chapter starts follows their ticks — the
        review once took "Stan remains defiant" for Change."""
        written = {k for k in written if k in STEPS}
        for k in STEPS:
            s = review.setdefault("steps", {}).setdefault(k, {"status": "missing", "what": "", "evidence": ""})
            if k in written and s["status"] != "written":
                s["status"], s["by_writer"] = "written", True
            elif k not in written and s["status"] == "written":
                s["status"], s["by_writer"] = ("planned" if project.circle.get(k) else "missing"), True
        review["next_steps"] = list(next_steps(review, review.get("chapter"), project.data["chapters"]))
        project.data["review"] = review
        project.save()
        return review

    def outline(self, project: Project, wish: str = "", cancel: threading.Event | None = None,
                review: dict | None = None) -> dict:
        """The plan for the next chapter: the circle's steps it covers, each with its scenes. Returned flat
        ("scenes", each with its "step") so the draft and the sidebar walk one list. With a review (D57), the
        chapter starts where the review found the story, and is told what's missing."""
        chapter, steps = project.this_chapter()
        if review is not None and review.get("chapter") == chapter:
            steps = tuple(review["next_steps"])
        lo, hi = scenes_per_step(len(steps), whole=chapter is None)
        if chapter is None:
            what, scope = "the user's story as one chapter", "This chapter is the whole story: all eight steps, in order."
        else:
            n = project.data["chapters"]
            done, later = STEPS[:STEPS.index(steps[0])], STEPS[STEPS.index(steps[-1]) + 1:]
            what = f"chapter {chapter} of {n}"
            scope = (f"The story runs over {n} chapters, and this is chapter {chapter}: it covers the steps "
                     f"{_names(steps)}." + (f" Earlier chapters covered {_names(done)}." if done else "") +
                     (f" Later chapters will cover {_names(later)}: don't get there yet — no scene here may show "
                      f"{STEP[later[0]]['name']} ({STEP_TESTS[later[0]]})." if later else
                      " This is the last chapter: the circle closes here."))
        per_step = f"{lo} scene" if lo == hi == 1 else f"{lo} scenes" if lo == hi else f"{lo} to {hi} scenes"
        prompt = OUTLINE_PROMPT.format(what=what, title=project.title, circle=CIRCLE_TEXT, scope=scope,
                                       per_step=per_step, notes=project.notes_text(),
                                       so_far=self.chapters_so_far(project, chapter) + review_text(review),
                                       wish=f"\nWhat the writer said before this chapter (it decides): {wish}" if wish else "")
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
            f"Chapter {d['chapter']}, \"{d['title']}\": "
            + (d.get("read", {}).get("summary") or d.get("summary") or "(no summary)")  # as the file is now (D57)
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
        later = STEPS[STEPS.index(outline["steps"][-1]) + 1:] if chapter and outline.get("steps") else ()
        not_yet = (f' Not in this chapter: "{STEP[later[0]]["name"]}" ({STEP_TESTS[later[0]]}) comes in a later '
                   f"chapter, so it mustn't happen yet." if later else "")
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
                                         not_yet=not_yet,
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
            text, fixed = clean_scene(text, _last_paragraph(scenes[-1]) if scenes else "", cjk_ok,
                                      earlier=[p for t in scenes for p in odt.paragraphs(t)])
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
        # the scenes' summaries, until the review reads the file itself (D57: the writer may edit it first)
        summary = " ".join(summaries) if chapter else ""
        project.add_draft(path, outline["chapter_title"], words, chapter=chapter, steps=outline.get("steps", ()),
                          summary=summary, finished=len(scenes) == total and not cancel.is_set())
        return {"file": path, "scenes": len(scenes), "of": total, "words": words, "lines": odt.estimate_lines(scenes),
                "stopped": cancel.is_set(), "chapter": chapter, **cleanup}
