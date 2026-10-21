# SPDX-License-Identifier: GPL-3.0-or-later
"""A project and its GitHub repository (docs/accounts-and-cloud.md): linked once, then saved (pushed) and brought up to
date (pulled) from AICUI's GitHub menu. Git signs in through our credential helper, which reads the computer's GitHub
link from the login keyring — no token in the project, in git's config or on screen.

What isn't the project's own stays out of its repository: AICUI's working folder (.cinminai/: the changelog, notes of
the models' runs), the Python environment, compiled files. That's checked at every save, not only when the project is
linked: test20 (2026-10-20) had a repository a model made itself, with .cinminai/ already staged, and ignore rules
don't take back what's staged.

Before a save leaves the computer, `review` lists what will go and what in it looks personal or unfinished (PLAN D62:
a Pages site is public; the choice stays the person's).
"""

from __future__ import annotations

import datetime
import fnmatch
import os
import re
import subprocess
import time

HELPER = "/usr/libexec/cinminai-git-credential"
IGNORE = (".cinminai/", ".venv/", "venv/", "__pycache__/", "*.pyc", "*.o")
PRIVATE = (".cinminai", ".venv", "venv")  # folders that never leave the computer, whoever made the repository
AICUI_FILES = ("original-request.txt",)  # AICUI's own notes at the project's top: the person decides if they go
TIMEOUT = 300


def git(root: str, *args: str, helper: str = HELPER) -> tuple[int, str]:
    """git in the project, signing in to github.com through the helper only; it never asks in a terminal. Over SSH,
    the person's own key, never a prompt; a host seen the first time is remembered, as answering "yes" would."""
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_ASKPASS": "/bin/false", "SSH_ASKPASS_REQUIRE": "never"}
    env.setdefault("GIT_SSH_COMMAND", "ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new")
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


def link(root: str, clone_url: str, login: str, name: str = "") -> str:
    """Make the project a git repository if it isn't one, keep AICUI's own folders out of it, and point it at the
    repository. Commits are the account's (its name on GitHub, its no-reply address)."""
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
    keep_private(root)
    if login:  # the account's name on GitHub (a machine's name, e.g. "Simon") when it has one, else its login
        git(root, "config", "user.name", name or login)
        git(root, "config", "user.email", f"{login}@users.noreply.github.com")
    if remote(root):
        git(root, "remote", "set-url", "origin", clone_url)
    else:
        git(root, "remote", "add", "origin", clone_url)
    return clone_url


def _private(path: str) -> bool:
    parts = path.split("/")
    if parts[0] in PRIVATE or "__pycache__" in parts[:-1]:
        return True
    return any(fnmatch.fnmatch(parts[-1], p) for p in IGNORE if not p.endswith("/"))


def keep_private(root: str) -> list[str]:
    """AICUI's folders out of the repository, whoever made it: listed in its local exclude file (never shared), and
    anything of theirs already staged or committed taken back out of git (the files stay on disk). Returns what was
    taken out."""
    if not os.path.isdir(os.path.join(root, ".git")):
        return []
    info = os.path.join(root, ".git", "info")
    path = os.path.join(info, "exclude")
    have = []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            have = f.read().split()
    missing = [p for p in IGNORE if p not in have]
    if missing:
        os.makedirs(info, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write("\n" + "\n".join(missing) + "\n")
    code, out = git(root, "ls-files", "--cached", "-z")
    tracked = [p for p in out.split("\0") if p] if code == 0 else []
    gone = [p for p in tracked if _private(p)]
    for i in range(0, len(gone), 200):
        git(root, "rm", "-q", "--cached", "--ignore-unmatch", "--", *gone[i:i + 200])
    return gone


def leave_out(root: str, rel: str) -> None:
    """One file kept off GitHub at the person's choice (the review's checkbox): in the local exclude file, and out of
    git if it was in. The file stays on disk."""
    if not os.path.isdir(os.path.join(root, ".git")):
        return
    path = os.path.join(root, ".git", "info", "exclude")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    have = []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            have = f.read().split()
    if "/" + rel not in have:
        with open(path, "a", encoding="utf-8") as f:
            f.write("\n/" + rel + "\n")
    git(root, "rm", "-q", "--cached", "--ignore-unmatch", "--", rel)


def private_staged(root: str) -> list[str]:
    """What of AICUI's own would go with the next commit (should be nothing)."""
    code, out = git(root, "diff", "--cached", "--name-only", "-z")
    return [p for p in out.split("\0") if p and _private(p)] if code == 0 else []


def push(root: str, message: str = "") -> tuple[bool, str]:
    """Everything of the project's own, committed (if anything changed) and sent to the repository."""
    if not remote(root):
        return False, "this project isn't linked to a GitHub repository yet"
    keep_private(root)
    git(root, "add", "-A")
    left = private_staged(root)
    if left:  # never sent: a private file still about to go means something here is wrong — stop and say so
        return False, ("not saved: AICUI's own files were still about to go to GitHub (" + ", ".join(left[:5]) +
                       "). Nothing was sent.")
    code, _ = git(root, "diff", "--cached", "--quiet")
    if code == 1:  # something to commit
        code, out = git(root, "commit", "-m", message or f"Saved from AICUI, {time.strftime('%Y-%m-%d %H:%M')}")
        if code != 0:
            return False, out[-800:]
    code, out = git(root, "push", "-u", "origin", "HEAD")
    if code != 0 and "without `workflows` permission" in out:
        return False, ("GitHub refused the save: it has a workflow file (.github/workflows/), and AICUI's GitHub app may "
                       "not send those. Nothing was sent. Leave the workflow out in the look before it goes, or delete "
                       "it, then save again.")
    return code == 0, out[-800:]


def pull(root: str) -> tuple[bool, str]:
    """The repository's newer work brought in — only when it follows on from this copy (nothing is merged by guess)."""
    if not remote(root):
        return False, "this project isn't linked to a GitHub repository yet"
    code, out = git(root, "pull", "--ff-only", "origin", "HEAD")
    if code != 0 and "fatal: Not possible to fast-forward" in out:
        out += "\nBoth this copy and the repository have new work: save yours to a new branch, or ask the AI to merge."
    return code == 0, out[-800:]


# --- bringing a project in: clone (Ian, 2026-10-21: "it shows what was searched so if you messed up something on the
# https or ssh it can be found easier") — the address read, searched, shown back with what was found, cloned on a yes --
HTTPS = re.compile(r"https://(?P<host>[A-Za-z0-9.-]+\.[A-Za-z]{2,})(?::\d+)?/(?P<path>[^\s?#]+?)(?:\.git)?/?")
SSH = re.compile(r"(?:ssh://)?(?P<user>[A-Za-z0-9._-]+)@(?P<host>[A-Za-z0-9.-]+\.[A-Za-z]{2,})(?::\d+/|:|/)"
                 r"(?P<path>[^\s?#]+?)(?:\.git)?/?")


def address(text: str) -> dict:
    """{"url", "kind" (https|ssh), "host", "owner", "name"} from what was pasted or typed; ValueError says what's off."""
    url = text.strip()
    if not url:
        raise ValueError("there's no address yet")
    if " " in url:
        raise ValueError("there's a space in it: an address has none")
    m = HTTPS.fullmatch(url) or SSH.fullmatch(url)
    if not m:
        if url.startswith("http://"):
            raise ValueError("it starts with http://: repositories use https://")
        if url.startswith(("https://", "git@", "ssh://")):
            raise ValueError("the start is right, but the rest isn't host/owner/name")
        raise ValueError("it starts with neither https:// nor git@ (copy it from the repository's Code button)")
    path = m.group("path").split("/")
    if len(path) < 2 or not all(path):
        raise ValueError("it names no repository: after the host it needs owner/name")
    return {"url": url, "kind": "https" if url.startswith("https://") else "ssh", "host": m.group("host").lower(),
            "owner": "/".join(path[:-1]), "name": path[-1]}


def explain(out: str, kind: str) -> str:
    """git's answer, in a sentence."""
    low = out.lower()
    if "could not resolve host" in low or "name or service not known" in low:
        return "that host name doesn't exist, or this computer is offline"
    if "permission denied (publickey)" in low or "no such identity" in low:
        return "SSH didn't let this computer in: it has no SSH key that host knows (the https address needs none)"
    if "host key verification failed" in low:
        return "the host's SSH key changed since this computer last saw it: check the address before going on"
    if "repository not found" in low or "not found" in low or "does not appear to be a git repository" in low:
        return ("no repository at this address" + (", or it's private: sign in to GitHub first" if kind == "https"
                                                   else ", or this account can't see it"))
    if "could not read username" in low or "authentication failed" in low or "terminal prompts disabled" in low:
        return "it's private, and this computer isn't signed in to it"
    if "timed out" in low or "took longer" in low:
        return "the host didn't answer in time"
    return out.strip().splitlines()[-1][:200] if out.strip() else "git didn't say why"


def find(url: str, kind: str = "https") -> dict:
    """Ask the host whether the repository is there, before anything downloads: {"ok", "branch"} or {"ok", "why"}."""
    code, out = git("/", "ls-remote", "--symref", url, "HEAD")
    if code != 0:
        return {"ok": False, "why": explain(out, kind)}
    m = re.search(r"^ref: refs/heads/(\S+)\s+HEAD", out, re.M)
    if not m and not out.strip():
        return {"ok": True, "branch": "", "empty": True}  # there, with nothing in it yet
    return {"ok": True, "branch": m.group(1) if m else ""}


def free_folder(parent: str, name: str) -> str:
    """parent/name, or name-2, name-3… — never an existing folder."""
    path, n = os.path.join(parent, name), 2
    while os.path.exists(path):
        path, n = os.path.join(parent, f"{name}-{n}"), n + 1
    return path


def clone(url: str, dest: str, kind: str = "https") -> tuple[bool, str]:
    """The repository into a new folder, AICUI's folders kept out of it from the start."""
    code, out = git(os.path.dirname(dest) or ".", "clone", "--", url, dest)
    if code != 0:
        return False, explain(out, kind)
    keep_private(dest)
    return True, dest


# --- the look before it goes (PLAN D62) ------------------------------------------------------------------------------
# What a person would want to know before a page goes public. Code finds the obvious; the person decides.
FLAGS = [
    ("a key or token", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----|\b(ghp_|gho_|github_pat_|hf_|sk-|xox[bp]-)"
                                  r"[A-Za-z0-9_-]{16,}|\b(AKIA|ASIA)[A-Z0-9]{16}\b")),
    ("placeholder text", re.compile(r"\(?\b555\)?[-.\s]?\d{3}[-.\s]?\d{4}\b|\(555\)|YOUR[_-](USER ?NAME|NAME|EMAIL)|"
                                    r"your-username|\bexample\.(com|org)\b|lorem ipsum|placeholder\.com",
                                    re.IGNORECASE)),
    ("an email address", re.compile(r"\b[A-Za-z0-9._%+-]+@(?!users\.noreply\.github\.com)[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    ("a phone number", re.compile(r"(?<![\d.])\(?\b\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}\b")),
    ("a street address", re.compile(r"\b\d{1,6}\s+(?:[A-Z][a-z]+\s){1,3}(?:Street|St|Avenue|Ave|Road|Rd|Lane|Ln|"
                                    r"Drive|Dr|Boulevard|Blvd|Court|Ct|Way|Place|Pl)\b")),
    ("a path on this computer", re.compile(r"/home/[a-z_][a-z0-9_-]*/|[A-Z]:\\Users\\")),
]
YEAR = re.compile(r"(?:©|&copy;|\(c\)|copyright)\s*(\d{4})", re.IGNORECASE)


def _files(root: str) -> list[str]:
    if os.path.isdir(os.path.join(root, ".git")):
        code, out = git(root, "ls-files", "-z", "--cached", "--others", "--exclude-standard")
        if code == 0:
            return sorted(p for p in out.split("\0") if p and not _private(p))
    found = []
    for top, dirs, names in os.walk(root):
        dirs[:] = [d for d in dirs if d != ".git" and not _private(os.path.relpath(os.path.join(top, d), root)
                                                                    .replace(os.sep, "/"))]
        found += [os.path.relpath(os.path.join(top, n), root).replace(os.sep, "/") for n in names]
    return sorted(p for p in found if not _private(p))


def review(root: str, limit: int = 40) -> dict:
    """{"files": what would go, "flags": [(file, line, what it looks like, the text)]} — a look, not a verdict."""
    files = _files(root)
    flags: list[tuple[str, int, str, str]] = []
    this_year = datetime.date.today().year
    for rel in files:
        if rel.split("/")[-1] in AICUI_FILES:
            flags.append((rel, 0, "AICUI's note of your request", "it goes too, unless you leave it out"))
        if rel.startswith(".github/workflows/"):
            flags.append((rel, 0, "a GitHub workflow", "AICUI publishes pages itself; a workflow runs code on GitHub"))
        full = os.path.join(root, rel)
        try:
            if os.path.getsize(full) > 512_000:
                continue
            with open(full, "rb") as f:
                raw = f.read()
        except OSError:
            continue
        if b"\0" in raw:
            continue  # pictures and other binaries
        for n, line in enumerate(raw.decode("utf-8", "replace").splitlines(), 1):
            for kind, rx in FLAGS:
                m = rx.search(line)
                if m:
                    flags.append((rel, n, kind, m.group(0)[:80]))
                    break  # one flag a line, the most telling first
            else:
                y = YEAR.search(line)
                if y and int(y.group(1)) < this_year:
                    flags.append((rel, n, "an old year", y.group(0)))
            if len(flags) >= limit:
                return {"files": files, "flags": flags, "more": True}
    return {"files": files, "flags": flags, "more": False}
