# SPDX-License-Identifier: GPL-3.0-or-later
"""Turn tokens on the computer (SPEC §22.4): every request is a task on the daemon's Team Table; a request that comes
while the assistant is answering waits its turn, the person's first."""

import json
import os
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "third_party", "team-table", "src"))  # the pinned submodule

from cin_minai.daemon import turns  # noqa: E402

try:
    from cin_minai.daemon import service
except ImportError:  # no PyGObject
    service = None


class Table(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.t = turns.Turns(os.path.join(d.name, "table.db"), guide_context=8192)

    def test_a_question_is_the_persons_request_for_the_guide(self):
        tid = self.t.request("How do I install VLC?")
        task = self.t.db.list_tasks()[0]
        self.assertEqual((task["id"], task["assignee"], task["origin"], task["kind"]),
                         (tid, "guide", "person", "ask"))

    def test_a_long_question_goes_by_reference(self):
        text = "Please read this:\n" + "x" * 5000  # over the 8K guide's 5 % (1,228 characters)
        tid = self.t.request(text)
        task = self.t.db.list_tasks()[0]
        self.assertEqual(task["description"], "")
        (key,) = task["refs"]
        self.assertEqual(self.t.db.get_shared_context(key)["value"], text)
        self.assertEqual(task["id"], tid)

    def test_the_person_goes_first_and_finished_requests_close(self):
        watch = self.t.request("News watch: Linux Mint", by=turns.SCHEDULE, kind="watch")
        mine = self.t.request("What time is it?")
        self.assertEqual(self.t.next(), mine)
        self.t.finish(mine, "done", "inspect_system")
        self.assertEqual(self.t.next(), watch)
        self.t.finish(watch, "failed", "no network")
        states = {t["title"]: (t["status"], t["result"]) for t in self.t.db.list_tasks()}
        self.assertEqual(states["What time is it?"], ("done", "inspect_system"))
        self.assertEqual(states["News watch: Linux Mint"], ("blocked", "no network"))

    def test_stop_and_a_restart(self):
        a = self.t.request("one")
        self.t.start(a)
        b = self.t.request("two")
        self.t.finish(a, "cancelled")
        self.assertEqual(self.t.close_stale(), 1)  # "two" was left waiting when the daemon stopped
        status = {t["id"]: t["status"] for t in self.t.db.list_tasks()}
        self.assertEqual((status[a], status[b]), ("cancelled", "blocked"))
        self.assertEqual([r["title"] for r in self.t.recent()], ["two", "one"])

    def test_no_team_table_no_record(self):
        with mock.patch.object(turns, "Turns", side_effect=ImportError("no team_table")):
            self.assertIsNone(turns.open_table())


@unittest.skipIf(service is None, "needs PyGObject")
class Queue(unittest.TestCase):
    def daemon(self, busy: bool):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        s = types.SimpleNamespace(
            busy=busy, waiting={}, rid_task={}, next_id=0, turn_ctx=0, emitted=[], asked=[],
            turns=turns.Turns(os.path.join(d.name, "table.db")),
            backend=types.SimpleNamespace(status=lambda: types.SimpleNamespace(context=8192)))
        s.emit = lambda name, fmt, *a: s.emitted.append((name, a))
        s.ask = lambda rid, text: s.asked.append((rid, text))
        for name in ("turn_request", "turn_finished", "next_turn"):
            setattr(s, name, getattr(service.Service, name).__get__(s))
        return s

    def ask(self, s, text):
        inv = mock.Mock()
        service.Service.call(s, None, None, None, None, "Ask", service.GLib.Variant("(s)", (text,)), inv)
        return inv

    def test_a_question_while_answering_waits_instead_of_busy(self):
        s = self.daemon(busy=True)
        inv = self.ask(s, "second question")
        inv.return_dbus_error.assert_not_called()
        self.assertEqual(s.asked, [])
        (name, args), = [e for e in s.emitted if e[0] == "Action"]
        self.assertEqual(args[1:4], ("queue", "{}", "waiting"))
        self.assertEqual(json.loads(args[4])["ahead"], 1)
        # the answer ahead finishes: this one starts, and its task is the one run
        s.busy = False
        with mock.patch.object(service.GLib, "idle_add", side_effect=lambda f, *a: f(*a)):
            service.Service.turn_finished(s, 99, None, {})
        self.assertEqual(s.asked, [(1, "second question")])
        self.assertEqual(s.waiting, {})

    def test_a_question_when_free_runs_at_once_and_its_task_closes(self):
        s = self.daemon(busy=False)
        self.ask(s, "first question")
        self.assertEqual(s.asked, [(1, "first question")])
        task = s.rid_task[1]
        service.Service.turn_finished(s, 1, None, {"tool": "lookup_help"})
        done = s.turns.db.list_tasks()[0]
        self.assertEqual((done["id"], done["status"], done["result"]), (task, "done", "lookup_help"))


if __name__ == "__main__":
    unittest.main()
