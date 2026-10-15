# SPDX-License-Identifier: GPL-3.0-or-later
"""The Benchmark's coding run (aicui/benchcode.py): one project grows in stages — expressed, held, re-expressed,
continued (Ian, 2026-10-15). Every stage must be fair (the stubs fail, the reference passes), its results split by
kind, and what it measures sets the junior's limits and its load (inference/benchmark.py)."""

import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

from cin_minai.aicui import benchcode as C
from cin_minai.inference import benchmark as B


class StagesTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, True)

    def test_every_stage_is_fair_and_grows_as_asked(self):
        p = C.Project(self.root)
        for target, kinds in ((100, {"new", "report"}), (300, {"new", "held", "changed", "report"}),
                              (700, {"new", "held", "changed", "report"})):
            task = p.grow(target)
            before = p.check()
            self.assertFalse(before["ok"])
            self.assertEqual(set(before) - {"ok", "why"}, kinds)
            if "held" in before:  # what's there keeps working before any work: only new and changed fail
                done, total = before["held"].split("/")
                self.assertEqual(done, total)
            p.fill_reference()
            after = p.check()
            self.assertTrue(after["ok"], after)
            self.assertLess(abs(p.lines() - target), target * 0.3)  # about the size asked for
        self.assertIn("Change these existing functions:", task)
        self.assertIn("Already there, and it must keep working", task)
        self.assertIn("report_s3(data)", task)

    def test_a_change_is_visible_in_the_tests(self):
        p = C.Project(self.root)
        p.grow(100)
        p.fill_reference()
        p.grow(300)
        changed = p.check()["changed"]
        self.assertEqual(changed.split("/")[0], "0")  # the old versions fail the changed tests

    def test_the_stages_set_the_limits_and_the_load(self):
        store = os.path.join(self.root, "benchmarks.json")
        self.assertEqual(B.coding_limits("m.gguf", "card", store),
                         {"lines": 150, "steps": 25, "capacity": 0, "measured": False})
        B.record_coding("m.gguf", "card", 1, True, store, total=121, added=121, steps=20)
        B.record_coding("m.gguf", "card", 2, True, store, total=314, added=193, steps=44)
        B.record_coding("m.gguf", "card", 3, False, store, total=500, added=186, steps=90)
        self.assertEqual(B.coding_limits("m.gguf", "card", store),
                         {"lines": 190, "steps": 66, "capacity": 314, "measured": True})
        B.reset_coding("m.gguf", "card", store)
        self.assertFalse(B.coding_limits("m.gguf", "card", store)["measured"])


class CodingRunEndToEndTest(unittest.TestCase):
    def test_stages_run_until_one_fails_and_are_recorded(self):
        sys.path.insert(0, os.path.dirname(__file__))
        from test_aicui_agent import Scripted, step

        from cin_minai.aicui import bench
        from cin_minai.inference.matcher import CATALOG, Machine
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        shadow = C.Project(os.path.join(d, "shadow"))  # what a correct first stage writes
        shadow.grow(100)
        shadow.fill_reference()
        writes = []
        for f in sorted(os.listdir(os.path.join(shadow.root, "ledger"))):
            if f.endswith(".py") and f != "__init__.py":
                with open(os.path.join(shadow.root, "ledger", f)) as fh:
                    writes.append(step(f"Write {f}.", tool="write", path=f"ledger/{f}", content=fh.read()))
        model = Scripted(writes + [step("Done.", tool="answer", text="Stage 1 done; the tests pass."),
                                   step("Done.", tool="answer", text="Stage 2: nothing written.")])
        fake = mock.Mock(chat=lambda m, **kw: model(m, **kw), unload=lambda: None)
        nine = next(m for ms in CATALOG.values() for m in ms if m.file == "Qwen3.5-9B-Q4_K_M.gguf")
        machine = Machine([{"name": "Test card", "api": "CUDA0", "total_mib": 11264, "free_mib": 11000}],
                          32, 26, 4, True, 5.0, 50)
        with mock.patch.dict(os.environ, {"XDG_DATA_HOME": d}), \
                mock.patch.object(bench, "backend_for", return_value=fake):
            lines = bench.coding_run(None, machine, nine.file, nine, "the 9B", say=lambda s: None,
                                     targets=[100, 300])
            lim = B.coding_limits(nine.file, "Test card")
        with open(os.path.join(d, "cinminai", "benchmarks.json")) as f:
            runs = json.load(f)[B.coding_key(nine.file, "Test card")]
        self.assertEqual([(r["stage"], r["ok"]) for r in runs], [(1, True), (2, False)])
        self.assertEqual(runs[0]["new"], "55/55")
        self.assertEqual(runs[1]["held"].split("/")[0], runs[1]["held"].split("/")[1])  # stage 1 still held
        self.assertTrue(lim["measured"])
        self.assertEqual(lim["capacity"], runs[0]["total"])
        self.assertIn("stage 1: held", lines[1])
        self.assertIn("Junior load for the 9B: carries", lines[0])


if __name__ == "__main__":
    unittest.main()
