# SPDX-License-Identifier: GPL-3.0-or-later
"""How much context the working models get, chosen by the person (PLAN D93; Ian, 2026-10-14: "if you have one model
working, you can just max out the context or maybe you want to reserve some working space for yourself while the
bot works, so you half it. Or you could have 2 bots, and you pick how big each ones context size is").

Four choices, kept per person (~/.config/cinminai/context.json) because they follow the computer, not the project:

* default — the sizes Cin-MinAI picks (the coder 32K where it fits, each of team B's two 32K);
* fill    — the most context that keeps each model answering about as fast as by default: at most a tenth slower
            (SLOWER), never a smaller cache type. A MoE model gives a little of its card to the cache by moving some
            experts to RAM, which costs little: only a few per cent of them are read for each word;
* room    — half of that, and the memory it frees held back for the person's own work (else a MoE model would
            fill it with experts);
* custom  — the sizes the person sets, placed as they fit (said plainly when that puts more of a model in RAM).

With two models, fill and room are shared by a split: how much of the room goes to the first model, the rest to the
second. Context costs memory for the model's cache, the same for every token (Qwen3.5-9B: 17 KB a token at q8_0)."""

from __future__ import annotations

import dataclasses
import json
import os

from . import matcher
from .matcher import MiB, Machine, Model

STEP = 4096
MIN = 8192
MAX = 131072            # beyond this the first read of a full context takes minutes on the cards we plan for
DEFAULT = 32768
SLOWER = 0.9          # fill: at most this much slower to answer than at the default size (matcher's estimate)
CHOICES = (("default", "As Cin-MinAI picks"), ("fill", "Fill the card"),
           ("room", "Leave me room (half)"), ("custom", "Choose the sizes"))


def defaults() -> dict:
    return {"choice": "default", "split": 0.5, "solo": DEFAULT, "first": DEFAULT, "second": DEFAULT}


def path() -> str:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, "cinminai", "context.json")


def clean(prefs) -> dict:
    out = defaults()
    if not isinstance(prefs, dict):
        return out
    if prefs.get("choice") in dict(CHOICES):
        out["choice"] = prefs["choice"]
    try:
        out["split"] = min(1.0, max(0.0, float(prefs.get("split", 0.5))))
    except (TypeError, ValueError):
        pass
    for k in ("solo", "first", "second"):
        try:
            out[k] = clamp(int(prefs.get(k, DEFAULT)))
        except (TypeError, ValueError):
            pass
    return out


def load(file: str | None = None) -> dict:
    try:
        with open(file or path(), encoding="utf-8") as f:
            return clean(json.load(f))
    except (OSError, ValueError):
        return defaults()


def save(prefs: dict, file: str | None = None) -> None:
    file = file or path()
    os.makedirs(os.path.dirname(file), exist_ok=True)
    with open(file + ".tmp", "w", encoding="utf-8") as f:
        json.dump(clean(prefs), f)
    os.replace(file + ".tmp", file)


def clamp(ctx: int) -> int:
    return max(MIN, min(MAX, int(ctx) // STEP * STEP))


def as_fast(a: dict | None, base: dict | None) -> bool:
    """Runs about as well as at the default size: the same cache type, and the same placement or at most a tenth
    slower by the matcher's speed estimate."""
    if not (a and base and a["cache"] == base["cache"]):
        return False
    return a["mode"] == base["mode"] or speed(a) >= SLOWER * speed(base)


def speed(p: dict) -> float:
    """The matcher's estimate (a pair plan gives it as a range, low and high)."""
    t = p["tok_s"]
    return sum(t) / len(t) if isinstance(t, (list, tuple)) else float(t)


def most(fits, lo: int = MIN) -> int:
    """The largest context (a multiple of STEP, lo..MAX) for which fits(ctx) holds; lo when none above it does."""
    lo, hi = clamp(lo), MAX
    if fits(hi):
        return hi
    while hi - lo > STEP:  # fits(lo) holds, fits(hi) doesn't
        mid = (lo + hi) // 2 // STEP * STEP
        lo, hi = (mid, hi) if fits(mid) else (lo, mid)
    return lo


def fit(m: Model, machine: Machine, prefs: dict, base_ctx: int = DEFAULT) -> tuple[int, dict | None]:
    """One model's context and plan (matcher.plan's shape) for the person's choice; base_ctx is the default size."""
    p = clean(prefs)
    if p["choice"] == "custom":
        return p["solo"], matcher.plan(m, machine, p["solo"])
    base_ctx = clamp(base_ctx)
    base = matcher.plan(m, machine, base_ctx)
    if p["choice"] == "default" or base is None:
        return base_ctx, base
    full = most(lambda c: as_fast(matcher.plan(m, machine, c), base), base_ctx)
    if p["choice"] == "fill":
        return full, matcher.plan(m, machine, full)
    ctx = clamp(full // 2)  # room: half the context, planned with the memory it frees held back for the person
    held = held_back(machine, kv_mib(m, matcher.plan(m, machine, full), full) / 2)
    return ctx, matcher.plan(m, held, ctx) or matcher.plan(m, machine, ctx)


def held_back(machine: Machine, mib: float) -> Machine:
    """The machine with mib of the card kept free for the person (a MoE model would otherwise fill it with experts)."""
    if not machine.cards:
        return machine
    card = dict(machine.cards[0], free_mib=machine.cards[0]["free_mib"] - int(mib))
    return dataclasses.replace(machine, cards=[card, *machine.cards[1:]])


def fit_pair(first: Model, second: Model, machine: Machine, prefs: dict,
             base_ctx: int = DEFAULT) -> tuple[tuple[int, int], dict | None]:
    """Team B's two contexts and their pair plan (matcher.pair_plan's shape): the first model (the Junior, placed
    first, whole on the card) and the second (the Senior, a MoE, in what's left). The split shares the room."""
    p = clean(prefs)
    if p["choice"] == "custom":
        sizes = (p["first"], p["second"])
        return sizes, matcher.pair_plan(first, second, machine, *sizes)
    base = matcher.pair_plan(first, second, machine, base_ctx, base_ctx)
    if p["choice"] == "default" or base is None:
        return (base_ctx, base_ctx), base

    def kv(m: Model, plan: dict) -> int:
        return m.kv8 if plan["cache"] == "q8_0" else m.kv4

    kv1, kv2 = kv(first, base["junior"]), kv(second, base["senior"])

    def sizes(spare_mib: int) -> tuple[int, int]:  # spare memory beyond the defaults, shared by the split
        a = base_ctx + int(p["split"] * spare_mib * MiB / kv1)
        b = base_ctx + int((1 - p["split"]) * spare_mib * MiB / kv2)
        return clamp(a), clamp(b)

    def fits(spare_mib: int) -> bool:
        pp = matcher.pair_plan(first, second, machine, *sizes(spare_mib))
        return bool(pp and as_fast(pp["junior"], base["junior"]) and as_fast(pp["senior"], base["senior"]))

    top = int(machine.cards[0]["total_mib"]) if machine.cards else 0
    lo, hi = 0, top
    while hi - lo > 16:  # the most spare memory (MiB) the two can share without either running differently
        mid = (lo + hi) // 2
        lo, hi = (mid, hi) if fits(mid) else (lo, mid)
    a, b = sizes(lo)
    if p["choice"] == "fill":
        return (a, b), matcher.pair_plan(first, second, machine, a, b)
    full = matcher.pair_plan(first, second, machine, a, b)  # room: half of each, the freed memory held back
    freed = (kv_mib(first, full["junior"], a) + kv_mib(second, full["senior"], b)) / 2 if full else 0
    a, b = clamp(a // 2), clamp(b // 2)
    return (a, b), (matcher.pair_plan(first, second, held_back(machine, freed), a, b)
                    or matcher.pair_plan(first, second, machine, a, b))


def kv_mib(m: Model, plan: dict | None, ctx: int) -> float:
    """The cache's memory at ctx, for saying what a size costs."""
    if not plan:
        return 0.0
    return (m.kv8 if plan["cache"] == "q8_0" else m.kv4) * ctx / MiB


def say(name: str, m: Model, ctx: int, plan: dict | None) -> str:
    """One line: the size, what it costs and where the model runs with it."""
    if not plan:
        return f"{name}: {ctx // 1024}K doesn't fit this computer"
    return (f"{name}: {ctx // 1024}K context ({kv_mib(m, plan, ctx) / 1024:.1f} GB of cache) — {plan['mode']}, "
            f"{plan['card_gb']:.1f} GB on the card")


def model_for(file: str, store_path: str) -> Model | None:
    """The matcher's entry for a model file: ours from the catalog, any other from its own header."""
    for ms in matcher.CATALOG.values():
        for m in ms:
            if m.file == file:
                return m
    try:
        return matcher.model_from_gguf(store_path)
    except Exception:
        return None

