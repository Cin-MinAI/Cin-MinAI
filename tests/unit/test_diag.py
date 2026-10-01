# SPDX-License-Identifier: GPL-3.0-or-later
"""cinminai-diag rules on recorded cases (SPEC §20.7): every real case is a fixture, every rule is tested on it.

    python3 -m unittest tests.unit.test_diag -v        (from the repo root)
"""

import copy
import json
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))

from cin_minai.diag import probes, report, rules  # noqa: E402
from cin_minai.diag.source import FixtureSource  # noqa: E402

FIX = os.path.join(ROOT, "tests", "fixtures", "diag")


def case(name: str) -> dict:
    return probes.collect(FixtureSource(os.path.join(FIX, name)))


def codes(ev: dict) -> dict:
    return {f["code"]: f for f in rules.evaluate(ev)}


class During70(unittest.TestCase):
    """2026-09-30, the boot of 20:01 on kernel 7.0: link errors, failed writes, driver not loaded."""

    @classmethod
    def setUpClass(cls):
        cls.ev = case("2026-09-30-v300-during-7.0.json")
        cls.f = codes(cls.ev)

    def test_all_four_active(self):
        for c in ("S401", "I301", "I302", "G101"):
            self.assertEqual(self.f[c]["status"], "active", c)

    def test_kernel_is_the_lead(self):
        self.assertEqual(rules.evaluate(self.ev)[0]["code"], "S401")
        s = self.f["S401"]["facts"]
        self.assertEqual(s["kernel"], "7.0.0-34-generic")
        self.assertEqual(s["good_kernel"], "6.14.0-37-generic")

    def test_link_errors_point_at_one_kernel_and_the_wire(self):
        i = self.f["I301"]
        self.assertEqual(i["cause"], "one_kernel")
        self.assertEqual((i["facts"]["disk"], i["facts"]["port"]), ("sda", "ata2"))
        self.assertIn("KINGSTON SV300", i["facts"]["model"])
        self.assertEqual(i["facts"]["largest_failed_kib"], 4096)
        self.assertIn("cable", i["facts"]["signal"])

    def test_driver_file_damaged_not_signature(self):
        g = self.f["G101"]
        self.assertEqual(g["cause"], "file_damaged")  # 2026-09-29's "signature" guess, ruled out by evidence
        self.assertEqual(g["facts"]["module"], "nvidia/580.178.04")

    def test_casper_check_known_harmless(self):
        self.assertEqual((self.f["I101"]["status"], self.f["I101"]["cause"]), ("seen", "known"))

    def test_guide_view_leads_with_the_fix_that_works(self):
        rep = report.build(self.ev, rules.evaluate(self.ev), now="2026-09-30T20:05:00-04:00")
        g = report.guide_view(rep)
        self.assertEqual(g["faults"][0]["code"], "S401")
        self.assertIn("Update Manager", " ".join(g["faults"][0]["steps"]))
        cmd = next(f for f in g["faults"] if f["code"] == "I301")["command"]
        self.assertEqual(cmd, "echo 1280 | sudo tee /sys/block/sda/queue/max_sectors_kb")

    def test_every_command_says_what_it_does_and_how_to_undo(self):
        rep = report.build(self.ev, rules.evaluate(self.ev), now="x")
        for f in rep["findings"]:
            for fx in f["fixes"]:
                if fx.get("command"):
                    self.assertTrue(fx.get("explain") and fx.get("undo"), (f["code"], fx))
                    self.assertNotIn("{", fx["command"], (f["code"], fx["command"]))  # every blank filled


class After68(unittest.TestCase):
    """The same machine on kernel 6.8, 7.0 removed: history, nothing active."""

    @classmethod
    def setUpClass(cls):
        cls.ev = case("2026-09-30-v300-after-6.8.json")
        cls.f = codes(cls.ev)

    def test_kernel_cleared_after_removal(self):
        self.assertEqual(self.f["S401"]["status"], "cleared")
        self.assertNotIn("G101", self.f)

    def test_disk_history_kept(self):
        self.assertEqual(self.f["I301"]["status"], "seen")
        self.assertEqual(self.f["I302"]["status"], "seen")

    def test_driver_loaded_on_68(self):
        self.assertEqual(self.ev["kernel"], "6.8.0-146-generic")
        self.assertEqual(self.ev["nvidia_version_loaded"], "580.178.04")

    def test_guide_view_has_no_active_fault(self):
        rep = report.build(self.ev, rules.evaluate(self.ev), now="x")
        self.assertFalse(any(f["now"] for f in report.guide_view(rep)["faults"]))

    def test_markdown_has_reading_guide_and_table(self):
        md = report.markdown(report.build(self.ev, rules.evaluate(self.ev), now="x"))
        self.assertIn("How to read this", md)
        self.assertIn("| start | kernel |", md)


class Branches(unittest.TestCase):
    """The tree's other branches, on the recorded case with one fact changed."""

    @classmethod
    def setUpClass(cls):
        cls.base = case("2026-09-30-v300-during-7.0.json")

    def ev(self):
        return copy.deepcopy(self.base)

    def test_not_built(self):
        e = self.ev()
        del e["dkms"]["7.0.0-34-generic"]
        f = codes(e)
        self.assertEqual(f["G101"]["cause"], "not_built")
        self.assertEqual(f["S301"]["status"], "active")

    def test_unsigned_with_secure_boot(self):
        e = self.ev()
        e["boots"][-1].update(secure_boot=True, sig_fail=1, zstd_fail=0)
        e["dkms"]["7.0.0-34-generic"]["warning"] = None
        self.assertEqual(codes(e)["G101"]["cause"], "unsigned")

    def test_loaded_driver_no_g101(self):
        e = self.ev()
        e["nvidia_module_loaded"] = True
        self.assertNotIn("G101", codes(e))

    def test_errors_on_every_kernel_mean_hardware(self):
        e = self.ev()
        for b in e["boots"]:
            b["links"] = copy.deepcopy(e["boots"][-1]["links"])
        f = codes(e)
        self.assertEqual(f["I301"]["cause"], "every_kernel")

    def test_root_read_only_now(self):
        e = self.ev()
        e["root"]["read_only"] = True
        self.assertEqual(codes(e)["I302"]["cause"], "read_only_now")

    def test_unclean_previous_boot(self):
        e = self.ev()
        e["boots"][-2]["clean_end"] = False
        self.assertIn("H401", codes(e))

    def test_interrupted_update(self):
        e = self.ev()
        e["dpkg_audit"] = "The following packages are only half configured"
        self.assertEqual(codes(e)["S101"]["status"], "active")


class Trees(unittest.TestCase):
    def test_every_cause_has_words_and_fixes_entry(self):
        with open(report.TREES, encoding="utf-8") as f:
            trees = json.load(f)["codes"]
        for rule in rules.RULES:
            code = rule.__name__.upper()
            self.assertIn(code, trees, code)
        for code, t in trees.items():
            for cause in t["causes"]:
                self.assertIn(cause, t["fixes"], (code, cause))
            for fixes in t["fixes"].values():
                for fx in fixes:
                    self.assertIn(fx.get("needs"), ("none", "user", "admin"), (code, fx))


if __name__ == "__main__":
    unittest.main()
