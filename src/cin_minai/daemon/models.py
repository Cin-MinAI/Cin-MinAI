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

    # --- the record of where every model is (Ian, 2026-10-02) -------------------------------------------------
    def record(self, model, where: str, path: str = "", replaced_by: str = "") -> None:
        """Note where a model is: "store" (in use here), "parked" (on another drive), or "deleted" (fetch it again
        from its source; replaced_by says what took its place in an upgrade)."""
        s = self.state()
        m = s.setdefault("models", {})
        file = getattr(model, "file", model)
        e = m.get(file, {})
        e.update(where=where, path=path or (self.path(file) if where == "store" else ""),
                 drive=drive_label(path) if where == "parked" else "", time=time.strftime("%Y-%m-%dT%H:%M:%S"))
        for k in ("source", "sha256", "size"):
            if getattr(model, k, None):
                e[k] = getattr(model, k)
        if replaced_by:
            e["replaced_by"] = replaced_by
        m[file] = e
        self.save(s)

    def where(self, file: str) -> dict | None:
        """The record for a file, with "present": whether it's there right now (a parked drive may be unplugged)."""
        e = self.state().get("models", {}).get(os.path.basename(file))
        if e is None and self.has(file):
            e = {"where": "store", "path": self.path(file)}
        if e is not None:
            e = dict(e, present=bool(e.get("path")) and os.path.isfile(e["path"]))
        return e

    def models(self) -> dict:
        """Every model we know of, with where it is and whether it's present (the store's files are always known)."""
        known = dict(self.state().get("models", {}))
        for f in os.listdir(self.root):
            if f.endswith(".gguf") and f not in known:
                known[f] = {"where": "store", "path": self.path(f)}
        return {f: dict(e, present=bool(e.get("path")) and os.path.isfile(e["path"])) for f, e in sorted(known.items())}

    def _copy_checked(self, src: str, dst: str, sha256: str, on_progress, cancel) -> None:
        part = dst + ".part"
        total, done = os.path.getsize(src), 0
        with open(src, "rb") as fi, open(part, "wb") as fo:
            for block in iter(lambda: fi.read(CHUNK), b""):
                if cancel.is_set():
                    raise Cancelled()
                fo.write(block)
                done += len(block)
                on_progress(done, total)
        if sha256 and not self.verify(part, sha256, cancel):
            os.remove(part)
            raise ValueError("the copy didn't match its checksum, so it was removed")
        os.replace(part, dst)

    def park(self, model, folder: str, on_progress: Callable[[int, int], None], cancel: threading.Event) -> str:
        """Move a model out of the store to another drive (copied and checked first); the record says where."""
        if os.path.basename(model.file) in {p.get("file") for p in self.state()["use"].values()}:
            raise ValueError("that model is in use: switch the task to another model first")
        if fat32(folder) and model.size >= 4 << 30:
            raise OSError("that drive is formatted FAT32, which can't hold files over 4 GB; exFAT or ext4 can")
        os.makedirs(folder, exist_ok=True)
        dst = os.path.join(folder, os.path.basename(model.file))
        self._copy_checked(self.path(model.file), dst, model.sha256, on_progress, cancel)
        os.remove(self.path(model.file))
        self.record(model, "parked", dst)
        return dst

    def bring_back(self, model, on_progress: Callable[[int, int], None], cancel: threading.Event) -> str:
        """Copy a parked model back into the store, checked; it stays on the other drive too."""
        e = self.where(model.file)
        if not e or e.get("where") != "parked" or not e.get("present"):
            raise OSError("that model isn't on a connected drive")
        self._copy_checked(e["path"], self.path(model.file), model.sha256, on_progress, cancel)
        self.record(model, "store")
        return self.path(model.file)

    def delete(self, model, replaced_by: str = "") -> None:
        """Remove a model from the store (an upgrade frees its space); the record keeps its source to fetch it again."""
        if self.has(model.file):
            os.remove(self.path(model.file))
        self.record(model, "deleted", replaced_by=replaced_by)

    def download(self, model, on_progress: Callable[[int, int], None], cancel: threading.Event) -> str:
        """Fetch model (a matcher.Model with source/sha256/size) into the store; resume a .part; verify. A parked
        copy on a connected drive is brought back instead of downloaded again."""
        if self.has(model.file):
            return self.path(model.file)
        e = self.where(model.file)
        if e and e.get("where") == "parked" and e.get("present"):
            return self.bring_back(model, on_progress, cancel)
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
        self.record(model, "store")
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


def mount_of(path: str) -> tuple[str, str, str]:
    """(mount point, device, file system) of the drive a path is on, from /proc/mounts."""
    path = os.path.realpath(path)
    while not os.path.ismount(path) and path != os.path.dirname(path):
        path = os.path.dirname(path)
    try:
        with open("/proc/mounts", encoding="utf-8") as f:
            for line in f:
                dev, mnt, fs = line.split()[:3]
                if mnt.encode().decode("unicode_escape") == path:
                    return path, dev, fs
    except OSError:
        pass
    return path, "", ""


def drive_label(path: str) -> str:
    """The drive's label (e.g. "USB Storage"), so the record says which drive a parked model is on."""
    _, dev, _ = mount_of(path)
    d = "/dev/disk/by-label"
    try:
        for name in os.listdir(d):
            if dev and os.path.realpath(os.path.join(d, name)) == os.path.realpath(dev):
                return name.encode().decode("unicode_escape")
    except OSError:
        pass
    return os.path.basename(mount_of(path)[0])


def fat32(path: str) -> bool:
    return mount_of(path)[2] in ("vfat", "msdos")


def main() -> int:
    """python3 -m cin_minai.daemon.models [--list | --park FILE FOLDER | --bring-back FILE | --record FILE WHERE PATH]"""
    import sys
    from cin_minai.inference import matcher
    store = ModelStore()
    catalog = {m.file: m for ms in matcher.CATALOG.values() for m in ms}
    a = sys.argv[1:]
    progress = lambda done, total: print(f"\r{done / 2**30:.1f} of {total / 2**30:.1f} GB", end="", flush=True)  # noqa: E731
    if a[:1] == ["--park"] and len(a) == 3:
        print("\nparked:", store.park(catalog[a[1]], a[2], progress, threading.Event()))
    elif a[:1] == ["--bring-back"] and len(a) == 2:
        print("\nback in the store:", store.bring_back(catalog[a[1]], progress, threading.Event()))
    elif a[:1] == ["--record"] and len(a) == 4:
        store.record(catalog.get(a[1], a[1]), a[2], a[3])
    for f, e in store.models().items():
        place = {"store": "in the store", "parked": f"parked on {e.get('drive') or 'another drive'}",
                 "deleted": "deleted (can be fetched again)"}.get(e["where"], e["where"])
        print(f"{f}: {place}{'' if e['present'] or e['where'] == 'deleted' else ' (not connected)'}"
              + (f", replaced by {e['replaced_by']}" if e.get("replaced_by") else "") + (f"  {e['path']}" if e.get("path") else ""))
    return 0


def backend_cfg(base: dict, plan: dict, model_path: str) -> dict:
    """LlamaCppBackend settings for a matcher plan: its args, minus what the backend sets itself (context, flash
    attention, cache type, full offload), plus its context, cache type and desktop margin."""
    args, extra, i = list(plan.get("args", [])), [], 0
    own = {"-c", "-fa", "-ctk", "-ctv"}
    while i < len(args):
        a = args[i]
        if a in own or (a == "-ngl" and i + 1 < len(args) and args[i + 1] == "99"):
            i += 2
            continue
        extra.append(a)
        i += 1
    cfg = dict(base)
    cfg.update(model=model_path, model_name=plan.get("model", ""), context=int(plan.get("context", 8192)),
               cache_type=plan.get("cache", "q8_0"), extra_args=extra, desktop_reserve_mib=int(plan.get("reserve_mib") or 0))
    if plan.get("mode") == "on the processor":
        cfg["build"] = "cpu"
    return cfg


def benchmark(chat: Callable, tokens: int = 120) -> float:
    """Generation speed with the model loaded (tokens a second), from llama-server's own timings."""
    _, timings = chat([{"role": "user", "content": "Write a short paragraph about an old lighthouse at dusk."}],
                      max_tokens=tokens)
    t = timings[-1] if isinstance(timings, list) and timings else timings
    return float((t or {}).get("predicted_per_second") or 0.0)


if __name__ == "__main__":
    raise SystemExit(main())
