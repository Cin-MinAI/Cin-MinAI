# SPDX-License-Identifier: GPL-3.0-or-later
"""Bigger models for a task, offered and fetched on the user's say-so (PLAN D60, M5; D30 offered never imposed;
Rule 1: nothing leaves the computer before the click).

The store is the user's own folder (no admin rights): ~/.local/share/cinminai/models/. A download resumes after an
interruption, goes to "<file>.part", and becomes "<file>" only after its SHA-256 matches the catalog. state.json
keeps the user's choices: the model in use per task (with the matcher's llama.cpp settings and the measured speed),
and what they said "don't ask again" to.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
import time
import urllib.request
from typing import Callable

ROOT = os.path.join(os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share"), "cinminai", "models")
HF = "https://huggingface.co/{repo}/resolve/{rev}/{file}"
CHUNK = 4 << 20


class Cancelled(Exception):
    pass


class ModelStore:
    def __init__(self, root: str = ROOT, opener: Callable = urllib.request.urlopen) -> None:
        self.root, self.open = root, opener
        os.makedirs(root, exist_ok=True)
        self.state_path = os.path.join(root, "state.json")

    # --- the user's choices --------------------------------------------------------------------------------
    def state(self) -> dict:
        try:
            with open(self.state_path, encoding="utf-8") as f:
                s = json.load(f)
        except (OSError, ValueError):
            s = {}
        s.setdefault("use", {})
        s.setdefault("declined", [])
        return s

    def save(self, s: dict) -> None:
        fd, tmp = tempfile.mkstemp(dir=self.root, prefix=".state-", suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(s, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self.state_path)

    def decline(self, file: str) -> None:
        s = self.state()
        if file not in s["declined"]:
            s["declined"].append(file)
        self.save(s)

    def use(self, task: str, plan: dict | None) -> None:
        """The model for a task (plan: the matcher's file, args, cache, ... and the measured speed), or None for
        back to the built-in guide."""
        s = self.state()
        if plan:
            s["use"][task] = plan
        else:
            s["use"].pop(task, None)
        self.save(s)

    def in_use(self, task: str) -> dict | None:
        p = self.state()["use"].get(task)
        return p if p and self.has(p["file"]) else None

    # --- files ---------------------------------------------------------------------------------------------
    def path(self, file: str) -> str:
        return os.path.join(self.root, os.path.basename(file))

    def has(self, file: str) -> bool:
        return os.path.isfile(self.path(file))

    def free_bytes(self) -> int:
        import shutil
        return shutil.disk_usage(self.root).free

    def download(self, model, on_progress: Callable[[int, int], None], cancel: threading.Event) -> str:
        """Fetch model (a matcher.Model with source/sha256/size) into the store; resume a .part; verify."""
        if self.has(model.file):
            return self.path(model.file)
        repo, _, rev = model.source.partition("@")
        url = HF.format(repo=repo, rev=rev or "main", file=model.file)
        part = self.path(model.file) + ".part"
        have = os.path.getsize(part) if os.path.exists(part) else 0
        if have > model.size:  # not ours: start over
            os.remove(part)
            have = 0
        if model.size - have > self.free_bytes() - (2 << 30):
            raise OSError(f"not enough free disk space: {model.size / 2**30:.1f} GB needed")
        if have < model.size:
            req = urllib.request.Request(url, headers={"Range": f"bytes={have}-"} if have else {})
            with self.open(req, timeout=60) as r, open(part, "ab" if have else "wb") as f:
                if have and getattr(r, "status", 206) == 200:  # the server ignored the range: start over
                    f.truncate(0)
                    have = 0
                last = 0.0
                while True:
                    if cancel.is_set():
                        raise Cancelled()
                    chunk = r.read(CHUNK)
                    if not chunk:
                        break
                    f.write(chunk)
                    have += len(chunk)
                    if time.monotonic() - last > 0.5:
                        on_progress(have, model.size)
                        last = time.monotonic()
        on_progress(have, model.size)
        if not self.verify(part, model.sha256, cancel):
            os.remove(part)
            raise ValueError("the downloaded file didn't match its checksum, so it was removed")
        os.replace(part, self.path(model.file))
        return self.path(model.file)

    @staticmethod
    def verify(path: str, sha256: str, cancel: threading.Event | None = None) -> bool:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for block in iter(lambda: f.read(CHUNK), b""):
                if cancel is not None and cancel.is_set():
                    raise Cancelled()
                h.update(block)
        return h.hexdigest() == sha256


def benchmark(chat: Callable, tokens: int = 120) -> float:
    """Generation speed with the model loaded (tokens a second), from llama-server's own timings."""
    _, timings = chat([{"role": "user", "content": "Write a short paragraph about an old lighthouse at dusk."}],
                      max_tokens=tokens)
    t = timings[-1] if isinstance(timings, list) and timings else timings
    return float((t or {}).get("predicted_per_second") or 0.0)
