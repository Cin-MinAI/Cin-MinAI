# SPDX-License-Identifier: GPL-3.0-or-later
"""Cloud models (src/cin_minai/inference/cloud.py; docs/accounts-and-cloud.md): Anthropic by API key, the agent's step
held to its schema through one forced tool call, every call's cost logged, a budget per project checked before each
call, the key kept out of everything but the request. A stand-in for Anthropic: nothing is sent anywhere.

    python3 -m unittest tests.unit.test_cloud -v        (from the repo root)
"""

import io
import json
import os
import shutil
import sys
import tempfile
import unittest
import urllib.error

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))

from cin_minai.daemon import accounts  # noqa: E402
from cin_minai.inference import cloud  # noqa: E402


class FakeAnthropic:
    def __init__(self, answers):
        self.answers, self.sent = list(answers), []

    def __call__(self, req, timeout=0):
        self.sent.append((req.full_url, json.loads(req.data) if req.data else None, dict(req.header_items())))
        a = self.answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return io.BytesIO(json.dumps(a).encode())


STEP = {"thinking": "Run it.", "action": {"tool": "run", "command": "bash run.sh"}}
REPLY = {"content": [{"type": "tool_use", "name": "step", "input": STEP}], "stop_reason": "tool_use",
         "usage": {"input_tokens": 1200, "output_tokens": 80, "cache_creation_input_tokens": 9000,
                   "cache_read_input_tokens": 0}}


class Cloud(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, True)

    def backend(self, answers):
        self.fake = FakeAnthropic(answers)
        return cloud.Anthropic(self.root, lambda: "sk-ant-test-key-0123456789abcdef", opener=self.fake)

    def test_a_step_through_one_forced_tool_call_with_the_cache_marked_and_its_cost_logged(self):
        b = self.backend([REPLY])
        messages = [{"role": "system", "content": "You are the coding agent."}, {"role": "user", "content": "Finish it."},
                    {"role": "assistant", "content": "{...earlier step...}"}, {"role": "user", "content": "Result: ok"},
                    {"role": "user", "content": "No progress in the last 6 steps."}]
        text, t = b.chat(messages, schema={"type": "object", "properties": {}}, max_tokens=1800)
        self.assertEqual(json.loads(text), STEP)
        url, body, headers = self.fake.sent[0]
        self.assertEqual(url, "https://api.anthropic.com/v1/messages")
        self.assertEqual(body["model"], "claude-haiku-4-5-20251001")
        self.assertEqual(body["tool_choice"], {"type": "tool", "name": "step"})
        self.assertEqual([m["role"] for m in body["messages"]], ["user", "assistant", "user"])  # notes merged in turn
        self.assertIn("No progress", body["messages"][-1]["content"][0]["text"])
        self.assertEqual(body["system"][-1]["cache_control"], {"type": "ephemeral"})
        self.assertEqual(body["messages"][-1]["content"][-1]["cache_control"], {"type": "ephemeral"})
        self.assertEqual(headers["X-api-key"], "sk-ant-test-key-0123456789abcdef")  # only in the request
        # Haiku 4.5: 1,200 in at $1, 80 out at $5, 9,000 cache written at $1.25 per million
        self.assertAlmostEqual(t["usd"], (1200 * 1.0 + 80 * 5.0 + 9000 * 1.25) / 1e6, places=6)
        self.assertAlmostEqual(cloud.spent(self.root), t["usd"], places=5)
        with open(os.path.join(self.root, cloud.USAGE)) as f:
            self.assertNotIn("sk-ant", f.read())  # the log holds tokens and dollars, never the key

    def test_the_budget_stops_before_a_call_and_says_what_was_spent(self):
        cloud.save_settings(self.root, role="finisher", budget_usd=0.01)
        b = self.backend([REPLY] * 3)
        b.chat([{"role": "user", "content": "go"}], schema={"type": "object"})
        with open(os.path.join(self.root, cloud.USAGE), "a") as f:
            f.write(json.dumps({"usd": 0.02}) + "\n")
        with self.assertRaises(cloud.CloudError) as e:
            b.chat([{"role": "user", "content": "go"}], schema={"type": "object"})
        self.assertIn("the cloud budget for this project is used up ($0.03 of $0.01)", str(e.exception))
        self.assertEqual(len(self.fake.sent), 1)  # nothing sent past the budget

    def test_a_refused_key_is_said_and_never_repeated(self):
        b = self.backend([urllib.error.HTTPError("u", 401, "no", {}, io.BytesIO(
            b'{"error": {"message": "invalid x-api-key"}}'))])
        with self.assertRaises(cloud.CloudError) as e:
            b.models()
        self.assertEqual(str(e.exception), "Anthropic said 401: invalid x-api-key")
        with self.assertRaises(cloud.CloudError) as e:
            cloud.Anthropic(self.root, lambda: "").chat([{"role": "user", "content": "x"}])
        self.assertIn("no Anthropic key on this computer", str(e.exception))

    def test_names_and_prices(self):
        self.assertEqual(cloud.label("claude-haiku-4-5-20251001"), "Claude Haiku 4.5")
        self.assertEqual(cloud.price_of("claude-sonnet-4-6")[:2], (3.0, 15.0))
        self.assertEqual(cloud.settings(self.root)["role"], "off")  # nothing chosen: the local models


class Keys(unittest.TestCase):
    def test_a_key_is_checked_by_shape_and_the_error_never_repeats_it(self):
        from tests.unit.test_accounts import FakeKeyring
        kr = FakeKeyring()
        with self.assertRaises(accounts.AccountError) as e:
            accounts.store_cloud_key("anthropic", "not-a-key-but-a-password-123", keyring=kr)
        self.assertNotIn("password-123", str(e.exception))
        accounts.store_cloud_key("anthropic", "  sk-ant-api03-ABCDEFGHIJKLMNOPQRSTUVWX  ", keyring=kr)
        self.assertEqual(accounts.cloud_key("anthropic", keyring=kr), "sk-ant-api03-ABCDEFGHIJKLMNOPQRSTUVWX")
        accounts.forget_cloud_key("anthropic", keyring=kr)
        self.assertEqual(accounts.cloud_key("anthropic", keyring=kr), "")


if __name__ == "__main__":
    unittest.main()
