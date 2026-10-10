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
        self.assertEqual(tools(junior), {"read", "list", "search", "distill", "edit", "replace_lines", "write",
                                         "append", "run",
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
        senior.do({"tool": "assign", "path": "rules.py", "task": "fill in draw(): take the top card", "kind": "write"})
        self.wait(p)
        ((n, kind, result),) = senior.inbox
        self.assertIn("task 1 (write rules.py) — STUCK POINT from your junior", result)
        self.assertIn("Its last steps:\n- Looking.", result)
        self.assertIn("Distill its next step: a smaller, exact task", result)
        senior.inbox.clear()
        junior.chat = Scripted([step("Looking.", tool="list", path=".") for _ in range(50)])
        senior.do({"tool": "assign", "path": "rules.py", "task": "fill in draw() again please", "kind": "write"})
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
        blocked = senior.do({"tool": "write", "path": "data/rules.json", "content": "[]\n"})
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
