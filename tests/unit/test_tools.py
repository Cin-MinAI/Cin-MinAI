# SPDX-License-Identifier: GPL-3.0-or-later
"""inspect_system shapes (src/cin_minai/daemon/tools.py). Linux only: they read /proc and /sys.

    python3 -m unittest tests.unit.test_tools -v        (from the repo root)
"""

import os
import sys
import unittest
from unittest import mock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))

from cin_minai.daemon import tools  # noqa: E402

LABELS = {"system_info": {"en": "System Information"}, "files": {"en": "Files"}}


@unittest.skipUnless(sys.platform.startswith("linux"), "reads /proc and /sys")
class Inspect(unittest.TestCase):
    def setUp(self):
        self.t = tools.Tools(LABELS, {}, "en")

    def test_overview_has_every_field(self):
        # regression: an edited comment swallowed the "gpu" field (2026-09-28)
        o = self.t.inspect("overview")
        self.assertEqual(set(o), {"open_with", "os", "cpu", "ram_gb", "gpu", "disk_gb"}, o)

    def test_storage_installed(self):
        with mock.patch.object(tools, "live_session", return_value=False):
            s = self.t.inspect("storage")
        self.assertIn("disks", s)
        self.assertEqual(s["open_with"], "Files")

    def test_storage_live_session_says_so(self):
        # boot check 1: "your hard drive is 17 GB and empty" was the live session's memory
        with mock.patch.object(tools, "live_session", return_value=True):
            s = self.t.inspect("storage")
        self.assertNotIn("disks", s)
        self.assertTrue(s["live_session"])
        self.assertIn("own disks are not used", s["note"])


if __name__ == "__main__":
    unittest.main()
