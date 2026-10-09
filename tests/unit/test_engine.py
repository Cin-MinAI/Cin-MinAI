# SPDX-License-Identifier: GPL-3.0-or-later
"""The multi-model engine on the Team Table (SPEC §22.4-22.5, D95): the request is the organizer's task, every move a
child task its member claims, references filled in by code, Stop cancels the tree.

    python3 -m unittest tests.unit.test_engine -v        (from the repo root)
"""

import json
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "third_party", "team-table", "src"))  # the pinned submodule

from cin_minai import engine  # noqa: E402


class EngineTest(unittest.TestCase):
    def setUp(self):
        from team_table.db import Database
        Database.reset_rate_limits()
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, True)
        with open(os.path.join(self.root, "game.py"), "w", encoding="utf-8") as f:
            f.write("".join(f"line {i}\n" for i in range(1, 101)))
        self.e = engine.Engine("4182ec9f-aaaa", self.root, db_path=os.path.join(self.root, ".table.db"))
        self.addCleanup(self.e.db.close)
        self.org = self.e.member("organizer", 8192, "guide 4B")
        self.coder = self.e.member("coder", 32768, "Qwen3.5-9B")

    def test_members_carry_the_project_and_where_they_run(self):
        self.assertEqual(self.org, "organizer.4182ec9f")
        cloud = self.e.member("senior", 200_000, "claude", where="cloud:anthropic")
        caps = next(m for m in self.e.db.list_members() if m["name"] == cloud)["capabilities"]
        self.assertEqual(caps, ["model:claude", "where:cloud:anthropic"])
        self.assertEqual(self.e.cap(self.coder), int(32768 * 0.05 * 3))

    def test_a_work_order_goes_through_the_table(self):
        root = self.e.request("make the ball bounce", self.org)
        self.assertEqual(root["status"], "in_progress")
        self.assertEqual(root["origin"], "person")
        refs = self.e.references("game.py:40-42, and the person's notes")
        self.assertEqual(len(refs), 1)
        order = self.e.order(root["id"], self.org, self.coder, "fix the bounce", "[write] fix the bounce", "write",
                             refs)
        self.assertIsNone(self.e.claim(self.org))  # the request waits while its child is open
        got = self.e.claim(self.coder)
        self.assertEqual(got["id"], order["id"])
        text = self.e.content(got)
        self.assertIn("   40 line 40", text)
        self.assertIn("   42 line 42", text)
        self.assertNotIn("line 43", text)
        self.e.finish(got, self.coder, "Qwen3.5-9B", "changed", "the bounce works")
        back = self.e.claim(self.org)
        self.assertEqual(back["id"], root["id"])  # the organizer has the request again
        (child,) = self.e.summary(root["id"])
        self.assertEqual((child["kind"], child["verdict"], child["model"], child["who"]),
                         ("write", "changed", "Qwen3.5-9B", self.coder))

    def test_references_stay_in_the_project(self):
        with self.assertRaises(engine.EngineError):
            self.e.reference("../outside.py")
        with self.assertRaises(engine.EngineError):
            self.e.reference("game.py:200-210")
        whole = self.e.content({"description": "x", "refs": [self.e.reference("game.py")]})
        self.assertIn("  100 line 100", whole)
        self.assertLess(len(self.e.content({"description": "x", "refs": [self.e.reference("game.py")]}, limit=300)),
                        400)

    def test_an_order_too_big_for_its_member_comes_back(self):
        root = self.e.request("go", self.org)
        with self.assertRaises(engine.EngineError) as cm:
            self.e.order(root["id"], self.org, self.coder, "big", "x" * 4950, "write")
        self.assertIn("Too big", str(cm.exception))
        with self.assertRaises(engine.EngineError):
            self.e.order(root["id"], self.org, self.coder, "review", "just look", "review")

    def test_a_long_request_goes_by_reference(self):
        root = self.e.request("do this:\n" + "detail " * 600, self.org)
        self.assertEqual(root["description"], "")
        self.assertIn("detail detail", self.e.content(root))

    def test_stop_cancels_the_tree(self):
        root = self.e.request("go", self.org)
        self.e.order(root["id"], self.org, self.coder, "a step", "[write] a step", "write")
        self.assertEqual(self.e.cancel(root["id"]), 2)
        self.assertIsNone(self.e.claim(self.coder))

    def test_an_earlier_run_left_open_is_closed(self):
        root = self.e.request("go", self.org)
        self.assertEqual(self.e.close_stale(), 1)
        tree = self.e.db.task_tree(root["id"])
        self.assertEqual(tree["status"], "cancelled")

    def test_a_result_says_who_and_how(self):
        root = self.e.request("go", self.org)
        self.e.finish(root, self.org, "guide 4B", "done", "all goals met")
        row = self.e.db.task_tree(root["id"])
        self.assertEqual(row["status"], "done")
        self.assertEqual(json.loads(row["result"])["verdict"], "done")


if __name__ == "__main__":
    unittest.main()
