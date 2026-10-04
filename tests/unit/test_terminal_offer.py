# SPDX-License-Identifier: GPL-3.0-or-later
"""D77: terminal sharing is offered once, when it would help — never pushed."""

import os
import tempfile
import unittest

from cin_minai.daemon import terminal as T
from cin_minai.sidebar import words

NOW = 1_791_100_000.0


class Offer(unittest.TestCase):
    def setUp(self):
        self.old_cfg = os.environ.get("XDG_CONFIG_HOME")
        os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()
        self.real = T.sharing
        self.state = {"available": True, "on": False, "open": 0}
        T.sharing = lambda: dict(self.state)

    def tearDown(self):
        T.sharing = self.real
        if self.old_cfg is None:
            os.environ.pop("XDG_CONFIG_HOME", None)
        else:
            os.environ["XDG_CONFIG_HOME"] = self.old_cfg

    def test_only_for_terminal_questions(self):
        self.assertTrue(T.should_offer("my command in the terminal failed", NOW))
        self.assertTrue(T.should_offer("Mi comando no funciona", NOW))
        self.assertTrue(T.should_offer("ターミナルでエラーが出た", NOW))
        self.assertFalse(T.should_offer("How do I change my wallpaper?", NOW))
        self.assertFalse(T.should_offer("LibreOffice shows an error", NOW))  # an error isn't a terminal

    def test_not_when_on_or_unavailable(self):
        self.state["on"] = True
        self.assertFalse(T.should_offer("my terminal command failed", NOW))
        self.state.update(on=False, available=False)
        self.assertFalse(T.should_offer("my terminal command failed", NOW))

    def test_not_now_waits_a_day(self):
        T.offered(NOW)
        self.assertFalse(T.should_offer("my terminal command failed", NOW + 3600))
        self.assertTrue(T.should_offer("my terminal command failed", NOW + T.OFFER_AGAIN + 1))

    def test_dont_ask_again_sticks(self):
        T._save_offer_state(dict(T._offer_state(), never=True))
        self.assertFalse(T.should_offer("my terminal command failed", NOW + 10 * T.OFFER_AGAIN))

    def test_what_the_sidebar_says(self):
        on = words.terminal_sharing_said("on", {"available": True, "on": True})
        self.assertIn("◆", on)
        self.assertIn("already open stay private", on)
        self.assertIn("won't ask again", words.terminal_sharing_said("never", {"available": True}))
        self.assertIn("isn't available", words.terminal_sharing_said("on", {"available": False}))
        self.assertIn("ai off", words.TERMINAL_OFFER_NOTE)


if __name__ == "__main__":
    unittest.main()
