# SPDX-License-Identifier: GPL-3.0-or-later
"""Installing through the assistant (update 6; PLAN D85, D88, D93): it proposes, the person allows the card, the system
asks for the administrator password (cinminai-admin), apt installs. The assistant is never the admin.

* A program by name: only a package the system's own sources have (apt), and not one that's already installed.
* The graphics driver: the one the system's driver tool recommends for this card — the same list Driver Manager shows.
* The CUDA engine (D93): once the NVIDIA driver is in and `cinminai-llama-cuda` isn't, offered once, with its size;
  "No" is remembered.

Everything here reads (dpkg, apt-cache, ubuntu-drivers); the change itself is the admin action.
"""

from __future__ import annotations

import json
import os
import re
import subprocess

from cin_minai.inference import hardware

CUDA_PKG = "cinminai-llama-cuda"
PKG = re.compile(r"[a-z0-9][a-z0-9+.-]{1,62}")


def _run(argv: list[str], timeout: float = 20) -> str:
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=timeout,
                              env={**os.environ, "LC_ALL": "C.UTF-8"}).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def state(package: str) -> str:
    """installed | available | unknown (not in this system's sources, or not a package name)."""
    if not PKG.fullmatch(package):
        return "unknown"
    if "install ok installed" in _run(["dpkg-query", "-W", "-f=${Status}", package]):
        return "installed"
    m = re.search(r"Candidate:\s*(\S+)", _run(["apt-cache", "policy", package]))
    return "available" if m and m.group(1) != "(none)" else "unknown"


def download_mb(package: str) -> int | None:
    """What installing it would download, with the packages it needs (apt's own list of files and sizes)."""
    out = _run(["apt-get", "--print-uris", "-qq", "install", package], timeout=30)
    sizes = [int(line.split()[2]) for line in out.splitlines() if line.startswith("'") and len(line.split()) >= 3
             and line.split()[2].isdigit()]
    return round(sum(sizes) / 2**20) if sizes else None


def recommended_driver() -> str:
    """The driver package the system's driver tool recommends for this computer's graphics card ("" if none)."""
    # "nvidia-driver-580 linux-modules-nvidia-580-generic-hwe-24.04" (Ian's PC, 2026-10-08); older versions put a comma
    # after the name. The driver package itself brings what it needs (DKMS builds the module for the running kernel).
    for line in _run(["ubuntu-drivers", "list", "--recommended"], timeout=60).splitlines():
        words = re.split(r"[\s,]+", line.strip())
        if words and PKG.fullmatch(words[0]) and words[0].startswith(("nvidia-driver-", "nvidia-", "amdgpu", "intel")):
            return words[0]
    return ""


def cuda_wanted(server_dir: str) -> bool:
    """The NVIDIA driver is loaded and the CUDA engine isn't installed."""
    return any(g.driver == "nvidia" for g in hardware.gpus()) and \
        not os.path.exists(os.path.join(server_dir, "libggml-cuda.so"))


def _offers_path() -> str:
    base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return os.path.join(base, "cinminai", "offers.json")


def declined(what: str) -> bool:
    try:
        with open(_offers_path(), encoding="utf-8") as f:
            return what in json.load(f).get("declined", [])
    except (OSError, ValueError):
        return False


def decline(what: str) -> None:
    path = _offers_path()
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {}
    data["declined"] = sorted(set(data.get("declined", [])) | {what})
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1)
