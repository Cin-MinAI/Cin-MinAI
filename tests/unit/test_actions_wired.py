# SPDX-License-Identifier: GPL-3.0-or-later
"""M4 slice 2: the daemon's real actions on the one path — the guide's spreadsheet waits in Ask mode, is made when
allowed, undone on Undo, and Undo refuses once the person has changed the sheet."""

import json
import os
import tempfile
import unittest
from unittest import mock

from cin_minai.actions import hook
from cin_minai.actions.core import Actions, Changed
from cin_minai.actions.record import Record


class SpreadsheetThroughThePath(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.home = os.path.join(self.dir, "home")
        os.makedirs(os.path.join(self.home, "Documents"))
        self.actions = Actions(Record(os.path.join(self.dir, "rec.jsonl")), os.path.join(self.dir, "undo"))
        hook.install(self.actions)
        self.addCleanup(hook.install, None)
        from cin_minai.daemon import tools
        self.patch = mock.patch.object(tools, "HOME", self.home)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.tools = tools.Tools.__new__(tools.Tools)
        self.tools.label = lambda key: key

    def make(self):
        return self.tools.make_spreadsheet({"title": "Expenses", "columns": ["Date", "Item", "Amount"], "rows": [],
                                            "total": "none"})

    def files(self):
        return sorted(os.listdir(os.path.join(self.home, "Documents")))

    def test_ask_mode_waits_and_changes_nothing(self):
        out = self.make()
        self.assertTrue(out.get("waiting_for_the_user"))
        self.assertEqual(self.files(), [])
        self.assertEqual(len(self.actions.open), 1)

    def test_allowed_it_is_made_and_undo_removes_it(self):
        self.make()
        (pid,) = self.actions.open
        self.actions.answer(pid, True)
        self.assertEqual(len(self.files()), 1)
        self.assertTrue(self.actions.undo(pid))
        self.assertEqual(self.files(), [])

    def test_auto_mode_makes_it_at_once_and_undo_refuses_after_the_person_edited_it(self):
        self.actions.mode = "auto"
        out = self.make()
        self.assertTrue(out["created"])
        path = os.path.join(self.home, "Documents", self.files()[0])
        with open(path, "ab") as f:
            f.write(b"the person's own edits")
        pid = [e["id"] for e in self.actions.record.entries if e["event"] == "done"][-1]
        with self.assertRaises(Changed):
            self.actions.undo(pid)
        self.assertTrue(os.path.exists(path))

    def test_the_record_names_the_action_not_the_content(self):
        self.actions.mode = "auto"
        self.make()
        with open(self.actions.record.path) as f:
            text = f.read()
        self.assertIn("a new spreadsheet in Documents", text)
        self.assertNotIn("Expenses", text)


if __name__ == "__main__":
    unittest.main()
