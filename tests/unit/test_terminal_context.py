# SPDX-License-Identifier: GPL-3.0-or-later
"""The terminal context the assistant is shown (M3 slice 2): when, what, and what never."""

import time
import unittest

from cin_minai.daemon import terminal as T

NOW = 1_791_100_000.0
# Ian's first real capture on the test SSD (2026-10-04): a password moment, then a question typed into the shell
IAN = [
    {"id": 1, "cmd": "sudo update", "cwd": "/home/brickmii", "exit": 1, "secret": True,
     "output": "\nsudo: update: command not found", "start": NOW - 60, "end": NOW - 58},
    {"id": 2, "cmd": "why didnt this work?", "cwd": "/home/brickmii", "exit": 127, "secret": False,
     "output": "Command 'why' not found, did you mean:\n  command 'who' from deb coreutils (9.4-3ubuntu6.2)",
     "start": NOW - 30, "end": NOW - 29},
]


class WhenToLook(unittest.TestCase):
    def test_pointing_question_after_a_failure(self):
        self.assertTrue(T.about_terminal("why didn't this work?", IAN, NOW))
        self.assertTrue(T.about_terminal("¿por qué no funciona?", IAN, NOW))
        self.assertTrue(T.about_terminal("Warum geht das nicht?", IAN, NOW))
        self.assertTrue(T.about_terminal("これはなぜ失敗したの？", IAN, NOW))

    def test_naming_the_terminal_or_an_error(self):
        ok = [dict(c, exit=0) for c in IAN]
        self.assertTrue(T.about_terminal("what does this error mean?", ok, NOW))
        self.assertTrue(T.about_terminal("what did my last command do in the terminal", ok, NOW))

    def test_not_about_the_terminal(self):
        self.assertFalse(T.about_terminal("How do I change my wallpaper?", IAN, NOW))
        self.assertFalse(T.about_terminal("Write a poem for my wife's birthday, she loves gardening and her roses "
                                          "and the way the morning light falls on them after a long winter, please.",
                                          IAN, NOW))

    def test_nothing_shared_or_too_old(self):
        self.assertFalse(T.about_terminal("why didn't this work?", [], NOW))
        self.assertFalse(T.about_terminal("why didn't this work?", IAN, NOW + 3600))

    def test_after_a_success_a_vague_question_isnt_about_it(self):
        ok = [dict(c, exit=0) for c in IAN]
        self.assertFalse(T.about_terminal("why is that?", ok, NOW))


class WhatItSees(unittest.TestCase):
    def test_context_reads_like_the_terminal(self):
        real = T.home_short
        T.home_short = lambda p: "~" if p == "/home/brickmii" else p  # the SSD's home, on any test machine
        try:
            ctx = T.context(IAN)
        finally:
            T.home_short = real
        self.assertIn("$ sudo update    (in ~: failed)", ctx)
        self.assertIn("sudo: update: command not found", ctx)
        self.assertIn("command not found", ctx)  # exit 127 in words
        self.assertIn("You can't run anything in it", ctx)

    def test_hidden_commands_never_appear(self):
        hidden = [dict(IAN[0], cmd=None, output="secret stuff")]
        self.assertNotIn("secret stuff", T.context(hidden))

    def test_fullscreen_output_isnt_shown(self):
        vim = [dict(IAN[1], cmd="vim notes.txt", exit=0, fullscreen=True, output="~\n~\n~")]
        self.assertIn("full-screen", T.context(vim))


class Redaction(unittest.TestCase):
    def test_credentials(self):
        cases = {
            "export API_KEY=abcd1234efgh5678": "abcd1234efgh5678",
            "curl -H 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.payload'": "eyJhbGciOiJIUzI1NiJ9",
            "git clone https://ian:hunter2@github.com/x/y": "hunter2",
            "aws key AKIAIOSFODNN7EXAMPLE": "AKIAIOSFODNN7EXAMPLE",
            "token ghp_aaaaaaaaaaaaaaaaaaaaaaaaaaaa": "ghp_aaaa",
            "mysql -u root password='s3cr3t pass'": "s3cr3t",
            "-----BEGIN OPENSSH PRIVATE KEY-----\nb3BlbnNzaC1rZXk\n-----END OPENSSH PRIVATE KEY-----": "b3BlbnNzaC1rZXk",
        }
        for text, secret in cases.items():
            self.assertNotIn(secret, T.redact(text), text)

    def test_ordinary_text_untouched(self):
        s = "sudo apt update\nE: Unable to locate package foo"
        self.assertEqual(T.redact(s), s)


class TheLinesThatMatter(unittest.TestCase):
    def test_short_output_whole(self):
        self.assertEqual(T.extract("one\ntwo\nthree"), "one\ntwo\nthree")

    def test_long_build_log(self):
        log = "\n".join([f"compiling unit {i}" for i in range(400)] +
                        ["src/main.c:42:7: error: 'counter' undeclared (first use in this function)",
                         "src/main.c:42:7: note: each undeclared identifier is reported only once"] +
                        [f"compiling unit {i}" for i in range(400, 800)] +
                        ["make: *** [Makefile:12: main.o] Error 1"])
        out = T.extract(log)
        self.assertIn("src/main.c:42:7: error: 'counter' undeclared", out)
        self.assertIn("make: *** [Makefile:12: main.o] Error 1", out)
        self.assertIn("lines left out", out)
        self.assertLessEqual(len(out), T.MAX_OUTPUT + 10)

    def test_python_traceback_tail(self):
        log = "\n".join([f"step {i}" for i in range(100)] + [
            "Traceback (most recent call last):", '  File "app.py", line 3, in <module>',
            "    import pygame", "ModuleNotFoundError: No module named 'pygame'"])
        out = T.extract(log)
        self.assertIn("ModuleNotFoundError: No module named 'pygame'", out)
        self.assertIn('File "app.py", line 3', out)

    def test_test_summary_kept(self):
        log = "\n".join([f"test_{i} ... ok" for i in range(200)] + ["FAILED tests/test_x.py::test_y",
                                                                   "=== 1 failed, 199 passed in 2.31s ==="])
        out = T.extract(log)
        self.assertIn("1 failed, 199 passed", out)


if __name__ == "__main__":
    unittest.main()
