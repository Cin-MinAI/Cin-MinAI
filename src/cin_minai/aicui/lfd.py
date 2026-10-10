# SPDX-License-Identifier: GPL-3.0-or-later
"""LFD — Large File Distillation (Ian, 2026-10-10): how team B takes in a large codebase.

The Senior starts a shared summary file. The project's own files go in a list by size: the Junior takes the smallest
and works up, the Senior takes the largest and works down, each file summarized in a fresh context (nothing of the
model's history comes along) and appended to the shared file by code, one at a time. They meet in the middle. Then
the Senior's working context is dumped: it goes on with only the request and the summary, makes the plan for moving
forward (roles for itself and the Junior), and works it.

The same per-file summary answers a `brief` (the Senior asks the Junior about some files, between its steps).
"""

from __future__ import annotations

import os
import threading
import time

from . import intake
from .project import tree

SUMMARY = "notes/project-summary.md"
MAX_FILES = 200
PART_CHARS = 12000       # one part of a file per request (a 9B at 32K and the MoE Senior both take it whole)
SKIP_TOP = ("notes", "sources", ".cinminai", ".venv", "venv", "node_modules", "__pycache__", ".git", "build")
SKIP_HOLDS = ("picture", "sound", "document")
PROMPT = """You summarize one file of a software project for: {focus}
This is {rel}{part}. In at most 150 words, from this text only: what it does; its parts (classes, functions, data)
by their exact names; what's unfinished (TODO, stubs, missing pieces); what looks wrong. No advice, no code."""


def project_files(root: str) -> list[tuple[str, int]]:
    """The project's own text files, smallest first: (path, bytes). Fetched material, notes, pictures, sounds and
    AICUI's own folders aren't the codebase."""
    out = []
    for rel, is_dir, _ in tree(root):
        top = rel.replace(os.sep, "/").split("/", 1)[0]
        if is_dir or top in SKIP_TOP or intake.came_in(root, rel) or intake.holds(root, rel) in SKIP_HOLDS:
            continue
        full = os.path.join(root, rel)
        try:
            size = os.path.getsize(full)
            with open(full, "rb") as f:
                if b"\0" in f.read(4096):
                    continue  # binary
        except OSError:
            continue
        if size:
            out.append((rel.replace(os.sep, "/"), size))
    return sorted(out, key=lambda x: (x[1], x[0]))[:MAX_FILES]


def summarize(agent, rel: str, focus: str, stop=lambda: False) -> str:
    """One file, in parts if it's long, each part in a fresh context of its own."""
    with open(os.path.join(agent.root, rel), encoding="utf-8", errors="replace") as f:
        text = f.read()
    parts = [text[i:i + PART_CHARS] for i in range(0, len(text), PART_CHARS)] or [""]
    said = []
    for n, part in enumerate(parts, 1):
        if stop():
            break
        where = f", part {n} of {len(parts)}" if len(parts) > 1 else ""
        raw, _ = agent.chat([{"role": "system", "content": PROMPT.format(focus=focus, rel=rel, part=where)},
                             {"role": "user", "content": part}], max_tokens=400)
        said.append((f"(part {n}) " if len(parts) > 1 else "") + " ".join(str(raw).split()))
    return "\n".join(said)


def run(senior, junior, focus: str, stop=lambda: False) -> dict:
    """Both ends of the list at once, meeting in the middle; each summary appended to the shared file as it comes.
    {"path", "files", "by_junior", "by_senior", "text", "seconds", "stopped"}."""
    files = project_files(senior.root)
    path = os.path.join(senior.root, SUMMARY)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:  # the Senior's summary file, made before the hand-off
        f.write(f"# Project summary (Large File Distillation, {time.strftime('%Y-%m-%d %H:%M')})\n\nFor: {focus}\n"
                f"{len(files)} files, smallest to largest; the junior from the small end, the senior from the large.\n")
    left, right = 0, len(files) - 1
    lock = threading.Lock()
    done = {"junior": 0, "senior": 0}
    sections: dict[str, str] = {}

    def take(end: str):
        nonlocal left, right
        with lock:
            if left > right:
                return None
            if end == "junior":
                left += 1
                return files[left - 1]
            right -= 1
            return files[right + 1]

    def work(who: str, agent) -> None:
        while not stop():
            item = take(who)
            if item is None:
                return
            rel, size = item
            agent.event("busy", doing=f"LFD: summarizing {rel} ({size:,} bytes)", tokens=0)
            try:
                said = summarize(agent, rel, focus, stop)
            except Exception as e:  # a file that can't be summarized is said, never fatal
                said = f"(not summarized: {type(e).__name__})"
            entry = f"\n## {rel} ({size:,} bytes, by the {who})\n{said}\n"
            with lock:
                sections[rel] = entry
                done[who] += 1
                with open(path, "a", encoding="utf-8") as f:
                    f.write(entry)

    start = time.monotonic()
    helper = threading.Thread(target=work, args=("junior", junior), daemon=True)
    helper.start()
    work("senior", senior)
    helper.join()
    # the finished file in the list's order, smallest to largest (they were appended as they came)
    head = open(path, encoding="utf-8").read().split("\n## ", 1)[0]
    text = head + "".join(sections[rel] for rel, _ in files if rel in sections)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    intake.record_origin(senior.root, SUMMARY, "Large File Distillation", kind="compiled")
    return {"path": SUMMARY, "files": len(files), "by_junior": done["junior"], "by_senior": done["senior"],
            "text": text, "seconds": round(time.monotonic() - start), "stopped": stop()}
