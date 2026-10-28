# SPDX-License-Identifier: GPL-3.0-or-later
"""Habits (PLAN D96, SPEC §23.2): a script and its check that worked, run by name. "The model directs, code carries
the bulk": a habit fetches and structures (run.py), checks what it made (check.py, exit 0 = passed), and the model
works from the checked result. Ian, 2026-10-08: "jsons, automated scripts for quick habit retrieval like maybe
reading a pdf and summarizing or fetching a youtube video and summarizing, or in code doing the json then checking it".

A habit is a folder: habit.json (name, what it's for, what it takes, what it gives, whether it needs the network,
where it came from), run.py and check.py. Three places, the nearest first: a project's (.cinminai/habits), the
person's own (~/.local/share/cinminai/habits) and the shipped ones (/usr/share/cinminai/habits, ours, reviewed).

Calling convention, the same for every habit: `python3 run.py INPUTS.json OUT.json` in the project folder, then
`python3 check.py OUT.json INPUTS.json`; check.py prints its findings (JSON or plain lines) and exits 0 when the data
is right. A habit kept from a project's own script may ignore the arguments: it writes the file habit.json names as
its `output`, and its check reads that file.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import time
from typing import Callable

SHIPPED = "/usr/share/cinminai/habits"
RUNS = os.path.join(".cinminai", "habit-runs")
NAME = re.compile(r"^[a-z0-9][a-z0-9-]{1,40}$")
Runner = Callable[[str, int, bool], "tuple[int | None, str]"]  # command, timeout, network -> (exit, output)


def user_dir() -> str:
    return os.path.join(os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share"), "cinminai", "habits")


def places(root: str = "") -> list[tuple[str, str]]:
    """Where habits are, the nearest first: a project's own beats the person's, which beats ours."""
    out = [("project", os.path.join(root, ".cinminai", "habits"))] if root else []
    return out + [("yours", user_dir()), ("shipped", os.environ.get("CINMINAI_HABITS") or SHIPPED)]


def _meta(folder: str) -> dict | None:
    try:
        with open(os.path.join(folder, "habit.json"), encoding="utf-8") as f:
            meta = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(meta, dict) or not os.path.isfile(os.path.join(folder, "run.py")) \
            or not os.path.isfile(os.path.join(folder, "check.py")):
        return None
    return meta


def find(name: str, root: str = "") -> dict | None:
    """{"name", "place", "dir", "meta"} for the habit called name, the nearest place first; None if there's none."""
    if not NAME.match(name or ""):
        return None
    for place, base in places(root):
        folder = os.path.join(base, name)
        meta = _meta(folder)
        if meta is not None:
            return {"name": name, "place": place, "dir": folder, "meta": meta}
    return None


def every(root: str = "") -> list[dict]:
    """Every habit that can run here, each once (the nearest place wins), as {"name", "place", "for", "takes",
    "network"}."""
    seen, out = set(), []
    for place, base in places(root):
        try:
            names = sorted(os.listdir(base))
        except OSError:
            continue
        for name in names:
            if name in seen or not NAME.match(name):
                continue
            meta = _meta(os.path.join(base, name))
            if meta is None:
                continue
            seen.add(name)
            out.append({"name": name, "place": place, "for": str(meta.get("for", "")), "takes": meta.get("takes", {}),
                        "network": bool(meta.get("network"))})
    return out


def local_runner(root: str) -> Runner:
    """Runs a command in the project folder, as it is (the tests; AICUI and the daemon pass their sandbox)."""
    def run(command: str, timeout: int, network: bool) -> tuple[int | None, str]:
        try:
            p = subprocess.run(["bash", "-c", command], cwd=root, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return None, ""
        return p.returncode, (p.stdout + p.stderr).strip()
    return run


def findings_of(printed: str) -> list:
    """What a check printed: a JSON list or object if it printed one, else its non-empty lines."""
    text = (printed or "").strip()
    for start in (text.find("["), text.find("{")):
        if start >= 0:
            try:
                got = json.loads(text[start:])
                return got if isinstance(got, list) else [got]
            except ValueError:
                pass
    return [ln for ln in text.splitlines() if ln.strip()][-20:]


def run(name: str, inputs: dict, root: str, runner: Runner | None = None, network_ok: bool = False,
        timeout: int = 300) -> dict:
    """Run a habit, then its check. {"ok", "habit", "place", "output" (the file, relative to the project), "findings",
    "said" (one line for the model or the person), "run" (the folder with its inputs, output and log)}."""
    h = find(name, root)
    if h is None:
        known = ", ".join(x["name"] for x in every(root)) or "none"
        return {"ok": False, "said": f"error: no habit called {name} (habits here: {known})"}
    meta = h["meta"]
    offline = meta.get("offline_with") and (inputs or {}).get(meta["offline_with"])  # e.g. a page already kept
    if meta.get("network") and not offline and not network_ok:
        return {"ok": False, "said": f"error: habit {name} needs the network, and it isn't allowed here"}
    runner = runner or local_runner(root)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    folder = os.path.join(root, RUNS, f"{name}-{stamp}")
    os.makedirs(folder, exist_ok=True)
    ins, out = os.path.join(folder, "inputs.json"), os.path.join(folder, "out.json")
    with open(ins, "w", encoding="utf-8") as f:
        json.dump(inputs or {}, f, ensure_ascii=False, indent=1)
    q = shlex.quote
    code, printed = runner(f"python3 {q(os.path.join(h['dir'], 'run.py'))} {q(ins)} {q(out)}",
                           int(meta.get("timeout") or timeout), bool(meta.get("network")) and not offline)
    produced = out if os.path.isfile(out) else os.path.join(root, str(meta.get("output", ""))) \
        if meta.get("output") else ""
    with open(os.path.join(folder, "log.txt"), "w", encoding="utf-8") as f:
        f.write(f"run exit {code}\n{printed}\n")
    if code != 0 or not produced or not os.path.isfile(produced):
        result = {"ok": False, "findings": findings_of(printed),
                  "said": f"habit {name} failed while running (exit {code}): {(printed or '')[-400:]}"}
    else:
        ccode, cprinted = runner(f"python3 {q(os.path.join(h['dir'], 'check.py'))} {q(produced)} {q(ins)}",
                                 120, False)
        with open(os.path.join(folder, "log.txt"), "a", encoding="utf-8") as f:
            f.write(f"check exit {ccode}\n{cprinted}\n")
        findings = findings_of(cprinted)
        rel = os.path.relpath(produced, root).replace(os.sep, "/")
        verdict = "passed its check" if ccode == 0 else "FAILED its check"
        result = {"ok": ccode == 0, "output": rel, "findings": findings,
                  "said": f"habit {name} {verdict}; its output is {rel}"
                          + (f" — {'; '.join(str(x) for x in findings[:5])[:400]}" if findings else "")}
    result.update(habit=name, place=h["place"], run=os.path.relpath(folder, root).replace(os.sep, "/"))
    record(name, result["ok"])
    return result


def record(name: str, ok: bool) -> None:
    """Each habit's runs (how many, the last that passed, the last that failed), kept in the person's habits folder:
    the shipped ones are read-only."""
    path = os.path.join(user_dir(), "runs.json")
    try:
        with open(path, encoding="utf-8") as f:
            runs = json.load(f)
    except (OSError, ValueError):
        runs = {}
    r = runs.setdefault(name, {"runs": 0})
    r["runs"] += 1
    r["last_passed" if ok else "last_failed"] = time.strftime("%Y-%m-%d %H:%M:%S")
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(runs, f, indent=1)
    except OSError:
        pass


def keep(root: str, name: str, purpose: str, script: str, check: str, output: str = "", takes: dict | None = None,
         network: bool = False, where: str = "project", origin: str = "") -> dict:
    """Assimilate (SPEC §23.1 step 6): a project's script and its check, kept as a habit — only when the person says so
    (Rule 9, D30: AICUI's Keep button calls this, never the model). where: "project" or "yours" (every project)."""
    if not NAME.match(name or ""):
        return {"ok": False, "said": "error: a habit's name is lowercase letters, digits and dashes (2-41)"}
    src, chk = (os.path.join(root, p) for p in (script, check))
    if not os.path.isfile(src) or not os.path.isfile(chk):
        return {"ok": False, "said": f"error: {script} and {check} must both be files in the project"}
    base = os.path.join(root, ".cinminai", "habits") if where == "project" else user_dir()
    folder = os.path.join(base, name)
    if os.path.exists(folder):
        return {"ok": False, "said": f"error: a habit called {name} is already kept there"}
    os.makedirs(folder)
    shutil.copyfile(src, os.path.join(folder, "run.py"))
    shutil.copyfile(chk, os.path.join(folder, "check.py"))
    meta = {"name": name, "for": purpose.strip()[:300], "takes": takes or {}, "output": output,
            "network": bool(network), "origin": origin or f"kept from {os.path.basename(os.path.abspath(root))}: "
                                                              f"{script} with its check {check}",
            "kept": time.strftime("%Y-%m-%d %H:%M:%S")}
    with open(os.path.join(folder, "habit.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    return {"ok": True, "said": f"kept {script} as the habit {name} ({'this project' if where == 'project' else 'every project'})",
            "dir": folder}
