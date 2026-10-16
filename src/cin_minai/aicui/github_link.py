# SPDX-License-Identifier: GPL-3.0-or-later
"""A project and its GitHub repository (docs/accounts-and-cloud.md): linked once, then saved (pushed) and brought up to
date (pulled) from AICUI's GitHub menu. Git signs in through our credential helper, which reads the computer's GitHub
link from the login keyring — no token in the project, in git's config or on screen.

What isn't the project's own stays out of its repository: AICUI's working folder (.cinminai/: the changelog, notes of
the models' runs), the Python environment, compiled files.
"""

from __future__ import annotations

import os
import subprocess
import time

HELPER = "/usr/libexec/cinminai-git-credential"
IGNORE = (".cinminai/", ".venv/", "venv/", "__pycache__/", "*.pyc", "*.o")
TIMEOUT = 300


def git(root: str, *args: str, helper: str = HELPER) -> tuple[int, str]:
    """git in the project, signing in to github.com through the helper only; it never asks in a terminal."""
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_ASKPASS": "/bin/false"}
    cmd = ["git", "-C", root, "-c", "credential.helper=", "-c", f"credential.helper=!{helper}", *args]
    import contextlib

    from cin_minai.inference import reach
    away = args[0] in ("push", "pull", "fetch", "clone", "ls-remote")  # the ones that go to GitHub
    try:
        with reach.out("web", "GitHub") if away else contextlib.nullcontext():  # the panel's WEB sign
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT, env=env)
    except subprocess.TimeoutExpired:
        return 124, f"git {args[0]} took longer than {TIMEOUT // 60} minutes and was stopped"
    return r.returncode, (r.stdout + r.stderr).strip()


def remote(root: str) -> str:
    code, out = git(root, "remote", "get-url", "origin")
    return out if code == 0 and out.startswith("https://github.com/") else ""


def link(root: str, clone_url: str, login: str) -> str:
    """Make the project a git repository if it isn't one, keep AICUI's own folders out of it, and point it at the
    repository. Commits are the person's (their GitHub name, its no-reply address)."""
    if not clone_url.startswith("https://github.com/"):
        raise ValueError("that isn't a GitHub repository address")
    if not os.path.isdir(os.path.join(root, ".git")):
        git(root, "init", "-b", "main")
    path = os.path.join(root, ".gitignore")
    have = []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            have = f.read().splitlines()
    missing = [p for p in IGNORE if p not in have]
    if missing:
        with open(path, "a", encoding="utf-8") as f:
            f.write(("\n" if have and have[-1] else "") + "\n".join(missing) + "\n")
    if login:
        git(root, "config", "user.name", login)
        git(root, "config", "user.email", f"{login}@users.noreply.github.com")
    if remote(root):
        git(root, "remote", "set-url", "origin", clone_url)
    else:
        git(root, "remote", "add", "origin", clone_url)
    return clone_url


def push(root: str, message: str = "") -> tuple[bool, str]:
    """Everything of the project's own, committed (if anything changed) and sent to the repository."""
    if not remote(root):
        return False, "this project isn't linked to a GitHub repository yet"
    git(root, "add", "-A")
    code, _ = git(root, "diff", "--cached", "--quiet")
    if code == 1:  # something to commit
        code, out = git(root, "commit", "-m", message or f"Saved from AICUI, {time.strftime('%Y-%m-%d %H:%M')}")
        if code != 0:
            return False, out[-800:]
    code, out = git(root, "push", "-u", "origin", "HEAD")
    return code == 0, out[-800:]


def pull(root: str) -> tuple[bool, str]:
    """The repository's newer work brought in — only when it follows on from this copy (nothing is merged by guess)."""
    if not remote(root):
        return False, "this project isn't linked to a GitHub repository yet"
    code, out = git(root, "pull", "--ff-only", "origin", "HEAD")
    if code != 0 and "fatal: Not possible to fast-forward" in out:
        out += "\nBoth this copy and the repository have new work: save yours to a new branch, or ask the AI to merge."
    return code == 0, out[-800:]
