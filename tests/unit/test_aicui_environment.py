# SPDX-License-Identifier: GPL-3.0-or-later
"""The project token and its environment (PLAN §1b closure 4, Ian's design), and what comes into a project
(intake: pages and files kept whole, the person's own input listed).

    python3 -m unittest tests.unit.test_aicui_environment -v        (from the repo root)
"""

import json
import os
import shutil
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))

from cin_minai.aicui import intake, project  # noqa: E402


class Environment(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.home, True)
        env = {"HOME": self.home, "XDG_DATA_HOME": os.path.join(self.home, ".local", "share")}
        p = mock.patch.dict(os.environ, env)
        p.start()
        self.addCleanup(p.stop)
        for name, value in (("ENVS", os.path.join(env["XDG_DATA_HOME"], "cinminai", "envs")),
                            ("PROJECTS", os.path.join(env["XDG_DATA_HOME"], "cinminai", "aicui-projects.json"))):
            q = mock.patch.object(project, name, value)
            q.start()
            self.addCleanup(q.stop)
        self.root = os.path.join(self.home, "game")
        os.makedirs(self.root)

    def test_only_a_folder_inside_home_becomes_a_project(self):
        self.assertFalse(project.can_be_project(self.home))       # the home folder itself: never
        self.assertFalse(project.can_be_project("/usr"))          # the system: never
        self.assertTrue(project.can_be_project(self.root))
        with self.assertRaises(ValueError):
            project.make_project(self.home)
        token = project.make_project(self.root)
        self.assertEqual(project.make_project(self.root), token)  # once
        self.assertEqual(project.token_of(self.root), token)
        self.assertEqual(project.known_projects(), [os.path.realpath(self.root)])

    def test_the_environment_is_a_header_until_the_work_shows_what_it_needs(self):
        with self.assertRaises(ValueError):
            project.declare_env(self.root)  # no token: no environment
        token = project.make_project(self.root)
        self.assertEqual(project.env_state(self.root), "none")
        header = project.declare_env(self.root)
        self.assertEqual(project.env_state(self.root), "declared")
        self.assertEqual(os.listdir(os.path.join(self.root, ".venv")), [project.HEADER])  # just the header
        self.assertEqual((header["token"], header["packages"], header["real"]),
                         (token, [], os.path.join(project.ENVS, token)))
        self.assertEqual(project.want_package(self.root, "pygame-ce", "the window"), "wanted")
        self.assertEqual(project.want_package(self.root, "pygame-ce"), "already")
        for bad in ("pygame; rm -rf /", "--index-url=http://evil", "a b"):
            with self.assertRaises(ValueError):
                project.want_package(self.root, bad)
        self.assertEqual(project.env_header(self.root)["wanted"], ["pygame-ce"])

    def test_built_outside_the_project_and_linked_with_the_persons_yes(self):
        project.make_project(self.root)
        header = project.declare_env(self.root)
        project.want_package(self.root, "pygame-ce", "the window")
        calls = []

        def run(argv, **kw):  # python -m venv and pip, as AICUI runs them (with the network, after a yes)
            calls.append(argv)
            if argv[1:3] == ["-m", "venv"]:
                os.makedirs(os.path.join(argv[3], "bin"))
                for exe in ("python", "pip"):
                    open(os.path.join(argv[3], "bin", exe), "w").close()
            return types.SimpleNamespace(returncode=0, stderr="")
        built = project.build_env(self.root, say=lambda m: None, run=run)
        self.assertEqual(calls[1][1:], ["install", "--disable-pip-version-check", "pygame-ce"])
        self.assertEqual((built["packages"], built["wanted"]), (["pygame-ce"], []))
        self.assertTrue(os.path.islink(os.path.join(self.root, ".venv")))
        self.assertEqual(os.path.realpath(os.path.join(self.root, ".venv")), os.path.realpath(header["real"]))
        self.assertEqual(project.env_state(self.root), "built")
        with open(os.path.join(self.root, "requirements.txt")) as f:
            self.assertEqual(f.read(), "pygame-ce\n")
        shutil.rmtree(self.root)  # the project is gone: its environment is offered for removal
        self.assertEqual(project.orphan_envs(project.known_projects()), [header["real"]])

    def test_a_venv_made_elsewhere_is_left_alone(self):
        project.make_project(self.root)
        os.makedirs(os.path.join(self.root, ".venv", "bin"))
        open(os.path.join(self.root, ".venv", "bin", "python"), "w").close()
        self.assertEqual(project.env_state(self.root), "external")
        project.declare_env(self.root)
        self.assertFalse(os.path.exists(os.path.join(self.root, ".venv", project.HEADER)))


class Intake(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, True)

    def test_links_from_a_sentence(self):
        for typed, url in (("https://x.org/a_(1E).", "https://x.org/a_(1E)"), ("(see https://x.org/a)", None),
                           ("https://x.org/a,", "https://x.org/a")):
            got = [i["value"] for i in intake.person_inputs(typed, self.root)]
            self.assertEqual(got, [url or "https://x.org/a"])

    def test_the_persons_files_and_pasted_material(self):
        with open(os.path.join(self.root, "notes.md"), "w") as f:
            f.write("x")
        found = intake.person_inputs("use notes.md and missing.md for this\n" + "".join(f"row {i}\n" for i in range(9)),
                                     self.root)
        self.assertEqual([(i["kind"], i["value"][:6]) for i in found], [("file", "notes."), ("pasted", "row 0\n")])
        rel = intake.keep_pasted(self.root, "a\nb")
        self.assertEqual(rel, os.path.join("sources", "pasted-1.txt"))

    def test_a_page_is_kept_with_its_html_and_a_file_as_it_came(self):
        page = intake.save(self.root, "https://w.org/wiki/Set_(1E)", b"<html><body><p>One</p><img alt='Two'></body>",
                           "text/html")
        self.assertEqual(page["files"], ["sources/Set_-1E.txt", "sources/Set_-1E.html"])
        with open(os.path.join(self.root, "sources", "Set_-1E.txt")) as f:
            first, rest = f.read().split("\n", 1)
        self.assertIn("From https://w.org/wiki/Set_(1E)", first)
        self.assertIn("One", rest)
        img = intake.save(self.root, "https://w.org/i/two.png", b"\x89PNG", "image/png")
        self.assertEqual(img["files"], ["assets/two.png"])
        with open(os.path.join(self.root, "assets", "two.png"), "rb") as f:
            self.assertEqual(f.read(), b"\x89PNG")

    def test_only_https_and_never_too_big(self):
        with self.assertRaises(intake.IntakeError):
            intake.get("http://x.org/a")

        class Big:
            headers = {"Content-Type": "application/octet-stream"}

            def read(self, n):
                return b"0" * n

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False
        with self.assertRaisesRegex(intake.IntakeError, "too big"):
            intake.get("https://x.org/big.bin", opener=lambda req, timeout: Big())


if __name__ == "__main__":
    unittest.main()
