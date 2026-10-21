# SPDX-License-Identifier: GPL-3.0-or-later
"""This computer's developer identity (src/cin_minai/aicui/identity.py, PLAN D62): its name and who maintains it, kept
on this computer, and the check of GitHub's profile against them.

    python3 -m unittest tests.unit.test_aicui_identity -v        (from the repo root)
"""

import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))

from cin_minai.aicui import identity  # noqa: E402


class Identity(unittest.TestCase):
    def setUp(self):
        home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, home, True)
        patch = mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": home})
        patch.start()
        self.addCleanup(patch.stop)

    def test_named_once_and_kept_on_this_computer(self):
        self.assertEqual(identity.load(), {"name": "", "maintainer": ""})  # nothing until the person names it
        identity.save("  Simon ", "Brickmii")
        self.assertEqual(identity.load(), {"name": "Simon", "maintainer": "Brickmii"})
        self.assertEqual(identity.bio(identity.load()), "Simon is maintained by Brickmii")

    def test_what_stops_a_name_is_said(self):
        self.assertIn("Type the computer's name", identity.problem(" ", "Brickmii"))
        self.assertIn("Type who maintains it", identity.problem("Simon", ""))
        self.assertIn("40 characters", identity.problem("S" * 41, "Brickmii"))
        self.assertIn("one line", identity.problem("Si\nmon", "Brickmii"))
        with self.assertRaises(ValueError):
            identity.save("", "Brickmii")
        self.assertEqual(identity.load()["name"], "")  # nothing saved

    def test_the_profile_is_checked_against_the_name(self):
        ident = {"name": "Simon", "maintainer": "Brickmii"}
        good = {"login": "cinminaidevbox", "name": "Simon",
                "bio": "Simon is maintained by Brickmii. Builds pages with Cin-MinAI."}
        self.assertEqual(identity.differences(good, ident), [])  # more in the bio is fine
        off = identity.differences({"login": "cinminaidevbox", "name": "", "bio": ""}, ident)
        self.assertEqual(len(off), 2)
        self.assertIn("Name on GitHub is empty", off[0])
        self.assertIn("doesn't name Brickmii", off[1])
        self.assertIn("'Simone', not 'Simon'", identity.differences(dict(good, name="Simone"), ident)[0])
        # the owner's own words count, as long as they name the maintainer (Simon's real bio names nobody yet)
        own = dict(good, bio="Hi there, I am the development test bed for Cin-MinAI, you can call me Simon! "
                             "Kept running by brickmii.")
        self.assertEqual(identity.differences(own, ident), [])
        real = dict(good, bio="Hi there, I am the development test bed for the Cin-MinAI operating system, you can "
                              "call me Simon! I will post my test projects here!")
        self.assertEqual(len(identity.differences(real, ident)), 1)


if __name__ == "__main__":
    unittest.main()
