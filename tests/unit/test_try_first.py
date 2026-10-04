# SPDX-License-Identifier: GPL-3.0-or-later
"""Try it first (M3 slice 4): what's refused, what's said, and — on Linux with bubblewrap — a real run on a copy."""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

from cin_minai import sandbox
from cin_minai.daemon import terminal as T
from cin_minai.sidebar import words


class Refusals(unittest.TestCase):
    def test_password_commands_arent_tried(self):
        for c in ("sudo apt install python3-tk", "  pkexec foo", "su -c ls"):
            r = T.try_first(c)
            self.assertFalse(r["ok"])
            self.assertIn("password", r["error"])
            self.assertFalse(words.can_try(c))
        self.assertTrue(words.can_try("python3 -m venv .venv"))
        self.assertTrue(words.can_try("sudoku --solve"))  # a word that starts like sudo isn't sudo

    @unittest.skipUnless(sys.platform.startswith("linux"), "Linux paths")
    def test_no_place_for_the_sandbox_to_write(self):
        for p in ("/", os.path.expanduser("~"), "/usr", "/etc/apt"):
            with self.assertRaises(ValueError):
                sandbox.valid_place(p)


class Words(unittest.TestCase):
    def test_verdicts(self):
        ok = {"ok": True, "exit": 0, "net": "pasta", "made": {"count": 1500, "top": [".venv"]},
              "changed": {"count": 0, "top": []}, "deleted": {"count": 0, "top": []}, "output": ""}
        self.assertIn("worked on the copy", words.try_verdict(ok))
        self.assertIn("wasn't touched", words.try_verdict(ok))
        self.assertIn("didn't work", words.try_verdict(dict(ok, exit=1)))
        self.assertIn("no internet", words.try_verdict(dict(ok, net="none")))
        self.assertIn("Couldn't try it", words.try_verdict({"ok": False, "error": "x"}))
        details = [t for t, _ in words.try_details(ok)]
        self.assertEqual(details, ["It would create: .venv (1500 files)"])


@unittest.skipUnless(sys.platform.startswith("linux") and shutil.which("bwrap"), "needs Linux and bubblewrap")
class RealSandbox(unittest.TestCase):
    """The copy, mounted at the folder's real path: a venv made there keeps working, and the folder isn't touched."""

    def test_copy_at_the_real_path(self):
        base = tempfile.mkdtemp(prefix="cinminai-proj-", dir=os.path.expanduser("~"))
        try:
            with open(os.path.join(base, "hello.py"), "w") as f:
                f.write('print("Hello World")\n')
            subprocess.run([sys.executable, "-m", "venv", "--without-pip", os.path.join(base, ".venv")], check=True)
            work = tempfile.mkdtemp(prefix="cinminai-try-")
            copy = os.path.join(work, "folder")
            shutil.copytree(base, copy, symlinks=True)
            r = sandbox.run(["bash", "-c", ".venv/bin/python hello.py && touch made-in-sandbox && pwd && ls -A ~"],
                            copy, net="none", timeout=60, mount_at=base)
            shutil.rmtree(work)
            self.assertEqual(r.returncode, 0, r.stderr)
            lines = r.stdout.split()
            self.assertEqual(lines[:2], ["Hello", "World"])  # the venv's absolute paths still work
            self.assertEqual(lines[2], base)                  # it ran at the real path
            self.assertEqual(lines[3:], [os.path.basename(base)])  # in the home folder: only the project
            self.assertFalse(os.path.exists(os.path.join(base, "made-in-sandbox")))  # the real folder is untouched
        finally:
            shutil.rmtree(base, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
