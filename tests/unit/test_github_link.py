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

    def test_a_repository_a_model_made_with_aicuis_folder_staged_still_keeps_it_here(self):
        # test20 (2026-10-20): the model ran `git init && git add .` before AICUI linked anything, so .cinminai/ and
        # .venv/ were staged; ignore rules added later don't take them back
        subprocess.run(["git", "-C", self.root, "init", "-q", "-b", "main"], check=True)
        subprocess.run(["git", "-C", self.root, "add", "."], check=True)
        bare = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, bare, True)
        subprocess.run(["git", "init", "--bare", "-b", "main", bare], capture_output=True, check=True)
        github_link.link(self.root, "https://github.com/brickmii/test20.git", "cinminaidevbox", "Simon")
        self.assertEqual(github_link.private_staged(self.root), [])  # taken back out at linking
        self.assertEqual(github_link.git(self.root, "config", "user.name")[1], "Simon")  # the machine's own name
        github_link.git(self.root, "remote", "set-url", "origin", bare)
        with mock.patch.object(github_link, "remote", return_value=bare):
            subprocess.run(["git", "-C", self.root, "add", "-f", ".cinminai/changelog.jsonl"], check=True)  # again
            ok, out = github_link.push(self.root, "first save")
            self.assertTrue(ok, out)
        shown = subprocess.run(["git", "-C", bare, "ls-tree", "-r", "--name-only", "main"],
                               capture_output=True, text=True).stdout.split()
        self.assertIn("main.py", shown)
        self.assertFalse([p for p in shown if p.startswith((".cinminai/", ".venv/"))], shown)
        self.assertTrue(os.path.exists(os.path.join(self.root, ".cinminai", "changelog.jsonl")))  # still on disk

    def test_a_file_the_person_leaves_out_stays_here(self):
        with open(os.path.join(self.root, "original-request.txt"), "w") as f:
            f.write("a store\n")
        subprocess.run(["git", "-C", self.root, "init", "-q", "-b", "main"], check=True)
        subprocess.run(["git", "-C", self.root, "add", "original-request.txt", "main.py"], check=True)
        github_link.leave_out(self.root, "original-request.txt")
        self.assertNotIn("original-request.txt", github_link.review(self.root)["files"])
        self.assertIn("main.py", github_link.review(self.root)["files"])
        self.assertTrue(os.path.exists(os.path.join(self.root, "original-request.txt")))

    def test_push_stops_when_a_private_file_would_still_go(self):
        with mock.patch.object(github_link, "remote", return_value="https://github.com/brickmii/x.git"), \
                mock.patch.object(github_link, "keep_private", return_value=[]), \
                mock.patch.object(github_link, "private_staged", return_value=[".cinminai/events.jsonl"]), \
                mock.patch.object(github_link, "git", return_value=(0, "")) as g:
            ok, out = github_link.push(self.root)
        self.assertFalse(ok)
        self.assertIn("Nothing was sent", out)
        self.assertNotIn("push", [c.args[1] for c in g.call_args_list])

    def test_the_look_before_publishing_names_what_goes_and_what_looks_personal_or_unfinished(self):
        page = ("<p>Email: info@secondhandhandbags.com</p>\n<p>Phone: (555) 123-4567</p>\n"
                "<p>123 Thrift Lane, Secondhand City</p>\n<footer>&copy; 2023 Store</footer>\n"
                "<img src='/home/brickmii/Pictures/bag.jpg'>\n<p>Call 412-867-0199</p>\n")
        for rel, text in (("index.html", page), ("original-request.txt", "a store\n"),
                          (".github/workflows/deploy.yml", "on: push\n")):
            os.makedirs(os.path.dirname(os.path.join(self.root, rel)) or self.root, exist_ok=True)
            with open(os.path.join(self.root, rel), "w") as f:
                f.write(text)
        got = github_link.review(self.root)
        self.assertIn("index.html", got["files"])
        self.assertFalse([p for p in got["files"] if p.startswith((".cinminai/", ".venv/"))])
        kinds = {(f, k) for f, _, k, _ in got["flags"]}
        for want in (("index.html", "an email address"), ("index.html", "placeholder text"),
                     ("index.html", "a street address"), ("index.html", "an old year"),
                     ("index.html", "a path on this computer"), ("index.html", "a phone number"),
                     ("original-request.txt", "AICUI's note of your request"),
                     (".github/workflows/deploy.yml", "a GitHub workflow")):
            self.assertIn(want, kinds)


if __name__ == "__main__":
    unittest.main()
