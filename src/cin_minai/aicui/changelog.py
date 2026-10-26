# SPDX-License-Identifier: GPL-3.0-or-later
"""AICUI's changelog (PLAN D61, SPEC §21): git under the hood, never in the user's history.

A shadow git store per project, `.cinminai/changelog.git`, with the project folder as its work tree. Before the AI
changes a file, the file's current state is snapshotted (once per file, so undo always has the original); after
the change, the new state. Each change is one line in `.cinminai/changelog.jsonl`: which file, the commits before
and after, the model, the goal, the lines added and removed. Undo restores the file exactly as it was before that
change. The user's own repository (`.git`) is never read for writing, staged or committed.
"""

from __future__ import annotations

import json
import os
import subprocess
import time

OUTSIDE = "outside AICUI"  # who made a change nobody in AICUI made
AUTHOR = ["-c", "user.name=AICUI changelog", "-c", "user.email=changelog@cinminai.local", "-c", "commit.gpgsign=false"]


class Changelog:
    def __init__(self, root: str) -> None:
        self.root = os.path.abspath(root)
        self.dir = os.path.join(self.root, ".cinminai")
        self.store = os.path.join(self.dir, "changelog.git")
        self.index = os.path.join(self.dir, "changelog.jsonl")

    def _git(self, *args: str, check: bool = True) -> str:
        r = subprocess.run(["git", f"--git-dir={self.store}", f"--work-tree={self.root}", *AUTHOR, *args],
                           capture_output=True, text=True, timeout=30)
        if check and r.returncode != 0:
            raise RuntimeError(f"changelog: git {' '.join(args[:2])}: {r.stderr.strip()[:300]}")
        return r.stdout

    def _ensure(self) -> None:
        if not os.path.isdir(self.store):
            os.makedirs(self.dir, exist_ok=True)
            subprocess.run(["git", "init", "-q", "--bare", self.store], check=True, capture_output=True, timeout=30)
            self._git("commit", "-q", "--allow-empty", "-m", "changelog start")
            hide_from_repo(self.root)


    def _snapshot(self, rel: str, message: str) -> str:
        if os.path.exists(os.path.join(self.root, rel)):
            self._git("add", "-f", "--", rel)
        else:
            self._git("rm", "-q", "--cached", "--ignore-unmatch", "--", rel)
        self._git("commit", "-q", "--allow-empty", "-m", message)
        return self._git("rev-parse", "HEAD").strip()

    def before(self, rel: str) -> str:
        """Call before changing rel: snapshots its state right now (the user may have edited it since the last
        change; a new file's "before" is its absence); returns that commit."""
        self._ensure()
        return self._snapshot(rel, f"before: {rel}")

    def after(self, rel: str, before: str, model: str = "", goal: str = "", what: str = "") -> dict:
        """Call after changing rel: records the change and returns its changelog entry."""
        commit = self._snapshot(rel, json.dumps({"file": rel, "model": model, "goal": goal, "what": what}))
        stat = self._git("diff", "--numstat", before, commit, "--", rel).split()
        entries = self.entries()
        e = {"id": (entries[-1]["id"] + 1) if entries else 1, "time": time.strftime("%Y-%m-%dT%H:%M:%S"), "file": rel,
             "before": before, "after": commit, "added": int(stat[0]) if stat and stat[0].isdigit() else 0,
             "removed": int(stat[1]) if len(stat) > 1 and stat[1].isdigit() else 0, "model": model, "goal": goal,
             "what": what, "undone": False}
        with open(self.index, "a", encoding="utf-8") as f:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
        return e

    def entries(self) -> list[dict]:
        try:
            with open(self.index, encoding="utf-8") as f:
                return [json.loads(line) for line in f if line.strip()]
        except (OSError, ValueError):
            return []

    def diff(self, e: dict) -> str:
        return self._git("diff", e["before"], e["after"], "--", e["file"], check=False)

    def undo(self, eid: int) -> dict:
        """Put the file back exactly as it was before change eid (a new file is removed again). The undo is itself
        snapshotted, so it can be seen in the store."""
        entries = self.entries()
        e = next(x for x in entries if x["id"] == eid)
        path = os.path.join(self.root, e["file"])
        existed = bool(self._git("ls-tree", "--name-only", e["before"], "--", e["file"]).strip())
        if existed:
            content = subprocess.run(["git", f"--git-dir={self.store}", "show", f"{e['before']}:{e['file']}"],
                                     capture_output=True, timeout=30, check=True).stdout
            os.makedirs(os.path.dirname(path) or self.root, exist_ok=True)
            with open(path, "wb") as f:
                f.write(content)
        elif os.path.exists(path):
            os.remove(path)
        self._snapshot(e["file"], f"undo of change {eid}: {e['file']}")
        for x in entries:
            if x["id"] == eid:
                x["undone"] = True
        tmp = self.index + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.writelines(json.dumps(x, ensure_ascii=False) + "\n" for x in entries)
        os.replace(tmp, self.index)
        return e


    # --- changes made outside AICUI: the person in an editor, or a program the project ran ------------------------
    def known(self, rel: str) -> bool:
        """Whether the store has this file (its last state is what the next change is measured from)."""
        self._ensure()
        return bool(self._git("ls-tree", "--name-only", "HEAD", "--", rel, check=False).strip())

    def same_as_kept(self, rel: str) -> bool:
        path = os.path.join(self.root, rel)
        kept = self._git("rev-parse", "-q", "--verify", f"HEAD:{rel}", check=False).strip()
        if not os.path.exists(path):
            return not kept
        return bool(kept) and self._git("hash-object", "--", path, check=False).strip() == kept  # (a full path:
        # hash-object reads paths from the process's folder, not the work tree)

    def baseline(self, rels: list[str]) -> None:
        """Files already there when AICUI opened: kept as they are, quietly, so later changes have a "before"."""
        self._ensure()
        self._git("add", "-f", "--", *rels)
        self._git("commit", "-q", "--allow-empty", "-m", f"baseline: {len(rels)} files")

    def outside(self, rel: str, who: str = OUTSIDE) -> dict | None:
        """A change nobody in AICUI made, recorded like the AI's (with undo); None when the file is as kept."""
        self._ensure()
        if self.same_as_kept(rel):
            return None
        before = self._git("rev-parse", "HEAD").strip()
        gone = not os.path.exists(os.path.join(self.root, rel))
        where = "outside AICUI" if who == OUTSIDE else "by a command it ran"  # a model's command: its own (agent.ran_by_me)
        return self.after(rel, before, model=who, what=("deleted " if gone else "changed ") + where)


WATCH_EXT = {".py", ".js", ".ts", ".html", ".css", ".json", ".md", ".txt", ".sh", ".c", ".cc", ".cpp", ".h", ".hpp",
             ".rs", ".go", ".java", ".toml", ".yaml", ".yml", ".ini", ".cfg", ".xml", ".svg", ".csv"}
WATCH_MAX = 512 * 1024   # bigger files aren't the project's code: not watched
SETTLE_S = 3.0           # a file changed in the last few seconds is looked at next time (an AI change may be finishing)


class Watcher:
    """Changes made outside AICUI, into the same changelog with undo (PLAN D61: "a changelog of every file … with
    undo"; Ian, 2026-10-15, fixed a run.sh himself). The project's own text files are looked at every few seconds;
    the AI's changes are already recorded, so they're never counted twice."""

    def __init__(self, log: Changelog, started: float | None = None) -> None:
        self.log, self.started, self.seen = log, started or time.time(), {}

    def candidates(self) -> dict:
        from . import intake
        from .project import tree
        out = {}
        for rel, is_dir, _ in tree(self.log.root):
            if is_dir or os.path.splitext(rel)[1].lower() not in WATCH_EXT or rel.split("/")[0] in ("sources",):
                continue
            try:
                st = os.stat(os.path.join(self.log.root, rel))
            except OSError:
                continue
            if st.st_size <= WATCH_MAX and not intake.came_in(self.log.root, rel):
                out[rel] = (st.st_mtime, st.st_size)
        return out

    def sweep(self, now: float | None = None) -> list[dict]:
        now = now or time.time()
        found, entries, quiet = self.candidates(), [], []
        for rel, sig in found.items():
            if self.seen.get(rel) == sig or now - sig[0] < SETTLE_S:
                continue
            first = rel not in self.seen
            self.seen[rel] = sig
            if not self.log.known(rel) and first and sig[0] < self.started:
                quiet.append(rel)  # there before AICUI opened: its starting point, not a change
                continue
            e = self.log.outside(rel)
            if e:
                entries.append(e)
        for rel in [r for r in self.seen if r not in found]:  # gone
            self.seen.pop(rel)
            if self.log.known(rel):
                e = self.log.outside(rel)
                if e:
                    entries.append(e)
        if quiet:
            self.log.baseline(quiet)
        return entries


def hide_from_repo(root: str) -> None:
    """In a git project, keep .cinminai/ out of `git status` via the repository's local exclude file (never
    committed or shared) — not .gitignore, which is the user's."""
    info = os.path.join(root, ".git", "info")
    if not os.path.isdir(os.path.join(root, ".git")):
        return
    path = os.path.join(info, "exclude")
    try:
        have = open(path, encoding="utf-8").read() if os.path.exists(path) else ""
        if ".cinminai/" not in have.split():
            os.makedirs(info, exist_ok=True)
            with open(path, "a", encoding="utf-8") as f:
                f.write(("" if have.endswith("\n") or not have else "\n") + ".cinminai/\n")
    except OSError:
        pass
