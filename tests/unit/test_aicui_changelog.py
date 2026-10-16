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


@unittest.skipUnless(shutil.which("git"), "the changelog needs git")
class OutsideChangesTest(unittest.TestCase):
    """PLAN D61's file-watching changelog: changes made outside AICUI (the person's editor, a program the project ran)
    go into the same changelog, with undo; the AI's own changes are never counted twice."""

    def setUp(self):
        import time
        from cin_minai.aicui.changelog import Watcher
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, True)
        self.t0 = time.time()
        write(os.path.join(self.root, "run.sh"), "python3 -m http.server 8000\n")
        os.utime(os.path.join(self.root, "run.sh"), (self.t0 - 60, self.t0 - 60))  # there before AICUI opened
        self.log = Changelog(self.root)
        self.w = Watcher(self.log, started=self.t0)

    def later(self, rel, text, seconds=10):
        p = os.path.join(self.root, rel)
        write(p, text)
        os.utime(p, (self.t0 + seconds, self.t0 + seconds))

    def test_what_was_there_is_the_start_not_a_change(self):
        self.assertEqual(self.w.sweep(now=self.t0 + 1), [])
        self.assertTrue(self.log.known("run.sh"))
        self.assertEqual(self.log.entries(), [])

    def test_the_persons_edit_is_recorded_and_can_be_undone(self):
        self.w.sweep(now=self.t0 + 1)
        self.later("run.sh", "python3 -m http.server 8000 &\nxdg-open http://localhost:8000\nwait\n")
        (e,) = self.w.sweep(now=self.t0 + 20)
        self.assertEqual((e["file"], e["model"], e["added"]), ("run.sh", "outside AICUI", 3))
        self.log.undo(e["id"])
        self.assertEqual(read(os.path.join(self.root, "run.sh")), "python3 -m http.server 8000\n")

    def test_a_file_changed_this_moment_waits_for_the_next_look(self):
        self.w.sweep(now=self.t0 + 1)
        self.later("run.sh", "echo hi\n", seconds=10)
        self.assertEqual(self.w.sweep(now=self.t0 + 11), [])  # 1 s old: maybe an AI change finishing
        self.assertEqual(len(self.w.sweep(now=self.t0 + 20)), 1)

    def test_the_ais_own_change_isnt_counted_twice(self):
        self.w.sweep(now=self.t0 + 1)
        before = self.log.before("run.sh")
        self.later("run.sh", "echo from the AI\n")
        self.log.after("run.sh", before, model="Qwen3.5-9B")
        self.assertEqual(self.w.sweep(now=self.t0 + 20), [])
        self.assertEqual([e["model"] for e in self.log.entries()], ["Qwen3.5-9B"])

    def test_new_and_deleted_files_outside(self):
        self.w.sweep(now=self.t0 + 1)
        self.later("notes.md", "my notes\n")
        (made,) = self.w.sweep(now=self.t0 + 20)
        self.assertEqual(made["file"], "notes.md")
        os.remove(os.path.join(self.root, "run.sh"))
        (gone,) = self.w.sweep(now=self.t0 + 30)
        self.assertEqual((gone["file"], gone["what"]), ("run.sh", "deleted outside AICUI"))
        self.log.undo(gone["id"])
        self.assertTrue(os.path.exists(os.path.join(self.root, "run.sh")))
