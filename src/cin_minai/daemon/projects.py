# SPDX-License-Identifier: GPL-3.0-or-later
"""Writing projects (PLAN D54, D55): the assistant takes in ideas for as long as the user wants, keeps them as
notes, and writes them up when asked. One folder per project in Documents/Writing/<title>/: project.json
(notes + the conversation) and the drafts beside it. Everything stays on this computer.

Notes are what the draft must respect: "facts" (things that are true in the story — the probe of 2026-09-30
drifted from "the message is from his younger self" to someone else's letter), "characters", "places",
"ideas" (things the user wants in it, not yet placed).
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
                         "notes": {k: [] for k in NOTE_KEYS}, "messages": [], "drafts": []})
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

    def add_notes(self, new: dict) -> int:
        """Merge new notes in; a note already there (same words, any case) isn't added twice."""
        added = 0
        for k in NOTE_KEYS:
            have = {n.lower().strip(" .") for n in self.notes[k]}
            for n in new.get(k, []) or []:
                n = re.sub(r"\s+", " ", str(n)).strip()[:MAX_NOTE]
                if n and n.lower().strip(" .") not in have:
                    self.notes[k].append(n)
                    have.add(n.lower().strip(" ."))
                    added += 1
        if added:
            self.save()
        return added

    def notes_text(self) -> str:
        labels = {"facts": "Facts (always true in this story)", "characters": "Characters", "places": "Places",
                  "ideas": "Ideas the writer wants in it"}
        parts = [f"{labels[k]}:\n" + "\n".join(f"- {n}" for n in self.notes[k]) for k in NOTE_KEYS if self.notes[k]]
        return "\n\n".join(parts) or "(no notes yet)"

    def remember(self, role: str, content: str) -> None:
        self.data["messages"].append({"role": role, "content": content})
        self.save()

    def add_draft(self, path: str, title: str, words: int) -> None:
        self.data["drafts"].append({"file": os.path.basename(path), "title": title, "words": words,
                                    "made": dt.datetime.now().astimezone().isoformat(timespec="seconds")})
        self.save()
