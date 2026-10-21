# SPDX-License-Identifier: GPL-3.0-or-later
"""Keep this computer offline (src/cin_minai/daemon/offline.py, PLAN D28): the switch turns NetworkManager's networking
off for the whole computer, going online for updates comes back offline only after an install has finished, and the
reminder about security updates comes at most once a month.

    python3 -m unittest tests.unit.test_offline -v        (from the repo root)
"""

import os
import shutil
import sys
import tempfile
import time
import unittest
from unittest import mock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))

from cin_minai.daemon import offline  # noqa: E402


class Offline(unittest.TestCase):
    def setUp(self):
        home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, home, True)
        env = mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": os.path.join(home, "config"),
                                           "XDG_STATE_HOME": os.path.join(home, "state"), "LANGUAGE": "en"})
        env.start()
        self.addCleanup(env.stop)
        self.calls, self.said = [], []
        for name, fake in (("nmcli", lambda *a: self.calls.append(a) or ""),
                           ("notify", lambda text, code=None: self.said.append(text))):
            p = mock.patch.object(offline, name, fake)
            p.start()
            self.addCleanup(p.stop)

    def test_the_switch_is_the_whole_computer(self):
        self.assertFalse(offline.on())
        offline.keep(True)
        self.assertTrue(offline.on())
        self.assertEqual(self.calls, [("networking", "off")])  # Wi-Fi and cable alike, not just our parts
        self.assertIn("Go online to install updates", self.said[0])
        offline.keep(False)
        self.assertFalse(offline.on())
        self.assertEqual(self.calls[-1], ("networking", "on"))

    def test_back_offline_waits_for_an_install(self):
        offline.keep(True)
        busy = [True, True, False]
        with mock.patch.object(offline, "installing", lambda: busy.pop(0)):
            offline.back_offline(wait=lambda s: None)
        self.assertEqual(busy, [])  # it waited until the install was done
        self.assertEqual(self.calls[-1], ("networking", "off"))
        self.assertIn("Back offline", self.said[-1])

    def test_switched_off_meanwhile_it_stays_online(self):
        offline.keep(True)
        offline.keep(False)
        n = len(self.calls)
        with mock.patch.object(offline, "installing", lambda: False):
            offline.back_offline(wait=lambda s: None)
        self.assertEqual(len(self.calls), n)  # the person's later choice stands

    def test_going_online_gives_up_after_a_while(self):
        clock = [0.0]

        def wait(s):
            clock[0] += s
        with mock.patch.object(offline, "connected", lambda: False):
            self.assertFalse(offline.go_online(wait=wait, now=lambda: clock[0]))
        self.assertGreaterEqual(clock[0], offline.CONNECT_S)
        with mock.patch.object(offline, "connected", lambda: True):
            self.assertTrue(offline.go_online(wait=wait, now=lambda: clock[0]))

    def test_a_reminder_at_most_once_a_month(self):
        now = time.time()
        self.assertFalse(offline.remind(now))  # online: never
        offline.keep(True)
        self.said.clear()
        self.assertFalse(offline.remind(now))  # just went offline
        later = now + offline.MONTH_S + 60
        self.assertTrue(offline.remind(later))
        self.assertIn("over a month", self.said[0])
        self.assertFalse(offline.remind(later + 86400))  # not again the next day
        os.utime(offline.reminded_path(), (now, now))
        self.assertTrue(offline.remind(later + offline.MONTH_S))

    def test_the_assistant_offers_nothing_that_goes_online(self):
        said = []
        self.assertIsNone(offline.says("en", said.append))  # online: the search card as before
        offline.keep(True)
        self.assertEqual(offline.says("de", said.append)["tool"], "offline")
        self.assertIn("Diesen Computer offline halten", said[0])  # how to go online, in the menu's own words

    def test_six_languages(self):
        for code in ("en", "es", "pt", "fr", "de", "ja"):
            self.assertEqual(set(offline.WORDS[code]), set(offline.WORDS["en"]), code)
        self.assertEqual(offline.words("assistant", "xx"), offline.WORDS["en"]["assistant"])


if __name__ == "__main__":
    unittest.main()
