#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Sample a balanced training mix from the session corpus (guide micro run G, cycle 0).

    python3 make_session_mix.py --turns 160 --seed 7 [--preset g|h] [--office N] --out mix.jsonl

The session corpus is skewed (reports 29 %, declines 22 %, vague 4 %: the generator's fallback turn
type). We pick TURNS turns to the planned shares (the journal mix) and train only those: every other
assistant message is marked "train": false and stays in the conversation as context; a session ends
after its last picked turn and sessions with no picked turn are left out. Reports that name the
program to open ("open_with" in the result) are picked first — the others only describe the problem
without offering the way to fix it (2026-09-26 reading).
"""

import argparse
import collections
import importlib.util
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SESSIONS = os.path.join(HERE, "..", "datasets", "sessions")
OFFICE = os.path.join(HERE, "..", "datasets", "office")
PRESETS = {
    "g": {"clear": 0.15, "system": 0.05, "report": 0.18, "walk": 0.20, "vague": 0.15, "decline": 0.12,
          "safety": 0.08, "chat": 0.07},
    # run G (72 %) lost the numbered steps: after a lookup it saw mostly one-step walkthrough replies and
    # list-free reports, so it wrote prose. H: twice the full numbered answers, and walkthroughs train only
    # their follow-up steps (the first reply after the lookup is context), so lookup -> numbered list stays
    # the default and step-by-step happens once the conversation is already a walkthrough.
    "h": {"clear": 0.30, "system": 0.08, "report": 0.12, "walk": 0.12, "vague": 0.12, "decline": 0.10,
          "safety": 0.08, "chat": 0.08},
}
FOLLOW_ONLY = {"g": False, "h": True}


def load_merge():
    spec = importlib.util.spec_from_file_location("sessions_merge", os.path.join(SESSIONS, "merge.py"))
    mod = importlib.util.module_from_spec(spec)
    saved, sys.argv = sys.argv, [sys.argv[0]]
    spec.loader.exec_module(mod)
    sys.argv = saved
    return mod


def names_program(segs: list) -> bool:
    res = json.loads(segs[0][2]["content"].split("\n", 1)[1].split("\n\n")[0])
    return bool(res.get("open_with")) and res["open_with"] in segs[0][-1]["content"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--turns", type=int, required=True), ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--out", required=True), ap.add_argument("--preset", choices=list(PRESETS), default="g")
    ap.add_argument("--office", type=int, default=0,
                    help="add N office examples (datasets/office/corpus.jsonl, a document shared; one call each)")
    o = ap.parse_args()
    shares, follow_only = PRESETS[o.preset], FOLLOW_ONLY[o.preset]
    M = load_merge()
    rnd = random.Random(o.seed)
    sessions = [json.loads(l) for l in open(os.path.join(SESSIONS, "corpus.jsonl"), encoding="utf-8")]
    pool = collections.defaultdict(list)  # kind -> [(session index, turn index, preferred)]
    split = []
    for si, s in enumerate(sessions):
        ts = M.turns(s)
        split.append(ts)
        for ti, (kind, segs) in enumerate(ts):
            if kind == "walk" and follow_only and len(segs) < 2:
                continue  # nothing to train: a walkthrough without a follow-up
            pool[kind].append((si, ti, kind == "report" and names_program(segs)))
    picked, short = set(), {}
    for kind, share in shares.items():
        want = round(o.turns * share)
        cands = pool[kind][:]
        rnd.shuffle(cands)
        cands.sort(key=lambda c: not c[2])  # stable: preferred first, random within each group
        picked |= {(si, ti) for si, ti, _ in cands[:want]}
        if len(cands) < want:
            short[kind] = f"{len(cands)} of {want}"
    rows, seqs, kinds = [], 0, collections.Counter()
    for si, (s, ts) in enumerate(zip(sessions, split)):
        mine = [ti for ti in range(len(ts)) if (si, ti) in picked]
        if not mine:
            continue
        msgs = [s["messages"][0]]
        for ti, (kind, segs) in enumerate(ts[:max(mine) + 1]):
            for j, seg in enumerate(segs):
                for k, m in enumerate(seg):
                    if m["role"] == "assistant":
                        # follow-only: the walkthrough's lookup call is trained, its first reply is context
                        train = ti in mine and not (kind == "walk" and follow_only and j == 0 and k == len(seg) - 1)
                        m = dict(m) if train else dict(m, train=False)
                        seqs += train
                    msgs.append(m)
            if ti in mine:
                kinds[kind] += 1
        rows.append({"messages": msgs, "meta": dict(s["meta"], trained_turns=[ts[t][0] for t in mine])})
    office = []
    if o.office:
        pool_o = [json.loads(l) for l in open(os.path.join(OFFICE, "corpus.jsonl"), encoding="utf-8")]
        office = rnd.sample(pool_o, min(o.office, len(pool_o)))
        rows += office
        seqs += len(office)
    rnd.shuffle(rows)
    with open(o.out, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    total = sum(kinds.values())
    print(json.dumps({"preset": o.preset, "sessions": len(rows) - len(office), "trained_turns": total, "training_sequences": seqs,
                      "shares": {k: f"{n} ({n / total:.0%})" for k, n in kinds.most_common()},
                      "reports_naming_the_program": sum(1 for si, ti, p in pool["report"] if p and (si, ti) in picked),
                      "office_examples": len(office), "short": short}, ensure_ascii=False))


if __name__ == "__main__":
    main()
