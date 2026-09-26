#!/usr/bin/env python3
"""Sample a training mix from the two corpora (guide micro runs, cycle 0).

    python3 make_mix.py --transition N --interpretation M --seed S --out mix.jsonl

Transition examples give two training sequences each (the lookup call and the reply), interpretation
examples one — so M/(2N+M) is the interpretation share of the training sequences. Sampling is
uniform within each corpus (seeded), so languages keep their corpus proportions.
"""

import argparse
import json
import os
import random

HERE = os.path.dirname(os.path.abspath(__file__))
CORPORA = os.path.join(HERE, "..", "datasets")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--transition", type=int, required=True), ap.add_argument("--interpretation", type=int, required=True)
    ap.add_argument("--seed", type=int, default=1), ap.add_argument("--out", required=True)
    o = ap.parse_args()
    rnd = random.Random(o.seed)
    rows = []
    for name, n in (("transition", o.transition), ("interpretation", o.interpretation)):
        pool = [json.loads(l) for l in open(os.path.join(CORPORA, name, "corpus.jsonl"), encoding="utf-8")]
        rows += rnd.sample(pool, min(n, len(pool)))
    rnd.shuffle(rows)
    with open(o.out, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    seqs = 2 * o.transition + o.interpretation
    print(f"{len(rows)} examples, ~{seqs} sequences, interpretation share {o.interpretation / max(seqs, 1):.0%}")


if __name__ == "__main__":
    main()
