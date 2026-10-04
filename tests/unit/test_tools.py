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
        # this reads the real machine: one with a problem on record adds it, with its note (the test SSD, 2026-10-04)
        self.assertEqual(set(o) - {"problems_found", "commands_note"},
                         {"open_with", "os", "cpu", "ram_gb", "gpu", "disk_gb"}, o)

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


class Drivers(unittest.TestCase):
    def test_basic_display_in_plain_words(self):
        # boot test 2 (2026-09-29): the live USB without nouveau; the check said "simple-framebuffer (open source)"
        from cin_minai.inference.hardware import Gpu
        gpus = [Gpu("other", "simple-framebuffer"), Gpu("intel", "i915"), Gpu("nvidia", "")]
        t = tools.Tools({"driver_manager": {"en": "Driver Manager"}}, {}, "en")
        with mock.patch.object(tools.hardware, "gpus", return_value=gpus), \
             mock.patch.object(tools, "run", side_effect=lambda argv, timeout=5: "nvidia-driver-580, (kernel modules provided by linux-modules-nvidia-580-generic-hwe-24.04)\n" if argv[0] == "ubuntu-drivers" else ""):
            d = t.inspect("drivers")
        self.assertNotIn("framebuffer", d["driver_in_use"])
        self.assertIn("NVIDIA card: no driver yet", d["driver_in_use"])
        self.assertIn("Intel graphics driver i915", d["driver_in_use"])
        self.assertEqual(d["recommended"], "nvidia-driver-580")
        self.assertIn("Driver Manager", d["note"])


class Diagnostics(unittest.TestCase):
    """D51/D53: active findings ride along with inspect_system, so the shipped guide explains them."""

    CASE = os.path.join(ROOT, "tests", "fixtures", "diag", "2026-09-30-v300-during-7.0.json")

    def inspect(self, topic: str, fixture: str = CASE) -> dict:
        t = tools.Tools({}, {}, "en")
        with mock.patch.dict(os.environ, {"CINMINAI_DIAG_FIXTURE": fixture}), \
             mock.patch.object(tools, "live_session", return_value=False), \
             mock.patch.object(tools.Tools, "_" + topic, return_value={"open_with": "x"}, create=True):
            return t.inspect(topic)

    def test_storage_carries_the_kernel_and_the_link(self):
        p = self.inspect("storage")["problems_found"]
        self.assertEqual([f["code"] for f in p], ["S401", "I301"])
        self.assertIn("command", p[1])

    def test_drivers_carry_the_driver_fault(self):
        self.assertIn("G101", [f["code"] for f in self.inspect("drivers")["problems_found"]])

    def test_unrelated_topic_stays_clean(self):
        self.assertNotIn("problems_found", self.inspect("network"))

    def test_history_only_adds_nothing(self):
        after = os.path.join(ROOT, "tests", "fixtures", "diag", "2026-09-30-v300-after-6.8.json")
        self.assertNotIn("problems_found", self.inspect("storage", after))

    def test_live_usb_adds_nothing(self):
        t = tools.Tools({}, {}, "en")
        with mock.patch.dict(os.environ, {"CINMINAI_DIAG_FIXTURE": self.CASE}), \
             mock.patch.object(tools, "live_session", return_value=True), \
             mock.patch.object(tools.Tools, "_storage", return_value={}):
            self.assertNotIn("problems_found", t.inspect("storage"))


if __name__ == "__main__":
    unittest.main()
