# SPDX-License-Identifier: GPL-3.0-or-later
"""What a setup really does on this computer, measured (Ian, 2026-10-14: "a benchmark setup button in AICUI, so it
benchmarks whatever setup you are currently using and tells you those things and stores the benchmark for the context
options").

The matcher plans from estimates: on Ian's 1080 Ti the 27B "fit" 84K and crashed (out of graphics memory once it
read), and a MoE ran at 43 words a second where 72 was estimated. A benchmark loads the setup at each context size,
fills it with text and has it answer; a crash during real work is recorded the same way. Kept per setup (the model
files), card and engine version (~/.local/share/cinminai/benchmarks.json), so a new driver or engine is measured
again. contextfit reads limits() and never offers a size that failed here."""

from __future__ import annotations

import json
import os
import re
import subprocess
import time

LADDER = (32768, 49152, 65536, 98304, 131072)


def path() -> str:
    base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return os.path.join(base, "cinminai", "benchmarks.json")


_engine: list[str] = []


def engine_version(server_dir: str = "/usr/lib/cinminai/llama") -> str:
    """The llama.cpp build in use, by its own build number ("build 11146, commit 7fe450e19"), not our package's
    version, which changes with every update: a new engine is measured again, a new Cin-MinAI build isn't."""
    if not _engine:
        try:
            out = subprocess.run([os.path.join(server_dir, "llama-server"), "--version"], capture_output=True,
                                 text=True, timeout=20, env={**os.environ, "LD_LIBRARY_PATH": server_dir}).stderr
        except (OSError, subprocess.TimeoutExpired):
            out = ""
        m = re.search(r"build (\d+), commit (\w+)", out)
        _engine.append(f"llama.cpp {m.group(1)} {m.group(2)}" if m else "")
    return _engine[0]


def setup_key(files: list[str], card: str, engine: str | None = None) -> str:
    """One setup on one card and engine: its model files in order (a pair: the first, then the second)."""
    return "|".join(["+".join(files), card or "processor", engine if engine is not None else engine_version()])


def card_of(machine) -> str:
    return machine.cards[0]["name"] if getattr(machine, "cards", None) else ""


def load(file: str | None = None) -> dict:
    try:
        with open(file or path(), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def record(key: str, sizes: list[int] | int, ok: bool, file: str | None = None, **measured) -> None:
    """One measurement: sizes (a pair: both) held or failed, with what was measured (why, card_mib, prompt_tps,
    gen_tps, seconds). A later measurement of the same sizes replaces the earlier one."""
    sizes = [int(sizes)] if isinstance(sizes, int) else [int(s) for s in sizes]
    file = file or path()
    data = load(file)
    runs = [r for r in data.get(key, []) if r.get("sizes") != sizes]
    runs.append({"sizes": sizes, "ok": bool(ok), "when": time.strftime("%Y-%m-%dT%H:%M:%S"), **measured})
    data[key] = sorted(runs, key=lambda r: r["sizes"])
    os.makedirs(os.path.dirname(file), exist_ok=True)
    with open(file + ".tmp", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1)
    os.replace(file + ".tmp", file)


def passed(run: dict) -> bool:
    """Held, and really read: a run marked held with nothing read was a crash that ended the stream quietly (the
    first benchmark, 2026-10-14, recorded 64K that way)."""
    return bool(run.get("ok")) and ("read" not in run or int(run.get("read") or 0) > 0)


def limits(key: str, file: str | None = None) -> dict:
    """{"held": the largest size that held below the smallest that failed (a pair: per model), "failed": that
    smallest failure, "runs": every measurement} — held/failed None when not measured."""
    runs = load(file).get(key, [])
    failed = [r["sizes"] for r in runs if not passed(r)]
    low = min(failed, key=lambda s: max(s)) if failed else None
    held = [r["sizes"] for r in runs if passed(r) and (low is None or max(r["sizes"]) < max(low))]
    return {"held": max(held, key=lambda s: max(s)) if held else None, "failed": low, "runs": runs}


def cap(sizes: list[int], key: str, file: str | None = None) -> tuple[list[int], str]:
    """sizes, kept below a size that failed on this card (the largest that held instead): (sizes, why) — why is ""
    when nothing changed."""
    lim = limits(key, file)
    if lim["failed"] is None or max(sizes) < max(lim["failed"]):
        return sizes, ""
    held = lim["held"] or [min(lim["failed"]) // 2] * len(sizes)
    out = [min(s, h) for s, h in zip(sizes, held + held[-1:] * (len(sizes) - len(held)))]
    return out, (f"{max(lim['failed']) // 1024}K failed on this card when measured; "
                 f"{', '.join(f'{s // 1024}K' for s in out)} held")


def summary(key: str, file: str | None = None) -> str:
    """A line for the Context dialog: what was measured here."""
    lim = limits(key, file)
    if not lim["runs"]:
        return "Not measured on this card yet: Benchmark (top bar) measures it."
    def k(s):
        return " + ".join(f"{x // 1024}K" for x in s)
    best = next((r for r in lim["runs"] if r["sizes"] == lim["held"]), None)
    parts = []
    if lim["held"]:
        parts.append(f"held up to {k(lim['held'])}"
                     + (f" ({best['gen_tps']:.0f} words a second)" if best and best.get("gen_tps") else ""))
    if lim["failed"]:
        parts.append(f"{k(lim['failed'])} failed")
    return "Measured on this card: " + ", ".join(parts) + "."


# --- the junior's limits, measured by the Benchmark's coding run (aicui/bench.py) ------------------------------------
# Ian, 2026-10-15: the junior's script limit and step limit per task "should be part of benchmark". Until a model is
# measured on this card, these stand in (said so wherever they're used).
JUNIOR_LINES = 150
JUNIOR_STEPS = 25


def coding_key(file: str, card: str, engine: str | None = None) -> str:
    return "coding|" + setup_key([file], card, engine)


def coding_limits(file: str, card: str, store: str | None = None) -> dict:
    """{"lines", "steps", "measured"}: what the model's largest passing coding task took (steps with headroom), or the
    stand-ins when it hasn't been measured here."""
    runs = load(store).get(coding_key(file, card), [])
    passed = [r for r in runs if r.get("ok")]
    if not passed:
        return {"lines": JUNIOR_LINES, "steps": JUNIOR_STEPS, "measured": False}
    best = max(passed, key=lambda r: r.get("lines", 0))
    steps = max(int(r.get("steps", 0)) for r in passed)
    return {"lines": max(40, int(best.get("lines", 0)) // 10 * 10), "steps": max(15, min(60, -(-steps * 3 // 2))),
            "measured": True}


def record_coding(file: str, card: str, functions: int, ok: bool, store: str | None = None, **measured) -> None:
    """One coding run: `functions` asked for, whether its tests passed, with lines written and steps taken."""
    store = store or path()
    data = load(store)
    key = coding_key(file, card)
    runs = [r for r in data.get(key, []) if r.get("functions") != functions]
    runs.append({"functions": functions, "ok": bool(ok), "when": time.strftime("%Y-%m-%dT%H:%M:%S"), **measured})
    data[key] = sorted(runs, key=lambda r: r["functions"])
    os.makedirs(os.path.dirname(store), exist_ok=True)
    with open(store + ".tmp", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1)
    os.replace(store + ".tmp", store)
