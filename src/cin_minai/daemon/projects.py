# SPDX-License-Identifier: GPL-3.0-or-later
"""Writing projects (PLAN D54, D55): the assistant takes in ideas for as long as the user wants, keeps them as
notes, and writes them up when asked. One folder per project in Documents/Writing/<title>/: project.json
(notes + the conversation) and the drafts beside it. Everything stays on this computer.

Notes are what the draft must respect: "facts" (things that are true in the story — the probe of 2026-09-30
drifted from "the message is from his younger self" to someone else's letter), "characters", "places",
"ideas" (things the user wants in it, not yet placed).

Stories follow Dan Harmon's Story Circle (PLAN D56): eight steps, kept as notes of their own ("circle"). A project
is either a story in one chapter (the whole circle) or a story over chapters (each chapter covers its piece of
the circle, in order).
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import tempfile

ROOT = os.path.join(os.path.expanduser("~"), "Documents", "Writing")
KINDS = ("story", "journal")
NOTE_KEYS = ("facts", "characters", "places", "ideas")
MAX_NOTE = 300  # characters per note

# Dan Harmon's Story Circle (PLAN D56), in our own words: key, name, what happens, the question that fills it
CIRCLE = (
    ("you", "You", "a character in their familiar world",
     "Who is the main character, and what is their everyday life like before the story starts?"),
    ("need", "Need", "they want something", "What does the main character want, or what's missing for them?"),
    ("go", "Go", "they cross into an unfamiliar situation", "What pulls them out of their familiar world?"),
    ("search", "Search", "they adapt to it and are tested", "How do they cope out there, and what tests them?"),
    ("find", "Find", "they get what they wanted", "What do they find or win?"),
    ("take", "Take", "and pay a heavy price for it", "What does getting it cost them?"),
    ("return", "Return", "they go back to their familiar world", "How do they come back to where they started?"),
    ("change", "Change", "having changed", "How are they different at the end?"),
)
STEPS = tuple(k for k, *_ in CIRCLE)
STEP = {k: {"name": n, "means": m, "ask": q} for k, n, m, q in CIRCLE}
SHAPES = ("chapter", "chapters")  # a story in one chapter / a story over chapters
CHAPTERS = (2, 8)


def chapter_steps(chapter: int, chapters: int) -> tuple[str, ...]:
    """The circle's steps chapter k of n covers: an even split, the first chapters one more (3 -> 3, 3, 2)."""
    base, extra = divmod(len(STEPS), chapters)
    start = sum(base + (i < extra) for i in range(chapter - 1))
    return STEPS[start:start + base + (chapter - 1 < extra)]


def slug(title: str) -> str:
    return re.sub(r'[\\/:*?"<>|\x00-\x1f]', "", str(title)).strip(" .")[:60].strip(" .") or "Untitled"


class Project:
    def __init__(self, folder: str, data: dict) -> None:
        self.folder, self.data = folder, data

    # --- the store ------------------------------------------------------------------------------------
    @classmethod
    def new(cls, title: str, kind: str = "story", root: str = ROOT) -> "Project":
        name, n = slug(title), 2
        folder = os.path.join(root, name)
        while os.path.exists(folder):
            folder, n = os.path.join(root, f"{name} ({n})"), n + 1
        os.makedirs(folder)
        p = cls(folder, {"kind": kind if kind in KINDS else "story", "title": str(title).strip() or "Untitled",
                         "created": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
                         "notes": {k: [] for k in NOTE_KEYS}, "circle": {k: [] for k in STEPS},
                         "shape": "chapter", "chapters": 4, "next_chapter": 1, "messages": [], "drafts": []})
        p.save()
        return p

    @classmethod
    def open(cls, folder: str) -> "Project":
        with open(os.path.join(folder, "project.json"), encoding="utf-8") as f:
            data = json.load(f)
        data.setdefault("notes", {})
        for k in NOTE_KEYS:
            data["notes"].setdefault(k, [])
        data.setdefault("messages", [])
        data.setdefault("drafts", [])
        data.setdefault("circle", {})  # projects from before D56
        for k in STEPS:
            data["circle"].setdefault(k, [])
        data.setdefault("shape", "chapter")
        data.setdefault("chapters", 4)
        data.setdefault("next_chapter", 1)
        return cls(folder, data)

    @staticmethod
    def list(root: str = ROOT) -> list[dict]:
        out = []
        for name in sorted(os.listdir(root)) if os.path.isdir(root) else []:
            path = os.path.join(root, name, "project.json")
            if os.path.isfile(path):
                try:
                    with open(path, encoding="utf-8") as f:
                        d = json.load(f)
                    out.append({"folder": os.path.join(root, name), "title": d.get("title", name), "kind": d.get("kind", "story"),
                                "notes": sum(len(v) for v in d.get("notes", {}).values())})
                except (OSError, ValueError):
                    pass
        return out

    def save(self) -> None:
        """Atomic: a crash mid-write never leaves a broken project.json."""
        fd, tmp = tempfile.mkstemp(dir=self.folder, prefix=".project-", suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=1)
            f.write("\n")
        os.replace(tmp, os.path.join(self.folder, "project.json"))

    # --- notes --------------------------------------------------------------------------------------------
    @property
    def title(self) -> str:
        return self.data["title"]

    @property
    def notes(self) -> dict:
        return self.data["notes"]

    @property
    def circle(self) -> dict:
        return self.data["circle"]

    def add_notes(self, new: dict) -> int:
        """Merge new notes in (the circle's under "circle"); a note already there (same words, any case) isn't
        added twice."""
        added = 0
        circle = new.get("circle") if isinstance(new.get("circle"), dict) else {}
        for store, keys, src in ((self.notes, NOTE_KEYS, new), (self.circle, STEPS, circle)):
            for k in keys:
                have = {n.lower().strip(" .") for n in store[k]}
                for n in src.get(k, []) or []:
                    n = re.sub(r"\s+", " ", str(n)).strip()[:MAX_NOTE]
                    if n and n.lower().strip(" .") not in have:
                        store[k].append(n)
                        have.add(n.lower().strip(" ."))
                        added += 1
        if added:
            self.save()
        return added

    def open_step(self) -> str | None:
        """The circle's first step with nothing in it yet: what the writing partner asks about next."""
        return next((k for k in STEPS if not self.circle[k]), None)

    def set_shape(self, shape: str | None = None, chapters: int | None = None, next_chapter: int | None = None) -> None:
        if shape in SHAPES:
            self.data["shape"] = shape
        if chapters is not None:
            self.data["chapters"] = min(CHAPTERS[1], max(CHAPTERS[0], int(chapters)))
        if next_chapter is not None:
            self.data["next_chapter"] = int(next_chapter)
        self.data["next_chapter"] = min(self.data["chapters"], max(1, self.data["next_chapter"]))
        self.save()

    def this_chapter(self) -> tuple[int | None, tuple[str, ...]]:
        """(chapter number, its steps): (None, all eight) for a story in one chapter."""
        if self.data["shape"] != "chapters":
            return None, STEPS
        k = self.data["next_chapter"]
        return k, chapter_steps(k, self.data["chapters"])

    def chapters_before(self, chapter: int) -> list[dict]:
        """The newest draft of each earlier chapter (a rewrite replaces the one before it)."""
        newest = {d["chapter"]: d for d in self.data["drafts"] if d.get("chapter") and d["chapter"] < chapter}
        return [newest[k] for k in sorted(newest)]

    def notes_text(self) -> str:
        labels = {"facts": "Facts (always true in this story)", "characters": "Characters", "places": "Places",
                  "ideas": "Ideas the writer wants in it"}
        parts = [f"{labels[k]}:\n" + "\n".join(f"- {n}" for n in self.notes[k]) for k in NOTE_KEYS if self.notes[k]]
        steps = [f"- {STEP[k]['name']} ({STEP[k]['means']}): " + " ".join(self.circle[k]) for k in STEPS if self.circle[k]]
        if steps:
            parts.append("The story's circle so far:\n" + "\n".join(steps))
        return "\n\n".join(parts) or "(no notes yet)"

    def remember(self, role: str, content: str) -> None:
        self.data["messages"].append({"role": role, "content": content})
        self.save()

    def add_draft(self, path: str, title: str, words: int, chapter: int | None = None, steps=(), summary: str = "",
                  finished: bool = True) -> None:
        """A written draft; a finished chapter of a story over chapters moves on to the next one."""
        self.data["drafts"].append({"file": os.path.basename(path), "title": title, "words": words,
                                    "made": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
                                    "chapter": chapter, "steps": list(steps), "summary": summary})
        if chapter is not None and finished:
            self.data["next_chapter"] = min(self.data["chapters"], chapter + 1)
        self.save()
