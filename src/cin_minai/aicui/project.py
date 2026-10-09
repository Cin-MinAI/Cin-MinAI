# SPDX-License-Identifier: GPL-3.0-or-later
"""AICUI's project side (PLAN D61, SPEC §21), no GTK: the working tree with git status, and the session goals.

A project is a folder (or the folder of an opened file). AICUI keeps its own things in `.cinminai/` there: the
session goals (goals.json) and, later, the changelog's shadow git store — never in the user's own git history.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid

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


# --- the project token and its environment (Ian, 2026-10-08; PLAN §1b closure 4) --------------------------------
# "When a folder is opened up if it is an AICUI created project it gets a project token, so if you open your system you
# don't install a venv on your whole system. Only AICUI projects can get a venv, and when it opens it asks if you want
# to create one for the project. … it is just the folder with a header to the real one the AI is using because the bot
# can't make it until it knows what it's making."
ENVS = os.path.join(os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share"), "cinminai", "envs")
HEADER = "cinminai-env.json"
PACKAGE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,80}(\[[A-Za-z0-9,._-]+\])?([<>=!~]=?[A-Za-z0-9.*+!_-]{1,40})?$")


def token_of(root: str) -> str | None:
    try:
        with open(os.path.join(root, ".cinminai", "project.json"), encoding="utf-8") as f:
            return str(json.load(f).get("token") or "") or None
    except (OSError, ValueError):
        return None


def can_be_project(root: str) -> bool:
    """A folder of the person's own, below their home: never the home folder itself or anything of the system."""
    home = os.path.realpath(os.path.expanduser("~"))
    root = os.path.realpath(root)
    return root != home and root.startswith(home + os.sep)


PROJECTS = os.path.join(os.path.dirname(ENVS), "aicui-projects.json")


def known_projects() -> list[str]:
    try:
        with open(PROJECTS, encoding="utf-8") as f:
            return [p for p in json.load(f) if isinstance(p, str)]
    except (OSError, ValueError):
        return []


def orphan_envs(projects: list[str]) -> list[str]:
    """Environments whose project is gone (by token), for AICUI to offer to remove."""
    live = {token_of(p) for p in projects if os.path.isdir(p)}
    try:
        return sorted(os.path.join(ENVS, t) for t in os.listdir(ENVS) if t not in live)
    except OSError:
        return []


def make_project(root: str) -> str:
    """Give a folder AICUI's project token (made by AICUI, or a folder the person made one)."""
    if not can_be_project(root):
        raise ValueError("only a folder inside your home folder can be a project")
    token = token_of(root)
    if token:
        return token
    token = uuid.uuid4().hex
    os.makedirs(os.path.join(root, ".cinminai"), exist_ok=True)
    with open(os.path.join(root, ".cinminai", "project.json"), "w", encoding="utf-8") as f:
        json.dump({"token": token, "made": time.strftime("%Y-%m-%dT%H:%M:%S"), "by": "aicui",
                   "name": os.path.basename(root)}, f, indent=1)
    projects = known_projects()
    if os.path.realpath(root) not in projects:
        os.makedirs(os.path.dirname(PROJECTS), exist_ok=True)
        with open(PROJECTS, "w", encoding="utf-8") as f:
            json.dump(projects + [os.path.realpath(root)], f, indent=1)
    return token


def env_header(root: str) -> dict | None:
    """The project's environment header (the .venv folder's, or the built environment's through its link)."""
    try:
        with open(os.path.join(root, ".venv", HEADER), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def env_state(root: str) -> str:
    """"none", "declared" (the header only: nothing installed yet), "built" (made by AICUI), "external" (a venv the
    person or another tool made — left as it is)."""
    venv = os.path.join(root, ".venv")
    header = env_header(root)
    if header and header.get("built") and os.path.exists(os.path.join(venv, "bin", "python")):
        return "built"
    if header:
        return "declared"
    if any(os.path.exists(os.path.join(root, n, "bin", "python")) for n in (".venv", "venv")):
        return "external"
    return "none"


def declare_env(root: str) -> dict:
    """The person accepted an environment: `.venv/` with its header only; nothing is installed until the work shows
    what it needs and the person agrees."""
    token = token_of(root)
    if not token:
        raise ValueError("only an AICUI project gets an environment")
    if env_state(root) in ("built", "external"):
        return env_header(root) or {}
    header = {"token": token, "python": f"{sys.version_info.major}.{sys.version_info.minor}", "packages": [],
              "wanted": [], "real": os.path.join(ENVS, token), "built": "", "made": time.strftime("%Y-%m-%dT%H:%M:%S")}
    os.makedirs(os.path.join(root, ".venv"), exist_ok=True)
    write_header(os.path.join(root, ".venv"), header)
    return header


def write_header(folder: str, header: dict) -> None:
    fd, tmp = tempfile.mkstemp(dir=folder, prefix=".env-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(header, f, ensure_ascii=False, indent=1)
    os.replace(tmp, os.path.join(folder, HEADER))


def want_package(root: str, package: str, why: str = "") -> str:
    """The AI declares a package the work needs: it goes in the header's "wanted"; AICUI asks the person and builds."""
    package = package.strip()
    if not PACKAGE.match(package):
        raise ValueError(f"{package!r} isn't a package name pip knows how to read")
    header = env_header(root)
    if header is None:
        raise ValueError("this project has no environment yet: the person can create one when AICUI opens it")
    if package in header.get("packages", []) or package in header.get("wanted", []):
        return "already"
    header.setdefault("wanted", []).append(package)
    header.setdefault("why", {})[package] = why[:200]
    write_header(os.path.realpath(os.path.join(root, ".venv")), header)
    return "wanted"


def has_tests(root: str) -> bool:
    """test_*.py (or *_test.py) at the project's top or in tests/."""
    for folder in (root, os.path.join(root, "tests")):
        try:
            if any(re.match(r"(test_.*|.*_test)\.py$", n) for n in os.listdir(folder)):
                return True
        except OSError:
            pass
    return False


def build_env(root: str, say=print, run=subprocess.run) -> dict:
    """Make (or bring up to date) the real environment outside the project, install what the header wants, and link
    `.venv` to it; write requirements.txt for other tools. Run by AICUI — with the network — after the person agreed."""
    header = env_header(root)
    if header is None:
        raise ValueError("no environment header")
    real = header["real"]
    if not os.path.exists(os.path.join(real, "bin", "python")):
        say(f"Making the Python environment in {real}…")
        r = run([sys.executable, "-m", "venv", real], capture_output=True, text=True)
        if r.returncode != 0 or not os.path.exists(os.path.join(real, "bin", "pip")):
            raise RuntimeError("Python couldn't make the environment (" + (r.stderr or "").strip()[-200:] + ") — is the "
                               "python3-venv package installed?")
    if has_tests(root) and "pytest" not in header.get("packages", []) + header.get("wanted", []):
        header.setdefault("wanted", []).append("pytest")  # the project has tests: the tool that runs them comes along
    wanted = [p for p in header.get("wanted", []) if p not in header.get("packages", [])]
    if wanted:
        say("Installing " + ", ".join(wanted) + " from PyPI…")
        r = run([os.path.join(real, "bin", "pip"), "install", "--disable-pip-version-check", *wanted],
                capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError("pip couldn't install " + ", ".join(wanted) + ": " + (r.stderr or "").strip()[-300:])
    header["packages"] = sorted(set(header.get("packages", [])) | set(wanted))
    header["wanted"] = []
    header["built"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    write_header(real, header)
    venv = os.path.join(root, ".venv")
    if not os.path.islink(venv):  # the header folder becomes the link to the real one
        shutil.rmtree(venv)
        os.symlink(real, venv)
    with open(os.path.join(root, "requirements.txt"), "w", encoding="utf-8") as f:
        f.write("".join(p + "\n" for p in header["packages"]))
    return header



DATA_FILES = (".json", ".csv", ".tsv", ".yaml", ".yml", ".xml")
CODE_FILES = (".py", ".c", ".cc", ".cpp", ".h", ".hpp", ".js", ".ts", ".html", ".sh")


def goal_stages(root: str, goal: dict) -> dict:
    """Where a goal stands in the habit cycle (D96; PLAN §1b closure 2), from its evidence and the files — fetched,
    structured, checked, used, reviewed. {"lines": the stages that have evidence, "unchecked": data no test reads}."""
    ev = goal.get("evidence", {})
    sources = [r for r in ev.get("sources", []) if os.path.exists(os.path.join(root, r))]
    data = [r for r in ev.get("data", []) if os.path.exists(os.path.join(root, r))]
    tests, code = {}, {}
    for rel, is_dir, _ in tree(root):
        if is_dir or not rel.endswith(CODE_FILES):
            continue
        try:
            with open(os.path.join(root, rel), encoding="utf-8", errors="replace") as f:
                text = f.read(400_000)
        except OSError:
            continue
        (tests if os.path.basename(rel).startswith("test_") else code)[rel] = text
    checked = [d for d in data if any(os.path.basename(d) in t for t in tests.values())]
    used = [d for d in data if any(os.path.basename(d) in c for c in code.values())]
    lines = []
    if sources:
        lines.append("fetched: " + ", ".join(sources))
    if data:
        lines.append("structured: " + ", ".join(data))
        unchecked = [d for d in data if d not in checked]
        lines.append("checked by a test: " + (", ".join(checked) or "nothing yet")
                     + (f" (not: {', '.join(unchecked)})" if checked and unchecked else ""))
        if used:
            lines.append("used by the code: " + ", ".join(used))
    if goal.get("ticked_by") == "person":
        lines.append("reviewed: ticked by the person")
    return {"lines": lines, "unchecked": [d for d in data if d not in checked]}


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

    def set_done(self, gid: int, done: bool, by: str = "") -> None:
        goals = self.load()
        for g in goals:
            if g["id"] == gid:
                g["done"] = done
                if by:
                    g["ticked_by"] = by if done else ""
        self.save(goals)

    def remove(self, gid: int) -> None:
        self.save([g for g in self.load() if g["id"] != gid])

    def current(self) -> dict | None:
        return next((g for g in self.load() if not g["done"]), None)

    def note(self, gid: int, kind: str, rel: str) -> None:
        """Evidence for a goal's cycle (D96): a source fetched, data structured from it, while the goal was worked."""
        goals = self.load()
        for g in goals:
            if g["id"] == gid:
                have = g.setdefault("evidence", {}).setdefault(kind, [])
                if rel not in have:
                    have.append(rel)
        self.save(goals)
