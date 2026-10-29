# SPDX-License-Identifier: GPL-3.0-or-later
"""What Cin-MinAI changes in Mint's installer (distro/installer/, PLAN D47): a drive of its own recommended in the six
languages, Erase disk offered on a drive that holds no other system, the start-up files on the drive holding /, and
hooks that refuse to apply to code they don't recognise.

    python3 -m unittest tests.unit.test_installer -v        (from the repo root)
"""

import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "distro", "installer"))

import cinminai_installer as inst  # noqa: E402
import patch_ubiquity  # noqa: E402

ERASE = "Erase disk and install Cin-MinAI"


class Advice(unittest.TestCase):
    def test_six_languages_naming_the_installers_own_options(self):
        self.assertEqual(set(inst.RECOMMEND), {"en", "es", "pt", "fr", "de", "ja"})
        self.assertEqual(set(inst.CRYPTO), set(inst.RECOMMEND))
        for code in inst.RECOMMEND:
            text = inst.advice(ERASE, "Encrypt the new Cin-MinAI installation for security", code)
            self.assertIn(ERASE, text, code)
            self.assertIn("Encrypt the new Cin-MinAI installation for security", text, code)
            self.assertIn("Windows", text, code)
        self.assertNotIn("\n", inst.advice(ERASE, "", "en"))  # no encryption box offered: no line about it

    def test_the_installers_language(self):
        self.assertEqual(inst.lang({"LANG": "de_DE.UTF-8"}), "de")
        self.assertEqual(inst.lang({"LANGUAGE": "pt_BR:pt", "LANG": "en_US.UTF-8"}), "pt")
        self.assertEqual(inst.lang({"LANG": "nl_NL.UTF-8"}), "en")
        self.assertEqual(inst.lang({}), "en")


class Drives(unittest.TestCase):
    OSLIST = {"/dev/sda1": "Windows Boot Manager", "/dev/nvme0n1p3": "Windows 11"}

    def test_a_drive_holding_another_system(self):
        self.assertEqual(inst.disk_device("/var/lib/partman/devices/=dev=sda"), "/dev/sda")
        self.assertTrue(inst.holds_system("/dev/sda", self.OSLIST))
        self.assertTrue(inst.holds_system("/dev/nvme0n1", self.OSLIST))
        self.assertFalse(inst.holds_system("/dev/sdb", self.OSLIST))
        self.assertFalse(inst.holds_system("/dev/sd", self.OSLIST))  # /dev/sda1 isn't on "/dev/sd"

    def test_the_free_drive_offered_first(self):
        disks = [("sda (Windows)", "=dev=sda"), ("sdb (new)", "=dev=sdb")]
        self.assertEqual(inst.free_drive(disks, self.OSLIST), 1)
        self.assertIsNone(inst.free_drive(disks[:1], self.OSLIST))  # one drive: nothing to recommend between
        self.assertIsNone(inst.free_drive([("a", "=dev=sda"), ("n", "=dev=nvme0n1")], self.OSLIST))  # all taken

    def test_the_bootloader_follows_the_drive_holding_root(self):
        parts = {"=dev=sda1": {"parted": {"path": "/dev/sda1"}, "mountpoint": "/boot/efi", "method": "efi"},
                 "=dev=sdb2": {"parted": {"path": "/dev/sdb2"}, "mountpoint": "/", "method": "format"}}
        to_disk = lambda p: p.rstrip("0123456789")  # noqa: E731
        self.assertEqual(inst.root_disk(parts, to_disk), "/dev/sdb")
        self.assertIsNone(inst.root_disk({"=dev=sda1": {"parted": {"path": "/dev/sda1"}}}, to_disk))


class Hooks(unittest.TestCase):
    def test_each_hook_matches_once_or_the_build_stops(self):
        sample = "\n".join(old for old, _ in patch_ubiquity.CHANGES)
        out = patch_ubiquity.patch(sample)
        self.assertEqual(out.count("Cin-MinAI (D47)"), 4)
        with self.assertRaises(SystemExit):
            patch_ubiquity.patch(sample.replace("self.part_auto_select_drive.set_active(0)", "set_active(1)"))
        with self.assertRaises(SystemExit):
            patch_ubiquity.patch(sample + sample)  # twice: not the code we read
        for old, new in patch_ubiquity.CHANGES:  # Mint's own lines stay, ours go around them
            for line in old.strip().splitlines():
                if "set_active(0)" not in line and "default = grub_bootdev" not in line:
                    self.assertIn(line, new)


if __name__ == "__main__":
    unittest.main()
