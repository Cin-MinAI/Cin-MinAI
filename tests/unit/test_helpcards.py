# SPDX-License-Identifier: GPL-3.0-or-later
"""lookup_help retrieval, measured on labelled queries (tests/data/lookup_queries.jsonl):

- "sessions": the queries the teacher wrote in the session corpus, with the card it was given (511);
- "eval-HO": the queries the shipped guide itself wrote on the public eval, with the card that task
  needs (80);
- "heldout-HO": the shipped guide's queries on the held-out eval (47), labelled by hand from the query
  alone (a list = either card is right; null = no card fits: rename a file, undo, select several files,
  write a letter). **The clean test:** the first two sets were used to write the search words; this
  one was labelled and measured once, after that (2026-09-28: 78.7 %, 37/47), and must not be tuned on.

    python3 -m unittest tests.unit.test_helpcards -v        (from the repo root)
    python3 tests/unit/test_helpcards.py --report            (accuracy per set and language, the misses)
"""

import collections
import json
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "distro", "packages", "cinminai-daemon"))

from cin_minai.daemon.helpcards import HelpIndex, resolve, tokens  # noqa: E402
import gen_data  # noqa: E402

QUERIES = [json.loads(l) for l in open(os.path.join(ROOT, "tests", "data", "lookup_queries.jsonl"), encoding="utf-8")]
# Floors, set just under what was measured (2026-09-28); a change to the index or the search words that
# drops below them fails. Raise them as retrieval improves.
FLOOR = {"sessions": 0.90, "eval-HO": 0.95, "heldout-HO": 0.75}

_DATA = None


def data() -> dict:
    global _DATA
    if _DATA is None:
        _DATA = gen_data.build(ROOT)
    return _DATA


def accuracy(index: HelpIndex, rows: list) -> tuple[float, list]:
    misses = []
    for r in rows:
        got, _ = index.lookup(r["q"], r["lang"])
        want = r["id"] if isinstance(r["id"], list) else [r["id"]]
        if got not in want:
            misses.append((r, got))
    return 1 - len(misses) / len(rows), misses


class HelpCards(unittest.TestCase):
    def setUp(self):
        self.index = HelpIndex(data()["help.json"])

    def test_accuracy(self):
        for src, floor in FLOOR.items():
            acc, _ = accuracy(self.index, [r for r in QUERIES if r["src"] == src])
            self.assertGreaterEqual(acc, floor, f"{src}: {acc:.1%}")

    def test_every_card_findable_by_its_windows_name(self):
        for c in data()["help.json"]["cards"]:
            self.assertEqual(self.index.lookup(c["windows"], "en")[0], c["id"], c["windows"])

    def test_no_match(self):
        self.assertEqual(self.index.lookup("the the and of", "en"), (None, "Nothing in the built-in help matches this."))

    def test_names_in_the_users_language(self):
        cid, text = self.index.lookup("Logithèque installer programme", "fr")
        self.assertEqual(cid, "install")
        self.assertIn("Logithèque", text)
        self.assertNotIn("{", text)

    def test_tokens(self):
        self.assertEqual(tokens("Installer un programme"), ["insta", "progr"])
        self.assertEqual(tokens("日本語"), ["日本", "本語"])
        self.assertEqual(resolve("{files}", {"files": {"en": "Files"}}, "ja"), "Files")


def report() -> None:
    index = HelpIndex(data()["help.json"])
    for src in FLOOR:
        rows = [r for r in QUERIES if r["src"] == src]
        acc, misses = accuracy(index, rows)
        by = collections.defaultdict(list)
        for r in rows:
            by[r["lang"]].append(r)
        langs = "  ".join(f"{l} {accuracy(index, rs)[0]:.0%}" for l, rs in sorted(by.items()))
        print(f"{src}: {acc:.1%} of {len(rows)}   {langs}")
        for r, got in misses:
            print(f"   {r['lang']} want {str(r['id']):<17} got {str(got):<17} | {r['q']}")


if __name__ == "__main__":
    if "--report" in sys.argv:
        report()
    else:
        unittest.main()
