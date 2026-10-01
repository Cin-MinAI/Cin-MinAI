# SPDX-License-Identifier: GPL-3.0-or-later
"""The report (SPEC §20.4): JSON for programs, Markdown for people and AI readers, both from the same data,
and a short view for the guide's `diagnose` tool (§20.6). Every reader gets the same facts."""

from __future__ import annotations

import datetime as dt
import json
import os
import socket

from . import SCHEMA

TREES = os.path.join(os.path.dirname(__file__), "trees.json")

READING_GUIDE = """\
How to read this (for people and for AI assistants): every finding is a **code** set by a fixed rule over
the evidence shown with it — never by a guess. **active** = true now; **seen** = in recent starts, not in
this one; **cleared** = its cause is gone. Each code has the likeliest **cause** the evidence points to and
**fixes**: the way without a terminal first, then a command the person can copy, with what it does and how
to undo it. Readers explain and suggest; they never run anything themselves. Anything that changes the
system is the person's decision and asks for their password (Cin-MinAI SPEC §20, PLAN D3, D51, D53)."""


class _Fill(dict):
    def __missing__(self, key):
        return "{" + key + "}"


def fill(text: str, facts: dict) -> str:
    return text.format_map(_Fill({k: v for k, v in facts.items()}))


def load_trees(path: str = TREES) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)["codes"]


def explain(fault: dict, trees: dict) -> dict:
    t = trees.get(fault["code"], {})
    facts = fault["facts"]
    fixes = []
    for fx in t.get("fixes", {}).get(fault["cause"], []):
        fixes.append({k: (fill(v, facts) if isinstance(v, str) else [fill(s, facts) for s in v] if isinstance(v, list) else v)
                      for k, v in fx.items()})
    return {"code": fault["code"], "status": fault["status"], "node": fault["node"],
            "title": t.get("title", fault["code"]), "meaning": fill(t.get("meaning", ""), facts),
            "cause": fault["cause"], "cause_words": fill(t.get("causes", {}).get(fault["cause"], ""), facts),
            "fixes": fixes, "facts": facts, "evidence": fault["evidence"], "boots": fault["boots"]}


def build(ev: dict, faults: list[dict], trees: dict | None = None, now: str | None = None) -> dict:
    trees = trees if trees is not None else load_trees()
    return {
        "schema": SCHEMA,
        "made": now or dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "machine": {"kernel": ev["kernel"], "kernels_installed": ev["kernels_installed"],
                    "kernel_packages": ev["packages"]["kernel_meta"], "nvidia_driver": ev["packages"]["nvidia_driver"],
                    "nvidia_loaded": ev["nvidia_version_loaded"] or (ev["nvidia_module_loaded"] or None),
                    "root": ev["root"], "disks": ev["disks"]},
        "readiness": {"boots_read": len(ev["boots"]), "not_read": ev["not_read"]},
        "findings": [explain(f, trees) for f in faults],
        "boots": [{"offset": b["offset"], "started": b["first"], "kernel": b["kernel"],
                   "clean_end": b.get("clean_end"), "link_errors": sum(l["exceptions"] for l in b["links"].values()),
                   "driver_file_unreadable": b["zstd_fail"], "nvidia_loaded": b["nvidia_loaded"]} for b in ev["boots"]],
    }


def markdown(rep: dict) -> str:
    m = rep["machine"]
    out = [f"# Diagnostic report ({rep['schema']})", "", f"Made {rep['made']} on {socket.gethostname()}.", "",
           READING_GUIDE, "", "## This computer", "",
           f"- Kernel running: {m['kernel']} (installed: {', '.join(m['kernels_installed']) or 'unknown'})",
           f"- Kernel line: {', '.join(m['kernel_packages']) or 'unknown'}",
           f"- Graphics driver: {m['nvidia_driver'] or 'no NVIDIA driver installed'}"
           + (f", loaded ({m['nvidia_loaded']})" if m["nvidia_loaded"] else ", not loaded" if m["nvidia_driver"] else ""),
           f"- System disk: {m['root'].get('device', '?')} ({m['root'].get('fstype', '?')}), "
           + ("**read-only**" if m["root"].get("read_only") else "read-write")]
    for name, d in m["disks"].items():
        out.append(f"- Disk {name}: {d['model'] or 'unknown'} (largest write {d['max_sectors_kb'] or '?'} KiB)")
    out += ["", "## Findings", ""]
    if not rep["findings"]:
        out.append("No faults found in what was read.")
    for f in rep["findings"]:
        out += [f"### {f['code']} — {f['title']} ({f['status']})", "", f["meaning"], ""]
        if f["cause_words"]:
            out += [f"**Likeliest cause:** {f['cause_words']}", ""]
        for i, fx in enumerate(f["fixes"], 1):
            out.append(f"**Fix {i}:** {fx['words']}")
            for s in fx.get("steps", []):
                out.append(f"- {s}")
            if fx.get("command"):
                out += ["", "```", fx["command"], "```", f"What it does: {fx['explain']}", f"Undo: {fx.get('undo', '')}"]
            out.append("")
        if f["evidence"]:
            out += ["Evidence:", "", "```"] + f["evidence"] + ["```", ""]
    out += ["## Recent starts", "", "| start | kernel | clean end | link errors | driver file unreadable | NVIDIA loaded |",
            "|---|---|---|---|---|---|"]
    for b in rep["boots"]:
        clean = "" if b["clean_end"] is None else ("yes" if b["clean_end"] else "**no**")
        out.append(f"| {b['started']} | {b['kernel']} | {clean} | {b['link_errors'] or ''} | "
                   f"{b['driver_file_unreadable'] or ''} | {'yes' if b['nvidia_loaded'] else ''} |")
    out += ["", f"Not read: {', '.join(rep['readiness']['not_read']) or 'nothing'}.", ""]
    return "\n".join(out)


def guide_view(rep: dict, code: str | None = None, limit: int | None = 3) -> dict:
    """What the guide's `diagnose` tool returns: short, plain, the first fix spelled out (a 4B model reads it)."""
    found = [f for f in rep["findings"] if f["status"] != "cleared" and (code is None or f["code"] == code)]
    if not found:
        return {"faults": [], "note": "No faults found in the checks that ran.",
                "not_checked": rep["readiness"]["not_read"]}
    out = []
    for f in found[:limit]:
        fx = f["fixes"][0] if f["fixes"] else {}
        item = {"code": f["code"], "now": f["status"] == "active", "problem": f["meaning"], "cause": f["cause_words"],
                "fix": fx.get("words", "")}
        if fx.get("steps"):
            item["steps"] = fx["steps"]
        if fx.get("command"):
            item["command"] = fx["command"]
            item["command_explained"] = fx["explain"]
            item["undo"] = fx.get("undo", "")
        out.append(item)
    return {"faults": out, "more": max(0, len(found) - len(out))}
