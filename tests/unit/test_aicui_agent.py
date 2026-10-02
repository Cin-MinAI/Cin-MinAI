# SPDX-License-Identifier: GPL-3.0-or-later
"""cinminai-code (PLAN D61) with a scripted model: tools, permission prompts, the changelog, goals, events.

    python3 -m unittest tests.unit.test_aicui_agent -v        (from the repo root)
"""

import json
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))

from cin_minai.aicui.agent import Agent, schema  # noqa: E402


class Scripted:
    def __init__(self, steps):
        self.steps, self.sent = list(steps), []

    def __call__(self, messages, schema=None, max_tokens=0, cancel=None):
        self.sent.append(messages)
        return json.dumps(self.steps.pop(0)), {}


def step(thinking, **action):
    return {"thinking": thinking, "action": action}


@unittest.skipUnless(shutil.which("git"), "the changelog needs git")
class AgentTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        with open(os.path.join(self.root, "app.py"), "w", encoding="utf-8", newline="\n") as f:
            f.write("def add(a, b):\n    return a - b\n")
        self.said = []

    def agent(self, steps, replies=("y",), mode="ask"):
        replies = list(replies)
        return Agent(self.root, Scripted(steps), "Qwen3.8-27B", mode,
                     ask=lambda prompt: replies.pop(0) if replies else "n", say=self.said.append)

    def events(self):
        with open(os.path.join(self.root, ".cinminai", "events.jsonl"), encoding="utf-8") as f:
            return [json.loads(line) for line in f]

    def test_read_edit_tick_answer(self):
        a = self.agent([step("Look first.", tool="read", path="app.py"),
                        step("Wrong operator.", tool="edit", path="app.py", old="a - b", new="a + b"),
                        step("Note the goal.", tool="goal_add", text="Fix add()"),
                        step("Done with it.", tool="goal_done", id=1),
                        step("Report.", tool="answer", text="Fixed add(): it subtracted.")])
        self.assertEqual(a.turn("add() is broken"), "Fixed add(): it subtracted.")
        with open(os.path.join(self.root, "app.py"), encoding="utf-8") as f:
            self.assertIn("return a + b", f.read())
        e = a.log.entries()
        self.assertEqual((len(e), e[0]["file"], e[0]["model"]), (1, "app.py", "Qwen3.8-27B"))
        kinds = [x["kind"] for x in self.events()]
        self.assertEqual(kinds, ["user", "thinking", "thinking", "change", "thinking", "goals", "thinking", "goals",
                                 "thinking", "answer"])
        self.assertTrue(a.goals.load()[0]["done"])
        self.assertTrue(any("+    return a + b" in s for s in self.said))  # the diff was shown before asking

    def test_no_means_no_and_always_means_always(self):
        a = self.agent([step("", tool="edit", path="app.py", old="a - b", new="a * b"),
                        step("", tool="answer", text="ok")], replies=["n"])
        a.turn("change it")
        with open(os.path.join(self.root, "app.py"), encoding="utf-8") as f:
            self.assertIn("a - b", f.read())
        self.assertEqual(a.log.entries(), [])
        b = self.agent([step("", tool="write", path="x.txt", content="1\n"),
                        step("", tool="write", path="y.txt", content="2\n"),
                        step("", tool="answer", text="ok")], replies=["a"])
        b.turn("two files")
        self.assertTrue(os.path.exists(os.path.join(self.root, "y.txt")))  # asked once, then always

    def test_auto_mode_asks_nothing(self):
        asked = []
        a = Agent(self.root, Scripted([step("", tool="write", path="z.txt", content="z\n"),
                                       step("", tool="answer", text="ok")]), "m", "auto",
                  ask=lambda p: asked.append(p) or "n", say=self.said.append)
        a.turn("go")
        self.assertEqual(asked, [])
        self.assertTrue(os.path.exists(os.path.join(self.root, "z.txt")))

    def test_the_project_folder_is_the_limit(self):
        a = self.agent([step("", tool="read", path="../../etc/passwd"),
                        step("", tool="write", path=".cinminai/goals.json", content="{}"),
                        step("", tool="answer", text="ok")])
        a.turn("try")
        results = [m["content"] for m in a.chat.sent[-1] if m["role"] == "user" and m["content"].startswith("Result")]
        self.assertIn("outside the project folder", results[0])
        self.assertIn("AICUI's own", results[1])

    def test_no_admin_refuses_sudo(self):
        a = self.agent([])
        self.assertIn("aren't allowed", a.run("sudo rm -rf /"))

    def test_schema_lists_every_tool(self):
        tools = [v["properties"]["tool"]["const"] for v in schema()["properties"]["action"]["anyOf"]]
        self.assertEqual(tools, ["read", "list", "search", "edit", "write", "run", "goal_add", "goal_done", "ask",
                                 "answer"])


if __name__ == "__main__":
    unittest.main()
