# SPDX-License-Identifier: GPL-3.0-or-later
"""The panel's WEB / CLOUD sign (inference/reach.py; PLAN D35, D28): every request out is marked while it's out and a
few seconds after; a cloud model's API is CLOUD, the rest WEB; the internet log only when the person switches it on.
Nothing here goes on the network: a data: address stands in."""

import os
import shutil
import tempfile
import time
import unittest
import urllib.request
from unittest import mock

from cin_minai.inference import reach


class ReachTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)
        env = mock.patch.dict(os.environ, {"XDG_RUNTIME_DIR": os.path.join(self.dir, "run"),
                                           "XDG_STATE_HOME": os.path.join(self.dir, "state"),
                                           "XDG_CONFIG_HOME": os.path.join(self.dir, "config")})
        env.start()
        self.addCleanup(env.stop)

    def test_cloud_apis_are_cloud_and_the_rest_web(self):
        self.assertEqual(reach.kind_of("https://api.openai.com/v1/responses"), ("cloud", "OpenAI"))
        self.assertEqual(reach.kind_of("https://api.anthropic.com/v1/messages"), ("cloud", "Anthropic"))
        self.assertEqual(reach.kind_of("https://huggingface.co/x"), ("web", "huggingface.co"))

    def test_a_mark_holds_while_out_and_a_few_seconds_after(self):
        with reach.out("cloud", "OpenAI"):
            self.assertEqual([m["to"] for m in reach.active()], ["OpenAI"])
        self.assertEqual(len(reach.active()), 1)  # just ended: still shown for a moment
        self.assertEqual(reach.active(now=time.time() + reach.HOLD_S + 1), [])

    def test_the_internet_log_is_off_until_the_person_switches_it_on(self):
        """Ian, 2026-10-16: a record kept by default "comes off as spying" — a log you can turn on instead."""
        with reach.out("web", "duckduckgo.com"):
            pass
        self.assertFalse(os.path.exists(reach.log_path()))  # off: nothing written
        os.makedirs(os.path.dirname(reach.switch_path()), exist_ok=True)
        open(reach.switch_path(), "w").close()  # the panel menu's switch, on
        with reach.out("cloud", "OpenAI"):
            pass
        with open(reach.log_path()) as f:
            line = f.read()
        self.assertRegex(line, r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d  CLOUD  OpenAI\n$")  # when, kind, where; never what

    def test_the_record_kept_unasked_is_removed(self):
        os.makedirs(reach.state_dir(), exist_ok=True)
        old = os.path.join(reach.state_dir(), "sent.jsonl")
        with open(old, "w") as f:
            f.write('{"kind": "web", "to": "x"}\n')
        with mock.patch.object(reach, "_installed", []):
            reach.install()
            urllib.request.install_opener(None)
        self.assertFalse(os.path.exists(old))

    def test_every_request_through_the_opener_is_marked_until_its_answer_is_read(self):
        with mock.patch.object(reach, "_installed", []):
            reach.install()
            try:
                r = urllib.request.urlopen("data:,hello")
                self.assertEqual(len(reach.active(now=time.time() + reach.HOLD_S + 1)), 1)  # still out
                self.assertEqual(r.read(), b"hello")
                self.assertEqual(reach.active(now=time.time() + reach.HOLD_S + 1), [])  # read to the end: done
            finally:
                urllib.request.install_opener(None)

    def test_cloud_comes_first_and_old_marks_are_tidied(self):
        with reach.out("web", "duckduckgo.com"), reach.out("cloud", "Anthropic"):
            self.assertEqual([m["kind"] for m in reach.active()], ["cloud", "web"])
        reach.tidy(now=time.time() + 3600)
        self.assertEqual(os.listdir(reach.folder()), [])


if __name__ == "__main__":
    unittest.main()
