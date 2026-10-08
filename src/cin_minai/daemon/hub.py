# SPDX-License-Identifier: GPL-3.0-or-later
"""Finding more models on Hugging Face for the Models view (SPEC §22.3, part 2). Every GGUF model there is shown,
whoever made it (Ian: "every model; we assume these are for personal use"), with its licence as its page states it —
not reviewed by us — and whether it runs on this computer.

What leaves the computer (D86, shown before the search is sent): the search words, and which repository and file
were looked at. Nothing else; no account, no token.

* **Search:** huggingface.co/api/models, GGUF only, most downloaded first.
* **Files:** the repository's files at one revision (pinned: what was checked is what's fetched), each with its
  SHA-256 from the repository's own record, so the download is checked like ours.
* **Runs here?** The first megabytes of the file (an HTTP range request) hold its header: the layers, the cache per
  token, the tensors. matcher.plan answers from that, before anything big is downloaded.
* **Download:** the model store's own (resumes, checked, kept in the user's folder).

A model in parts (…-00001-of-00003.gguf), a picture reader (mmproj) and helper files (an imatrix, a
speculative-decoding head) aren't offered: shown, with why.
"""

from __future__ import annotations

import json
import os
import re
import struct
import tempfile
import urllib.parse
import urllib.request
from typing import Callable

from cin_minai.inference import matcher

API = "https://huggingface.co/api"
RESOLVE = "https://huggingface.co/{repo}/resolve/{rev}/{path}"
HEADER_STEPS = (8 << 20, 32 << 20, 96 << 20)  # the header's size varies with the tokenizer: try small first
REPO = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*$")
REV = re.compile(r"^[0-9a-f]{40}$")
PARTS = re.compile(r"-\d{5}-of-\d{5}\.gguf$", re.I)
HELPER = re.compile(r"imatrix|^mtp-|draft", re.I)  # a quantizer's statistics, a speculative-decoding head: not models
UA = {"User-Agent": "Cin-MinAI model finder"}


class HubError(Exception):
    pass


def _get(url: str, opener: Callable, timeout: int = 30):
    try:
        with opener(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except (OSError, ValueError) as e:
        raise HubError(f"Hugging Face didn't answer: {e}") from e


def check_repo(repo: str) -> str:
    if not REPO.match(repo or "") or ".." in repo:
        raise HubError("that isn't a Hugging Face repository name")
    return repo


def licence(tags: list, card: dict | None = None) -> str:
    """The licence as the repository states it (its tags or its card): not reviewed by us."""
    for t in tags or []:
        if isinstance(t, str) and t.startswith("license:"):
            return t.split(":", 1)[1]
    return str((card or {}).get("license") or "")


def search(query: str, opener: Callable = urllib.request.urlopen, limit: int = 20) -> list[dict]:
    """GGUF repositories matching the words, most downloaded first."""
    query = " ".join((query or "").split())[:100]
    if not query:
        raise HubError("type what you're looking for, e.g. qwen coder")
    q = urllib.parse.urlencode({"search": query, "filter": "gguf", "sort": "downloads", "direction": "-1",
                                "limit": str(limit)})
    out = []
    for r in _get(f"{API}/models?{q}", opener):
        repo = r.get("id") or r.get("modelId") or ""
        if not REPO.match(repo) or r.get("private"):
            continue
        out.append({"repo": repo, "licence": licence(r.get("tags")), "downloads": int(r.get("downloads") or 0),
                    "likes": int(r.get("likes") or 0)})
    return out


def files(repo: str, opener: Callable = urllib.request.urlopen) -> dict:
    """The repository at its current revision: its licence, whether it asks for sign-in, and its GGUF files."""
    check_repo(repo)
    info = _get(f"{API}/models/{repo}", opener)
    rev = info.get("sha") or ""
    if not REV.match(rev):
        raise HubError("Hugging Face didn't say which revision this is")
    tree = _get(f"{API}/models/{repo}/tree/{rev}?recursive=true", opener)
    out = []
    for f in tree:
        path = f.get("path") or ""
        if f.get("type") != "file" or not path.lower().endswith(".gguf"):
            continue
        lfs = f.get("lfs") or {}
        name = os.path.basename(path)
        why = ("in parts" if PARTS.search(name) else "picture reader" if "mmproj" in name.lower() else
               "helper file" if HELPER.search(name) else
               "no checksum" if not re.fullmatch(r"[0-9a-f]{64}", lfs.get("oid") or "") else "")
        out.append({"path": path, "file": name, "size": int(lfs.get("size") or f.get("size") or 0),
                    "sha256": lfs.get("oid") or "", "offered": not why, "why_not": why})
    out.sort(key=lambda f: (not f["offered"], f["size"]))
    return {"repo": repo, "revision": rev, "licence": licence(info.get("tags"), info.get("cardData")),
            "gated": bool(info.get("gated")), "files": out}


def model_for(repo: str, rev: str, f: dict, opener: Callable = urllib.request.urlopen) -> matcher.Model:
    """The matcher's entry for one file there, from its header (the first megabytes only)."""
    check_repo(repo)
    if not REV.match(rev or "") or not f.get("offered"):
        raise HubError("that file can't be checked")
    url = RESOLVE.format(repo=repo, rev=rev, path=urllib.parse.quote(f["path"]))
    last = None
    with tempfile.TemporaryDirectory() as d:
        head = os.path.join(d, "head.gguf")
        for n in HEADER_STEPS:
            req = urllib.request.Request(url, headers={**UA, "Range": f"bytes=0-{min(n, f['size']) - 1}"})
            try:
                with opener(req, timeout=120) as r, open(head, "wb") as out:
                    if getattr(r, "status", 206) != 206 and n < f["size"]:
                        raise HubError("Hugging Face sent the whole file instead of its start")
                    out.write(r.read(n))
            except OSError as e:
                raise HubError(f"couldn't read the file's start: {e}") from e
            try:
                m = matcher.model_from_gguf(head, name=os.path.splitext(f["file"])[0], size=f["size"])
                break
            except (struct.error, ValueError, UnicodeDecodeError, EOFError) as e:
                last = e  # the header goes on past what we have: fetch more
        else:
            raise HubError(f"that file's header couldn't be read: {last}")
    if m.layers <= 0 or m.weights <= 0:
        raise HubError("that file isn't a model llama.cpp can run on its own")
    return matcher.Model(m.name, f["file"], m.weights, m.layers, m.kv8, m.kv4, emb=m.emb, experts=m.experts,
                         active=m.active, note="from Hugging Face, your choice", source=f"{repo}@{rev}",
                         sha256=f["sha256"], size=f["size"],
                         remote=f["path"] if f["path"] != f["file"] else "")


def fit(m: matcher.Model, machine) -> dict:
    """Which jobs it can do here, and how fast (the matcher's estimate; the speed test after the download measures)."""
    from . import jobs
    out = {}
    for job, _task, locked, active in jobs.JOBS:
        if locked or not active or job == "vision":
            continue
        p = matcher.plan(m, machine, jobs.context(job))
        out[job] = {"fits": p is not None, "mode": (p or {}).get("mode", ""),
                    "tok_s": round((p or {}).get("tok_s", 0), 1)}
    return out


def on_drives(roots: list[str] | None = None, depth: int = 3) -> list[dict]:
    """GGUF models on connected drives (USB sticks and other disks), so they can be brought in rather than
    downloaded again. Picture readers and parts are skipped, as on Hugging Face."""
    user = os.environ.get("USER") or ""
    roots = roots if roots is not None else [p for p in (f"/media/{user}", f"/run/media/{user}", "/mnt") if p]
    found = []
    for root in roots:
        if not os.path.isdir(root):
            continue
        base = root.rstrip(os.sep).count(os.sep)
        for here, dirs, names in os.walk(root, onerror=lambda e: None):
            if here.count(os.sep) - base >= depth:
                dirs[:] = []
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for n in names:
                if n.lower().endswith(".gguf") and not PARTS.search(n) and "mmproj" not in n.lower():
                    p = os.path.join(here, n)
                    try:
                        found.append({"path": p, "file": n, "size": os.path.getsize(p)})
                    except OSError:
                        pass
    return found
