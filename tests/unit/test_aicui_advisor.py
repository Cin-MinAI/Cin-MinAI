# SPDX-License-Identifier: GPL-3.0-or-later
"""The cloud as advisor (src/cin_minai/aicui/advisor.py): the local model works and asks; AICUI asks by itself when
the work stalls; a few calls a request; what's sent is the request, the goals, the last steps and the checks.

    python3 -m unittest tests.unit.test_aicui_advisor -v        (from the repo root)
"""

import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(ROOT, "third_party", "team-table", "src"))

from test_aicui_agent import Scripted, step  # noqa: E402

from cin_minai.aicui import advisor as advisor_mod  # noqa: E402
from cin_minai.aicui.agent import Agent, schema  # noqa: E402


class Cloud:
    """A stand-in for the cloud model: what it was sent, and its advice."""
    def __init__(self, advice="Read app.py first: add() subtracts."):
        self.advice, self.sent = advice, []

    def chat(self, messages, schema=None, max_tokens=0, **kw):
        self.sent.append(messages)
        return self.advice, {}


def tools_of(a):
    return {v["properties"]["tool"]["const"] for v in schema(None, a.excluded())["properties"]["action"]["anyOf"]}


@unittest.skipUnless(shutil.which("git"), "the changelog needs git")
class AdvisorTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, True)
        with open(os.path.join(self.root, "app.py"), "w") as f:
            f.write("def add(a, b):\n    return a - b\n")

    def agent(self, steps):
        a = Agent(self.root, Scripted(steps), "Qwen3.8-27B", "auto", say=lambda s: None)
        self.cloud = Cloud()
        adv = advisor_mod.Advisor(a, self.cloud, "Claude Haiku 4.5")
        a.advisor_fn, a.advisor_reset, a.advisor_name = adv.ask, adv.reset, adv.name
        return a

    def test_the_local_model_asks_and_the_advice_is_its_result(self):
        a = self.agent([step("Not sure where the bug is.", tool="advisor", question="Why does add fail its test?"),
                        step("", tool="answer", text="ok")])
        self.assertIn("advisor", tools_of(a))
        self.assertIn("is your advisor", a.system())
        a.turn("fix add")
        sent = self.cloud.sent[0][1]["content"]
        self.assertIn("The person's request: fix add", sent)
        self.assertIn("Why does add fail its test?", sent)
        self.assertIn("Its files:", sent)
        self.assertIn("app.py", sent)
        last = a.chat.sent[-1]
        self.assertTrue(any("Advice from Claude Haiku 4.5 (the cloud advisor):\nRead app.py first" in m["content"]
                            for m in last))

    def test_no_advisor_without_the_role(self):
        a = Agent(self.root, Scripted([]), "m", "auto", say=lambda s: None)
        self.assertNotIn("advisor", tools_of(a))
        self.assertNotIn("is your advisor", a.system())

    def test_a_stalled_task_asks_the_advisor_by_itself_before_the_stuck_rule(self):
        reads = [step(f"Look again {i}.", tool="read", path="app.py") for i in range(13)]
        a = self.agent(reads + [step("", tool="answer", text="done")])
        a.turn("fix add")
        self.assertEqual(len(self.cloud.sent), 1)
        self.assertIn("steps without progress", self.cloud.sent[0][1]["content"])
        self.assertTrue(any("Advice from" in m["content"] for m in a.chat.sent[-1]))
        self.assertEqual(a.stopped, "answer")  # it went on and answered; the stuck rule didn't stop it

    def test_the_same_refusal_twice_goes_to_the_advisor_before_the_work_stops(self):
        """2026-10-13, test13: "main.cpp doesn't exist yet. I'll create it now" — and it read main.cpp again, twice;
        the run stopped and the advisor was never asked."""
        again = step("I'll create main.cpp now.", tool="read", path="src/main.cpp")
        a = self.agent([again, again, step("Write it.", tool="write", path="src/main.cpp", content="int main() {}\n"),
                        step("", tool="answer", text="main.cpp written")])
        self.assertEqual(a.turn("make main"), "main.cpp written")
        self.assertEqual(len(self.cloud.sent), 1)
        self.assertIn("refused twice", self.cloud.sent[0][1]["content"])
        self.assertIn("doesn't exist yet — write it to create it", self.cloud.sent[0][1]["content"])

    def test_without_an_advisor_the_same_refusal_twice_still_stops(self):
        again = step("I'll create main.cpp now.", tool="read", path="src/main.cpp")
        a = Agent(self.root, Scripted([again, again]), "m", "auto", say=lambda s: None)
        self.assertIn("refused the same way", a.turn("make main"))
        self.assertEqual(a.stopped, "stuck")

    def test_a_few_calls_a_request(self):
        a = self.agent([])
        ask = a.advisor_fn
        for _ in range(advisor_mod.MAX_USES):
            self.assertTrue(ask("What should I do next here?").startswith("Advice"))
        self.assertIn("has answered", ask("And now what should I do?"))
        a.advisor_reset()
        self.assertTrue(ask("A new request: what first?").startswith("Advice"))


if __name__ == "__main__":
    unittest.main()
