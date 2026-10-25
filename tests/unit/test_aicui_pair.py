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

# the code specifics a senior gives (the protocol, 2026-10-15: a write or fix task names them)
DETAIL = (" — signature unchanged, no new imports; return the value the docstring names; keep the TODO "
          "markers out; check it with python3 -m py_compile and the project's tests before you answer")


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
        self.assertEqual(tools(junior), {"read", "list", "search", "distill", "edit", "replace_lines", "write",
                                         "append", "run",
                                         "ask", "answer"})
        self.assertIn("You are the Senior", senior.system())
        self.assertIn("You are the junior developer", junior.system())

    def test_the_skeleton_comes_first(self):
        senior, _, _ = self.pair()
        said = senior.do({"tool": "assign", "path": "battle.py", "task": "write the battle step" + DETAIL, "kind": "write"})
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
        said = senior.do({"tool": "assign", "path": "rules.py", "task": "fill in draw(): take the top card" + DETAIL,
                          "kind": "write"})
        self.assertIn("task 2 given to your junior (write rules.py); rules.py is held for it", said)
        blocked = senior.do({"tool": "edit", "path": "rules.py", "old": "pass", "new": "return None"})
        self.assertIn("rules.py is held by your junior's task 2", blocked)
        gate.set()
        self.wait(p)
        with open(os.path.join(self.root, "rules.py")) as f:
            self.assertIn("return deck.pop(0)", f.read())
        self.assertFalse(os.path.exists(os.path.join(self.root, "other.py")))  # outside its task: refused
        ((n, kind, result),) = senior.inbox
        self.assertEqual((n, kind), (2, "task"))
        self.assertIn("task 2 (write rules.py) — done. It said: draw() takes the top card", result)
        self.assertIn("Changed: rules.py", result)
        (child,) = self.engine.db.task_tree(p.root["id"])["children"]
        self.assertEqual((child["assignee"], child["kind"], child["status"]), (p.second, "write", "done"))
        self.assertIn("logged as change", senior.do({"tool": "edit", "path": "rules.py", "old": "deck.pop(0)",
                                                     "new": "deck.pop(0)  # the top card"}))  # free again once closed

    def test_a_fix_is_edits_checked_and_shown(self):
        """Ian, 2026-10-25: "have the Senior read, assign edits, then the junior does them and verifies the edits before
        dumping and moving on to the next job". A fix changes lines, never the whole file; the result carries what
        changed and AICUI's own start, so the Senior judges in one step (on test16 it re-checked by hand: ~20 calls)."""
        with open(os.path.join(self.root, "main.py"), "w") as f:
            f.write("import rules\nprint('ok')\n")
        senior, junior, p = self.pair(junior_steps=[
            step("Rewrite it.", tool="write", path="rules.py", content="def draw(deck):\n    return deck.pop(0)\n"),
            step("Edit the stub.", tool="replace_lines", path="rules.py", first=2, last=3, new="    return deck.pop(0)"),
            step("", tool="answer", text="rules.py:2 now returns deck.pop(0); py_compile passes; main.py starts.")])
        senior.do({"tool": "assign", "path": "rules.py", "kind": "fix",
                   "task": "fix draw() at lines 2-3: the stub returns None; make it return deck.pop(0)" + DETAIL})
        self.wait(p)
        sent = junior.chat.sent[0][-1]["content"]
        self.assertIn("This is a fix: change only the lines your senior named, with edit or replace_lines", sent)
        refused = junior.chat.sent[1][-1]["content"]
        self.assertIn("this is a fix: change the named lines of rules.py with edit or replace_lines", refused)
        ((n, kind, result),) = senior.inbox
        self.assertIn("— done. It said: rules.py:2 now returns deck.pop(0)", result)
        self.assertIn("What changed:", result)
        self.assertIn("+    return deck.pop(0)", result)
        self.assertIn("-    pass", result)
        self.assertIn("Started by AICUI (main.py, 5 s): finished", result)
        self.assertFalse(junior.edits_only)  # the next task is whatever it is: a write task may write the file
        p.current = {"rules.py"}
        self.assertIn("logged as change", junior.do({"tool": "write", "path": "rules.py",
                                                     "content": "def draw(deck):\n    return deck.pop(0)  # top\n"}))

    def test_a_write_tasks_draft_waits_for_the_next_write(self):
        """2026-10-25 (test16): the junior's 193-line draft of a rewrite was set aside when its task stopped."""
        senior, junior, p = self.pair(junior_steps=[step("", tool="answer", text="placeholder")])
        line = "# " + "x" * 200 + "\n"
        junior.chat.steps[:0] = [step("The first part.", tool="write", path="rules.py",
                                      content=line * (junior.content_max // len(line) + 1))]
        draft = junior.draft_path("rules.py")
        senior.do({"tool": "assign", "path": "rules.py", "kind": "write",
                   "task": "rewrite draw() to take the top card and return it" + DETAIL})
        self.wait(p)
        self.assertTrue(os.path.exists(draft))  # kept for the next write on it
        ((n, kind, result),) = senior.inbox
        self.assertIn("Drafted and kept (the file itself is as it was): rules.py", result)
        senior.inbox.clear()
        junior.chat.steps.append(step("", tool="answer", text="Fixed line 2."))
        senior.do({"tool": "assign", "path": "rules.py", "kind": "fix",
                   "task": "fix draw() at line 2: return deck.pop(0) instead of pass" + DETAIL})
        self.wait(p)
        self.assertFalse(os.path.exists(draft))  # another kind of task sets it aside
        self.assertTrue(os.listdir(os.path.join(self.root, ".cinminai", "drafts-stale")))

    def test_the_table_is_the_backbone(self):
        """Ian, 2026-10-21: "make the table the backbone". The Junior's queue, its holds and its instructions are on the
        table; the table's refusals reach the Senior; a cancel there frees the file; no team without it."""
        import threading
        senior, junior, p = self.pair(junior_steps=[step("", tool="answer", text="Ran it: it imports.")])
        gate = threading.Event()
        work = junior.work
        junior.work = lambda text, cancel: (gate.wait(10), work(text, cancel))[1]
        long = "run rules.py and report what fails; " + "check each rule in turn. " * 80  # past the 5 % of an 8K junior
        self.engine.member("junior", 8192)  # a small junior: a task for it is at most 1,228 characters
        said = senior.do({"tool": "assign", "path": "rules.py", "task": long, "kind": "test"})
        self.assertIn("task 2 given to your junior", said)
        t = self.engine.get(2)
        self.assertEqual((t["assignee"], len(t["refs"])), (p.second, 1))  # the bulk by reference
        self.assertEqual(p.instruction(t), long.strip())
        gate.set()
        self.wait(p)
        self.assertIn(("check each rule in turn. " * 80).strip(), junior.chat.sent[0][-1]["content"])  # whole, from the table
        # the hold is the table's: cancelled there (the Requests view's Stop), the file is free at once
        junior.chat = Scripted([step("", tool="answer", text="never")])
        gate.clear()
        senior.do({"tool": "assign", "path": "rules.py", "task": "fill in draw(): take the top card" + DETAIL,
                   "kind": "write"})
        self.assertEqual(set(p.held), {"rules.py"})
        self.engine.cancel(p.root["id"])
        self.assertEqual(p.held, {})
        gate.set()
        self.wait(p)
        # the request's budget, spent: the table's words are the Senior's answer
        small = engine.Engine("test0004", self.root, db_path=os.path.join(self.root, ".small.db"), budget=2)
        self.addCleanup(small.db.close)
        p2 = Pair(senior, junior, engine=small)
        p2.root = small.request("one small request", p2.lead)
        junior.work = lambda text, cancel: (gate.wait(10), work(text, cancel))[1]
        gate.clear()
        self.assertIn("given to your junior", senior.do({"tool": "assign", "path": "rules.py", "kind": "test",
                                                         "task": "run it and report what fails"}))
        refused = senior.do({"tool": "brief", "files": ["rules.py"], "question": "what does draw do"})
        self.assertIn("the Team Table refused this task: This request's budget is spent (2 of 2 tasks)", refused)
        gate.set()
        self.wait(p2)
        with self.assertRaises(RuntimeError):
            Pair(senior, junior, engine=None)

    def test_the_senior_reviews_and_a_rejection_goes_back(self):
        senior, junior, p = self.pair(junior_steps=[
            step("", tool="answer", text="Done (but I left the stub)."),
            step("Now really.", tool="edit", path="rules.py", old="    # TODO\n    pass\n", new="    return deck[0]\n"),
            step("", tool="answer", text="Filled.")])
        senior.do({"tool": "assign", "path": "rules.py", "task": "fill in draw(): take the top card" + DETAIL, "kind": "write"})
        self.wait(p)
        senior.inbox.clear()
        back = senior.do({"tool": "review_task", "n": 2, "accept": False, "note": "the stub is still there"})
        self.assertIn("task 3 given to your junior", back)
        self.wait(p)
        sent = junior.chat.sent[-2][-1]["content"]
        self.assertIn("Correction of task 2 — your senior's corrections: the stub is still there", sent)
        self.assertIn("This task's limits: 25 steps, 150 lines of code", sent)  # not measured yet: the stand-ins
        self.assertEqual(senior.do({"tool": "review_task", "n": 3, "accept": True, "note": ""}), "task 3 accepted")
        first = next(c for c in self.engine.db.task_tree(p.root["id"])["children"] if "Correction" not in c["title"])
        self.assertEqual(json.loads(first["result"])["verdict"], "rejected")

    def test_one_correction_attempt_then_the_corrections_are_the_seniors(self):
        """Ian, 2026-10-15: "Sr gives detail on code specifics and jr executes on script, gives back to sr, sr checks, if
        good jr dumps. if no good sr gives corrections. After the 1st attempt at correction sr takes all script
        corrections." Each task starts fresh, within its limits."""
        senior, junior, p = self.pair(junior_steps=[step("", tool="answer", text="Done."),
                                                    step("", tool="answer", text="Corrected.")])
        self.assertIn("give your junior the code specifics", senior.do(
            {"tool": "assign", "path": "rules.py", "task": "fill in draw()", "kind": "write"}))
        junior.history = [{"user": "an earlier task", "answer": "its answer"}]
        senior.do({"tool": "assign", "path": "rules.py", "task": "fill in draw(): take the top card" + DETAIL,
                   "kind": "write"})
        self.wait(p)
        first = json.dumps(junior.chat.sent[0])
        self.assertNotIn("an earlier task", first)  # a fresh start: only this task's instruction
        self.assertEqual(junior.history, [])  # and dumped after
        back = senior.do({"tool": "review_task", "n": 2, "accept": False, "note": "the stub is still there"})
        self.assertIn("its one correction attempt", back)
        self.wait(p)
        theirs = senior.do({"tool": "review_task", "n": 3, "accept": False, "note": "still the stub"})
        self.assertIn("the corrections to rules.py are yours now", theirs)
        self.assertEqual(p.out, 0)  # nothing went back to the junior
        self.assertIn("had its correction attempt on rules.py", senior.do(
            {"tool": "assign", "path": "rules.py", "task": "fix draw(): it still returns the stub" + DETAIL,
             "kind": "fix"}))
        self.assertIn("logged as change", senior.do(
            {"tool": "edit", "path": "rules.py", "old": "    # TODO\n    pass\n", "new": "    return deck[0]\n"}))

    def test_the_senior_plans_with_its_juniors_measured_load(self):
        """Ian, 2026-10-16: "We can make that work as a task protocol and limiter for Sr. Now it knows what Jr can
        handle." The 35B on the 1080 Ti: 1,510 lines and 93 steps a task, a 2,902-line project held."""
        from unittest import mock
        senior, junior, p = self.pair()
        self.assertIn("isn't measured on this card yet", senior.system())
        held = {"lines": 1510, "steps": 93, "capacity": 2902, "measured": True}
        with mock.patch.object(p, "limits", return_value=held):
            self.assertIn("up to 1,510 lines of code and 93 steps a task; it kept a 2,902-line project working",
                          senior.system())
            self.assertNotIn("past what it held", senior.system())
        with mock.patch.object(p, "limits", return_value={**held, "capacity": 2}):
            self.assertIn("past what it held: give it one file at a time", senior.system())
        self.assertNotIn("Your junior", junior.system())

    def test_the_juniors_script_limit_stops_a_long_change(self):
        senior, junior, p = self.pair()
        p.current = {"rules.py"}  # its task's file
        junior.line_limit, junior.task_lines = 10, 8
        said = junior.do({"tool": "append", "path": "rules.py", "content": "x = 1\ny = 2\nz = 3\n"})
        self.assertIn("over its limit of 10", said)
        self.assertIn("logged as change", junior.do({"tool": "append", "path": "rules.py", "content": "x = 1\n"}))
        self.assertEqual(junior.task_lines, 9)

    def test_protected_by_origin_not_by_folder(self):
        """2026-10-10: the project's own assets/decks/*.json was refused as kept material, so the decks went into C++.
        What came in from outside stays as it came; the project's own files, in any folder, are its own."""
        from cin_minai.aicui import intake
        senior, _, _ = self.pair()
        intake.save(self.root, "https://cards.example/img/blue.jpg", b"JFIF", "image/jpeg", "assets/cards")
        refused = senior.do({"tool": "write", "path": "assets/cards/blue.jpg", "content": "x\n"})
        self.assertIn("is gathered material: it came in from outside", refused)
        own = senior.do({"tool": "write", "path": "assets/decks/starter.json", "content": '{"cards": []}\n'})
        self.assertIn("logged as change", own)
        self.assertEqual(intake.origins(self.root)["assets/cards/blue.jpg"]["from"], "https://cards.example/img/blue.jpg")

    def test_a_junior_never_replaces_most_of_a_file(self):
        """2026-10-10: a finished draft replaced 1,088 of 1,136 lines. The new version is kept aside; the Senior decides."""
        _, junior, p = self.pair()
        with open(os.path.join(self.root, "decks.cpp"), "w") as f:
            f.write("".join(f"// card {i}\n" for i in range(200)))
        p.current = {"decks.cpp"}
        said = junior.do({"tool": "write", "path": "decks.cpp", "content": "// short\n" * 10})
        self.assertIn("this would replace most of decks.cpp (200 lines → 10); that's your senior's call", said)
        with open(os.path.join(self.root, "decks.cpp")) as f:
            self.assertEqual(f.read().count("\n"), 200)
        self.assertTrue(os.listdir(os.path.join(self.root, ".cinminai", "drafts-stale")))

    def test_the_juniors_stuck_point_goes_up_and_stop_reaches_it(self):
        """Ian, 2026-10-10: "the jr writes, reads, writes, reads, gets stuck, sends to sr, sr reads, distills next step,
        gives to jr." Its stuck point, with its last steps, goes to the Senior; and Stop reaches it every step."""
        from cin_minai.aicui.agent import STUCK_STEPS
        senior, junior, p = self.pair(junior_steps=[step("Looking.", tool="list", path=".")
                                                    for _ in range(STUCK_STEPS)])
        senior.do({"tool": "assign", "path": "rules.py", "task": "fill in draw(): take the top card" + DETAIL, "kind": "write"})
        self.wait(p)
        ((n, kind, result),) = senior.inbox
        self.assertIn("task 2 (write rules.py) — STUCK POINT from your junior", result)
        self.assertIn("Its last steps:\n- Looking.", result)
        self.assertIn("Distill its next step: a smaller, exact task", result)
        senior.inbox.clear()
        junior.chat = Scripted([step("Looking.", tool="list", path=".") for _ in range(50)])
        senior.do({"tool": "assign", "path": "rules.py", "task": "fill in draw() again please" + DETAIL, "kind": "write"})
        p.stop_junior.set()  # Stop, while it works
        self.wait(p)
        self.assertIn("stopped by the person", senior.inbox[0][2])

    def test_distill_reads_the_sources_for_an_intent_and_compiles_by_code(self):
        """GatheredData (SPEC §23.5): fetch read it, distill extracts what the intent asked with where it stands, a
        gathered record keeps it, and compile writes the data file by code — nothing is retyped from memory."""
        from cin_minai.aicui import intake
        senior, _, _ = self.pair()
        intake.save(self.root, "https://cards.example/set", b"<html><body><table><tr><td>Stone Giant</td><td>3000"
                                                            b"</td></tr></table></body></html>", "text/html")
        solo = Agent(self.root, Scripted([({"items": [{"name": "Stone Giant", "atk": 3000, "where": "row 1"}]}, {})]),
                     "m", "auto", say=lambda s: None, ctx=32768)
        solo.chat = lambda messages, **kw: (json.dumps({"items": [{"name": "Stone Giant", "atk": 3000,
                                                                     "where": "row 1"}]}), {})
        said = solo.do({"tool": "distill", "sources": ["sources/set.html"], "intent": "each card's name and ATK",
                        "into": "data/cards.json", "format": "json"})
        self.assertIn('distilled 1 items for "each card\'s name and ATK" from sources/set.txt (1 parts) — gathered '
                      "record 1", said)
        self.assertIn("compiled into data/cards.json", said)
        with open(os.path.join(self.root, "data", "cards.json")) as f:
            self.assertEqual(json.load(f), [{"name": "Stone Giant", "atk": 3000, "where": "row 1",
                                             "source": "sources/set.txt"}])
        with open(os.path.join(self.root, ".cinminai", "gathered", "1.json")) as f:
            record = json.load(f)
        self.assertEqual((record["intent"], record["sources"][0]["from"]), ("each card's name and ATK",
                                                                          "https://cards.example/set"))
        self.assertEqual(intake.origins(self.root)["data/cards.json"]["kind"], "compiled")  # the project's own
        self.assertIn("data/cards.json: compiled from gathered record 1 (sources/set.txt) — 1 items, as distilled",
                      "\n".join(solo.compiled_check()))
        with open(os.path.join(self.root, "data", "cards.json"), "w") as f:
            f.write("[]\n")
        self.assertIn("0 items now, 1 in the record: changed since it was compiled", "\n".join(solo.compiled_check()))

    def test_a_compiled_file_is_checked_against_its_record_item_by_item(self):
        """Compile checked against the sources (SPEC §23.5): which items are missing, added or changed, field by field —
        at the goal check and right after a change to the file, so drift is seen when it's made."""
        senior, _, _ = self.pair()
        from cin_minai.aicui import intake
        intake.save(self.root, "https://cards.example/set", b"<html><body><p>Stone Giant 3000</p><p>Sea Wyrm 1800</p>"
                                                            b"</body></html>", "text/html")
        solo = Agent(self.root, Scripted([]), "m", "auto", say=lambda s: None, ctx=32768)
        solo.chat = lambda messages, **kw: (json.dumps({"items": [{"name": "Stone Giant", "atk": 3000, "where": "p1"},
                                                                    {"name": "Sea Wyrm", "atk": 1800, "where": "p2"}]}), {})
        solo.do({"tool": "distill", "sources": ["sources/set.html"], "intent": "each card's name and ATK",
                 "into": "data/cards.json"})
        changed = solo.do({"tool": "write", "path": "data/cards.json", "content": json.dumps(
            {"cards": [{"name": "Stone Giant", "atk": 2500}, {"name": "Fire Imp", "atk": 900}]})})
        self.assertIn("logged as change", changed)
        self.assertIn("data/cards.json: compiled from gathered record 1", changed)  # the check comes back at once
        for part in ("1 missing (Sea Wyrm)", "1 not in the record (Fire Imp)", "1 changed (Stone Giant (atk: 3000 → "
                     "2500))"):
            self.assertIn(part, changed)
        solo.do({"tool": "write", "path": "data/cards.json", "content": json.dumps(
            [{"name": "Sea Wyrm", "atk": 1800}, {"name": "Stone Giant", "atk": 3000}])})  # order and "where" aside
        self.assertIn("2 items, as distilled", "\n".join(solo.compiled_check()))

    def test_pictures_are_distilled_as_the_pictures_not_the_page(self):
        """Ian, 2026-10-10: reading an internet image "grabs the image instead of trying to fix a website". Format
        files: the page's own picture addresses (each beside its words), downloaded with one approval, an index of which
        is which compiled by code; an address the page doesn't hold is left out."""
        from unittest import mock
        from cin_minai.aicui import intake
        intake.save(self.root, "https://cards.example/giant", b'<html><head><meta property="og:image" content='
                    b'"https://img.example/giant-full.jpg"></head><body><img alt="Stone Giant" src="/pics/giant.jpg">'
                    b"<p>A big one.</p></body></html>", "text/html")
        with open(os.path.join(self.root, "sources", "giant.txt"), encoding="utf-8") as f:
            page = f.read()
        self.assertIn("[image: Stone Giant — https://cards.example/pics/giant.jpg]", page)  # the picture beside its words
        self.assertIn("https://img.example/giant-full.jpg", page)  # the page's main picture, listed too
        asked = []
        solo = Agent(self.root, Scripted([]), "m", "auto", say=lambda s: None, ctx=32768,
                     ask=lambda p: (asked.append(p), "y")[1])
        solo.chat = lambda messages, **kw: (json.dumps({"items": [
            {"name": "Stone Giant", "url": "https://cards.example/pics/giant.jpg", "where": "the card's picture"},
            {"name": "Sea Wyrm", "url": "https://cards.example/pics/wyrm.jpg", "where": "from memory"}]}), {})
        self.assertIn("which folder under assets/", solo.do({"tool": "distill", "sources": ["sources/giant.html"],
                                                          "intent": "each card's picture", "format": "files"}))
        with mock.patch.object(intake, "get", side_effect=lambda u: (b"JFIF" + u.encode(), "image/jpeg")):
            said = solo.do({"tool": "distill", "sources": ["sources/giant.html"], "intent": "each card's picture",
                            "into": "assets/cards", "format": "files"})
        self.assertEqual(len(asked), 1)  # one approval for the pictures
        self.assertIn("1 addresses weren't in the sources as given, left out", said)  # the made-up one
        self.assertIn("downloaded 1 of 1 into assets/cards/", said)
        self.assertIn("compiled into assets/cards/index.json", said)
        with open(os.path.join(self.root, "assets", "cards", "index.json"), encoding="utf-8") as f:
            index = json.load(f)
        self.assertEqual([(i["name"], i["file"]) for i in index], [("Stone Giant", "assets/cards/giant.jpg")])
        self.assertTrue(intake.came_in(self.root, "assets/cards/giant.jpg"))  # the picture stays as it came
        self.assertFalse(intake.came_in(self.root, "assets/cards/index.json"))  # the index is the project's own
        self.assertIn("1 items, as distilled", "\n".join(solo.compiled_check()))
        os.remove(os.path.join(self.root, "assets", "cards", "giant.jpg"))
        self.assertIn("1 files gone (assets/cards/giant.jpg)", "\n".join(solo.compiled_check()))

    def test_in_team_b_the_seniors_reading_goes_to_the_junior(self):
        """Ian, 2026-10-10: "Jr should do mostly reading and distilling, Sr should do mostly direction and organizing."
        The Senior's distill is queued for the Junior (it reads ~10x faster here); the record comes back between steps."""
        from cin_minai.aicui import intake
        senior, junior, p = self.pair()
        intake.save(self.root, "https://rules.example/rules", b"<html><body><p>Draw Phase: draw one card.</p>"
                                                              b"</body></html>", "text/html")
        junior.chat = lambda messages, **kw: (json.dumps({"items": [{"phase": "Draw", "rule": "draw one card",
                                                                       "where": "p1"}]}), {})
        said = senior.do({"tool": "distill", "sources": ["sources/rules.html"], "intent": "the rule of each phase",
                          "into": "data/rules.json", "format": "json"})
        self.assertIn("given to your junior (distill into data/rules.json, held for it)", said)
        self.wait(p)
        ((n, kind, result),) = senior.inbox
        self.assertIn("(distill, by your junior) — distilled 1 items for \"the rule of each phase\"", result)
        self.assertTrue(os.path.exists(os.path.join(self.root, "data", "rules.json")))
        self.assertNotIn("errand", {v["properties"]["tool"]["const"] for v in
                                    schema(None, senior.excluded())["properties"]["action"]["anyOf"]})
        # pictures too: the junior downloads them and writes their index, which its task holds
        from unittest import mock
        intake.save(self.root, "https://cards.example/giant", b'<html><body><img alt="Stone Giant" src="/g.jpg">'
                                                              b"</body></html>", "text/html")
        junior.chat = lambda messages, **kw: (json.dumps({"items": [{"name": "Stone Giant",
                                                                       "url": "https://cards.example/g.jpg"}]}), {})
        junior.fetch_ok = True  # the person's "always this session"
        senior.inbox.clear()
        with mock.patch.object(intake, "get", side_effect=lambda u: (b"JFIF", "image/jpeg")):
            said = senior.do({"tool": "distill", "sources": ["sources/giant.html"], "intent": "each card's picture",
                              "into": "assets/cards", "format": "files"})
            self.assertIn("held for it", said)
            self.wait(p)
        self.assertIn("compiled into assets/cards/index.json", senior.inbox[0][2])

    def test_in_team_b_the_junior_reads_what_the_senior_fetches_first(self):
        """Ian, 2026-10-10: "Jr should do first reading and hand to senior and hold notes… we want Jr waiting on Sr
        direction." The Senior's fetch keeps the page and gives it to the Junior; the Senior gets the notes, not the page."""
        from unittest import mock
        from cin_minai.aicui import intake
        senior, junior, p = self.pair()
        senior.fetch_ok = True
        senior.given("the rules: https://rules.example/rulebook")
        senior.last_thinking = "I need the rules of the Battle Phase."
        junior.chat = lambda messages, **kw: ("## sources/rulebook.txt, part 1\nBattle Phase: each monster attacks once.",
                                              {})
        with mock.patch.object(intake, "get", return_value=(b"<html><body><p>Battle Phase: each monster attacks once."
                                                             b"</p><p>Lots more.</p></body></html>", "text/html")):
            said = senior.do({"tool": "fetch", "url": "https://rules.example/rulebook"})
        self.assertIn("Your junior reads it first and keeps notes in notes/rulebook.md", said)
        self.assertNotIn("Lots more", said)  # the page goes to the junior, not into the senior's context
        self.assertTrue(senior.progressed({"tool": "fetch"}, said))  # a new source
        self.wait(p)
        ((n, kind, result),) = senior.inbox
        self.assertIn("(distill, by your junior)", result)
        with open(os.path.join(self.root, "notes", "rulebook.md"), encoding="utf-8") as f:
            self.assertIn("Battle Phase: each monster attacks once.", f.read())
        with open(os.path.join(self.root, ".cinminai", "gathered", "1.json"), encoding="utf-8") as f:
            self.assertIn("I need the rules of the Battle Phase.", json.load(f)["intent"])  # read for what it was after

    def test_a_new_project_starts_with_the_plan_and_its_needs_come_first(self):
        """Ian, 2026-10-10 (test6): the Senior "didnt search, didnt use the junior, and didnt really make a plan" — it laid
        a skeleton and typed the card data from memory. The plan is a tool: the request as goals, each with what it
        needs from outside, its files and who does it; the person sees it once; a goal's files wait for its needs."""
        from unittest import mock
        from cin_minai.aicui import intake
        senior, junior, p = self.pair()
        senior.goals.remove(1)  # a new project: no goals yet
        shown = []
        senior.ask = lambda prompt: (shown.append(prompt), "y")[1]
        self.assertIn("a new project starts with its plan",
                      senior.do({"tool": "write", "path": "engine.py", "content": "x = 1\n"}))
        self.assertIn("1 parts", senior.do({"tool": "list", "path": "."}) + " 1 parts")  # looking around is fine
        said = senior.do({"tool": "plan", "goals": [
            {"text": "Get the official rules into data", "from_outside": ["the official rulebook"],
             "files": ["data/rules.json"], "who": "senior"},
            {"text": "The card list as data", "from_outside": ["the official card list"], "files": ["data/cards.json"],
             "who": "junior"},
            {"text": "The engine's skeleton", "from_outside": [], "files": ["engine.py"], "who": "senior"}]})
        self.assertIn("the plan is in: goals 1–3", said)
        self.assertIn("2. [your assistant] The card list as data\n       from outside: the official card list (text)",
                      shown[0])
        goals = senior.goals.load()
        self.assertEqual([(g["who"], g["from_outside"], g["files"]) for g in goals],
                         [("senior", [{"what": "the official rulebook", "kind": "text"}], ["data/rules.json"]),
                          ("junior", [{"what": "the official card list", "kind": "text"}], ["data/cards.json"]),
                          ("senior", [], ["engine.py"])])
        self.assertEqual({(g["by"], g.get("via")) for g in goals}, {("user", "plan")})  # approved: the person's goals
        blocked =senior.do({"tool": "write", "path": "data/rules.json", "content": "[]\n"})
        self.assertIn("belongs to goal 1", blocked)
        self.assertIn("takes from outside the official rulebook (text) — still missing: the official rulebook (text)", blocked)
        self.assertIn("logged as change", senior.do({"tool": "write", "path": "engine.py", "content": "x = 1\n"}))
        self.assertIn("NOT ticked — what it takes from outside isn't in yet", senior.do({"tool": "goal_done", "id": 1}))
        self.assertFalse(p.out)  # nothing for the junior yet: its goal waits for its card list

        def jchat(messages, **kw):  # the junior: notes when it reads first, steps when it works its goal
            if messages[0]["content"].startswith("You distill"):
                return "## part 1\nStone Giant 3000", {}
            return json.dumps(next(steps)), {}
        steps = iter([step("Write the card list.", tool="write", path="data/cards.json",
                           content='[{"name": "Stone Giant", "atk": 3000}]\n'),
                      step("", tool="answer", text="data/cards.json from the card list; checked it loads")])
        junior.chat = jchat
        senior.fetch_ok = True
        senior.given("https://rules.example/rulebook https://cards.example/list")
        with mock.patch.object(intake, "get", return_value=(b"<html><body><p>Stone Giant 3000</p></body></html>",
                                                             "text/html")):
            senior.do({"tool": "fetch", "url": "https://rules.example/rulebook", "goal": 1})
            senior.do({"tool": "fetch", "url": "https://cards.example/list", "goal": 2})
        self.assertIn("logged as change", senior.do({"tool": "write", "path": "data/rules.json", "content": "[]\n"}))
        p.release_goals()  # between the senior's steps: goal 2's need is in, so it goes to the junior
        self.assertTrue(senior.goals.load()[1].get("queued"))
        self.assertIn("held by your junior", senior.do({"tool": "write", "path": "data/cards.json", "content": "[]\n"}))
        self.wait(p)
        results = [r for _, _, r in senior.inbox]
        self.assertIn('for: The card list as data', results[1])  # read for the goal it was fetched for
        self.assertTrue(any("(goal data/cards.json) — done" in r for r in results), results)
        with open(os.path.join(self.root, "data", "cards.json")) as f:
            self.assertIn("Stone Giant", f.read())

    def test_the_seniors_tool_list_names_the_plan_and_a_refusal_twice_is_stuck(self):
        """2026-10-10 (test7): the Senior planned in its thinking but its tool list said goal_add and "write them as
        goals"; the gate refused goal_add fifteen times, the same step each time."""
        senior, junior, p = self.pair()
        senior.goals.remove(1)
        text = senior.system()
        self.assertIn("- plan (a new project's goals, made once", text)
        self.assertIn("never the project's own work", text)
        self.assertIn("A new project starts with\nits plan (plan)", text)
        self.assertNotIn("write them as goals", text)
        solo = Agent(self.root, Scripted([]), "m", "auto", say=lambda s: None)
        self.assertIn("write them as goals", solo.system())  # solo and style A are as they were
        self.assertNotIn("- plan (", solo.system())
        senior.chat = Scripted([step("Add the goals.", tool="goal_add", text="Research the rules"),
                                step("Add the goals.", tool="goal_add", text="Research the rules"),
                                step("never reached", tool="list", path=".")])
        said = senior.turn("make a game")
        self.assertIn("I tried the same step twice and it was refused the same way", said)
        self.assertEqual(senior.stopped, "stuck")
        self.assertEqual(len(senior.chat.steps), 1)  # it stopped after the second refusal

    def test_kept_files_say_what_they_hold_and_needs_are_met_by_their_kind(self):
        """Ian, 2026-10-10 (test8): "classifiers for both of those files that allow the model to know what to pick from
        which file, html or txt. It shouldnt count txt as images for a goal." One card-list page (its .txt and .html)
        met both "the card lists" and "the card images"."""
        from unittest import mock
        from cin_minai.aicui import intake
        senior, junior, p = self.pair()
        senior.goals.remove(1)
        senior.ask = lambda prompt: "y"
        senior.fetch_ok = True
        senior.first_reader = None  # this test reads the kinds, not the junior's notes
        senior.do({"tool": "plan", "goals": [{"text": "The cards, as data and pictures", "who": "senior",
                                              "files": ["data/cards.json"], "from_outside": [
                                                  {"what": "the card list", "kind": "text"},
                                                  {"what": "the card pictures", "kind": "pictures"}]}]})
        senior.given("https://cards.example/list https://img.example/a.jpg https://img.example/b.jpg "
                     "https://rules.example/rules.pdf")
        with mock.patch.object(intake, "get", return_value=(b"<html><body><p>Stone Giant</p></body></html>",
                                                             "text/html")):
            said = senior.do({"tool": "fetch", "url": "https://cards.example/list", "goal": 1})
        self.assertIn("sources/list.txt (page text: read and distill this)", said)
        self.assertIn("sources/list.html (page markup: for a script, not for reading)", said)
        self.assertIn("still missing: the card pictures (pictures)",
                      senior.do({"tool": "write", "path": "data/cards.json", "content": "[]\n"}))  # a page isn't pictures
        with mock.patch.object(intake, "get", side_effect=lambda u: (b"JFIF", "image/jpeg")):
            senior.do({"tool": "download", "urls": ["https://img.example/a.jpg", "https://img.example/b.jpg"],
                       "folder": "cards", "goal": 1})
        self.assertIn("logged as change", senior.do({"tool": "write", "path": "data/cards.json", "content": "[]\n"}))
        self.assertIn("  sources/list.txt", senior.system())
        self.assertIn("[page text]", senior.system())  # the file list says what kept files hold
        with mock.patch.object(intake, "get", return_value=(b"%PDF-1.4", "application/pdf")), \
                mock.patch.object(intake, "pdf_text", return_value="Draw Phase: draw one card."):
            pdf = senior.do({"tool": "fetch", "url": "https://rules.example/rules.pdf"})
        self.assertIn("assets/rules.pdf (document)", pdf)
        self.assertIn("sources/rules.txt (document text: read and distill this)", pdf)
        self.assertEqual(intake.holds(self.root, "assets/cards/a.jpg"), "picture")

    def test_the_senior_checks_on_a_long_junior_task_and_can_direct_it(self):
        """Ian, 2026-10-10: "after completing a few of its tasks it can check on Jr's progress if none has been shown
        yet. If there is progress and its just taking awhile Sr will wait. If Jr is stuck, Sr will provide further
        direction, hopefully correcting any previous mistakes." """
        from cin_minai.aicui import pair as P
        senior, junior, p = self.pair()
        p.running = {"n": 4, "what": "goal src/engine/Battle.cpp", "since": 0, "log0": 0, "kinds": 0}
        junior.steps = [{"did": {"thinking": "Read the battle rules.", "action": {"tool": "read"}}, "result": "..."}]
        junior.kinds_done = []
        senior.progress_total = P.FOLLOW_UP - 1
        p.check_in()
        self.assertEqual(senior.inbox, [])  # too soon: the senior hasn't moved on enough yet
        senior.progress_total = P.FOLLOW_UP
        p.check_in()
        ((n, kind, report),) = senior.inbox
        self.assertEqual((n, kind), (4, "progress"))
        self.assertIn("1 steps so far, progress 0 times", report)
        self.assertIn("No progress since the last word. If it's stuck or going the wrong way, direct it with follow_up "
                      "(4, note)", report)
        senior.inbox.clear()
        junior.kinds_done = ["write"]
        senior.progress_total = 2 * P.FOLLOW_UP
        p.check_in()
        self.assertIn("It's moving since the last word: let it work.", senior.inbox[0][2])
        said = senior.do({"tool": "follow_up", "n": 4, "note": "Use the damage table in notes/rules.md, not memory."})
        self.assertIn("it reads it at its next step on task 4", said)
        steps = []
        junior.deliver(steps)
        self.assertIn("Your senior's direction on task 4:\nUse the damage table in notes/rules.md", steps[-1]["note"])
        self.assertIn("isn't with your junior", senior.do({"tool": "follow_up", "n": 9, "note": "Do it differently."}))
        self.assertIn("follow_up (`n`,", senior.system())

    def test_large_file_distillation_meets_in_the_middle_then_the_senior_plans_fresh(self):
        """Ian, 2026-10-10: LFD — "The Sr picks the smallest file in the project by size and puts the Jr on summarizing
        it. It goes to the largest file in the project and does the same. They both write to a common summary… meet in
        the middle… It must dump its context in between… so it can process the summarized information into a plan." """
        from cin_minai.aicui import lfd
        senior, junior, p = self.pair()
        sizes = {"a.py": 10, "b.py": 200, "c.py": 3000, "d.py": 9000}
        for rel, n in sizes.items():
            with open(os.path.join(self.root, rel), "w") as f:
                f.write("#" * n + "\n")
        os.makedirs(os.path.join(self.root, "sources"))
        with open(os.path.join(self.root, "sources", "page.txt"), "w") as f:
            f.write("fetched, not the codebase\n")
        self.assertEqual([r for r, _ in lfd.project_files(self.root)], ["a.py", "rules.py", "b.py", "c.py", "d.py"])
        steps = iter([step("Take the project in.", tool="lfd", focus="what's left for each goal"),
                      step("Plan from the summary.", tool="plan", goals=[
                          {"text": "Finish the rules from the summary", "from_outside": [], "files": ["rules.py"],
                           "who": "senior"}]),
                      step("", tool="answer", text="planned")])
        sent = []

        def senior_chat(messages, **kw):
            if messages[0]["content"].startswith("You summarize"):
                return "SENIOR read " + messages[0]["content"].split("This is ")[1].split(".")[0], {}
            sent.append(messages)
            return json.dumps(next(steps)), {}
        senior.chat = senior_chat
        junior.chat = lambda messages, **kw: (
            "JUNIOR read " + messages[0]["content"].split("This is ")[1].split(".")[0], {})
        senior.ask = lambda prompt: "y"
        for g in senior.goals.load():
            senior.goals.remove(g["id"])
        senior.goals.add("an old open goal", by="ai")
        mine = senior.goals.add("The person's own goal", by="user", via="plan")
        senior.turn("pick the project up")
        with open(os.path.join(self.root, "notes", "project-summary.md")) as f:
            summary = f.read()
        self.assertIn("For: what's left for each goal", summary)
        self.assertIn("## a.py (11 bytes, by the junior)", summary)  # the junior took the small end
        self.assertIn("## d.py (9,001 bytes, by the senior)", summary)  # the senior the large one
        self.assertLess(summary.index("## a.py"), summary.index("## d.py"))  # in size order
        planning = " ".join(m["content"] for m in sent[1])
        self.assertIn("Large File Distillation is done: 5 files", planning)
        self.assertIn("your context is fresh", planning)
        self.assertNotIn("Take the project in.", planning)  # the dumped steps are gone
        # the AI's own open goal gave way; the person's stays as it was (Ian, 2026-10-14: test14's replan rewrote the
        # person's goals as "(complete) — Mark complete"), and the new plan's goals are the AI's
        self.assertEqual([(g["text"], g["by"]) for g in senior.goals.load()],
                         [("The person's own goal", "user"), ("Finish the rules from the summary", "ai")])
        self.assertEqual(senior.goals.load()[0]["id"], mine["id"])
        self.assertIn("(the person's)", senior.system())

    def test_the_lead_waits_for_its_junior_instead_of_asking_the_person(self):
        """Ian, 2026-10-14 (test18): the cloud lead asked the person "What is the current status of task 1? Has the
        junior finished?" — 48 seconds before the junior answered. wait costs no call; a question waits for the
        junior's next result; with tasks out the nudge says wait, not ask."""
        import threading
        senior, junior, p = self.pair()
        self.assertIn("nothing to wait for", senior.do({"tool": "wait"}))
        out = {"n": 1}
        senior.errands_pending = lambda: out["n"] > 0
        senior.inbox = []

        def back():  # the junior's task comes back a moment later
            time.sleep(0.5)
            senior.inbox.append((1, "task", "index.html written and checked"))
            out["n"] = 0
        threading.Thread(target=back).start()
        self.assertTrue(senior.do({"tool": "wait"}).startswith("back"))
        self.assertTrue(senior.progressed({"tool": "wait"}, "back: your junior's result is in your notes"))
        self.assertNotIn("wait", senior.excluded())
        self.assertIn("wait", junior.excluded())  # the junior has nothing to wait for

        # a question with a task out: the junior's result first, then the lead decides again
        out["n"], senior.inbox = 1, []
        threading.Thread(target=back).start()
        senior.chat = Scripted([step("Is the junior done?", tool="ask", question="Has the junior finished task 1?"),
                                step("It's back; nothing to ask.", tool="answer", text="index.html is done")])
        senior.ask = lambda prompt: self.fail("the person was asked: " + prompt)
        said = senior.turn("make the page")
        self.assertEqual(said, "index.html is done")
        self.assertIn("Task 1 is back from your junior", json.dumps(senior.chat.sent[-1]))

    def test_the_ai_ticks_the_persons_goals_but_never_erases_them(self):
        senior, junior, p = self.pair()
        g = senior.goals.add("Make the duel playable", by="user")
        own = senior.goals.add("A helper module", by="ai")
        self.assertFalse(senior.goals.remove(g["id"], by="ai"))
        self.assertTrue(senior.goals.remove(own["id"], by="ai"))  # its own: a different course is the AI's choice
        self.assertIn(g["id"], [x["id"] for x in senior.goals.load()])
        self.assertTrue(senior.goals.remove(g["id"]))  # the person removes anything

    def test_a_brief_has_the_junior_read_files_and_answer_between_steps(self):
        """Ian, 2026-10-10 (test9): "Have your assistant scan each file and summarize to you" — the Senior read fifteen
        files itself at ~20 tokens a second (one of them five minutes); a junior's brief counts as progress."""
        senior, junior, p = self.pair()
        junior.chat = lambda messages, **kw: ("draw() is a stub marked TODO", {})
        said = senior.do({"tool": "brief", "files": ["rules.py", "nope.py"], "question": "what is left to do here?"})
        self.assertIn("given to your junior (brief: rules.py", said)
        self.assertIn("not files here: nope.py", said)
        self.wait(p)
        steps = []
        self.assertTrue(senior.deliver(steps))  # a brief arriving is progress
        self.assertIn("(brief, by your junior) — what is left to do here?\n## rules.py\ndraw() is a stub marked TODO",
                      steps[-1]["note"])

    def test_the_juniors_question_goes_to_the_person_and_the_senior_first_answer_wins(self):
        """Ian, 2026-10-10: "If jr asks both user and sr can click yes or no." (That day the senior's progress line wiped
        the junior's question off the screen and both waited.)"""
        import threading
        from cin_minai.aicui import agent as A
        senior, junior, p = self.pair()
        junior.mode = senior.mode = "ask"
        junior.refresh = senior.refresh = lambda: None
        p.terminal = lambda prompt, q: (q["event"].wait(5), q["answer"])[1]  # the person doesn't answer: the senior does
        got = {}
        t = threading.Thread(target=lambda: got.setdefault("ok", junior.allowed(
            "edit", "- old\n+ new", "src/engine/Game.cpp")))
        t.start()
        for _ in range(100):
            if senior.inbox:
                break
            time.sleep(0.02)
        ((n, kind, text),) = senior.inbox
        self.assertEqual(kind, "question")
        self.assertIn("edit src/engine/Game.cpp", text)
        self.assertIn("+ new", text)  # the senior sees the change it's asked about
        steps = []
        senior.deliver(steps)
        self.assertIn(f"Your junior asks (question {n}): may it edit src/engine/Game.cpp", steps[-1]["note"])
        self.assertIn("told your junior: yes", senior.do({"tool": "permit", "n": n, "allow": True}))
        t.join(5)
        self.assertTrue(got["ok"])
        self.assertIn("answered already (yes, by the senior)", senior.do({"tool": "permit", "n": n, "allow": False}))
        p.terminal = lambda prompt, q: "n"  # the person answers first
        self.assertFalse(junior.allowed("run", "$ rm -rf build", "rm -rf build"))
        self.assertIn("answered already (no, by the person)", senior.do({"tool": "permit", "n": n + 1, "allow": True}))
        seen = []
        asker = Agent(self.root, Scripted([]), "m", "ask", say=lambda s: None,
                      ask=lambda prompt: (seen.append(A.PENDING["prompt"]), "y")[1])
        asker.refresh = lambda: None
        asker.allowed("edit", "+ x", "app.py")
        self.assertIn("Allow edit app.py?", seen[0])  # the question is on screen while it waits, saying what for
        self.assertEqual(A.PENDING["prompt"], "")

    def test_the_team_is_chosen_per_project(self):
        from cin_minai.aicui import pair as P
        self.assertEqual(P.team_of(self.root), "A")  # nothing chosen: team A
        os.makedirs(os.path.join(self.root, ".cinminai"), exist_ok=True)
        with open(os.path.join(self.root, ".cinminai", "team.json"), "w") as f:
            json.dump({"team": "B"}, f)
        self.assertEqual(P.team_of(self.root), "B")
        with open(os.path.join(self.root, ".cinminai", "team.json"), "w") as f:
            json.dump({"team": "solo"}, f)
        self.assertEqual(P.team_of(self.root), "solo")  # one local model, after a team
        with open(os.path.join(self.root, ".cinminai", "team.json"), "w") as f:
            json.dump({"team": "Z"}, f)
        self.assertEqual(P.team_of(self.root), "A")  # anything else: team A

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
                step("The junior fills it.", tool="assign", path="battle.py", task="fill in battle(): higher ATK wins" + DETAIL,
                     kind="write"),
                step("Meanwhile, the deck.", tool="write", path="deck.py", content="DECK = []\n"),
                step("", tool="answer", text="Waiting."),
                step("", tool="review_task", n=3, accept=True, note=""),
                step("", tool="answer", text="Skeleton laid."),  # goal 1 is open: sent back once
                step("", tool="answer", text="Skeleton laid; battle filled by the junior and accepted.")],
            junior_steps=[
                step("Fill it.", tool="edit", path="battle.py", old="    # TODO\n    pass\n",
                     new="    return a if a >= b else b\n"),
                step("", tool="answer", text="battle() returns the higher ATK.")])
        p.root = None  # turn makes its own request
        out = p.turn("Build the battle step")
        self.assertEqual(out, "Skeleton laid; battle filled by the junior and accepted.")
        sent = "\n".join(m[-1]["content"] for m in senior.chat.sent)
        self.assertIn("Task 3 is back from your junior", sent)
        self.assertIn("Goals are still open: 1. A match follows the rules", sent)
        with open(os.path.join(self.root, "battle.py")) as f:
            self.assertIn("return a if a >= b else b", f.read())
        events = [json.loads(line) for line in open(os.path.join(self.root, ".cinminai", "events.jsonl"))]
        self.assertIn(("senior", "junior"), [(e.get("by"), e.get("to")) for e in events if e["kind"] == "handoff"])
        self.assertTrue(any(e.get("who") == "junior" for e in events))  # the Junior's work shows as its own


@unittest.skipUnless(shutil.which("git"), "the changelog needs git")
class CrewTest(unittest.TestCase):
    """Ian, 2026-10-12: the cloud leads; the local models are its contributors with set functions, one or two."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, True)
        with open(os.path.join(self.root, "rules.py"), "w") as f:
            f.write("def draw(deck):NLNL    passNL".replace("NL", chr(10)).replace(chr(10) + chr(10), chr(10)))

    def test_the_cloud_lead_directs_two_local_contributors(self):
        from cin_minai.aicui.pair import Crew
        lead = Agent(self.root, Scripted([]), "Claude Haiku 4.5 (cloud)", "auto", say=lambda s: None, ctx=200000)
        coder = Agent(self.root, Scripted([
            step("Fill it.", tool="edit", path="rules.py", old="pass", new="return deck.pop(0)"),
            step("", tool="answer", text="draw() takes the top card."),
            step("Run it.", tool="run", command="python3 -c 'import rules'"),
            step("", tool="answer", text="It imports; nothing fails.")]), "Qwen3.6-35B-A3B", "auto",
            say=lambda s: None, ctx=32768)
        reader = Agent(self.root, Scripted([("draw() returns nothing yet.", {})]), "Qwen3.5-9B", "auto",
                       say=lambda s: None, ctx=32768)
        lead.goals.add("Cards are drawn", by="user")
        crew = Crew(lead, coder, reader, engine=engine.Engine("test0003", self.root,
                                                          db_path=os.path.join(self.root, ".table.db")))
        lead.cloud_crew = "Two contributors: Qwen3.6-35B-A3B writes, fixes, checks and tests; Qwen3.5-9B reads."
        self.assertIn("You lead from the cloud", lead.system())
        self.assertIn("Two contributors", lead.system())
        self.assertEqual((coder.role, reader.role, lead.role), ("junior", "junior", "senior"))
        self.assertIn("web_search", coder.excluded())  # team B's junior: no web
        coder.web = reader.web = True  # a cloud lead's contributors: "Fetch this, write that" (Ian)
        self.assertNotIn("web_search", reader.excluded())
        self.assertNotIn("fetch", reader.excluded())
        self.assertIn("web_search (a `query`", reader.system())
        self.assertIn("task 2 given to your junior (write rules.py)", lead.do(
            {"tool": "assign", "path": "rules.py", "task": "fill draw so it takes the top card" + DETAIL, "kind": "write"}))
        self.assertIn("task 3 given to your junior", lead.do(
            {"tool": "brief", "files": ["rules.py"], "question": "what does draw do now"}))
        for _ in range(200):
            if crew.out == 0:
                break
            time.sleep(0.05)
        self.assertEqual(crew.out, 0)
        with open(os.path.join(self.root, "rules.py")) as f:
            self.assertIn("return deck.pop(0)", f.read())  # the coder wrote it
        got = {n: text for n, kind, text in lead.inbox}
        self.assertIn("draw() returns nothing yet.", got[3])  # the reader briefed
        self.assertIs(crew.holder(2), crew.coder)
        self.assertIs(crew.holder(3), crew.reader)
        self.assertIn("task 2 accepted", lead.do({"tool": "review_task", "n": 2, "accept": True, "note": ""}))
        # test: run and report, nothing held, nothing changed
        self.assertIn("task 4 given to your junior", lead.do(
            {"tool": "assign", "path": "rules.py", "task": "run it and say what fails", "kind": "test"}))
        self.assertEqual(crew.coder.held, {})
        for _ in range(200):
            if crew.out == 0:
                break
            time.sleep(0.05)
        self.assertIn("It imports; nothing fails.", {n: t for n, k, t in lead.inbox}[4])


if __name__ == "__main__":
    unittest.main()
