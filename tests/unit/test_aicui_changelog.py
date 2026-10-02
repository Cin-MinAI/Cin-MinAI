# SPDX-License-Identifier: GPL-3.0-or-later
"""AICUI's changelog (PLAN D61): a shadow git store, undo exact, the user's own repository untouched.

    python3 -m unittest tests.unit.test_aicui_changelog -v        (from the repo root)
"""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))

from cin_minai.aicui.changelog import Changelog  # noqa: E402


def write(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


@unittest.skipUnless(shutil.which("git"), "needs git")
class Shadow(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.f = os.path.join(self.root, "src", "app.py")
        write(self.f, "print('one')\n")
        self.log = Changelog(self.root)

    def change(self, rel, text, what=""):
        b = self.log.before(rel)
        write(os.path.join(self.root, rel), text)
        return self.log.after(rel, b, model="Qwen3.8-27B", goal="Say two", what=what)

    def test_records_and_undoes_exactly(self):
        e = self.change("src/app.py", "print('two')\nprint('three')\n", "say two")
        self.assertEqual((e["id"], e["added"], e["removed"], e["model"]), (1, 2, 1, "Qwen3.8-27B"))
        self.assertIn("+print('two')", self.log.diff(e))
        self.log.undo(1)
        self.assertEqual(read(self.f), "print('one')\n")
        self.assertTrue(self.log.entries()[0]["undone"])

    def test_the_users_own_edit_in_between_is_kept_as_before(self):
        self.change("src/app.py", "print('ai')\n")
        write(self.f, "print('mine')\n")  # the user edits it themselves
        self.change("src/app.py", "print('ai again')\n")
        self.log.undo(2)
        self.assertEqual(read(self.f), "print('mine')\n")

    def test_a_new_file_is_removed_by_undo(self):
        self.change("docs/NEW.md", "# new\n")
        self.log.undo(1)
        self.assertFalse(os.path.exists(os.path.join(self.root, "docs", "NEW.md")))

    def test_the_users_repository_is_untouched(self):
        run = lambda *a: subprocess.run(["git", "-C", self.root, *a], capture_output=True, text=True)  # noqa: E731
        run("init", "-q")
        self.change("src/app.py", "print('two')\n")
        self.assertEqual(run("log", "--oneline").stdout, "")  # no commits by AICUI in the user's history
        self.assertNotIn("A ", run("status", "--porcelain").stdout)  # nothing staged
        self.assertNotIn(".cinminai", run("status", "--porcelain").stdout)  # kept out via .git/info/exclude
        self.assertFalse(os.path.exists(os.path.join(self.root, ".gitignore")))  # the user's file, not ours


if __name__ == "__main__":
    unittest.main()
