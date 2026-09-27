#!/usr/bin/env python3
"""Merge raw office runs into the published office corpus (guide fine-tune, cycle 0).

The generator already checked every example (literal values in the message, computed calls, answers that
contain the fact, refusals, language, decontamination). Here, whatever run produced it:
  - the line parses and the call is valid against the document's tool schema (the eval's own);
  - no user message is too close to an eval task (public, held-out, vague set) — re-checked;
  - exact repeats (same document context and same message) are dropped. Short messages like
    "What's on slide 3?" repeat on purpose across documents and are kept.

    python3 merge.py --out . RAW_DIR [RAW_DIR ...]

Writes OUT/corpus.jsonl and OUT/merge-stats.json.
"""

import argparse
import collections
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("office_generate", os.path.join(HERE, "generate.py"))
O = importlib.util.module_from_spec(_spec)
_saved, sys.argv = sys.argv, [sys.argv[0]]
_spec.loader.exec_module(O)
sys.argv = _saved
T, R = O.T, O.R


def valid_call(call: dict, doc: str) -> bool:
    for s in R.schema(doc)["anyOf"]:
        if s["properties"]["tool"]["const"] != call.get("tool"):
            continue
        props = s["properties"]["args"]
        args = call.get("args", {})
        return set(props["required"]) <= set(args) and set(args) <= set(props["properties"])
    return False


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("raw", nargs="+")
    o = ap.parse_args()
    evalq = O.eval_questions()
    drop, kept, seen = collections.Counter(), [], set()
    for d in o.raw:
        for line in open(os.path.join(d, "examples.jsonl"), encoding="utf-8"):
            try:
                e = json.loads(line)
                call = json.loads(e["messages"][2]["content"])
            except (json.JSONDecodeError, KeyError, IndexError):
                drop["unparseable"] += 1
                continue
            if not valid_call(call, e["meta"]["doc"]):
                drop["call not valid for the document's tools"] += 1
                continue
            q = e["messages"][1]["content"]
            if max((T.similar(q, x) for x in evalq), default=0) >= 0.5:
                drop["too close to an eval task"] += 1
                continue
            key = (e["messages"][0]["content"], q)
            if key in seen:
                drop["exact repeat"] += 1
                continue
            seen.add(key)
            e["meta"]["source_run"] = os.path.basename(os.path.normpath(d))
            kept.append(e)
    os.makedirs(o.out, exist_ok=True)
    with open(os.path.join(o.out, "corpus.jsonl"), "w", encoding="utf-8") as f:
        for e in kept:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    stats = {"kind": "office", "sources": [os.path.basename(os.path.normpath(d)) for d in o.raw], "kept": len(kept),
             "dropped": dict(drop),
             "by_language": dict(collections.Counter(e["meta"]["lang"] for e in kept)),
             "by_document": dict(collections.Counter(e["meta"]["doc"] for e in kept)),
             "by_intent": dict(sorted(collections.Counter(f"{e['meta']['doc']}/{e['meta']['intent']}" for e in kept).items())),
             "by_tool": dict(collections.Counter(json.loads(e["messages"][2]["content"])["tool"] for e in kept).most_common()),
             "max_eval_similarity": max((e["meta"]["max_eval_similarity"] for e in kept), default=0)}
    json.dump(stats, open(os.path.join(o.out, "merge-stats.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print(json.dumps(stats, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
