# SPDX-License-Identifier: GPL-3.0-or-later
"""Jobs and their models (SPEC §22.3, PLAN D93): the Models view's data. Each job uses a model — our pick for this
computer unless the person chose another — and the person can give it any model on this computer that runs here.

* **Help and the system** is locked to the guide: it holds the system and admin tools (D94), so it stays with the
  model we trained and measured.
* **Writing code** (AICUI), **writing** and **pictures and video** use the choice today. Pictures need a model with a
  picture reader (a projector).
* **Laying out code**, **reviewing** and **research papers** come with the hand-offs (§22.5): shown, not yet chosen.
* The news has no job: its report is built in code, never by a model (D92).

The choice is kept in the model store (ModelStore.use: the plan, with the matcher's settings for this machine).
"""

from __future__ import annotations

import os
import types

from cin_minai.inference import matcher

# job, the matcher's task (its context and catalog), locked to the guide, in use today
JOBS = [
    ("system", "help", True, True),
    ("coding", "coding", False, True),
    ("writing", "writing", False, True),
    ("vision", "coding", False, True),
    ("junior", "help", False, False),
    ("review", "coding", False, False),
    ("research", "writing", False, False),
]
BY_JOB = {j[0]: j for j in JOBS}


class JobError(Exception):
    pass


def context(job: str) -> int:
    return matcher.VISION_CONTEXT if job == "vision" else matcher.CONTEXT[BY_JOB[job][1]]


def job_plan(m, machine, job: str, why: str = "your choice") -> dict | None:
    """How this machine runs m for a job, as our own pick would: the job's context, or the larger one when the model
    still runs the same way with it (2026-10-08: the 27B ran at 32K as our pick and dropped to 16K once chosen here)."""
    import dataclasses
    plan = matcher.full_plan(m, machine, context(job), why=why)
    task = BY_JOB[job][1]
    if plan and job != "vision" and task in matcher.MORE_CONTEXT:
        tighter = dataclasses.replace(machine, cards=[{**c, "free_mib": c["free_mib"] - matcher.MORE_CONTEXT_EXTRA_MIB}
                                                      for c in machine.cards])
        big = matcher.full_plan(m, tighter, matcher.MORE_CONTEXT[task], why=why)
        if big and big["mode"] == plan["mode"]:
            plan = big
    return plan


def catalog_entry(file: str):
    return next((m for ms in matcher.CATALOG.values() for m in ms if m.file == os.path.basename(file)), None)


def entry(store, file: str, guide_path: str = ""):
    """The matcher's entry for a model on this computer: ours from the catalog, any other from its header."""
    m = catalog_entry(file)
    if m is not None:
        return m
    path = store.path(file) if store.has(file) else ""
    if not path and guide_path and os.path.basename(guide_path) == os.path.basename(file):
        path = guide_path
    if not path:
        raise JobError(f"{file} isn't on this computer")
    try:
        return matcher.model_from_gguf(path)
    except (OSError, ValueError) as e:
        raise JobError(f"{file} can't be read as a model: {e}") from e


def projector_files() -> set:
    return {p.file for p in matcher.PROJECTORS.values()}


def on_this_computer(store, guide_path: str) -> list[dict]:
    """Every model here: the guide that ships with the system, and the store's (with where each one is). Only the
    store's can be given a job; a parked one comes back first (the Models list's Bring back)."""
    out = []
    if guide_path and os.path.isfile(guide_path):
        out.append({"file": os.path.basename(guide_path), "model": matcher.CATALOG["help"][0].name,
                    "size": os.path.getsize(guide_path), "where": "system", "drive": "", "present": True})
    skip = projector_files() | ({os.path.basename(guide_path)} if guide_path else set())
    for file, rec in store.models().items():
        if file in skip or rec.get("where") == "deleted":
            continue  # a picture reader is part of a model, not a model
        m = catalog_entry(file)
        size = rec.get("size") or (os.path.getsize(rec["path"]) if rec.get("present") else 0)
        out.append({"file": file, "model": m.name if m else os.path.splitext(file)[0], "size": size,
                    "where": rec.get("where", "store"), "drive": rec.get("drive", ""), "present": rec["present"]})
    return out


def ours(store, job: str, machine) -> dict | None:
    """What the job uses when nobody chose: as each part of the system picks today."""
    if job == "system":
        return {"model": matcher.CATALOG["help"][0].name, "file": matcher.CATALOG["help"][0].file}
    task = BY_JOB[job][1]
    for m in matcher.CATALOG[task] if job in ("coding", "vision") else []:
        if job == "vision" and m.file not in matcher.PROJECTORS:
            continue
        ok = store.has(m.file) and (matcher.vision_plan(m, machine) if job == "vision"
                                    else matcher.plan(m, machine, context(job)))
        if ok:
            return {"model": m.name, "file": m.file}
    return {"model": matcher.CATALOG["help"][0].name, "file": matcher.CATALOG["help"][0].file}  # the guide


def view(store, guide_path: str, machine=None) -> dict:
    """The Models view: each job with its model (the person's choice or ours) and the models that can do it here."""
    machine = machine or matcher.read_machine(models_dir=store.root)
    here = on_this_computer(store, guide_path)
    jobs = []
    for job, _task, locked, active in JOBS:
        used = store.in_use(job) if not locked else None
        chosen = bool(used and used.get("why") == "your choice")
        current = None if not active else (
            {"model": used["model"], "file": used["file"]} if used else ours(store, job, machine))
        choices = []
        if active and not locked:
            for h in here:
                if h["where"] != "store" or not h["present"]:
                    continue  # the guide is every job's fallback already; a parked model comes back first
                if job == "vision" and h["file"] not in matcher.PROJECTORS:
                    continue
                try:
                    m = entry(store, h["file"], guide_path)
                    p = matcher.vision_plan(m, machine) if job == "vision" else matcher.plan(m, machine, context(job))
                except JobError:
                    p = None
                choices.append({"file": h["file"], "model": h["model"], "fits": p is not None,
                                "mode": (p or {}).get("mode", ""),
                                "tok_s": round((p or {}).get("tok_s", 0), 1)})
        jobs.append({"job": job, "locked": locked, "active": active, "chosen": chosen, "current": current,
                     "choices": choices})
    use = store.state()["use"]
    for h in here:  # which jobs use it: a model in use isn't removed
        h["used_by"] = sorted(j for j, p in use.items() if p and p.get("file") == h["file"])
    return {"jobs": jobs, "models": here, "free_bytes": store.free_bytes()}


def remove(store, file: str) -> dict:
    """Take a model out of the model folder (the record keeps where it came from). Not while a job uses it."""
    file = os.path.basename(file)
    if not store.has(file):
        raise JobError(f"{file} isn't in the model folder")
    using = [j for j, p in store.state()["use"].items() if p and p.get("file") == file]
    if using:
        raise JobError("a job uses that model: give the job another model first")
    store.delete(catalog_entry(file) or types.SimpleNamespace(file=file))
    return {"removed": file}


def assign(store, job: str, file: str, guide_path: str = "", machine=None) -> dict:
    """Give a job a model ("" = our pick again). Refused for the locked job, for jobs not in use yet, and for a
    model that doesn't run here."""
    if job not in BY_JOB:
        raise JobError(f"no job called {job!r}")
    _, _task, locked, active = BY_JOB[job]
    if locked:
        raise JobError("help and the system stay with the guide: it holds the system's tools")
    if not active:
        raise JobError("this job comes with the hand-offs; it can't be given a model yet")
    machine = machine or matcher.read_machine(models_dir=store.root)
    if not file:  # our pick again: the matcher's, when it's here (an offer once accepted), else as if never chosen
        pick = matcher.match(machine).get(BY_JOB[job][1]) if job != "vision" else None
        store.use(job, pick if pick and store.has(pick["file"]) else None)
        return {"job": job, "ours": True, **ours(store, job, machine)}
    if job == "vision" and os.path.basename(file) not in matcher.PROJECTORS:
        raise JobError("pictures and video need a model with a picture reader")
    if not store.has(file):
        raise JobError(f"{os.path.basename(file)} isn't in the model folder: bring it back first")
    m = entry(store, file, guide_path)
    if job == "vision":
        p = matcher.vision_plan(m, machine)
        plan = dict(p, model=m.name, file=m.file, why="your choice", context=matcher.VISION_CONTEXT) if p else None
    else:
        plan = job_plan(m, machine, job)
    if plan is None:
        raise JobError(f"{m.name} doesn't run on this computer")
    store.use(job, plan)
    return {"job": job, "model": m.name, "file": m.file, "mode": plan.get("mode", "")}
