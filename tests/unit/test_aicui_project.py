# SPDX-License-Identifier: GPL-3.0-or-later
"""AICUI's project side (PLAN D61): the working tree with git status, and the session goals.

    python3 -m unittest tests.unit.test_aicui_project -v        (from the repo root)
"""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))

from cin_minai.aicui.project import Goals, git_status, project_root, tree  # noqa: E402


def write(path: str, text: str = "x\n") -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


class Project(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        write(os.path.join(self.root, "src", "main.py"))
        write(os.path.join(self.root, "README.md"))
        write(os.path.join(self.root, "node_modules", "big.js"))
        write(os.path.join(self.root, ".cinminai", "goals.json"), '{"goals": []}')

    def test_tree_hides_tool_folders_folders_first(self):
        rels = [r for r, _, _ in tree(self.root)]
        self.assertEqual(rels[0], "src")
        self.assertIn(os.path.join("src", "main.py"), rels)
        self.assertNotIn("node_modules", rels)
        self.assertFalse(any(r.startswith(".cinminai") for r in rels))

    @unittest.skipUnless(shutil.which("git"), "needs git")
    def test_git_status_marks_changes(self):
        run = lambda *a: subprocess.run(["git", "-C", self.root, *a], capture_output=True, check=True)  # noqa: E731
        run("init", "-q")
        run("-c", "user.email=t@t", "-c", "user.name=t", "add", "src/main.py")
        run("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "first")
        write(os.path.join(self.root, "src", "main.py"), "changed\n")
        st = git_status(self.root)
        self.assertEqual(st["src/main.py"], "M")
        self.assertEqual(st["README.md"], "?")
        marks = {r: s for r, _, s in tree(self.root)}
        self.assertEqual(marks["src"], "M")  # a folder with a change in it
        norm = lambda p: os.path.normcase(os.path.realpath(p))  # noqa: E731
        self.assertEqual(norm(project_root(os.path.join(self.root, "src", "main.py"))), norm(self.root))

    def test_goals_by_both_ticked_and_kept(self):
        g = Goals(self.root)
        a = g.add("Make the tests pass", by="user")
        b = g.add("Find out which Python version  it needs", by="ai")
        g.set_done(a["id"], True)
        goals = Goals(self.root).load()
        self.assertEqual([(x["text"], x["done"], x["by"]) for x in goals],
                         [("Make the tests pass", True, "user"), ("Find out which Python version it needs", False, "ai")])
        g.remove(b["id"])
        self.assertEqual(len(g.load()), 1)


if __name__ == "__main__":
    unittest.main()
