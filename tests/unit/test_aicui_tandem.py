# SPDX-License-Identifier: GPL-3.0-or-later
"""Two models on one project (SPEC §22.5, slice 3): the organizer (the guide) picks the next task from the map and the
problems the checks find; the coder does it; one hint when it's stuck, then the person.

    python3 -m unittest tests.unit.test_aicui_tandem -v        (from the repo root)
"""

import json
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.dirname(__file__))

from test_aicui_agent import Scripted, step  # noqa: E402

from cin_minai.aicui import tandem  # noqa: E402
from cin_minai.aicui.agent import STUCK_STEPS, Agent  # noqa: E402


def move(kind, thinking="", **fields):
    return {"thinking": thinking, "next": {"move": kind, **fields}}


class Junior(Scripted):
    """The organizer, scripted: each reply is a move (or an exception to raise)."""
    def __call__(self, messages, schema=None, max_tokens=0, cancel=None, on_text=None):
        if self.steps and isinstance(self.steps[0], Exception):
            self.sent.append(messages)
            raise self.steps.pop(0)
        return super().__call__(messages, schema, max_tokens, cancel, on_text)


@unittest.skipUnless(shutil.which("git"), "the changelog needs git")
class TandemTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, True)
        with open(os.path.join(self.root, "gui.py"), "w", encoding="utf-8", newline="\n") as f:
            f.write("class GameWindow:\n    def run(self):\n        return 1\n\n    def run(self):\n        return 2\n\n\n"
                    "def main():\n    GameApp().run()\n")
        self.said = []

    def pair(self, coder_steps, junior_moves, ctx=32768):
        a = Agent(self.root, Scripted(coder_steps), "Qwen3.8-27B", "auto", say=self.said.append, ctx=ctx)
        a.goals.add("A round runs", by="user")
        return a, tandem.Tandem(a, Junior(junior_moves), say=self.said.append)

    def events(self):
        with open(os.path.join(self.root, ".cinminai", "events.jsonl"), encoding="utf-8") as f:
            return [json.loads(line) for line in f]

    def test_continue_goes_straight_to_the_problem(self):
        task = "gui.py: run is defined twice in GameWindow (lines 2 and 5): delete lines 2-4; main calls GameApp: " \
               "use GameWindow. Check that gui.py compiles."
        a, t = self.pair([step("Delete the old one.", tool="replace_lines", path="gui.py", first=2, last=4, new=""),
                          step("Fix the name.", tool="edit", path="gui.py", old="GameApp()", new="GameWindow()"),
                          step("", tool="answer", text="Removed the old run() and fixed main().")],
                         [move("coder", "The checks name two problems in gui.py.", task=task),
                          move("done", summary="gui.py: the duplicate is gone and main() starts GameWindow.")])
        out = t.turn("continue")
        self.assertEqual(out, "gui.py: the duplicate is gone and main() starts GameWindow.")
        with open(os.path.join(self.root, "gui.py")) as f:
            self.assertEqual(f.read().count("def run"), 1)
        first = t.junior.sent[0][1]["content"]  # what the organizer was shown: the problems and the map, no code
        self.assertIn("run is defined twice in class GameWindow", first)
        self.assertIn("GameApp (called on line", first)
        self.assertIn("1. [ ] A round runs", first)
        self.assertNotIn("return 2", first)
        second = t.junior.sent[1][1]["content"]
        self.assertIn("Removed the old run() and fixed main().", second)  # it hears what the coder did
        self.assertNotIn("Problems the checks find", second)  # and the checks as they are now: none left
        coder_got = a.chat.sent[0][-1]["content"]
        self.assertIn("A task from the organizer", coder_got)
        self.assertIn(task, coder_got)
        handoffs = [e for e in self.events() if e["kind"] == "handoff"]
        self.assertEqual([(h["by"], h["to"]) for h in handoffs], [("organizer", "coder")])

    def test_a_task_is_a_turn_token_capped_at_5_percent(self):
        _, t = self.pair([], [], ctx=32768)
        self.assertEqual(t.cap, int(32768 * 0.05 * 3))
        coder = tandem.plan_schema(t.cap)["properties"]["next"]["anyOf"][0]
        self.assertEqual(coder["properties"]["task"]["maxLength"], t.cap)

    def stuck(self, thinking="Looking."):
        return [step(thinking, tool="list", path=".") for _ in range(STUCK_STEPS)]

    def test_stuck_gets_one_hint_then_the_person(self):
        # the checks name problems: the hint is made from them by code (the 4B's hints varied; once it told the coder
        # to read more, once it asked the person a vague question)
        a, t = self.pair(self.stuck() + [step("Now I see it.", tool="answer", text="Fixed with the hint.")],
                         [move("coder", task="Fix gui.py."), move("done", summary="All done.")])
        self.assertEqual(t.turn("continue"), "All done.")
        hinted = a.chat.sent[STUCK_STEPS][-1]["content"]
        self.assertIn("Hint from the organizer: Act on what the checks find now, with replace_lines", hinted)
        self.assertIn("run is defined twice in class GameWindow (lines 2-3 and 5-6)", hinted)
        # no problems for the checks to name: the organizer writes the hint
        with open(os.path.join(self.root, "gui.py"), "w") as f:
            f.write("def main():\n    return 1\n")
        a, t = self.pair(self.stuck() + [step("", tool="answer", text="Done.")],
                         [move("coder", task="Add a menu."),
                          {"next": {"move": "hint", "hint": "Write menu.py with replace_lines in gui.py line 2."}},
                          move("done", summary="Menu added.")])
        self.assertEqual(t.turn("continue"), "Menu added.")
        self.assertIn("Write menu.py", a.chat.sent[STUCK_STEPS][-1]["content"])
        a, t = self.pair(self.stuck() + self.stuck("Still looking."),
                         [move("coder", task="Add a menu."), {"next": {"move": "hint", "hint": "Look at line 2."}}])
        out = t.turn("continue")
        self.assertIn(f"I've gone {STUCK_STEPS} steps", out)  # the second stop goes to the person, no second hint
        self.assertEqual(len(t.junior.sent), 2)

    @unittest.skipUnless(shutil.which("g++"), "needs g++")
    def test_cpp_that_doesnt_build_is_a_problem_the_organizer_sees(self):
        """2026-10-08: nothing compiled the C++; two namespaces and a missing header went unseen by both models."""
        os.makedirs(os.path.join(self.root, "include"))
        os.makedirs(os.path.join(self.root, "src"))
        with open(os.path.join(self.root, "Makefile"), "w") as f:
            f.write("CXXFLAGS = -std=c++17 -Iinclude\n")
        with open(os.path.join(self.root, "include", "item.h"), "w") as f:
            f.write("#pragma once\nnamespace shop { struct Item { int price; }; }\n")
        with open(os.path.join(self.root, "src", "engine.cpp"), "w") as f:
            f.write("#include \"item.h\"\nnamespace store {\nint power(const Item& c) { return c.price; }\n}\n")
        with open(os.path.join(self.root, "src", "api.cpp"), "w") as f:
            f.write("#include \"items.h\"\n")
        a, t = self.pair([step("", tool="answer", text="ok")], [move("done", summary="ok")])
        found = "\n".join(a.problems())
        self.assertIn("src/engine.cpp: doesn't compile: src/engine.cpp:3:", found)
        self.assertIn("Item", found)
        self.assertIn("src/api.cpp: doesn't compile: src/api.cpp:1: items.h: No such file or directory", found)
        t.turn("continue")
        self.assertIn("items.h: No such file or directory", t.junior.sent[0][1]["content"])
        with open(os.path.join(self.root, "src", "api.cpp"), "w") as f:
            f.write("#include \"item.h\"\nint f() { return shop::Item{3}.price; }\n")
        self.assertNotIn("api.cpp", "\n".join(a.problems()))

    def test_a_hint_goes_out_as_the_task(self):
        a, t = self.pair(self.stuck() + [step("", tool="answer", text="Done.")],
                         [move("coder", task="In gui.py, keep lines 641-654."), move("done", summary="ok")])
        t.turn("continue")
        sent = a.chat.sent[STUCK_STEPS][-1]["content"]
        self.assertTrue(sent.split("\n", 1)[1].startswith("Hint from the organizer:"), sent[:200])
        self.assertIn("its line numbers may have moved since", sent)

    def test_a_task_that_changes_nothing_comes_back(self):
        """The move contract: a task changes something (a review, a no-op such as "call X at line 13" where line 13 is
        X, changed nothing on 2026-10-08) — told to the organizer; twice in a row goes to the person."""
        a, t = self.pair([step("", tool="answer", text="Looked at everything; it's fine."),
                          step("", tool="answer", text="Line 13 already is that function.")],
                         [move("coder", task="Review the code in gui.py.", acts_on="gui.py", proof="it's fine"),
                          move("coder", task="In gui.py, call main at line 9.", acts_on="gui.py line 9", proof="runs")])
        out = t.turn("continue")
        self.assertIn("Two tasks in a row changed nothing", out)
        second = t.junior.sent[1][1]["content"]
        self.assertIn("changed nothing (no file, source, goal or environment): Looked at everything", second)

    def test_the_coder_may_decline_and_the_organizer_revises(self):
        a, t = self.pair([step("", tool="decline", reason="line 13 already is initDatabase"),
                          step("Fix.", tool="replace_lines", path="gui.py", first=2, last=4, new=""),
                          step("", tool="answer", text="Removed the old run().")],
                         [move("coder", task="In db.py, call initDatabase at line 13.", acts_on="db.py", proof="build"),
                          move("coder", task="In gui.py, delete lines 2-4 (the first run).", acts_on="gui.py 2-4",
                               proof="gui.py compiles"),
                          move("done", summary="ok")])
        self.assertEqual(t.turn("continue"), "ok")
        self.assertIn("declined by the coder — I'm not doing this task: line 13 already is initDatabase",
                      t.junior.sent[1][1]["content"])
        handoffs = [(e["by"], e["to"]) for e in self.events() if e["kind"] == "handoff"]
        self.assertIn(("coder", "organizer"), handoffs)

    def test_what_the_person_gives_is_used_first(self):
        """2026-10-08: asked for a source, the person gave a link; the 4B's next task was something else."""
        link = "https://example.org/wiki/Set_(1E)"
        a, t = self.pair([], [move("coder", task="In gui.py, add a menu.", acts_on="gui.py", proof="runs"),
                              move("fetch", url=link), move("done", summary="ok")])
        a.fetch = lambda url: f"saved {url} as sources/Set_(1E).txt"
        self.assertEqual(t.turn(f"use this page: {link}."), "ok")
        first = t.junior.sent[0][1]["content"]
        self.assertIn(f"What they gave, not used yet:\n  - a link: {link}", first)
        self.assertIn("not done: the person gave https://example.org/wiki/Set_(1E) — use it first",
                      t.junior.sent[1][1]["content"])
        self.assertNotIn("not used yet", t.junior.sent[2][1]["content"])  # used: no longer listed
        a, t = self.pair([], [move("coder", task="Add a menu.", acts_on="gui.py", proof="runs"),
                              move("coder", task="Add a menu.", acts_on="gui.py", proof="runs")])
        self.assertIn("didn't use what you gave", t.turn(f"use {link}"))

    def test_a_fetch_is_a_web_address_and_the_coder_knows_the_screen(self):
        """2026-10-08: the 4B "fetched" gui.py, then asked the person for "the correct URL"; and the coder, without a
        display, couldn't know that a 1280x720 window on a 4K screen at 3x scaling is a third of its width."""
        from unittest import mock
        a, t = self.pair([], [move("fetch", url="gui.py"), move("done", summary="ok")])
        a.fetch = lambda url: self.fail("fetch called for a file")
        t.turn("the window is too small")
        self.assertIn("not done: gui.py isn't a web address — files in the project are the coder's",
                      t.junior.sent[1][1]["content"])
        with mock.patch.dict(os.environ, {"CINMINAI_SCREEN": "3840x2160@3"}):
            shown = a.system()
        self.assertIn("The person's screen is 3840x2160 pixels at 3x scaling", shown)
        self.assertIn("shows a 1280x720 window at the size other windows have", shown)
        with mock.patch.dict(os.environ, {"CINMINAI_SCREEN": ""}):
            self.assertNotIn("person's screen", a.system())

    def test_pasted_material_is_kept_as_a_source(self):
        a, t = self.pair([], [move("done", summary="ok")])
        rows = "".join(f"item {i}, {i * 10}\n" for i in range(12))
        t.turn("here's the list:\n" + rows)
        with open(os.path.join(self.root, "sources", "pasted-1.txt")) as f:
            self.assertEqual(f.read(), rows)
        self.assertIn("a file: sources/pasted-1.txt", t.junior.sent[0][1]["content"])

    def test_goals_show_their_cycle_and_unchecked_data_isnt_ticked(self):
        """Closure 2: where each goal stands (fetched, structured, checked); use needs checked data — 2026-10-08 a goal
        was ticked on a test that checked the 7 entries parsed, not the list against its source."""
        a, t = self.pair([], [])
        g = a.goals.load()[0]
        os.makedirs(os.path.join(self.root, "sources"))
        for rel, text in (("sources/list.txt", "a\nb\n"), ("items.json", "[1, 2]"),
                          ("test_ok.py", "assert True\n")):
            with open(os.path.join(self.root, rel), "w") as f:
                f.write(text)
        a.goals.note(g["id"], "sources", "sources/list.txt")
        a.goals.note(g["id"], "data", "items.json")
        shown = t.situation("continue", [], [])
        self.assertIn("fetched: sources/list.txt", shown)
        self.assertIn("structured: items.json", shown)
        self.assertIn("checked by a test: nothing yet", shown)
        refused = a.do({"tool": "goal_done", "id": g["id"]})
        self.assertIn("NOT ticked", refused)
        self.assertIn("not checked by any test: items.json", refused)
        with open(os.path.join(self.root, "test_ok.py"), "w") as f:
            f.write("import json\nassert len(json.load(open('items.json'))) == 2\n")
        self.assertIn("ticked", a.do({"tool": "goal_done", "id": g["id"]}))

    def test_an_honest_stop_goes_to_the_person(self):
        _, t = self.pair(self.stuck(), [move("coder", task="Fill in every card's attack."),
                                        {"next": {"move": "ask", "question": "Which source should the card stats "
                                                                            "come from?"}}])
        self.assertEqual(t.turn("continue"), "Which source should the card stats come from?")

    def test_the_coders_own_question_goes_to_the_person(self):
        _, t = self.pair([step("", tool="ask", question="pygame or pygame-ce?")],
                         [move("coder", task="Start the window."), move("done", summary="never reached")])
        self.assertEqual(t.turn("continue"), "pygame or pygame-ce?")

    def test_no_loop_between_the_two(self):
        _, t = self.pair([step("", tool="answer", text="Done."), step("", tool="answer", text="Done again.")],
                         [move("coder", task="Fix gui.py."), move("coder", task="Fix gui.py.")])
        self.assertIn("same task twice in a row", t.turn("continue"))

    def test_the_organizer_failing_never_loses_the_request(self):
        a, t = self.pair([step("", tool="answer", text="Worked on it alone.")], [RuntimeError("no server")])
        self.assertEqual(t.turn("continue"), "Worked on it alone.")
        self.assertIn("continue", a.chat.sent[0][-1]["content"])

    def test_a_page_is_fetched_with_permission_and_kept(self):
        a, t = self.pair([], [move("fetch", url="https://example.org/set-list"), move("done", summary="Saved.")])
        got = []
        a.fetch = lambda url: (got.append(url), f"saved {url} as sources/set-list.txt and sources/set-list.html")[1]
        self.assertEqual(t.turn("get the set list"), "Saved.")
        self.assertEqual(got, ["https://example.org/set-list"])  # the agent's fetch: asks, then keeps it whole
        self.assertIn("saved https://example.org/set-list as sources/set-list.txt", t.junior.sent[1][1]["content"])


if __name__ == "__main__":
    unittest.main()
