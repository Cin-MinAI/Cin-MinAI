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


class ThinkItThrough(unittest.TestCase):
    """D7: past the end of the trees the model may be asked to reason it through — offered, plain text, bounded."""

    def test_offered_only_past_the_trees(self):
        tools = Tools({}, {}, "en")
        self.assertTrue(tools.past_the_trees("sound", json.dumps({"topic": "sound"})))  # asked, nothing found
        self.assertFalse(tools.past_the_trees("overview", json.dumps({"topic": "overview"})))  # good news only
        self.assertTrue(tools.past_the_trees("overview", json.dumps({"problems_found": [{"code": "X999"}]})))
        self.assertFalse(tools.past_the_trees("sound", json.dumps({"error": "a probe failed"})))
        self.assertFalse(tools.past_the_trees("sound", "not json"))

    def test_a_fault_without_fixes_gets_no_card(self):
        tools = Tools({}, {}, "en")
        with mock.patch.dict(os.environ, {"CINMINAI_DIAG_FIXTURE": DURING}):
            tools.diagnose()
            code = tools.report()["findings"][0]["code"]
            for f in tools.report()["findings"]:
                f["fixes"] = []
            self.assertIsNone(tools.walk_start(json.dumps({"problems_found": [{"code": code}]})))

    def test_the_request_and_its_evidence(self):
        from cin_minai.diag import think
        md = report.markdown(rep(DURING))
        ev = think.evidence(md, '{"topic": "display"}')
        self.assertTrue(ev.startswith("## What the assistant's check read"))
        self.assertIn(md[:200], ev)
        self.assertLessEqual(len(think.evidence("x" * 50000)), think.EVIDENCE_CHARS + 100)
        msgs = think.messages("my screen flickers", ev)
        self.assertIn("Never suggest reinstalling", msgs[0]["content"])
        self.assertIn("my screen flickers", msgs[1]["content"])

    def test_the_budget_fits_the_context(self):
        from cin_minai.diag import think
        msgs = think.messages("my computer freezes", think.evidence(report.markdown(rep(DURING))))
        self.assertEqual(think.budget(16384, msgs), think.BUDGET)  # the coding role's 16K: the whole budget
        self.assertTrue(think.MIN_BUDGET <= think.budget(8192, msgs) < think.BUDGET)  # 8K: a smaller one
        self.assertEqual(think.budget(4096, msgs), 0)  # stepped down far: a plain answer

    def test_the_thinking_server_has_a_budget(self):
        from cin_minai.inference.llamacpp import LlamaCppBackend
        b = LlamaCppBackend({"model": "/x/m.gguf", "reasoning": "on", "reasoning_budget": 4096,
                             "reasoning_budget_message": " answer now."}, lambda m: None)
        p = mock.Mock(context=8192, gpu_layers="99", device="none")
        a = b.argv(p)
        self.assertEqual(a[a.index("--reasoning") + 1], "on")
        self.assertEqual(a[a.index("--reasoning-budget") + 1], "4096")
        plain = LlamaCppBackend({"model": "/x/m.gguf"}, lambda m: None).argv(p)
        self.assertEqual(plain[plain.index("--reasoning") + 1], "off")  # the guide: off, as always (D7)
        self.assertNotIn("--reasoning-budget", plain)

    def test_six_languages(self):
        sys.path.insert(0, os.path.join(ROOT, "src"))
        from cin_minai.sidebar import words
        for code in ("en", "es", "pt", "fr", "de", "ja"):
            self.assertEqual(set(words.THINK[code]), set(words.THINK["en"]), code)
            self.assertIn("{model}", words.THINK[code]["note_model"])


if __name__ == "__main__":
    unittest.main()
