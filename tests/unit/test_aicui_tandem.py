# SPDX-License-Identifier: GPL-3.0-or-later
"""Two models on one project, the coder leading (SPEC §22.5; Ian, 2026-10-09: "flip the tandem"): the coding model
works the request with its own judgement; the guide is its helper — reading long files for a question, reviewing a
goal before it's ticked; every request and helper job is a task on the Team Table. And the coder's own checks.

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
sys.path.insert(0, os.path.join(ROOT, "third_party", "team-table", "src"))  # the pinned submodule

from test_aicui_agent import Scripted, step  # noqa: E402

from cin_minai import engine  # noqa: E402
from cin_minai.aicui import tandem  # noqa: E402
from cin_minai.aicui.agent import Agent  # noqa: E402


class Helper(Scripted):
    """The helper, scripted: each reply is text, a dict (JSON), or an exception to raise."""
    def __call__(self, messages, schema=None, max_tokens=0, cancel=None, on_text=None):
        self.sent.append(messages)
        s = self.steps.pop(0)
        if isinstance(s, Exception):
            raise s
        return (json.dumps(s) if isinstance(s, dict) else s), {}


@unittest.skipUnless(shutil.which("git"), "the changelog needs git")
class Base(unittest.TestCase):
    def setUp(self):
        from team_table.db import Database
        Database.reset_rate_limits()  # the table counts writes per member per minute, across this whole process
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, True)
        with open(os.path.join(self.root, "gui.py"), "w", encoding="utf-8", newline="\n") as f:
            f.write("class GameWindow:\n    def run(self):\n        return 1\n\n    def run(self):\n        return 2\n\n\n"
                    "def main():\n    GameApp().run()\n")
        self.said = []

    def agent(self, coder_steps=(), ctx=32768):
        a = Agent(self.root, Scripted(list(coder_steps)), "Qwen3.8-27B", "auto", say=self.said.append, ctx=ctx)
        a.goals.add("A round runs", by="user")
        return a

    def pair(self, coder_steps=(), helper_replies=()):
        a = self.agent(coder_steps)
        self.engine = engine.Engine("test0001", self.root, db_path=os.path.join(self.root, ".table.db"))
        self.addCleanup(self.engine.db.close)
        return a, tandem.Tandem(a, Helper(list(helper_replies)), say=self.said.append, engine=self.engine)

    def tree(self):
        (root,) = [r for r in self.engine.db.list_tasks() if r["parent_id"] is None]
        return self.engine.db.task_tree(root["id"])


class TandemTest(Base):
    def test_the_coder_leads_the_request_on_the_table(self):
        a, t = self.pair([step("Delete the old one.", tool="replace_lines", path="gui.py", first=2, last=4, new=""),
                          step("Fix the name.", tool="edit", path="gui.py", old="GameApp()", new="GameWindow()"),
                          step("", tool="answer", text="Removed the old run() and fixed main().")])
        self.assertEqual(t.turn("continue"), "Removed the old run() and fixed main().")
        with open(os.path.join(self.root, "gui.py")) as f:
            self.assertEqual(f.read().count("def run"), 1)
        self.assertEqual(a.chat.sent[0][-1]["content"], "continue")  # the person's words, not an order about them
        self.assertEqual(t.junior.sent, [])                            # the helper only when the coder asks
        tree = self.tree()
        self.assertEqual((tree["assignee"], tree["status"], tree["origin"]), (t.lead, "done", "person"))
        self.assertEqual(json.loads(tree["result"])["model"], "Qwen3.8-27B")

    def test_the_helper_reads_a_long_file_for_the_coder(self):
        """The bulk stays out of the coder's context: the helper reads it in parts and keeps its answer."""
        os.makedirs(os.path.join(self.root, "sources"))
        rows = "".join(f"row {i}: filler text for the page\n" for i in range(700))  # ~3 parts
        with open(os.path.join(self.root, "sources", "list.txt"), "w") as f:
            f.write(rows)
        a, t = self.pair([step("A long page: the helper reads it.", tool="ask_helper", source="sources/list.txt",
                               question="Which entries score over 2000?"),
                          step("", tool="answer", text="Got them.")],
                         ["Stone Giant 3000", "nothing here", "River Knight 2500"])
        t.turn("make the card list")
        told = a.chat.sent[1][-1]["content"]
        self.assertIn("the helper read sources/list.txt in 3 parts for: Which entries score over 2000?", told)
        self.assertIn("Stone Giant 3000", told)
        kept = [f for f in os.listdir(os.path.join(self.root, ".cinminai", "helper"))]
        with open(os.path.join(self.root, ".cinminai", "helper", kept[0])) as f:
            answer = f.read()
        self.assertIn("## part 1\nStone Giant 3000", answer)
        self.assertIn("## part 3\nRiver Knight 2500", answer)
        self.assertNotIn("nothing here", answer)
        self.assertIn("part 2 of 3", t.junior.sent[1][0]["content"])
        (child,) = self.tree()["children"]
        self.assertEqual((child["assignee"], child["kind"], child["status"]), (t.helper_name, "read", "done"))
        self.assertEqual(json.loads(child["result"])["verdict"], "answered")

    def test_a_goal_is_ticked_after_the_helpers_review(self):
        """2026-10-09: a goal for "the set's cards with card images" was ticked on 7 cards and no images, because its
        tests passed. Before a tick, the helper — another model — says whether every part is covered."""
        a, t = self.pair([], [{"covered": False, "missing": "card images: no image files, and no test reads any"},
                              {"covered": True, "missing": ""}])
        a.verify = lambda: (True, "test_cards.py: passed")
        refused = a.do({"tool": "goal_done", "id": 1})
        self.assertIn("goal 1 NOT ticked", refused)
        self.assertIn("not covered yet — card images: no image files", refused)
        self.assertIn("The goal: A round runs", t.junior.sent[0][1]["content"])
        self.assertIn("goal 1 ticked", a.do({"tool": "goal_done", "id": 1}))

    def test_the_helper_failing_never_stops_the_coder(self):
        a, t = self.pair([], [RuntimeError("no server"), RuntimeError("no server")])
        with open(os.path.join(self.root, "notes.txt"), "w") as f:
            f.write("x\n")
        self.assertIn("error: the helper couldn't do it", a.do({"tool": "ask_helper", "source": "notes.txt",
                                                               "question": "what's in it?"}))
        a.verify = lambda: (True, "test_x.py: passed")
        self.assertIn("goal 1 ticked", a.do({"tool": "goal_done", "id": 1}))  # no review answer: the checks decide

    def test_the_coders_question_goes_to_the_person(self):
        _, t = self.pair([step("", tool="ask", question="pygame or pygame-ce?")])
        self.assertEqual(t.turn("continue"), "pygame or pygame-ce?")
        tree = self.tree()
        self.assertEqual((tree["status"], json.loads(tree["result"])["verdict"]), ("blocked", "asks the person"))

    def test_stop_cancels_the_request_on_the_table(self):
        a, t = self.pair([])
        a.chat = lambda *args, **kw: (_ for _ in ()).throw(KeyboardInterrupt())  # Stop while the coder works
        with self.assertRaises(KeyboardInterrupt):
            t.turn("continue")
        self.assertEqual({r["status"] for r in self.engine.db.list_tasks()}, {"cancelled"})

    def test_alone_there_is_no_helper(self):
        a = self.agent()
        self.assertIn("no helper is running here", a.do({"tool": "ask_helper", "source": "gui.py", "question": "?"}))


class CoderChecks(Base):
    """What the coder's own checks find, with or without a helper."""

    @unittest.skipUnless(shutil.which("g++"), "needs g++")
    def test_a_cpp_header_is_checked_as_cpp_without_a_makefile(self):
        """2026-10-09: "card.h:2: string: No such file or directory" on every check — a C++ header compiled as C."""
        from cin_minai.aicui.agent import compile_check
        os.makedirs(os.path.join(self.root, "engine"))
        with open(os.path.join(self.root, "engine", "card.h"), "w") as f:
            f.write("#pragma once\n#include <string>\nstruct Card { std::string name; };\n")
        with open(os.path.join(self.root, "engine", "plain.h"), "w") as f:
            f.write("#pragma once\nint add(int a, int b);\n")
        self.agent()
        self.assertEqual(compile_check(os.path.join(self.root, "engine", "card.h")), "")
        self.assertEqual(compile_check(os.path.join(self.root, "engine", "plain.h")), "")

    @unittest.skipUnless(shutil.which("g++"), "needs g++")
    def test_cpp_that_doesnt_build_is_a_problem(self):
        """2026-10-08: nothing compiled the C++; two namespaces and a missing header went unseen."""
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
        a = self.agent()
        found = "\n".join(a.problems())
        self.assertIn("src/engine.cpp: doesn't compile: src/engine.cpp:3:", found)
        self.assertIn("src/api.cpp: doesn't compile: src/api.cpp:1: items.h: No such file or directory", found)
        self.assertIn("items.h: No such file or directory", a.project_map())
        with open(os.path.join(self.root, "src", "api.cpp"), "w") as f:
            f.write("#include \"item.h\"\nint f() { return shop::Item{3}.price; }\n")
        self.assertNotIn("api.cpp", "\n".join(a.problems()))

    def test_progress_is_four_kinds_of_action(self):
        """Ian, 2026-10-09: "The only 4 things that qualify as an action that counts as progress is pass, fail,
        write, delete. Accept, reject, create, destroy." Gathering isn't progress."""
        a = self.agent()
        a.outputs = set()
        gathering = [({"tool": "fetch"}, "saved https://x.org/a.jpg as assets/a.jpg (503 bytes)"),
                     ({"tool": "look"}, "Looked at program (…)\nwindow \"Ball\": 400x300"),
                     ({"tool": "read"}, "    1 import pygame"), ({"tool": "list"}, "main.py  (1 bytes)"),
                     ({"tool": "search"}, "main.py:1: import pygame")]
        for act, result in gathering:
            self.assertFalse(a.progressed(act, result), act)
        self.assertTrue(a.progressed({"tool": "write"}, "main.py changed (+3 -0), logged as change 4"))  # write
        self.assertTrue(a.progressed({"tool": "edit"}, "the user said no to this change"))              # reject
        self.assertTrue(a.progressed({"tool": "goal_add"}, "goal 2 added"))                              # create
        self.assertTrue(a.progressed({"tool": "run"}, "exit 1\nFAILED test_x"))                          # fail
        self.assertFalse(a.progressed({"tool": "run"}, "exit 1\nFAILED test_x"))                         # same verdict
        self.assertTrue(a.progressed({"tool": "run"}, "exit 0\nok"))                                     # pass
        self.assertTrue(a.progressed({"tool": "goal_done"}, "goal 1 NOT ticked — the checks failed: …"))  # fail

    def test_goals_show_their_cycle_and_unchecked_data_isnt_ticked(self):
        """Where each goal stands (fetched, structured, checked); use needs checked data — 2026-10-08 a goal was ticked
        on a test that checked the 7 entries parsed, not the list against its source."""
        a = self.agent()
        g = a.goals.load()[0]
        os.makedirs(os.path.join(self.root, "sources"))
        for rel, text in (("sources/list.txt", "a\nb\n"), ("items.json", "[1, 2]"),
                          ("test_ok.py", "assert True\n")):
            with open(os.path.join(self.root, rel), "w") as f:
                f.write(text)
        a.goals.note(g["id"], "sources", "sources/list.txt")
        a.goals.note(g["id"], "data", "items.json")
        shown = a.system()
        self.assertIn("fetched: sources/list.txt", shown)
        self.assertIn("structured: items.json", shown)
        refused = a.do({"tool": "goal_done", "id": g["id"]})
        self.assertIn("NOT ticked", refused)
        self.assertIn("not checked by any test: items.json", refused)
        with open(os.path.join(self.root, "test_ok.py"), "w") as f:
            f.write("import json\nassert len(json.load(open('items.json'))) == 2\n")
        self.assertIn("ticked", a.do({"tool": "goal_done", "id": g["id"]}))

    def test_a_kept_page_is_material_not_code(self):
        """2026-10-09: a fetched page's own HTML had an "unclosed script tag"; the coder was sent to fix the kept page."""
        os.makedirs(os.path.join(self.root, "sources"))
        with open(os.path.join(self.root, "sources", "gallery.html"), "w", encoding="utf-8") as f:
            f.write("<html><body><script>x()</script></script></body></html>\n")
        a = self.agent()
        self.assertNotIn("gallery.html", "\n".join(a.problems()))
        self.assertNotIn("gallery.html", a.project_map())
        said = a.do({"tool": "replace_lines", "path": "sources/gallery.html", "first": 1, "last": 1, "new": ""})
        self.assertIn("is kept material", said)


if __name__ == "__main__":
    unittest.main()
