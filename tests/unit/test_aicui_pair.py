# SPDX-License-Identifier: GPL-3.0-or-later
"""Style B of the two cards (PLAN §1b): a MoE Senior lays the skeleton and assigns one file at a time; the 9B Junior
codes it on its own thread, writing only the file its task holds; the Senior reviews and has the final word.

    python3 -m unittest tests.unit.test_aicui_pair -v        (from the repo root)
"""

import json
import os
import shutil
import sys
import tempfile
import time
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(ROOT, "third_party", "team-table", "src"))  # the pinned submodule

from test_aicui_agent import Scripted, step  # noqa: E402

from cin_minai import engine  # noqa: E402
from cin_minai.aicui.agent import Agent, schema  # noqa: E402
from cin_minai.aicui.pair import Pair  # noqa: E402


@unittest.skipUnless(shutil.which("git"), "the changelog needs git")
class PairTest(unittest.TestCase):
    def setUp(self):
        from team_table.db import Database
        Database.reset_rate_limits()
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, True)
        with open(os.path.join(self.root, "rules.py"), "w") as f:
            f.write("def draw(deck):\n    # TODO\n    pass\n")

    def pair(self, senior_steps=(), junior_steps=()):
        senior = Agent(self.root, Scripted(list(senior_steps)), "Qwen3.6-35B-A3B", "auto", say=lambda s: None,
                       ctx=32768)
        junior = Agent(self.root, Scripted(list(junior_steps)), "Qwen3.5-9B", "auto", say=lambda s: None, ctx=32768)
        senior.goals.add("A match follows the rules", by="user")
        self.engine = engine.Engine("test0002", self.root, db_path=os.path.join(self.root, ".table.db"))
        self.addCleanup(self.engine.db.close)
        p = Pair(senior, junior, engine=self.engine)
        p.root = self.engine.request("build it", p.lead)
        return senior, junior, p

    def wait(self, p):
        for _ in range(200):
            if p.out == 0:
                return
            time.sleep(0.05)
        self.fail("the junior's task never finished")

    def test_each_card_has_its_tools(self):
        senior, junior, _ = self.pair()
        tools = lambda a: {v["properties"]["tool"]["const"] for v in schema(None, a.excluded())["properties"]["action"]["anyOf"]}  # noqa: E731,E501
        self.assertIn("assign", tools(senior))
        self.assertIn("review_task", tools(senior))
        self.assertEqual(tools(junior), {"read", "list", "search", "edit", "replace_lines", "write", "append", "run",
                                         "ask", "answer"})
        self.assertIn("You are the Senior", senior.system())
        self.assertIn("You are the junior developer", junior.system())

    def test_the_skeleton_comes_first(self):
        senior, _, _ = self.pair()
        said = senior.do({"tool": "assign", "path": "battle.py", "task": "write the battle step", "kind": "write"})
        self.assertIn("doesn't exist yet — lay the skeleton first", said)

    def test_a_held_file_is_the_juniors_alone(self):
        senior, junior, p = self.pair(junior_steps=[
            step("Fill the stub.", tool="edit", path="rules.py", old="    # TODO\n    pass\n",
                 new="    return deck.pop(0)\n"),
            step("Not mine.", tool="write", path="other.py", content="x = 1\n"),
            step("", tool="answer", text="draw() takes the top card; it compiles.")])
        import threading
        gate = threading.Event()
        work = junior.work
        junior.work = lambda text, cancel: (gate.wait(10), work(text, cancel))[1]
        said = senior.do({"tool": "assign", "path": "rules.py", "task": "fill in draw(): take the top card",
                          "kind": "write"})
        self.assertIn("task 1 given to your junior (write rules.py); rules.py is held for it", said)
        blocked = senior.do({"tool": "edit", "path": "rules.py", "old": "pass", "new": "return None"})
        self.assertIn("rules.py is held by your junior's task 1", blocked)
        gate.set()
        self.wait(p)
        with open(os.path.join(self.root, "rules.py")) as f:
            self.assertIn("return deck.pop(0)", f.read())
        self.assertFalse(os.path.exists(os.path.join(self.root, "other.py")))  # outside its task: refused
        ((n, kind, result),) = senior.inbox
        self.assertEqual((n, kind), (1, "task"))
        self.assertIn("task 1 (write rules.py) — done. It said: draw() takes the top card", result)
        self.assertIn("Changed: rules.py", result)
        (child,) = self.engine.db.task_tree(p.root["id"])["children"]
        self.assertEqual((child["assignee"], child["kind"], child["status"]), (p.second, "write", "done"))
        self.assertIn("logged as change", senior.do({"tool": "edit", "path": "rules.py", "old": "deck.pop(0)",
                                                     "new": "deck.pop(0)  # the top card"}))  # free again once closed

    def test_the_senior_reviews_and_a_rejection_goes_back(self):
        senior, junior, p = self.pair(junior_steps=[
            step("", tool="answer", text="Done (but I left the stub)."),
            step("Now really.", tool="edit", path="rules.py", old="    # TODO\n    pass\n", new="    return deck[0]\n"),
            step("", tool="answer", text="Filled.")])
        senior.do({"tool": "assign", "path": "rules.py", "task": "fill in draw(): take the top card", "kind": "write"})
        self.wait(p)
        senior.inbox.clear()
        back = senior.do({"tool": "review_task", "n": 1, "accept": False, "note": "the stub is still there"})
        self.assertIn("task 2 given to your junior", back)
        self.wait(p)
        sent = junior.chat.sent[-2][-1]["content"]
        self.assertIn("Rework of task 1 — your senior's note: the stub is still there", sent)
        self.assertEqual(senior.do({"tool": "review_task", "n": 2, "accept": True, "note": ""}), "task 2 accepted")
        first = next(c for c in self.engine.db.task_tree(p.root["id"])["children"] if "Rework" not in c["title"])
        self.assertEqual(json.loads(first["result"])["verdict"], "rejected")

    def test_the_team_is_chosen_per_project(self):
        from cin_minai.aicui import pair as P
        self.assertEqual(P.team_of(self.root), "A")  # nothing chosen: team A
        os.makedirs(os.path.join(self.root, ".cinminai"), exist_ok=True)
        with open(os.path.join(self.root, ".cinminai", "team.json"), "w") as f:
            json.dump({"team": "B"}, f)
        self.assertEqual(P.team_of(self.root), "B")

    def test_team_b_says_why_it_cant_start(self):
        """A model missing from the store: a plain reason (the agent then works as team A)."""
        from unittest import mock
        from cin_minai.aicui import pair as P
        from cin_minai.daemon import models

        class Empty:
            root = self.root

            def has(self, f):
                return False
        with mock.patch.object(models, "ModelStore", Empty):
            with self.assertRaises(RuntimeError) as cm:
                P.pair_backends(say=lambda s: None)
        self.assertIn("team B needs Qwen3.5-9B-Q4_K_M.gguf and Qwen3.6-35B-A3B-Q4_K_M.gguf in the model store",
                      str(cm.exception))

    def test_a_turn_with_both(self):
        """The Senior lays a file, assigns it, works on another, and finishes once the Junior's result is back."""
        senior, junior, p = self.pair(
            senior_steps=[
                step("The skeleton.", tool="write", path="battle.py", content="def battle(a, b):\n    # TODO\n    pass\n"),
                step("The junior fills it.", tool="assign", path="battle.py", task="fill in battle(): higher ATK wins",
                     kind="write"),
                step("Meanwhile, the deck.", tool="write", path="deck.py", content="DECK = []\n"),
                step("", tool="answer", text="Waiting."),
                step("", tool="review_task", n=1, accept=True, note=""),
                step("", tool="answer", text="Skeleton laid; battle filled by the junior and accepted.")],
            junior_steps=[
                step("Fill it.", tool="edit", path="battle.py", old="    # TODO\n    pass\n",
                     new="    return a if a >= b else b\n"),
                step("", tool="answer", text="battle() returns the higher ATK.")])
        p.root = None  # turn makes its own request
        out = p.turn("Build the battle step")
        self.assertEqual(out, "Skeleton laid; battle filled by the junior and accepted.")
        sent = "\n".join(m[-1]["content"] for m in senior.chat.sent)
        self.assertIn("Task 1 is back from your junior", sent)
        with open(os.path.join(self.root, "battle.py")) as f:
            self.assertIn("return a if a >= b else b", f.read())
        events = [json.loads(line) for line in open(os.path.join(self.root, ".cinminai", "events.jsonl"))]
        self.assertIn(("senior", "junior"), [(e.get("by"), e.get("to")) for e in events if e["kind"] == "handoff"])
        self.assertTrue(any(e.get("who") == "junior" for e in events))  # the Junior's work shows as its own


if __name__ == "__main__":
    unittest.main()
