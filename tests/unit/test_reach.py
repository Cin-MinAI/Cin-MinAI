# SPDX-License-Identifier: GPL-3.0-or-later
"""The panel's WEB / CLOUD sign (inference/reach.py; PLAN D35, D28): every request out is marked while it's out and a
few seconds after; a cloud model's API is CLOUD, the rest WEB; each one is a line in the local record of what was
sent where. Nothing here goes on the network: a data: address stands in."""

import json
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
                                           "XDG_STATE_HOME": os.path.join(self.dir, "state")})
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
        with open(reach.record_path()) as f:
            line = json.loads(f.readline())
        self.assertEqual((line["kind"], line["to"]), ("cloud", "OpenAI"))  # where, never what

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
