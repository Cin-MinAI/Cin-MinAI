# SPDX-License-Identifier: GPL-3.0-or-later
"""A project and its GitHub repository (src/cin_minai/aicui/github_link.py): linked once (git made, AICUI's own folders
kept out, the person as the author), saved and brought up to date — here against a local bare repository standing in
for GitHub, so nothing leaves the computer.

    python3 -m unittest tests.unit.test_github_link -v        (from the repo root)
"""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))

from cin_minai.aicui import github_link  # noqa: E402


@unittest.skipUnless(shutil.which("git"), "needs git")
class Link(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, True)
        for rel, text in (("main.py", "print('hi')\n"), (".cinminai/changelog.jsonl", "{}\n"), (".venv/x", "x\n")):
            os.makedirs(os.path.dirname(os.path.join(self.root, rel)) or self.root, exist_ok=True)
            with open(os.path.join(self.root, rel), "w") as f:
                f.write(text)

    def test_linking_makes_the_repository_keeps_aicuis_folders_out_and_points_at_github(self):
        github_link.link(self.root, "https://github.com/brickmii/test8.git", "brickmii")
        self.assertTrue(os.path.isdir(os.path.join(self.root, ".git")))
        with open(os.path.join(self.root, ".gitignore")) as f:
            ignored = f.read().splitlines()
        for p in (".cinminai/", ".venv/", "__pycache__/"):
            self.assertIn(p, ignored)
        self.assertEqual(github_link.remote(self.root), "https://github.com/brickmii/test8.git")
        self.assertEqual(github_link.git(self.root, "config", "user.email")[1], "brickmii@users.noreply.github.com")
        github_link.link(self.root, "https://github.com/brickmii/other.git", "brickmii")  # again: the address changes
        self.assertEqual(github_link.remote(self.root), "https://github.com/brickmii/other.git")
        with open(os.path.join(self.root, ".gitignore")) as f:
            self.assertEqual(f.read().count(".cinminai/"), 1)  # nothing added twice
        with self.assertRaises(ValueError):
            github_link.link(self.root, "https://evil.example/x.git", "brickmii")

    def test_save_and_bring_in_against_a_stand_in(self):
        bare = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, bare, True)
        subprocess.run(["git", "init", "--bare", "-b", "main", bare], capture_output=True, check=True)
        github_link.link(self.root, "https://github.com/brickmii/test8.git", "brickmii")
        github_link.git(self.root, "remote", "set-url", "origin", bare)  # the stand-in for GitHub
        with mock.patch.object(github_link, "remote", return_value=bare):
            ok, out = github_link.push(self.root, "first save")
            self.assertTrue(ok, out)
            shown = subprocess.run(["git", "-C", bare, "ls-tree", "-r", "--name-only", "main"],
                                   capture_output=True, text=True).stdout.split()
            self.assertIn("main.py", shown)
            self.assertNotIn(".cinminai/changelog.jsonl", shown)  # AICUI's own folder stays here
            self.assertNotIn(".venv/x", shown)
            ok, out = github_link.push(self.root)  # nothing new: pushed as it is, no empty commit
            self.assertTrue(ok, out)
            other = tempfile.mkdtemp()
            self.addCleanup(shutil.rmtree, other, True)
            subprocess.run(["git", "clone", "-q", bare, other], check=True)
            with open(os.path.join(other, "rules.py"), "w") as f:
                f.write("x = 1\n")
            for args in (("add", "-A"), ("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "more"),
                         ("push", "-q")):
                subprocess.run(["git", "-C", other, *args], check=True)
            ok, out = github_link.pull(self.root)
            self.assertTrue(ok, out)
            self.assertTrue(os.path.exists(os.path.join(self.root, "rules.py")))
        with mock.patch.object(github_link, "remote", return_value=""):
            self.assertEqual(github_link.push(self.root), (False, "this project isn't linked to a GitHub repository yet"))


if __name__ == "__main__":
    unittest.main()
