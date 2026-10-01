# SPDX-License-Identifier: GPL-3.0-or-later
"""The journal (src/cin_minai/daemon/journal.py, PLAN D55): the PIN, private entries (encrypted, the key from the
keyring — a fixed test key here), the conversation kept off the disk, the interviewer against a scripted model.

    python3 -m unittest tests.unit.test_journal -v        (from the repo root; encryption: Linux with gpg)
"""

import datetime as dt
import json
import os
import shutil
import sys
import tempfile
import threading
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))

from cin_minai.daemon.journal import Interviewer, Journal, JournalError  # noqa: E402

WHEN = dt.datetime(2026, 10, 1, 21, 30)
GPG = os.name == "posix" and shutil.which("gpg") is not None


def journal():
    return Journal(tempfile.mkdtemp(), key=lambda: "test-key-not-the-keyring")


class Pin(unittest.TestCase):
    def test_four_digits_and_change_needs_the_old(self):
        j = journal()
        for bad in ("123", "12345", "abcd", ""):
            with self.assertRaises(JournalError):
                j.set_pin(bad)
        j.set_pin("4321")
        self.assertTrue(j.check_pin("4321"))
        self.assertFalse(j.check_pin("1234"))
        with self.assertRaises(JournalError):
            j.set_pin("1111", old="0000")
        j.set_pin("1111", old="4321")
        self.assertTrue(j.check_pin("1111"))
        with open(j.index_path, encoding="utf-8") as f:
            self.assertNotIn("1111", f.read())  # only a salted hash is kept

    def test_private_needs_a_pin(self):
        with self.assertRaises(JournalError):
            journal().write("t", "text", WHEN, private=True)


class Entries(unittest.TestCase):
    def test_public_entry_is_a_dated_document(self):
        j = journal()
        e = j.write("A walk by the sea", "I walked by the sea today.", WHEN, private=False)
        self.assertEqual(os.path.basename(e["path"]), "2026-10-01 21.30 — A walk by the sea.odt")
        self.assertEqual(j.entries()[0]["title"], "A walk by the sea")

    @unittest.skipUnless(GPG, "needs gpg and POSIX pipes")
    def test_private_entry_is_sealed_and_opens_with_the_pin(self):
        j = journal()
        j.set_pin("2468")
        e = j.write("About Mom", "I miss my mother more than I say.", WHEN, private=True)
        self.assertTrue(e["path"].endswith(".odt.gpg"))
        with open(e["path"], "rb") as f:
            raw = f.read()
        self.assertNotIn(b"mother", raw)
        self.assertNotIn(b"About Mom", raw)
        self.assertEqual(j.entries()[0]["title"], "")  # the list doesn't show a private title
        with self.assertRaises(JournalError):
            j.read_private(e["file"], "1357")
        r = j.read_private(e["file"], "2468")
        self.assertEqual((r["title"], r["text"]), ("About Mom", "I miss my mother more than I say."))
        self.assertFalse([f for f in os.listdir(j.root) if f.endswith(".odt")])  # no plain copy left behind

    @unittest.skipUnless(GPG, "needs gpg and POSIX pipes")
    def test_two_private_entries_in_one_minute(self):
        j = journal()
        j.set_pin("2468")
        a, b = j.write("a", "one", WHEN, True), j.write("b", "two", WHEN, True)
        self.assertNotEqual(a["file"], b["file"])


class Scripted:
    def __init__(self):
        self.sent = []

    def __call__(self, messages, schema=None, max_tokens=600, on_text=None, cancel=None, sampling=None):
        self.sent.append(messages)
        if schema:
            return json.dumps({"title": "A walk by the sea", "entry": "I walked by the sea and felt calm."}), {}
        return "That sounds peaceful. What did you notice on the way?", {}


class Interview(unittest.TestCase):
    def test_conversation_stays_in_memory_and_feeds_the_entry(self):
        j, m = journal(), Scripted()
        iv = Interviewer(m)
        reply = iv.reply(j, "I walked by the sea after work, it was cold but lovely.", lambda t: None, threading.Event())
        self.assertIn("?", reply)
        self.assertIn("never give advice", m.sent[0][0]["content"].lower())
        with open(j.index_path, encoding="utf-8") if os.path.exists(j.index_path) else open(os.devnull) as f:
            self.assertNotIn("sea after work", f.read())
        title, text = iv.entry(j, WHEN)
        self.assertEqual(title, "A walk by the sea")
        prompt = m.sent[-1][-1]["content"]
        self.assertIn("\nI walked by the sea after work", prompt)
        # the companion's last question had no reply: it isn't in the prompt at all (it got answered, invented,
        # in the entry of 2026-10-01)
        self.assertNotIn("What did you notice on the way?", prompt)
        self.assertIn("Thursday, 01 October 2026, 21:30", m.sent[-1][-1]["content"])

    def test_answered_questions_in_brackets(self):
        j, m = journal(), Scripted()
        iv = Interviewer(m)
        iv.reply(j, "I walked by the sea.", lambda t: None, threading.Event())
        iv.reply(j, "I noticed the gulls.", lambda t: None, threading.Event())
        prompt = iv.entry(j, WHEN) and m.sent[-1][-1]["content"]
        self.assertIn("I walked by the sea.\n[That sounds peaceful. What did you notice on the way?]\nI noticed the gulls.",
                      prompt)

    def test_a_date_is_not_a_title(self):
        class DateTitle(Scripted):
            def __call__(self, messages, schema=None, **kw):
                if schema:
                    return json.dumps({"title": "Thursday, 01 October 2026, 00:34",
                                       "entry": "Today I finally fixed the old computer for my neighbour."}), {}
                return super().__call__(messages, schema=schema, **kw)
        j = journal()
        iv = Interviewer(DateTitle())
        iv.reply(j, "I fixed a computer.", lambda t: None, threading.Event())
        self.assertEqual(iv.entry(j, WHEN)[0], "Today I finally fixed the…")

    def test_nothing_said_nothing_written(self):
        with self.assertRaises(JournalError):
            Interviewer(Scripted()).entry(journal(), WHEN)


if __name__ == "__main__":
    unittest.main()
