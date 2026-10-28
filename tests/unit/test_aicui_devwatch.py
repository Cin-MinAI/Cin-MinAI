# SPDX-License-Identifier: GPL-3.0-or-later
"""Developer mode's watcher (aicui/devwatch.py): the program's output into error records."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from cin_minai.aicui import devwatch  # noqa: E402


def feed(x, text, t=0.0):
    out = []
    for line in text.splitlines():
        out += x.feed(line, t)
    return out


class Extractor(unittest.TestCase):
    def test_an_error_tk_caught_in_a_callback_is_written_down(self):
        """Test29 (2026-10-27): Save failed inside a Tk callback; Tk printed it to a terminal nobody saw."""
        x = devwatch.Extractor("/home/p/test29")
        got = feed(x, """starting
Exception in Tkinter callback
Traceback (most recent call last):
  File "/usr/lib/python3.12/tkinter/__init__.py", line 1968, in __call__
    return self.func(*args)
  File "/home/p/test29/gui/ui_deck.py", line 213, in save_deck
    with open(filename, 'w', encoding='utf-8') as f:
TypeError: open() got an unexpected keyword argument 'encoding'
after""")
        ((r, new),) = got
        self.assertTrue(new)
        self.assertEqual(r["kind"], "Tk callback: TypeError")
        self.assertEqual(r["where"], "gui/ui_deck.py:213")  # the project's frame, not tkinter's
        self.assertIn("unexpected keyword argument 'encoding'", r["message"])
        self.assertEqual(r["before"], ["starting"])

    def test_the_same_error_again_is_counted_not_repeated(self):
        x = devwatch.Extractor("/p")
        tb = 'Traceback (most recent call last):\n  File "/p/gui/duel.py", line 9, in draw\nKeyError: \'img\''
        first = feed(x, tb, 1.0)
        again = feed(x, tb, 2.0) + feed(x, tb, 3.0)
        self.assertTrue(first[0][1])
        self.assertEqual([new for _, new in again], [False, False])
        (r,) = x.records.values()
        self.assertEqual((r["count"], r["first"], r["last"]), (3, 1.0, 3.0))

    def test_native_errors_and_a_silent_crash(self):
        x = devwatch.Extractor()
        feed(x, "engine/src/game.cpp:23: error: expected unqualified-id\nSegmentation fault (core dumped)")
        self.assertEqual(len(x.records), 2)
        y = devwatch.Extractor()
        feed(y, "drawing the board")
        ((r, new),) = y.ended(139)
        self.assertEqual((r["kind"], r["message"]), ("Exit", "exit 139"))
        self.assertEqual(devwatch.Extractor().ended(0), [])  # a clean exit says nothing

    def test_the_summary_for_the_correcting_agent(self):
        x = devwatch.Extractor("/p")
        feed(x, 'Traceback (most recent call last):\n  File "/p/a.py", line 3, in f\nValueError: bad deck')
        r = list(x.records.values())
        r[0]["picture"] = ".cinminai/runs/1/error-1.png"
        said = devwatch.summary(r, "run.sh", ".cinminai/runs/1/output.log")
        self.assertIn("1 error(s) while the person played run.sh", said)
        self.assertIn("ValueError: bad deck at a.py:3 (1x); picture of the window: .cinminai/runs/1/error-1.png", said)
        self.assertIn("ran with no errors", devwatch.summary([], "run.sh", "x.log"))


if __name__ == "__main__":
    unittest.main()
