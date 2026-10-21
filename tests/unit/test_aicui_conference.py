# SPDX-License-Identifier: GPL-3.0-or-later
"""The conference table (src/cin_minai/aicui/conference.py; Ian, 2026-10-21): seats of local, cloud and outside agents,
a crowned lead, goals on the paper assigned to seats, one speaker at a time at the table's conversation — on the real
Team Table, with scripted models.

    python3 -m unittest tests.unit.test_aicui_conference -v        (from the repo root)
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
from cin_minai.aicui import conference  # noqa: E402
from cin_minai.aicui.agent import Agent  # noqa: E402

DETAIL = (" — signature unchanged, no new imports; return the value the docstring names; keep the TODO "
          "markers out; check it with python3 -m py_compile and the project's tests before you answer")
SETUP = {"seats": [
    {"name": "Haiku", "kind": "cloud", "provider": "anthropic", "model": "claude-haiku-4-5-20251001", "lead": True},
    {"name": "Coder", "kind": "local", "model": "Qwen3.5-9B-Q4_K_M.gguf"},
    {"name": "Claude", "kind": "outside", "agent": "Claude Code"}]}


class Setup(unittest.TestCase):
    def test_what_stops_a_table_from_sitting_down_is_said(self):
        self.assertEqual(conference.problems(SETUP), [])
        self.assertIn("Seat 2 is empty: choose who sits there", conference.problems(conference.default()))
        two_leads = {"seats": [dict(s, lead=True) for s in SETUP["seats"][:2]]}
        self.assertIn("one seat wears the crown: the lead", conference.problems(two_leads))
        outside_lead = {"seats": [dict(SETUP["seats"][2], lead=True), dict(SETUP["seats"][1])]}
        self.assertTrue(any("the lead is a local or cloud seat" in p for p in conference.problems(outside_lead)))
        same = {"seats": [SETUP["seats"][0], dict(SETUP["seats"][1], name="haiku")]}
        self.assertIn("two seats have the same name", conference.problems(same))

    def test_saved_with_the_project(self):
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root, True)
        self.assertEqual(conference.load(root), conference.default())  # two empty seats to start
        conference.save(root, SETUP)
        self.assertEqual(conference.load(root), SETUP)

    def test_an_outside_seats_key_reaches_only_its_seat(self):
        """Over SSH (Ian: "secured through the team table encryption processes… over ssh"): the key may only start
        that seat's server for this project — no shell, no forwarding — and only AICUI's own line is removed."""
        home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, home, True)
        keys = os.path.join(home, ".ssh", "authorized_keys")
        os.makedirs(os.path.dirname(keys))
        with open(keys, "w") as f:
            f.write("ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOwnpersonalkeypersonalkeypersonalkey ian@laptop\n")
        pub = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIClaudeCodeKeyClaudeCodeKeyClaudeCodeKey claude@devpc"
        conference.add_key("/home/x/Documents/my store", "Claude", pub, keys)
        lines = open(keys).read().splitlines()
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[1].startswith('command="/usr/bin/cinminai-seat --project \'/home/x/Documents/my store\' '
                                            '--seat claude",restrict ssh-ed25519 '), lines[1])
        self.assertEqual(oct(os.stat(keys).st_mode & 0o777), "0o600")
        with self.assertRaises(ValueError):
            conference.add_key("/home/x/p", "Claude", "not a key", keys)
        self.assertTrue(conference.remove_key("/home/x/Documents/my store", "Claude", keys))
        self.assertEqual(open(keys).read().splitlines(), lines[:1])  # the person's own key untouched
        said = conference.connect_lines({"name": "Claude"}, "/home/x/p", "you@192.0.2.10")
        self.assertEqual(said["Claude Code"], "claude mcp add team-table -- ssh -T you@192.0.2.10")
        self.assertIn('command = "ssh"', said["Codex"])


@unittest.skipUnless(shutil.which("git"), "the changelog needs git")
class Running(unittest.TestCase):
    def setUp(self):
        from team_table.db import Database
        Database.reset_rate_limits()
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, True)
        with open(os.path.join(self.root, "rules.py"), "w") as f:
            f.write("def draw(deck):\n    # TODO\n    pass\n")

    def table(self, coder_steps=()):
        lead = Agent(self.root, Scripted([]), "Claude Haiku 4.5 (cloud)", "auto", say=lambda s: None, ctx=200000)
        coder = Agent(self.root, Scripted(list(coder_steps)), "Qwen3.5-9B", "auto", say=lambda s: None, ctx=32768)
        lead.goals.add("Cards are drawn", by="user")
        self.engine = engine.Engine("test0005", self.root, db_path=os.path.join(self.root, ".table.db"))
        self.addCleanup(self.engine.db.close)
        t = conference.Table(lead, {"Coder": coder}, SETUP, say=lambda s: None, engine=self.engine)
        return lead, coder, t

    def wait(self, t):
        for _ in range(200):
            if t.out == 0:
                return
            time.sleep(0.05)
        self.fail("a seat's task never finished")

    def test_the_lead_gives_work_to_each_seat_by_name(self):
        lead, coder, t = self.table([step("Fill it.", tool="edit", path="rules.py", old="    # TODO\n    pass\n",
                                          new="    return deck.pop(0)\n"),
                                     step("", tool="answer", text="draw() takes the top card.")])
        self.assertIn("Coder (local: Qwen3.5-9B-Q4_K_M)", lead.system())
        self.assertIn("Claude (outside agent: Claude Code", lead.system())
        self.assertIn("You lead the Team Table", lead.system())
        given = lead.do({"tool": "assign", "path": "rules.py", "task": "fill draw so it takes the top card" + DETAIL,
                         "kind": "write", "to": "coder"})
        self.assertIn("given to your junior (write rules.py)", given)
        self.wait(t)
        with open(os.path.join(self.root, "rules.py")) as f:
            self.assertIn("return deck.pop(0)", f.read())
        self.assertIn("error: there's no seat \"gemini\"", lead.do(
            {"tool": "assign", "path": "rules.py", "task": "x" * 30 + DETAIL, "kind": "write", "to": "gemini"}))

    def test_an_outside_seat_claims_its_task_on_the_table_and_its_result_comes_back(self):
        lead, coder, t = self.table()
        given = lead.do({"tool": "assign", "path": "rules.py", "task": "fill draw so it takes the top card" + DETAIL,
                         "kind": "write", "to": "Claude"})
        self.assertIn("put on the table for Claude", given)
        n = int(given.split()[1])
        claude = t.outside["Claude"]
        self.assertEqual(set(claude.held), {"rules.py"})
        self.assertIn("held by Claude's task", lead.do({"tool": "edit", "path": "rules.py", "old": "pass",
                                                        "new": "return None"}))
        mine = self.engine.claim(claude.second)  # Claude Code, through its seat server
        self.assertEqual(mine["id"], n)
        self.engine.finish(mine, claude.second, "Claude Code", "done", "draw() now pops the top card")
        lead.each_step()
        ((m, kind, text),) = [x for x in lead.inbox if x[1] == "task"]
        self.assertEqual(m, n)
        self.assertIn("by Claude. It said: draw() now pops the top card", text)
        self.assertEqual(lead.do({"tool": "review_task", "n": n, "accept": True, "note": ""}), f"task {n} accepted")

    def test_a_task_at_the_table_holds_every_file_its_work_needs(self):
        """Ian, 2026-10-21 (test21): the lead wrote "make the scene, its script, the README and run.sh", the task held
        one file, and it came back half done three times. `also` names the others, new ones included."""
        lead, coder, t = self.table([step("Both.", tool="write", path="deck.py", content="DECK = []\n"),
                                     step("", tool="edit", path="rules.py", old="    # TODO\n    pass\n",
                                          new="    return deck.pop(0)\n"),
                                     step("", tool="answer", text="deck.py made, draw() filled.")])
        given = lead.do({"tool": "assign", "path": "rules.py", "task": "fill draw and make deck.py" + DETAIL,
                         "kind": "write", "to": "Claude", "also": ["notes/plan.md", "rules.py"]})
        self.assertIn("put on the table for Claude", given)
        self.assertEqual(set(t.outside["Claude"].held), {"rules.py", "notes/plan.md"})
        self.assertIn("held by Claude's task", lead.do(
            {"tool": "assign", "path": "rules.py", "task": "x" * 30 + DETAIL, "kind": "write", "to": "coder"}))
        self.assertIn("held by Claude's task", lead.do(  # a file it also holds is held too
            {"tool": "assign", "path": "rules.py", "task": "x" * 30 + DETAIL, "kind": "write", "to": "coder",
             "also": ["notes/plan.md"]}))
        self.engine.db.cancel_task(int(given.split()[1]), t.lead_member)  # the lead stops it: its files are free
        self.assertIn("isn't a file in the project", lead.do(
            {"tool": "assign", "path": "rules.py", "task": "x" * 30 + DETAIL, "to": "coder", "also": ["../x.py"]}))
        given = lead.do({"tool": "assign", "path": "rules.py", "task": "fill draw and make deck.py" + DETAIL,
                         "kind": "write", "to": "coder", "also": ["deck.py"]})  # a local seat: both files are its
        self.assertIn("given to your junior", given)
        self.wait(t)
        with open(os.path.join(self.root, "rules.py")) as f:
            self.assertIn("return deck.pop(0)", f.read())
        with open(os.path.join(self.root, "deck.py")) as f:
            self.assertEqual(f.read(), "DECK = []\n")
        coder_pair = next(iter(t.pairs.values()))
        coder_pair.many = False  # a senior and its junior outside the table: one file per task, as before
        self.assertIn("one file per task here", coder_pair.assign("rules.py", "x" * 30 + DETAIL, also=["deck.py"]))

    def test_goals_on_the_paper_go_to_their_seat(self):
        lead, coder, t = self.table()
        g = lead.goals.add("The deck shuffles", by="user", files=["rules.py"], who="Claude")
        t.release_goals()
        (task,) = t.outside["Claude"].open_tasks()
        self.assertIn(f"goal {g['id']}: The deck shuffles", task["title"])
        self.assertTrue(next(x for x in lead.goals.load() if x["id"] == g["id"])["queued"])

    def test_one_speaker_at_a_time_and_the_lead_hears_it(self):
        lead, coder, t = self.table()
        self.assertIn("say", {a for a in ("say", "pass_floor", "request_floor")} - lead.excluded())
        self.assertNotIn("say", coder.excluded())  # a seat in AICUI talks too
        self.assertEqual(coder.do({"tool": "request_floor"}), "you have the floor: say what you need")
        self.assertEqual(coder.do({"tool": "say", "text": "Is the deck a list or a deque?"}), "said at the table")
        self.assertIn("has the floor", t.talk(t.outside["Claude"].second, "say", {"text": "me"}))
        self.assertEqual(lead.do({"tool": "say", "text": "A list."}), "said at the table")  # the lead: any time
        self.assertIn("the floor is", coder.do({"tool": "pass_floor", "to": "Claude"}))
        self.assertEqual(self.engine.db.floor(t.channel)["holder"], t.outside["Claude"].second)
        lead.each_step()
        talk = [text for n, kind, text in lead.inbox if kind == "talk"]
        self.assertIn("coder: Is the deck a list or a deque?", talk[0])
        self.assertNotIn("A list.", talk[0])  # its own words don't come back to it


if __name__ == "__main__":
    unittest.main()
