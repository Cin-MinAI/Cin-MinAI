# SPDX-License-Identifier: GPL-3.0-or-later
"""Terminal sharing on/off (D77): one marked line in ~/.bashrc, added at the top on yes, removed on off, and nothing
else in the file touched."""

import os
import stat
import tempfile
import unittest

from cin_minai.shell import ctl

USER_RC = "# my own settings\nalias ll='ls -l'\nexport EDITOR=nano\n"


class SharingSwitch(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp()
        self.rc = os.path.join(self.home, ".bashrc")

    def write(self, text):
        with open(self.rc, "w", encoding="utf-8") as f:
            f.write(text)

    def read(self):
        with open(self.rc, encoding="utf-8") as f:
            return f.read()

    def test_off_by_default(self):
        self.write(USER_RC)
        self.assertFalse(ctl.enabled(self.home))

    def test_enable_puts_the_line_first_and_keeps_the_rest(self):
        self.write(USER_RC)
        self.assertTrue(ctl.enable(self.home))
        lines = self.read().split("\n")
        self.assertEqual(lines[0], ctl.MARK)
        self.assertEqual(lines[1], ctl.LINE)
        self.assertTrue(self.read().endswith(USER_RC))
        self.assertTrue(ctl.enabled(self.home))

    def test_enable_twice_adds_it_once(self):
        self.write(USER_RC)
        ctl.enable(self.home)
        self.assertFalse(ctl.enable(self.home))
        self.assertEqual(self.read().count(ctl.LINE), 1)

    def test_disable_restores_the_file_exactly(self):
        self.write(USER_RC)
        ctl.enable(self.home)
        self.assertTrue(ctl.disable(self.home))
        self.assertEqual(self.read(), USER_RC)
        self.assertFalse(ctl.enabled(self.home))
        self.assertFalse(ctl.disable(self.home))  # already off: nothing to do

    def test_no_bashrc_yet(self):
        self.assertTrue(ctl.enable(self.home))
        self.assertTrue(ctl.enabled(self.home))
        ctl.disable(self.home)
        self.assertEqual(self.read(), "")

    @unittest.skipIf(os.name == "nt", "POSIX file modes")
    def test_file_mode_kept(self):
        self.write(USER_RC)
        os.chmod(self.rc, 0o600)
        ctl.enable(self.home)
        self.assertEqual(stat.S_IMODE(os.stat(self.rc).st_mode), 0o600)

    def test_the_line_only_sources_start_bash_if_it_exists(self):
        # after the package is removed, the leftover line must do nothing
        self.assertTrue(ctl.LINE.startswith(f"[ -r {ctl.START} ] &&"))


if __name__ == "__main__":
    unittest.main()
