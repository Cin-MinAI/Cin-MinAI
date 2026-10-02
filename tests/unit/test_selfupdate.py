# SPDX-License-Identifier: GPL-3.0-or-later
"""The daemon restarts itself after an update (PLAN D59): the watcher, and the test load.

    python3 -m unittest tests.unit.test_selfupdate -v        (from the repo root)
"""

import os
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))

from cin_minai.daemon import selfupdate  # noqa: E402


def touch(path: str, text: str, ns: int) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    os.utime(path, ns=(ns, ns))


class Watcher(unittest.TestCase):
    def setUp(self):
        self.pkg = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.pkg, "daemon", "__pycache__"))
        touch(os.path.join(self.pkg, "daemon", "service.py"), "a = 1\n", 10**18)
        touch(os.path.join(self.pkg, "daemon", "__pycache__", "service.cpython-312.pyc"), "x", 10**18)

    def test_an_update_is_ready_once_it_holds_still(self):
        w = selfupdate.Watcher(self.pkg)
        self.assertEqual(w.check(), "same")
        touch(os.path.join(self.pkg, "daemon", "__pycache__", "service.cpython-312.pyc"), "y", 2 * 10**18)
        self.assertEqual(w.check(), "same")  # compiled files don't count
        touch(os.path.join(self.pkg, "daemon", "service.py"), "a = 2\n", 2 * 10**18)
        self.assertEqual(w.check(), "changing")  # dpkg may still be unpacking
        self.assertEqual(w.check(), "ready")
        touch(os.path.join(self.pkg, "daemon", "manuscript.py"), "b = 1\n", 3 * 10**18)  # a new module
        self.assertEqual(w.check(), "changing")
        self.assertEqual(w.check(), "ready")

    def test_put_back_as_it_was_is_no_update(self):
        w = selfupdate.Watcher(self.pkg)
        touch(os.path.join(self.pkg, "daemon", "service.py"), "a = 3\n", 4 * 10**18)
        self.assertEqual(w.check(), "changing")
        touch(os.path.join(self.pkg, "daemon", "service.py"), "a = 1\n", 10**18)
        self.assertEqual(w.check(), "same")

    def test_the_open_project_survives_the_restart(self):
        os.environ["XDG_RUNTIME_DIR"] = tempfile.mkdtemp()
        path = selfupdate.state_file()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write("/home/u/Documents/Writing/Missed the Moon")
        self.assertEqual(selfupdate.take_reopen(), "/home/u/Documents/Writing/Missed the Moon")
        self.assertEqual(selfupdate.take_reopen(), "")  # read once
        self.assertEqual(selfupdate.RESTART_CODE, 75)

    @unittest.skipUnless(sys.platform.startswith("linux"), "loads the daemon, which needs PyGObject")
    def test_the_installed_code_loads(self):
        ok, why = selfupdate.loads()
        self.assertTrue(ok, why)


if __name__ == "__main__":
    unittest.main()
