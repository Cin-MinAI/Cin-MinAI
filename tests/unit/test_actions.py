# SPDX-License-Identifier: GPL-3.0-or-later
"""M4 slice 1: the action path and its walls (PLAN D67, D85; SPEC §8)."""

import json
import os
import tempfile
import unittest

from cin_minai.actions.core import ActionError, Actions, Kind
from cin_minai.actions.record import Record, RecordError


def tree(root):
    """Every file under root with its bytes — to prove what changed and what didn't."""
    out = {}
    for r, _, fs in os.walk(root):
        for f in fs:
            p = os.path.join(r, f)
            with open(p, "rb") as h:
                out[os.path.relpath(p, root)] = h.read()
    return out


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.home = os.path.join(self.dir, "home")
        os.makedirs(self.home)
        self.record = Record(os.path.join(self.dir, "state", "record.jsonl"))
        self.actions = Actions(self.record, os.path.join(self.dir, "state", "undo"))
        self.calls = []

        def write(args):
            self.calls.append(args)
            with open(args["path"], "w") as f:
                f.write(args["text"])
            return len(args["text"])

        self.actions.register(Kind("write_note", "user", True, lambda a: f"write {os.path.basename(a['path'])}",
                                   write, check=lambda a, r: r == len(a["text"]), touches=lambda a: [a["path"]]))
        self.actions.register(Kind("send_mail", "user_approved", False, lambda a: "send a message",
                                   lambda a: self.calls.append(a)))
        self.actions.register(Kind("install", "admin", False, lambda a: f"install {a['pkg']}",
                                   lambda a: self.calls.append(a)))

    def note(self, name="a.txt"):
        return os.path.join(self.home, name)


class TestWalls(Base):
    def test_ask_is_the_default_and_nothing_runs_before_the_answer(self):
        before = tree(self.home)
        p = self.actions.propose("write_note", {"path": self.note(), "text": "hi"})
        self.assertEqual(p.state, "waiting")
        self.assertEqual(self.calls, [])
        self.assertEqual(tree(self.home), before)

    def test_auto_runs_reversible_actions_on_their_own(self):
        self.actions.mode = "auto"
        p = self.actions.propose("write_note", {"path": self.note(), "text": "hi"})
        self.assertEqual(p.state, "done")
        self.assertEqual([e["event"] for e in self.record.of(p.id)], ["proposed", "auto", "snapshot", "sealed", "done"])

    def test_irreversible_always_asks_even_in_auto(self):
        self.actions.mode = "auto"
        p = self.actions.propose("send_mail", {"to": "x"})
        self.assertEqual(p.state, "waiting")
        self.assertEqual(self.calls, [])

    def test_admin_always_asks_whatever_the_chooser_says(self):
        class Reckless:
            def decide(self, kind, args, mode, record):
                return "auto"
        self.actions.boundary = Reckless()
        self.actions.mode = "auto"
        p = self.actions.propose("install", {"pkg": "gimp"})
        self.assertEqual(p.state, "waiting")
        self.assertEqual(self.calls, [])

    def test_a_denied_action_changes_nothing(self):
        before = tree(self.home)
        p = self.actions.propose("write_note", {"path": self.note(), "text": "hi"})
        self.actions.answer(p.id, False)
        self.assertEqual((p.state, self.calls), ("denied", []))
        self.assertEqual(tree(self.home), before)

    def test_an_admin_action_cannot_be_declared_reversible(self):
        with self.assertRaises(ValueError):
            Kind("bad", "admin", True, lambda a: "x", lambda a: None)

    def test_unknown_actions_are_refused(self):
        with self.assertRaises(ActionError):
            self.actions.propose("format_disk", {})


class TestUndo(Base):
    def test_undo_restores_byte_for_byte_and_removes_what_was_created(self):
        with open(self.note(), "w") as f:
            f.write("original")
        before = tree(self.home)
        self.actions.mode = "auto"
        a = self.actions.propose("write_note", {"path": self.note(), "text": "changed"})
        b = self.actions.propose("write_note", {"path": self.note("new.txt"), "text": "new"})
        self.assertTrue(self.actions.undo(b.id))
        self.assertTrue(self.actions.undo(a.id))
        self.assertEqual(tree(self.home), before)

    def test_a_failed_check_is_undone_automatically(self):
        self.actions.register(Kind("bad_write", "user", True, lambda a: "write", lambda a: open(a["path"], "w").write("x"),
                                   check=lambda a, r: False, touches=lambda a: [a["path"]]))
        self.actions.mode = "auto"
        p = self.actions.propose("bad_write", {"path": self.note()})
        self.assertEqual(p.state, "failed")
        self.assertFalse(os.path.exists(self.note()))
        self.assertIn("undone", [e["event"] for e in self.record.of(p.id)])

    def test_a_kind_whose_undo_failed_asks_again(self):
        self.actions.mode = "auto"
        p = self.actions.propose("write_note", {"path": self.note(), "text": "x"})
        os.chmod(self.home, 0o500)                     # the way back is blocked
        try:
            ok = self.actions.undo(p.id)
        finally:
            os.chmod(self.home, 0o700)
        if os.geteuid() == 0:
            self.skipTest("root ignores the permission that blocks the undo")
        self.assertFalse(ok)
        q = self.actions.propose("write_note", {"path": self.note("b.txt"), "text": "y"})
        self.assertEqual(q.state, "waiting")

    def test_nothing_can_be_undone_twice_or_without_a_snapshot(self):
        self.actions.mode = "auto"
        p = self.actions.propose("write_note", {"path": self.note(), "text": "x"})
        self.actions.undo(p.id)
        with self.assertRaises(ActionError):
            self.actions.undo(p.id)
        q = self.actions.propose("send_mail", {"to": "x"})
        with self.assertRaises(ActionError):
            self.actions.undo(q.id)


class TestLaterWork(Base):
    def test_undo_refuses_when_the_file_was_changed_afterwards(self):
        from cin_minai.actions.core import Changed
        self.actions.mode = "auto"
        p = self.actions.propose("write_note", {"path": self.note(), "text": "draft"})
        with open(self.note(), "a") as f:
            f.write(" and an hour of the person's own writing")
        with self.assertRaises(Changed):
            self.actions.undo(p.id)
        with open(self.note()) as f:
            self.assertIn("hour", f.read())                    # nothing touched

    def test_created_files_are_recorded_and_undone(self):
        def make(args):
            path = os.path.join(self.home, "Report (2).odt")    # the name is only known when it's made
            with open(path, "w") as f:
                f.write("doc")
            return {"created": [path]}
        self.actions.register(Kind("make_doc", "user", True, lambda a: "make a document", make))
        p = self.actions.perform("make_doc", {})
        self.assertEqual(p.state, "done")
        self.assertTrue(self.actions.undo(p.id))
        self.assertEqual(tree(self.home), {})

    def test_private_paths_stay_out_of_the_record(self):
        def entry(args):
            path = os.path.join(self.home, "2026-10-06 — my secret title.odt")
            with open(path, "w") as f:
                f.write("x")
            return {"created": [path]}
        self.actions.register(Kind("journal_entry", "user", True, lambda a: "write a journal entry", entry,
                                   private_paths=True))
        p = self.actions.perform("journal_entry", {})
        with open(self.record.path) as f:
            self.assertNotIn("secret", f.read())
        self.assertTrue(self.actions.undo(p.id))

    def test_what_the_person_starts_runs_and_is_recorded_as_theirs(self):
        p = self.actions.perform("send_mail", {"to": "x"})
        self.assertEqual(p.state, "done")
        self.assertEqual([e.get("by") for e in self.record.of(p.id)][:2], ["person", "person"])


class TestRecord(Base):
    def test_every_step_is_recorded_in_order_and_survives_a_reload(self):
        p = self.actions.propose("write_note", {"path": self.note(), "text": "hi"})
        self.actions.answer(p.id, True)
        events = [e["event"] for e in Record(self.record.path).of(p.id)]
        self.assertEqual(events, ["proposed", "allowed", "snapshot", "sealed", "done"])

    def test_content_never_goes_into_the_record(self):
        self.actions.mode = "auto"
        self.actions.propose("write_note", {"path": self.note(), "text": "my secret diary"})
        with open(self.record.path) as f:
            self.assertNotIn("secret", f.read())

    def test_tampering_is_caught(self):
        self.actions.propose("write_note", {"path": self.note(), "text": "hi"})
        with open(self.record.path) as f:
            lines = f.readlines()
        lines[0] = lines[0].replace('"by":"assistant"', '"by":"person"')
        with open(self.record.path, "w") as f:
            f.writelines(lines)
        with self.assertRaises(RecordError):
            Record(self.record.path)

    def test_a_torn_last_line_is_set_aside(self):
        self.actions.propose("write_note", {"path": self.note(), "text": "hi"})
        with open(self.record.path, "a") as f:
            f.write('{"seq":99,"ev')
        r = Record(self.record.path)
        self.assertEqual(len(r.entries), 1)
        with open(self.record.path + ".torn") as f:
            self.assertIn('"seq":99', f.read())
        r.add("note", text="after the tear")
        self.assertEqual(r.verify(), 2)


if __name__ == "__main__":
    unittest.main()
