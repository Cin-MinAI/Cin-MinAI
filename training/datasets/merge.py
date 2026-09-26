#!/usr/bin/env python3
"""Merge the raw generator outputs into the published corpora (guide fine-tune, phase 2).

Every example goes through the same final checks, whatever run produced it:
  - the line parses (a half-written last line after a power cut is dropped);
  - the question is cleaned (persona labels, prefixes) and must be valid (no junk, right language,
    no persona/commentary traces) — the cleaned text replaces the original in the example;
  - the reply passes its checks again with the current scorer (transition: the eval's stage-B checks;
    interpretation: its own checks);
  - no question is too close to any eval task, public or held-out (decontamination, 3-gram Jaccard);
  - near-duplicate questions (same language) are dropped.

    python3 merge.py --kind transition --out ../datasets/transition RAW_DIR [RAW_DIR ...]
    python3 merge.py --kind interpretation --out ../datasets/interpretation RAW_DIR [RAW_DIR ...]

Writes OUT/corpus.jsonl and OUT/merge-stats.json.
"""

import argparse
import collections
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def load(name: str, path: str):
    """Both generators are called generate.py: load each by path, under its own module name."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    saved, sys.argv = sys.argv, [sys.argv[0]]
    spec.loader.exec_module(mod)
    sys.argv = saved
    return mod


# the interpretation generator does `import generate as T` from ../transition: make that resolve
sys.path.insert(0, os.path.join(HERE, "transition"))
T = load("generate", os.path.join(HERE, "transition", "generate.py"))


def interp_module():
    return load("interp_generate", os.path.join(HERE, "interpretation", "generate.py"))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kind", choices=["transition", "interpretation"], required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("raw", nargs="+")
    o = ap.parse_args()
    I = interp_module() if o.kind == "interpretation" else None
    topics = {t["id"]: t for t in T.KB.TOPICS}
    evalq = T.eval_questions()
    drop = collections.Counter()
    kept, seen = [], collections.defaultdict(list)
    for d in o.raw:
        path = os.path.join(d, "examples.jsonl")
        for line in open(path, encoding="utf-8"):
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                drop["unparseable line"] += 1
                continue
            lang = e["meta"]["lang"]
            q = T.clean_question(e["messages"][1]["content"])
            if not T.valid_question(q, lang):
                drop["invalid question"] += 1
                continue
            if o.kind == "transition":
                topic = topics[e["meta"]["topic"]]
                must = [[T.label(k, lang) for k in (m if isinstance(m, list) else [m])] for m in topic["must"]]
                fails = T.R.stage_b({"lang": lang, "must": must, "must_not": T.NO_CMD,
                                     "steps": 2 if topic["steps"] else 0}, e["messages"][4]["content"])
            else:
                fails = I.checks(lang, json.loads(e["messages"][2]["content"])["args"]["text"])
            if fails:
                drop["reply fails current checks"] += 1
                continue
            reply = e["messages"][4]["content"] if o.kind == "transition" else \
                json.loads(e["messages"][2]["content"])["args"]["text"]
            if T.mixed_language(reply, lang):
                drop["reply has a line in another language"] += 1
                continue
            if reply.splitlines()[0].strip() == q.strip():
                drop["reply echoes the question"] += 1
                continue
            worst = max((T.similar(q, x) for x in evalq), default=0)
            if worst >= 0.5:
                drop["too close to an eval task"] += 1
                continue
            if any(T.similar(q, s) >= 0.8 for s in seen[lang]):
                drop["near-duplicate"] += 1
                continue
            seen[lang].append(q)
            e["messages"][1]["content"] = q
            e["meta"]["source_run"] = os.path.basename(os.path.normpath(d))
            e["meta"]["max_eval_similarity"] = round(worst, 2)
            kept.append(e)
    os.makedirs(o.out, exist_ok=True)
    with open(os.path.join(o.out, "corpus.jsonl"), "w", encoding="utf-8") as f:
        for e in kept:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    key = "topic" if o.kind == "transition" else "theme"
    stats = {"kind": o.kind, "sources": [os.path.basename(os.path.normpath(d)) for d in o.raw],
             "kept": len(kept), "dropped": dict(drop),
             "by_language": dict(collections.Counter(e["meta"]["lang"] for e in kept)),
             f"by_{key}": dict(collections.Counter(e["meta"][key] for e in kept)),
             "max_eval_similarity": max((e["meta"]["max_eval_similarity"] for e in kept), default=0)}
    json.dump(stats, open(os.path.join(o.out, "merge-stats.json"), "w", encoding="utf-8"), indent=1,
              ensure_ascii=False)
    print(json.dumps({k: v for k, v in stats.items() if not k.startswith("by_t")}, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
