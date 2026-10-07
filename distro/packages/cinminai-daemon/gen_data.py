#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build hook helper: the guide's data files for cinminai-daemon, from the sources it was trained on.

    python3 gen_data.py OUT_DIR REPO

Writes OUT_DIR/guide.json (system prompt v2 exactly as rendered in training and the eval, the reply
instruction, the tool-call JSON schema, the inspect_system topics, the apps open_app knows) and
OUT_DIR/help.json (the help cards from training/kb/ with their search words, Mint's labels, and the
.desktop file for each label). Nothing is retyped: a change to the prompt or the knowledge base reaches
the daemon with the next package build, and the checks below stop the build if they drift apart.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import sys


def load(path: str, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    saved, sys.argv = sys.argv, [path]  # run_eval looks at sys.argv when imported
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.argv = saved
    return mod


def build(repo: str) -> dict:
    ev = os.path.join(repo, "training", "eval", "guide")
    kb = os.path.join(repo, "training", "kb")
    R = load(os.path.join(ev, "run_eval.py"), "run_eval")
    X = load(os.path.join(ev, "extract_labels.py"), "extract_labels")
    T = load(os.path.join(kb, "transition.py"), "kb_transition")
    L = load(os.path.join(kb, "lessons.py"), "kb_lessons")
    K = load(os.path.join(kb, "terminal.py"), "kb_terminal")  # terminal-error cards (M3)
    S = load(os.path.join(kb, "search.py"), "kb_search")

    # v2 is the prompt the shipped guide was trained and measured with (MODEL_CARD.md); v2.1 = v2 plus one
    # tool, make_spreadsheet (D53), adopted 2026-09-30 after the A/B: 140/157 vs 141/157, the same tool
    # choices, the new tool never called by mistake. With a document shared the prompt is v2's, unchanged.
    # v2.2 = v2.1 with rule 2 rewritten (world questions -> web_search, writing -> help, advice -> decline) and the
    # web_search tool (D54, D55), adopted 2026-10-01 after the A/B: 138/157 vs 140/157, the unchanged items better
    # (123 vs 120 of 137). v2.3 = v2.2 with "what is…" about this computer sent to the help and the reply keeping the
    # help's comparison and cautions (D84), adopted 2026-10-06 after the A/B on the 4070: public 144/157 vs 141/157,
    # D84 30/33 vs 23/33, diagnostics 17 vs 16, terminal/create/web equal (docs/d84-coverage.md).
    # CINMINAI_GUIDE_PROMPT: a test daemon tries another prompt without changing what ships.
    R.PROMPT = os.environ.get("CINMINAI_GUIDE_PROMPT", "v2.3")
    guide = {
        "prompt": R.PROMPT,
        "system": R.system_prompt({}),
        "style": R.style(),
        "result_format": "Result of {tool}:\n{result}\n\n{style}",
        "schema": R.schema(None),
        "tools": {name: desc for name, (_, desc) in R.GUIDE_TOOLS.items()},
        "topics": R.TOPICS,
        "apps": sorted(R.LABELS),
    }
    # the same text the corpus generator used: training/datasets/sessions/generate.py
    assert "No document is shared." in guide["system"] and "- lookup_help:" in guide["system"]

    # with a LibreOffice document shared (D20): the prompt and tools the office corpus trained, per kind.
    # The context goes where SENTINEL is; the daemon puts the document's context there (office.py).
    sentinel = json.dumps({"__CTX__": 1})
    guide["documents"] = {}
    for kind, tools in R.OFFICE_TOOLS.items():
        system = R.system_prompt({"doc": kind, "ctx": {"__CTX__": 1}})
        assert system.count(sentinel) == 1 and "The user shared a LibreOffice" in system, kind
        guide["documents"][kind] = {
            "system": system, "context_slot": sentinel, "schema": R.schema(kind),
            "read": [n for n, (_, d) in tools.items() if not d.startswith("EDIT")],
            "edit": [n for n, (_, d) in tools.items() if d.startswith("EDIT")],
        }

    cards = []
    for source, mod in (("transition", T), ("lessons", L), ("terminal", K)):
        for c in mod.TOPICS:
            if c["id"] not in S.KEYWORDS:
                raise SystemExit(f"help card {c['id']} has no search words in training/kb/search.py")
            cards.append({**c, "source": source, "keywords": S.KEYWORDS[c["id"]]})
    ids = [c["id"] for c in cards]
    if len(ids) != len(set(ids)):
        raise SystemExit("duplicate help card ids")
    unknown = set(S.KEYWORDS) - set(ids)
    if unknown:
        raise SystemExit(f"search words for unknown cards: {sorted(unknown)}")
    desktop = {**{k: v + ".desktop" for k, v in X.LABELS.items()}, **{k: None for k in X.ACTIONS}}
    help_ = {"labels": R.LABELS, "ui": R.UI, "desktop": desktop, "cards": cards}
    for c in cards:
        for key in re.findall(r"\{(\w+)\}", c["card"]):
            if key not in R.LABELS and key not in R.UI:
                raise SystemExit(f"card {c['id']}: unknown label {{{key}}}")
    return {"guide.json": guide, "help.json": help_}


def main() -> None:
    out, repo = sys.argv[1], sys.argv[2]
    os.makedirs(out, exist_ok=True)
    for name, data in build(repo).items():
        with open(os.path.join(out, name), "w", encoding="utf-8", newline="\n") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)  # never sort_keys: the schema's key order is the order the model writes
            f.write("\n")


if __name__ == "__main__":
    main()
