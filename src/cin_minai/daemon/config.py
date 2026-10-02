# SPDX-License-Identifier: GPL-3.0-or-later
"""Settings: /etc/cinminai/daemon.toml (the packaged defaults), then the user's
~/.config/cinminai/config.toml on top (SPEC §9: every llama-server option reachable from there).
Only the [inference] and [guide] tables are read; unknown keys are ignored.
"""

from __future__ import annotations

import os
import tomllib

SYSTEM = "/etc/cinminai/daemon.toml"
DEFAULTS = {
    "inference": {
        "model": "/usr/share/cinminai/models/Qwen3.5-4B-guide-HO-Q4_K_M.gguf",
        "model_name": "Cin-MinAI guide",
        "build": "auto",          # auto | cuda | vulkan | cpu
        "context": 8192,          # on the graphics card
        "cpu_context": 4096,      # on the processor (PLAN D27: short prompts there)
        "threads": "auto",
        "temperature": 0.0,       # as measured (training/eval/guide)
        "idle_unload_s": 0,       # SPEC §4.2: idle unload is a choice, not a default
        "desktop_reserve_mib": 0, # graphics memory kept for the desktop; 0 = by the screens (SPEC §4.2)
        "load_timeout_s": 600,
        "extra_args": [],
        "server_dir": "/usr/lib/cinminai/llama",   # cinminai-llama
    },
    "guide": {
        "data_dir": "/usr/share/cinminai/guide",
        "history_chars": 12000,       # on the graphics card
        "cpu_history_chars": 3000,    # on the processor: every token read costs time (D27)
        "preload": "auto",            # load the model when the daemon starts; auto = not on the live USB
    },
}


def user_config() -> str:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, "cinminai", "config.toml")


def live_session() -> bool:
    """Running from the live USB (casper)? There the model loads on the first question instead."""
    try:
        with open("/proc/cmdline", encoding="utf-8") as f:
            return "boot=casper" in f.read().split()
    except OSError:
        return False


def preload(cfg: dict) -> bool:
    p = cfg["guide"]["preload"]
    return not live_session() if p == "auto" else bool(p)


def load(paths: list[str] | None = None) -> dict:
    cfg = {k: dict(v) for k, v in DEFAULTS.items()}
    for path in paths if paths is not None else [SYSTEM, user_config()]:
        try:
            with open(path, "rb") as f:
                data = tomllib.load(f)
        except FileNotFoundError:
            continue
        except (OSError, tomllib.TOMLDecodeError) as e:
            print(f"ignoring {path}: {e}", flush=True)
            continue
        for table in cfg:
            cfg[table].update({k: v for k, v in data.get(table, {}).items() if k in DEFAULTS[table]})
    return cfg
