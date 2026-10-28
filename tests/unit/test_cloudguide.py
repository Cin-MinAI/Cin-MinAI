# SPDX-License-Identifier: GPL-3.0-or-later
"""The assistant on a cloud model (src/cin_minai/inference/cloudguide.py, PLAN D35): the guide's own turn, its tools
sent as the cloud's tools and its call back in the guide's shape, the choice offered only for measured models, the
key never in what's kept. A stand-in for Anthropic: nothing is sent anywhere.

    python3 -m unittest tests.unit.test_cloudguide -v        (from the repo root)
"""

import io
import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
from unittest import mock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "distro", "packages", "cinminai-daemon"))

from cin_minai.daemon.guide import Guide  # noqa: E402
from cin_minai.daemon.helpcards import HelpIndex  # noqa: E402
from cin_minai.daemon.tools import Tools  # noqa: E402
from cin_minai.inference import cloud, cloudguide  # noqa: E402
from cin_minai.inference.backend import BackendError, Cancelled  # noqa: E402
import gen_data  # noqa: E402

DATA = gen_data.build(ROOT)
KEY = "sk-ant-test-key-0123456789abcdef"


class FakeAnthropic:
    def __init__(self, answers):
        self.answers, self.sent = list(answers), []

    def __call__(self, req, timeout=0):
        self.sent.append(json.loads(req.data) if req.data else None)
        return io.BytesIO(json.dumps(self.answers.pop(0)).encode())


def called(name, **inputs):
    return {"content": [{"type": "tool_use", "name": name, "input": {"reason": "", **inputs}}], "stop_reason": "tool_use",
            "usage": {"input_tokens": 900, "output_tokens": 40}}


def said(text):
    return {"content": [{"type": "text", "text": text}], "stop_reason": "end_turn",
            "usage": {"input_tokens": 1100, "output_tokens": 60}}


class CloudGuideTest(unittest.TestCase):
    def setUp(self):
        self.where = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.where, True)
        patcher = mock.patch.dict(os.environ, {"XDG_CACHE_HOME": self.where})
        patcher.start()
        self.addCleanup(patcher.stop)

    def guide(self, answers):
        self.fake = FakeAnthropic(answers)
        inner = cloud.Anthropic(self.where, lambda: KEY, "claude-haiku-5-5", opener=self.fake)
        b = cloudguide.CloudGuide("anthropic", "claude-haiku-5-5", self.where, inner)
        h = DATA["help.json"]
        return Guide(b, DATA["guide.json"], HelpIndex(h), Tools(h["labels"], h["desktop"], "en"),
                     {"history_chars": 12000, "cpu_history_chars": 3000})

    def turn(self, g, text):
        out = []
        res = g.turn(text, out.append, lambda *a: None, threading.Event())
        return res, "".join(out)

    def test_an_answer_streams_as_the_guides_own(self):
        g = self.guide([called("answer", text="Press Super and type Files.")])
        res, shown = self.turn(g, "How do I open my files?")
        self.assertEqual((res["tool"], res["reply"]), ("answer", "Press Super and type Files."))
        self.assertEqual(shown, "Press Super and type Files.")
        tools = {t["name"] for t in self.fake.sent[0]["tools"]}
        self.assertTrue({"answer", "decline", "lookup_help"} <= tools)
        self.assertEqual(g.backend.status().build, "cloud")

    def test_a_tool_then_the_reply_in_plain_text(self):
        g = self.guide([called("lookup_help", query="install a program"), said("Open the Software Manager.")])
        res, shown = self.turn(g, "How do I install a program?")
        self.assertEqual(res["tool"], "lookup_help")
        self.assertEqual(res["args"], {"query": "install a program"})
        self.assertIn("Open the Software Manager.", shown)
        self.assertNotIn("tools", self.fake.sent[1])  # the reply is written as text
        self.assertTrue(any("Result of lookup_help" in json.dumps(m) for m in self.fake.sent[1]["messages"]))
        with open(os.path.join(self.where, cloud.USAGE), encoding="utf-8") as f:
            log = f.read()
        self.assertEqual(log.count("\n"), 2)
        self.assertNotIn(KEY, log)

    def test_the_schema_both_ways(self):
        schema = {"anyOf": [{"type": "object", "required": ["tool", "args"], "properties": {
            "tool": {"const": "web_search"},
            "args": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}}]}
        tools = cloud.flat_tools(cloudguide.to_steps(schema))
        self.assertEqual([t["name"] for t in tools], ["web_search"])
        self.assertEqual(tools[0]["input_schema"]["required"], ["reason", "query"])
        back = cloudguide.from_step(json.dumps({"thinking": "", "action": {"tool": "web_search", "query": "x"}}))
        self.assertEqual(json.loads(back), {"tool": "web_search", "args": {"query": "x"}})

    def test_errors_and_stopping(self):
        class Refusing:
            def chat(self, *a, **kw):
                raise cloud.CloudError("Anthropic said 401: invalid x-api-key")
        b = cloudguide.CloudGuide("anthropic", "claude-haiku-5-5", self.where, Refusing())
        with self.assertRaises(BackendError) as e:
            b.chat([{"role": "user", "content": "hi"}])
        self.assertIn("401", str(e.exception))
        stop = threading.Event()
        stop.set()
        with self.assertRaises(Cancelled):
            b.chat([{"role": "user", "content": "hi"}], cancel=stop)

    def test_offered_only_when_measured(self):
        with self.assertRaises(BackendError):
            cloudguide.choose("claude-haiku-5-5", where=self.where)
        self.assertIsNone(cloudguide.choice(self.where))
        with mock.patch.dict(cloudguide.MEASURED, {"claude-haiku-5-5": "150/157"}):
            got = cloudguide.choose("claude-haiku-5-5", where=self.where)
        self.assertEqual((got["model"], got["provider"], got["budget_usd"]), ("claude-haiku-5-5", "anthropic", 2.0))
        self.assertEqual(cloudguide.choice(self.where)["label"], "Claude Haiku 5.5")
        self.assertEqual(cloudguide.choose("", 4.0, where=self.where), {"model": ""})  # back to this computer
        self.assertIsNone(cloudguide.choice(self.where))
        self.assertFalse(os.path.exists(os.path.join(self.where, "cinminai", "cloud-last-model")))  # not AICUI's


if __name__ == "__main__":
    unittest.main()
