# SPDX-License-Identifier: GPL-3.0-or-later
"""An outside agent's seat (src/cin_minai/aicui/seatmcp.py): MCP over stdio as Claude Code speaks it — initialize, the
tool list, the table, its task, the files its task holds (and only those), finishing, talking — against a table AICUI
has seated.

    python3 -m unittest tests.unit.test_aicui_seatmcp -v        (from the repo root)
"""

import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(ROOT, "third_party", "team-table", "src"))  # the pinned submodule

from test_aicui_agent import Scripted  # noqa: E402

from cin_minai import engine  # noqa: E402
from cin_minai.aicui import conference, seatmcp  # noqa: E402
from cin_minai.aicui.agent import Agent  # noqa: E402

SETUP = {"seats": [
    {"name": "Haiku", "kind": "cloud", "provider": "anthropic", "model": "claude-haiku-4-5-20251001", "lead": True},
    {"name": "Claude", "kind": "outside", "agent": "Claude Code"}]}
DETAIL = (" — signature unchanged, no new imports; return the value the docstring names; keep the TODO "
          "markers out; check it with python3 -m py_compile and the project's tests before you answer")


@unittest.skipUnless(shutil.which("git"), "the changelog needs git")
class SeatServer(unittest.TestCase):
    def setUp(self):
        from team_table.db import Database
        Database.reset_rate_limits()
        self.root = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, True)
        with open(os.path.join(self.root, "rules.py"), "w") as f:
            f.write("def draw(deck):\n    # TODO\n    pass\n")
        with open(os.path.join(self.root, "other.py"), "w") as f:
            f.write("x = 1\n")
        conference.save(self.root, SETUP)
        db = os.path.join(self.root, ".table.db")
        self.engine = engine.Engine("test0006", self.root, db_path=db)
        self.addCleanup(self.engine.db.close)
        self.lead = Agent(self.root, Scripted([]), "Claude Haiku 4.5 (cloud)", "auto", say=lambda s: None, ctx=200000)
        self.table = conference.Table(self.lead, {}, SETUP, say=lambda s: None, engine=self.engine)
        # the seat server opens the same table (in its own process, as Claude Code starts it)
        with mock.patch("cin_minai.engine.table_path", return_value=db), \
                mock.patch("cin_minai.aicui.pair.project_of", return_value="test0006"):
            self.seat = seatmcp.Seat(self.root, "claude")

    def rpc(self, *msgs):
        out = io.StringIO()
        seatmcp.serve(self.seat, io.StringIO("".join(json.dumps(m) + "\n" for m in msgs)), out)
        return [json.loads(line) for line in out.getvalue().splitlines()]

    def call(self, name, **args):
        (r,) = self.rpc({"jsonrpc": "2.0", "id": 9, "method": "tools/call", "params": {"name": name, "arguments": args}})
        return json.loads(r["result"]["content"][0]["text"]), r["result"]["isError"]

    def test_claude_code_sits_down_and_does_its_task(self):
        init, listed = self.rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                                 "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                                            "clientInfo": {"name": "claude-code", "version": "2"}}},
                                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                                {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        self.assertEqual(init["result"]["protocolVersion"], "2025-06-18")
        self.assertIn("Call table_info first", init["result"]["instructions"])
        self.assertIn("next_task", {t["name"] for t in listed["result"]["tools"]})
        info, _ = self.call("table_info")
        self.assertEqual((info["you"], info["lead"], info["seated"]), ("claude", "Haiku", True))
        self.assertEqual(self.call("next_task")[0]["task"], None)  # nothing yet
        given = self.lead.do({"tool": "assign", "path": "rules.py", "task": "fill draw so it takes the top card"
                                                                            + DETAIL, "kind": "write", "to": "Claude"})
        n = int(given.split()[1])
        task, _ = self.call("next_task")
        self.assertEqual((task["id"], task["you_may_change"]), (n, ["rules.py"]))
        self.assertIn("fill draw so it takes the top card", task["instruction"])
        read, _ = self.call("read_file", path="rules.py")
        self.assertIn("    1 def draw(deck):", read["text"])
        refused, failed = self.call("write_file", path="other.py", content="x = 2\n")
        self.assertTrue(failed)
        self.assertIn("isn't part of your task", refused["error"])
        self.assertTrue(self.call("read_file", path="../etc/passwd")[1])  # outside the project: refused
        self.assertTrue(self.call("read_file", path=".cinminai/table.json")[1])  # AICUI's own: refused
        done, failed = self.call("edit_file", path="rules.py", old="    # TODO\n    pass\n", new="    return deck.pop(0)\n")
        self.assertFalse(failed, done)
        self.assertEqual(self.lead.log.entries()[-1]["model"], "claude (outside agent)")  # in the changelog, with undo
        self.assertEqual(self.call("finish_task", id=n, verdict="done", result="draw() pops the top card; read back")[0],
                         {"finished": n})
        self.lead.each_step()
        back = [t for k, kind, t in self.lead.inbox if kind == "task"]
        self.assertIn("by Claude. It said: draw() pops the top card", back[0])

    def test_it_talks_at_the_table_one_speaker_at_a_time(self):
        self.assertFalse(self.call("say", text="Shall I take the shuffle too?")[1])  # a free floor: it speaks
        self.assertEqual(self.engine.db.floor(self.table.channel)["holder"], self.seat.member)
        self.lead.each_step()
        talk = [t for k, kind, t in self.lead.inbox if kind == "talk"]
        self.assertIn("claude: Shall I take the shuffle too?", talk[0])
        said, _ = self.call("conversation")
        self.assertEqual(said["said"][0]["who"], "claude")


if __name__ == "__main__":
    unittest.main()
