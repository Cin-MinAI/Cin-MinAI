# SPDX-License-Identifier: GPL-3.0-or-later
"""Long sessions (src/cin_minai/daemon/notebook.py, PLAN D40, SPEC §11.5.1): the transcript kept on this computer,
trimmed turns folded into notes the person is shown, recall of an earlier turn by its words, the rundown offered
after a pause and asked about once after three no's.

    python3 -m unittest tests.unit.test_notebook -v        (from the repo root)
"""

import json
import os
import shutil
import sys
import tempfile
import threading
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "distro", "packages", "cinminai-daemon"))

from cin_minai.daemon.guide import Guide  # noqa: E402
from cin_minai.daemon.helpcards import HelpIndex  # noqa: E402
from cin_minai.daemon.notebook import KEEP_DAYS, PAUSE_S, Notebook  # noqa: E402
from cin_minai.daemon.tools import Tools  # noqa: E402
from cin_minai.inference.backend import Status  # noqa: E402
import gen_data  # noqa: E402

DATA = gen_data.build(ROOT)
DAY = 86400


class Clock:
    def __init__(self, t=1_800_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


class Scripted:
    def __init__(self, replies):
        self.replies, self.sent = list(replies), []

    def status(self):
        return Status("ready", "test", "cuda", 8192)

    def chat(self, messages, *, schema=None, max_tokens=600, on_text=None, cancel=None):
        self.sent.append([dict(m) for m in messages])
        text = self.replies.pop(0)
        on_text and on_text(text)
        return text, {}


def answer(text):
    return json.dumps({"tool": "answer", "args": {"text": text}})


class NotebookTest(unittest.TestCase):
    def setUp(self):
        self.where = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.where, True)
        self.clock = Clock()

    def nb(self):
        return Notebook(self.where, self.clock)

    def test_the_transcript_is_kept_a_while(self):
        nb = self.nb()
        nb.record("Which driver for my Brother printer?", "The brlaser driver, from Driver Manager.")
        self.clock.t += (KEEP_DAYS + 2) * DAY
        nb.record("new question", "new answer")
        self.assertEqual([t["user"] for t in nb.turns()], ["new question"])  # out of the live transcript
        self.assertEqual(sorted(os.listdir(self.where)),
                         sorted(["archive.tar", "index.jsonl", os.path.basename(nb.path(
                             __import__("datetime").date.fromtimestamp(self.clock.t).isoformat() + ".jsonl"))]))
        self.assertIn("brlaser", nb.system_note("that brother printer driver again"))  # found in the archive
        self.clock.t += DAY
        nb.record("another", "day")  # archiving again doesn't add the day twice
        import tarfile
        with tarfile.open(os.path.join(self.where, "archive.tar")) as tar:
            self.assertEqual(len(tar.getnames()), 1)

    def test_never_kept_secrets_and_declined(self):
        nb = self.nb()
        nb.record("my password is hunter2 and the key sk-abcdefghijklmnopqrstu", "Noted.")
        kept = json.dumps(nb.turns())
        self.assertNotIn("hunter2", kept)
        self.assertNotIn("sk-abcdefghijklmnopqrstu", kept)
        b = Scripted([json.dumps({"tool": "decline", "args": {"text": "I can't help with that."}})])
        h = DATA["help.json"]
        g = Guide(b, DATA["guide.json"], HelpIndex(h), Tools(h["labels"], h["desktop"], "en"),
                  {"history_chars": 12000, "cpu_history_chars": 3000}, notebook=nb)
        g.turn("something declined", lambda t: None, lambda *a: None, threading.Event())
        self.assertNotIn("something declined", json.dumps(nb.turns()))

    def test_turns_fold_into_notes(self):
        nb = self.nb()
        nb.record("My printer won't print", "Let's check the driver.")
        sent = []

        def chat(messages, max_tokens=0):
            sent.append(messages[0]["content"])
            return "Here are the notes:\n- Goal: get the printer printing\n- Tried: checked the driver\n", {}
        lines = nb.fold(nb.turns(), chat)
        self.assertEqual(lines, ["Goal: get the printer printing", "Tried: checked the driver"])
        self.assertIn("My printer won't print", sent[0])
        self.assertEqual(nb.state()["folded_until"], self.clock.t)
        self.assertEqual(nb.fold(nb.turns(), lambda m, max_tokens=0: ("nothing usable", {})), lines)  # kept
        self.assertEqual(nb.remove(0), ["Tried: checked the driver"])  # the person takes a line out

    def test_the_guide_folds_trimmed_turns_and_says_so(self):
        nb = self.nb()
        b = Scripted([answer("one"), answer("two"), answer("three"), "- They asked three things", answer("four")])
        h = DATA["help.json"]
        g = Guide(b, DATA["guide.json"], HelpIndex(h), Tools(h["labels"], h["desktop"], "en"),
                  {"history_chars": 12000, "cpu_history_chars": 3000, "history_turns": 2}, notebook=nb)
        actions = []
        for q in ("first question", "second question", "third question", "fourth question"):
            self.clock.t += 60
            g.turn(q, lambda t: None, lambda *a: actions.append(a), threading.Event())
        self.assertEqual(len(nb.turns()), 4)
        kept = [a for a in actions if a[0] == "notebook"]
        self.assertEqual(json.loads(kept[0][3]), {"lines": ["They asked three things"]})
        self.assertIn("first question", b.sent[3][0]["content"])  # the fold call saw the dropped turns
        self.assertIn("- They asked three things", b.sent[4][0]["content"])  # the guide sees the notes
        g.reset()  # New conversation: the notes start fresh, the transcript stays
        self.assertEqual(nb.lines(), [])
        self.assertEqual(len(nb.turns()), 4)

    def test_recall_brings_back_an_earlier_turn(self):
        self.nb().record("Which driver for my Brother printer?", "The brlaser driver, from Driver Manager.")
        self.clock.t += 3 * DAY
        nb = self.nb()
        note = nb.system_note("that brother printer driver again")
        self.assertIn("brlaser", note)
        self.assertEqual(nb.system_note("hello there"), "")
        nb.recent = {"The brlaser driver, from Driver Manager."}  # still in view: not brought in twice
        self.assertNotIn("brlaser", nb.system_note("that brother printer driver again"))

    def test_the_rundown(self):
        self.assertFalse(self.nb().offer()["offer"])  # nothing to tell
        self.nb().record("Set up my printer", "Done: it prints.")
        self.clock.t += PAUSE_S + 60
        nb = self.nb()  # the next session
        self.assertTrue(nb.offer()["offer"])
        self.assertEqual(len(nb.earlier()), 1)
        self.assertFalse(nb.said("no")["ask_stop"])
        self.assertFalse(nb.said("no")["ask_stop"])
        self.assertTrue(nb.said("no")["ask_stop"])  # the third no in a row: asked once
        nb.said("keep")
        self.assertFalse(nb.said("no")["ask_stop"])
        self.assertFalse(nb.said("no")["ask_stop"])
        self.assertFalse(nb.said("no")["ask_stop"])  # not asked again
        nb.said("stop")
        self.assertFalse(nb.offer()["offer"])


if __name__ == "__main__":
    unittest.main()
