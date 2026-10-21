# SPDX-License-Identifier: GPL-3.0-or-later
"""Walking a fault's tree (src/cin_minai/diag/walk.py, PLAN D51, D7) on the recorded cases: code walks it, the rule
decides after each fix — gone, the next fix, or the end of the tree — never a model.

    python3 -m unittest tests.unit.test_diag_walk -v        (from the repo root)
"""

import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from unittest import mock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))

from cin_minai.daemon.tools import Tools  # noqa: E402
from cin_minai.diag import probes, report, rules, walk  # noqa: E402
from cin_minai.diag.source import FixtureSource  # noqa: E402

FIX = os.path.join(ROOT, "tests", "fixtures", "diag")
DURING = os.path.join(FIX, "2026-09-30-v300-during-7.0.json")
AFTER = os.path.join(FIX, "2026-09-30-v300-after-6.8.json")


def rep(path: str) -> dict:
    ev = probes.collect(FixtureSource(path))
    return report.build(ev, rules.evaluate(ev))


class Walk(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.during, cls.after = rep(DURING), rep(AFTER)

    def setUp(self):
        home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, home, True)
        env = mock.patch.dict(os.environ, {"XDG_STATE_HOME": home})
        env.start()
        self.addCleanup(env.stop)

    def finding(self, code):
        return [f for f in self.during["findings"] if f["code"] == code][0]

    def test_the_fixes_in_order(self):
        s401 = self.finding("S401")  # the kernel: two fixes
        first = walk.step(s401, 0)
        self.assertEqual((first["fix_n"], first["fixes"]), (0, 2))
        self.assertEqual(first["fix"], s401["fixes"][0]["words"])
        self.assertEqual(walk.step(s401, 1)["fix"], s401["fixes"][1]["words"])
        self.assertIsNone(walk.step(s401, 2))

    def test_the_rule_decides_after_each_fix(self):
        still = walk.check(self.during, "S401", 0)
        self.assertEqual(still["outcome"], "still")
        self.assertEqual(still["next"]["fix_n"], 1)  # the next fix, not the same one again
        self.assertEqual(walk.check(self.during, "S401", 1)["outcome"], "end")  # the tree's fixes used up
        gone = walk.check(self.after, "S401", 0, "Faults follow one kernel")  # back on 6.8: cleared
        self.assertEqual(gone["outcome"], "gone")
        self.assertIn("Fixed", walk.words("gone", "en", title=gone["title"]))

    def test_a_fix_that_needs_a_restart_is_checked_after_it(self):
        g101 = self.finding("G101")
        self.assertTrue(walk.step(g101, 0)["restart"])  # "after a restart, nvidia-smi shows the card"
        self.assertIsNone(walk.kept())
        walk.keep("G101", 0, g101["title"])
        self.assertEqual(walk.kept()["code"], "G101")
        self.assertIsNone(walk.kept(time.time() + (walk.KEEP_DAYS + 1) * 86400))  # moved on: dropped
        self.assertIsNone(walk.kept())

    def test_the_card_comes_from_the_reading_the_guide_got(self):
        tools = Tools({}, {}, "en")
        with mock.patch.dict(os.environ, {"CINMINAI_DIAG_FIXTURE": DURING}):
            lead = tools.diagnose()["faults"][0]
            step = tools.walk_start(json.dumps({"problems_found": [lead]}))
        self.assertEqual(step["code"], lead["code"])
        self.assertEqual(step["fix"], lead["fix"])
        self.assertIsNone(tools.walk_start(json.dumps({"topic": "sound"})))  # nothing found: no card
        if step["restart"]:
            self.assertEqual(walk.kept()["code"], step["code"])
        # still there after a fix that needed a restart: it goes on from the next fix
        s401 = self.finding("S401")
        walk.keep("S401", 0, s401["title"])
        nxt = tools.walk_start(json.dumps({"problems_found": [{"code": "S401"}]}))
        self.assertEqual(nxt["fix_n"], 1)

    def test_six_languages(self):
        for code in ("en", "es", "pt", "fr", "de", "ja"):
            self.assertEqual(set(walk.WORDS[code]), set(walk.WORDS["en"]), code)


if __name__ == "__main__":
    unittest.main()
