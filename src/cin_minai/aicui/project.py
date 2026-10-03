# SPDX-License-Identifier: GPL-3.0-or-later
"""AICUI's project side (PLAN D61, SPEC §21), no GTK: the working tree with git status, and the session goals.

A project is a folder (or the folder of an opened file). AICUI keeps its own things in `.cinminai/` there: the
session goals (goals.json) and, later, the changelog's shadow git store — never in the user's own git history.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time

HIDE = {".git", ".cinminai", "__pycache__", "node_modules", ".venv", "venv", ".mypy_cache", ".pytest_cache",
        ".idea", ".gradle", "build", "dist", "target"}
MAX_ENTRIES = 4000  # a working tree is for looking at, not for indexing a home folder


def project_root(path: str) -> str:
    """The folder to work in: the path itself, the folder of a file, or the enclosing git repository."""
    path = os.path.abspath(os.path.expanduser(path))
    folder = path if os.path.isdir(path) else os.path.dirname(path)
    top = git(folder, "rev-parse", "--show-toplevel")
    return os.path.normpath(top.strip()) if top else folder


def entry_point(root: str) -> str | None:
    """What "run this project" starts, relative to the root: run.sh, else main.py (the root's, else the first one
    a level down), else index.html (a web page, opened in the browser)."""
    for rel in ("run.sh", "main.py"):
        if os.path.isfile(os.path.join(root, rel)):
            return rel
    for rel, is_dir, _ in tree(root):
        if not is_dir and os.path.basename(rel) == "main.py" and rel.count(os.sep) <= 1:
            return rel
    for rel, is_dir, _ in tree(root):
        if not is_dir and os.path.basename(rel) == "index.html" and rel.count(os.sep) <= 1:
            return rel
    return None


def venv_python(root: str) -> str:
    """The project's own Python when it has a venv, else the system's."""
    for name in (".venv", "venv"):
        p = os.path.join(root, name, "bin", "python")
        if os.path.exists(p):
            return p
    return "python3"


def git(folder: str, *args: str) -> str | None:
    try:
        r = subprocess.run(["git", "-C", folder, *args], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout if r.returncode == 0 else None


def git_status(root: str) -> dict[str, str]:
    """{relative path: status letter} from git (M modified, A added, D deleted, ? untracked); {} if not a repo."""
    out = git(root, "status", "--porcelain=v1", "-uall")
    status = {}
    for line in (out or "").splitlines():
        code, path = line[:2], line[3:]
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        status[path.strip('"')] = "?" if code == "??" else (code.strip() or "M")[0]
    return status


def tree(root: str) -> list[tuple[str, bool, str]]:
    """[(relative path, is folder, git status)], folders first, hidden build/tool folders left out."""
    status = git_status(root)
    out = []
    for folder, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in HIDE and not d.startswith("."))
        rel = os.path.relpath(folder, root)
        for d in dirs:
            p = os.path.normpath(os.path.join(rel, d))
            changed = any(k.startswith(p + "/") for k in status)
            out.append((p, True, "M" if changed else ""))
        for f in sorted(files):
            p = os.path.normpath(os.path.join(rel, f))
            out.append((p, False, status.get(p, "")))
        if len(out) > MAX_ENTRIES:
            break
    return out


class Goals:
    """The session goals (SPEC §21): written by the user and the AI, then the AI's to-do list; they stay with the
    project. Each: {"id", "text", "done", "by": "user"|"ai", "made"}."""

    def __init__(self, root: str) -> None:
        self.dir = os.path.join(root, ".cinminai")
        self.path = os.path.join(self.dir, "goals.json")

    def load(self) -> list[dict]:
        try:
            with open(self.path, encoding="utf-8") as f:
                return json.load(f).get("goals", [])
        except (OSError, ValueError):
            return []

    def save(self, goals: list[dict]) -> None:
        os.makedirs(self.dir, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.dir, prefix=".goals-", suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"goals": goals}, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self.path)

    def add(self, text: str, by: str = "user") -> dict:
        goals = self.load()
        g = {"id": max([x["id"] for x in goals], default=0) + 1, "text": " ".join(text.split()), "done": False,
             "by": by, "made": time.strftime("%Y-%m-%dT%H:%M:%S")}
        goals.append(g)
        self.save(goals)
        return g

    def set_done(self, gid: int, done: bool) -> None:
        goals = self.load()
        for g in goals:
            if g["id"] == gid:
                g["done"] = done
        self.save(goals)

    def remove(self, gid: int) -> None:
        self.save([g for g in self.load() if g["id"] != gid])
