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


_CACHE = tempfile.mkdtemp()


def setUpModule():  # what the backend remembers (the last model, free choice) stays in the tests
    os.environ["XDG_CACHE_HOME"] = _CACHE


def tearDownModule():
    shutil.rmtree(_CACHE, True)


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
REPLY = {"content": [{"type": "tool_use", "name": "run", "input": {"reason": "Run it.", "command": "bash run.sh"}}], "stop_reason": "tool_use",
         "usage": {"input_tokens": 1200, "output_tokens": 80, "cache_creation_input_tokens": 9000,
                   "cache_read_input_tokens": 0}}


SCHEMA = {"type": "object", "required": ["thinking", "action"], "properties": {
    "thinking": {"type": "string", "maxLength": 1500},
    "action": {"anyOf": [
        {"type": "object", "required": ["tool", "command"],
         "properties": {"tool": {"const": "run"}, "command": {"type": "string"}}},
        {"type": "object", "required": ["tool", "text"],
         "properties": {"tool": {"const": "answer"}, "text": {"type": "string"}}}]}}}


class Cloud(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, True)

    def backend(self, answers):
        self.fake = FakeAnthropic(answers)
        return cloud.Anthropic(self.root, lambda: "sk-ant-test-key-0123456789abcdef", opener=self.fake)

    def test_a_step_through_one_flat_tool_per_action_with_the_cache_marked_and_its_cost_logged(self):
        b = self.backend([REPLY])
        messages = [{"role": "system", "content": "You are the coding agent."}, {"role": "user", "content": "Finish it."},
                    {"role": "assistant", "content": "{...earlier step...}"}, {"role": "user", "content": "Result: ok"},
                    {"role": "user", "content": "No progress in the last 6 steps."}]
        text, t = b.chat(messages, schema=SCHEMA, max_tokens=1800)
        self.assertEqual(json.loads(text), STEP)
        url, body, headers = self.fake.sent[0]
        self.assertEqual(url, "https://api.anthropic.com/v1/messages")
        self.assertEqual(body["model"], "claude-haiku-4-5-20251001")
        self.assertEqual(body["tool_choice"], {"type": "any"})
        self.assertEqual([t["name"] for t in body["tools"]], ["run", "answer"])
        self.assertEqual(body["tools"][0]["input_schema"]["required"], ["reason", "command"])
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
        self.assertEqual(cloud.settings(self.root)["crew"], "one")
        cloud.save_settings(self.root, role="lead", crew="two")
        self.assertEqual((cloud.settings(self.root)["role"], cloud.settings(self.root)["crew"]), ("lead", "two"))


class FreeChoice(unittest.TestCase):
    """Ian, 2026-10-26: "make a 2 time attempt for every cloud model, first with our arrangement then with whatever you
    do next" (Claude Sonnet 5.5: 400 "tool_choice: type "tool" and "any" are not supported for this model")."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, True)
        old = os.environ.get("XDG_CACHE_HOME")
        os.environ["XDG_CACHE_HOME"] = os.path.join(self.root, "cache")  # what's remembered stays in the test
        self.addCleanup(lambda: os.environ.__setitem__("XDG_CACHE_HOME", old) if old is not None
                        else os.environ.pop("XDG_CACHE_HOME", None))

    @staticmethod
    def refusal():
        return urllib.error.HTTPError("u", 400, "bad", {}, io.BytesIO(
            b'{"error": {"message": "tool_choice: type \\"tool\\" and \\"any\\" are not supported for this model."}}'))

    def test_a_refused_forced_tool_is_asked_again_with_a_free_choice_and_remembered(self):
        fake = FakeAnthropic([self.refusal(), REPLY, REPLY])
        b = cloud.Anthropic(self.root, lambda: "sk-ant-test-key-0123456789abcdef", "claude-sonnet-5-5", opener=fake)
        messages = [{"role": "system", "content": "You are the coding agent."}, {"role": "user", "content": "go"}]
        text, _ = b.chat(messages, schema=SCHEMA)
        self.assertEqual(json.loads(text), STEP)
        first, second = fake.sent[0][1], fake.sent[1][1]
        self.assertEqual(first["tool_choice"], {"type": "any"})       # our way first
        self.assertEqual(second["tool_choice"], {"type": "auto"})     # then a free choice, said in the system text
        self.assertIn(cloud.CHOOSE_ONE, second["system"][-1]["text"])
        self.assertTrue(cloud.free_choice("claude-sonnet-5-5"))
        b.chat(messages, schema=SCHEMA)  # remembered: one request, a free choice at once
        self.assertEqual((len(fake.sent), fake.sent[2][1]["tool_choice"]), (3, {"type": "auto"}))
        other = FakeAnthropic([urllib.error.HTTPError("u", 400, "bad", {}, io.BytesIO(
            b'{"error": {"message": "max_tokens: too large"}}'))])
        with self.assertRaises(cloud.CloudError):  # another 400 isn't retried
            cloud.Anthropic(self.root, lambda: "sk-ant-x" * 5, "claude-haiku-5-5", opener=other).chat(
                messages, schema=SCHEMA)
        self.assertEqual(len(other.sent), 1)

    def test_openai_the_same(self):
        fake = FakeAnthropic([self.refusal(), OPENAI_REPLY])
        b = cloud.OpenAI(self.root, lambda: "sk-proj-test-key-0123456789abcdef", "gpt-6-astra", opener=fake)
        from cin_minai.aicui.agent import schema
        b.chat([{"role": "system", "content": "You are the coder."}, {"role": "user", "content": "go"}],
               schema=schema())
        self.assertEqual((fake.sent[0][1]["tool_choice"], fake.sent[1][1]["tool_choice"]), ("required", "auto"))
        self.assertIn(cloud.CHOOSE_ONE, fake.sent[1][1]["instructions"])
        self.assertTrue(cloud.free_choice("gpt-6-astra"))

    def test_a_stronger_model_gets_thinking_room_a_fallback_and_its_refusals_said(self):
        """Ian, 2026-10-26: "the first time we've used a more advanced model ... plan for anything that might hold you
        up": Sonnet 5.5's picture answers came back empty at 300 tokens (its thinking counts), it reported the board in
        plain text, and it refused twice with no reason kept."""
        cloud.remember_free_choice("claude-sonnet-5-5")
        said = {"content": [{"type": "text", "text": "The board is done: a 7-column mat."}], "stop_reason": "end_turn",
                "model": "claude-sonnet-5-5", "usage": {"input_tokens": 10, "output_tokens": 20}}
        refused = {"content": [], "stop_reason": "refusal", "stop_details": {"type": "refusal", "category": "cyber"},
                   "usage": {"input_tokens": 10, "output_tokens": 0}}
        fake = FakeAnthropic([said, refused])
        b = cloud.Anthropic(self.root, lambda: "sk-ant-test-key-0123456789abcdef", "claude-sonnet-5-5", opener=fake)
        text, _ = b.chat([{"role": "user", "content": "go"}], schema=SCHEMA, max_tokens=300)
        self.assertEqual(json.loads(text), {"thinking": "", "action": {"tool": "answer",
                                                                      "text": "The board is done: a 7-column mat."}})
        body, headers = fake.sent[0][1], fake.sent[0][2]
        self.assertEqual(body["max_tokens"], 300 + cloud.THINKING_ROOM)
        self.assertEqual((body["fallbacks"], headers["Anthropic-beta"]), ("default", cloud.FALLBACK_BETA))
        with self.assertRaises(cloud.CloudError) as e:
            b.chat([{"role": "user", "content": "go"}], schema=SCHEMA)
        self.assertIn("declined this step (Anthropic's safety filter: cyber)", str(e.exception))
        kept = sorted(os.listdir(os.path.join(self.root, ".cinminai", "cutoffs")))
        with open(os.path.join(self.root, ".cinminai", "cutoffs", kept[-1])) as f:
            self.assertEqual(json.load(f)["stop_details"]["category"], "cyber")
        older = FakeAnthropic([REPLY])  # Haiku 4.5: no thinking room, no fallback
        cloud.Anthropic(self.root, lambda: "sk-ant-x" * 5, "claude-haiku-4-5-20251001", opener=older).chat(
            [{"role": "user", "content": "go"}], schema=SCHEMA, max_tokens=300)
        self.assertEqual(older.sent[0][1]["max_tokens"], 300)
        self.assertNotIn("fallbacks", older.sent[0][1])

    def test_the_55_calls_logged_before_their_prices_are_counted_again(self):
        """2026-10-26: Haiku 5.5 was logged at Haiku 4.5's price, ten times too high; the budget ran out early."""
        os.makedirs(os.path.join(self.root, ".cinminai"))
        with open(os.path.join(self.root, cloud.USAGE), "w") as f:
            f.write(json.dumps({"model": "claude-haiku-5-5", "input_tokens": 1_000_000, "output_tokens": 0,
                                "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0, "usd": 1.0}) + "\n")
            f.write(json.dumps({"model": "gpt-6-luna", "usd": 0.25}) + "\n")
        self.assertAlmostEqual(cloud.spent(self.root), 0.10 + 0.25, places=6)

    def test_a_new_project_starts_from_the_last_model_chosen(self):
        """2026-10-26 (test22): a new project started on Haiku 4.5, the built-in default, not the Luna Ian chose."""
        other = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, other, True)
        self.assertEqual(cloud.settings(other)["model"], cloud.DEFAULT_MODEL)
        cloud.save_settings(self.root, model="gpt-6-luna", role="lead")
        fresh = cloud.settings(other)
        self.assertEqual((fresh["model"], fresh["provider"], fresh["role"]), ("gpt-6-luna", "openai", "off"))

    def test_the_55_prices(self):
        self.assertEqual(cloud.price_of("claude-haiku-5-5")[:2], (0.10, 0.50))
        self.assertEqual(cloud.price_of("claude-sonnet-5-5")[:2], (2.00, 10.00))
        self.assertEqual(cloud.price_of("claude-opus-5-5")[:2], (4.00, 20.00))
        self.assertEqual(cloud.price_of("claude-haiku-4-5-20251001")[:2], (1.00, 5.00))
        self.assertTrue(cloud.price_checked("claude-sonnet-5-5"))


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


class Quirks(unittest.TestCase):
    def test_a_schema_without_actions_is_one_forced_tool_and_its_input_the_reply(self):
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root, True)
        reply = {"content": [{"type": "tool_use", "name": "reply", "input": {"items": ["a"]}}],
                 "usage": {"input_tokens": 10, "output_tokens": 5}}
        fake = FakeAnthropic([reply])
        b = cloud.Anthropic(root, lambda: "sk-ant-test-key-0123456789abcdef", opener=fake)
        text, _ = b.chat([{"role": "user", "content": "go"}], schema={"type": "object"})
        self.assertEqual(json.loads(text), {"items": ["a"]})
        self.assertEqual(fake.sent[0][1]["tool_choice"], {"type": "tool", "name": "reply"})

    def test_the_agents_real_schema_becomes_one_tool_per_action(self):
        sys.path.insert(0, os.path.join(ROOT, "third_party", "team-table", "src"))
        from cin_minai.aicui import agent
        tools = cloud.flat_tools(agent.schema(None, set()))
        names = [t["name"] for t in tools]
        self.assertIn("write", names)
        self.assertIn("answer", names)
        for t in tools:
            self.assertEqual(t["input_schema"]["required"][0], "reason")
            self.assertNotIn("tool", t["input_schema"]["properties"])


class Pictures(unittest.TestCase):
    def test_a_picture_goes_as_an_image_block_beside_its_text(self):
        system, turns = cloud.Anthropic.shape([
            {"role": "user", "content": "Fix the board."},
            {"role": "user", "content": [{"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,QUJD"}},
                                         {"type": "text", "text": "What does the window show?"}]}])
        parts = turns[0]["content"]
        self.assertEqual([p["type"] for p in parts], ["text", "image", "text"])
        self.assertEqual(parts[1]["source"], {"type": "base64", "media_type": "image/jpeg", "data": "QUJD"})

    def test_no_empty_text_is_ever_sent(self):
        """2026-10-12: Anthropic said 400, "text content blocks must be non-empty", and Haiku's run ended."""
        system, turns = cloud.Anthropic.shape([
            {"role": "user", "content": "Go."}, {"role": "assistant", "content": ""},
            {"role": "user", "content": "   "}, {"role": "user", "content": [{"type": "text", "text": ""}]}])
        for t in turns:
            for p in t["content"]:
                if p["type"] == "text":
                    self.assertTrue(p["text"].strip())

    def test_a_reply_without_a_tool_call_is_kept_and_its_text_tried(self):
        """2026-10-12: Haiku leading sent 8 replies the agent couldn't use; nothing showed what they were."""
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root, True)
        reply = {"content": [{"type": "text", "text": json.dumps(STEP)}], "stop_reason": "end_turn",
                 "usage": {"input_tokens": 10, "output_tokens": 30}}
        b = cloud.Anthropic(root, lambda: "sk-ant-test-key-0123456789abcdef", opener=FakeAnthropic([reply]))
        text, _ = b.chat([{"role": "user", "content": "go"}], schema=SCHEMA)
        self.assertEqual(json.loads(text), STEP)
        kept = os.listdir(os.path.join(root, ".cinminai", "cutoffs"))
        self.assertEqual(len(kept), 1)
        with open(os.path.join(root, ".cinminai", "cutoffs", kept[0])) as f:
            got = f.read()
        self.assertIn("end_turn", got)
        self.assertNotIn("sk-ant", got)

    def test_earlier_steps_go_as_tool_calls_and_their_results(self):
        """2026-10-12: shown its own steps as JSON text but made to answer with tool calls, Haiku mixed the two."""
        step = json.dumps({"thinking": "Read it.", "action": {"tool": "read", "path": "a.py"}})
        _, turns = cloud.Anthropic.shape([{"role": "user", "content": "go"}, {"role": "assistant", "content": step},
                                          {"role": "user", "content": "Result: line 1"},
                                          {"role": "user", "content": "A note."}], {"read"})
        call = turns[1]["content"][0]
        self.assertEqual((call["type"], call["name"], call["input"]),
                         ("tool_use", "read", {"reason": "Read it.", "path": "a.py"}))
        answer = turns[2]["content"]
        self.assertEqual((answer[0]["type"], answer[0]["tool_use_id"], answer[0]["content"]),
                         ("tool_result", call["id"], "line 1"))
        self.assertEqual(answer[1]["text"], "A note.")
        _, plain = cloud.Anthropic.shape([{"role": "user", "content": "go"}, {"role": "assistant", "content": step}])
        self.assertEqual(plain[1]["content"][0]["type"], "text")  # no tools offered: as it was

    def test_parameters_written_into_the_reason_are_taken_back_out(self):
        """2026-10-12, Haiku leading: the call's fields inside its reason text, JSON-style or in its own markup."""
        leak = {"reason": 'Check the page text.", "path": "sources/Cat.txt", "start": 1} </invoke>'}
        self.assertEqual(cloud.unleak(leak, ["reason", "path"]),
                         {"reason": "Check the page text.", "path": "sources/Cat.txt", "start": 1})
        xml = {"reason": 'Run the tests.</thinking> <parameter name="command">python3 test_build_system.py'}
        self.assertEqual(cloud.unleak(xml, ["reason", "command"]),
                         {"reason": "Run the tests.", "command": "python3 test_build_system.py"})
        tail = {"reason": 'Run them.</thinking> <parameter name="command">x', "command": "make test"}
        self.assertEqual(cloud.unleak(tail, ["reason", "command"]), {"reason": "Run them.", "command": "make test"})
        fine = {"reason": 'He said "go", "now".', "path": "a.py"}
        self.assertEqual(cloud.unleak(fine, ["reason", "path"]), fine)


class Offered(unittest.TestCase):
    def test_the_box_offers_each_familys_newest_two_and_says_which_prices_are_checked(self):
        """Ian, 2026-10-13: the bottom-right box filled by the connected providers' own model lists."""
        ids = ["claude-3-haiku-20240307", "claude-haiku-4-5-20251001", "claude-sonnet-4-6", "claude-sonnet-4-5-20250929",
               "claude-opus-4-8", "claude-opus-4-1-20250805", "claude-3-7-sonnet-20250219", "claude-opus-5-5"]
        self.assertEqual(cloud.offered(ids), ["claude-opus-5-5", "claude-opus-4-8", "claude-sonnet-4-6",
                                              "claude-sonnet-4-5-20250929", "claude-haiku-4-5-20251001",
                                              "claude-3-haiku-20240307"])
        self.assertTrue(cloud.price_checked("claude-haiku-4-5-20251001"))
        self.assertTrue(cloud.price_checked("claude-opus-5-5"))   # read 2026-10-26
        self.assertFalse(cloud.price_checked("claude-opus-6"))    # a newer one: counted at Opus's price, and said so
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root, True)
        old = cloud.MODELS_CACHE
        cloud.MODELS_CACHE = os.path.join(root, "models.json")
        self.addCleanup(setattr, cloud, "MODELS_CACHE", old)
        self.assertEqual(cloud.cached_models(), [])
        cloud.cache_models(["claude-opus-4-8"])
        self.assertEqual(cloud.cached_models(), ["claude-opus-4-8"])


class LockedKeyring(unittest.TestCase):
    def test_a_locked_keyring_is_said_not_taken_for_a_missing_key(self):
        """2026-10-13: after a restart with automatic login the login keyring was locked; AICUI said the key was gone."""
        from tests.unit.test_accounts import FakeKeyring

        class Locked(FakeKeyring):
            def __init__(self):
                super().__init__()
                self.is_locked, self.prompted = True, 0

            def locked(self):
                return self.is_locked

            def unlock(self):
                self.prompted += 1
                self.is_locked = False
                return True
        kr = Locked()
        self.assertTrue(accounts.keyring_locked(keyring=kr))
        self.assertTrue(accounts.unlock_keyring(keyring=kr))
        self.assertEqual(kr.prompted, 1)
        self.assertFalse(accounts.keyring_locked(keyring=kr))
        old = accounts.keyring_locked
        accounts.keyring_locked = lambda keyring=None: True
        self.addCleanup(setattr, accounts, "keyring_locked", old)
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root, True)
        with self.assertRaises(cloud.CloudError) as e:
            cloud.Anthropic(root, lambda: "").chat([{"role": "user", "content": "x"}])
        self.assertIn("the login keyring is locked", str(e.exception))


OPENAI_REPLY = {"status": "completed", "output": [
    {"type": "reasoning", "summary": []},
    {"type": "function_call", "call_id": "call_1", "name": "run",
     "arguments": json.dumps({"reason": "Run it.", "command": "bash run.sh"})}],
    "usage": {"input_tokens": 10000, "output_tokens": 200, "input_tokens_details": {"cached_tokens": 8000}}}


class OpenAITest(unittest.TestCase):
    """D35, 2026-10-16: OpenAI by API key, through the Responses API (the GPT-6 models take tools only there)."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, True)

    def backend(self, answers, model="gpt-6.1-sol"):
        self.fake = FakeAnthropic(answers)
        return cloud.OpenAI(self.root, lambda: "sk-proj-test-key-0123456789abcdef", model, opener=self.fake)

    def test_a_step_is_one_required_function_call_and_its_cost_is_logged(self):
        from cin_minai.aicui.agent import schema
        b = self.backend([OPENAI_REPLY])
        text, t = b.chat([{"role": "system", "content": "You are the coder."},
                          {"role": "user", "content": "start it"}], schema=schema(), max_tokens=900)
        self.assertEqual(json.loads(text), STEP)
        url, body, headers = self.fake.sent[0]
        self.assertEqual(url, "https://api.openai.com/v1/responses")
        self.assertEqual(headers["Authorization"], "Bearer sk-proj-test-key-0123456789abcdef")
        # a reasoning model gets room to think on top of the step's limit (2026-10-16: Luna spent all 745 tokens
        # of a step reasoning, four times, and the step came back empty)
        self.assertEqual((body["tool_choice"], body["max_output_tokens"], body["store"]),
                         ("required", 900 + cloud.REASONING_ROOM, False))
        self.assertEqual(body["instructions"], "You are the coder.")
        run = next(x for x in body["tools"] if x["name"] == "run")
        self.assertEqual((run["type"], run["strict"]), ("function", False))
        self.assertEqual(body["input"], [{"role": "user", "content": [{"type": "input_text", "text": "start it"}]}])
        # 2,000 new input at $2, 8,000 cached at $0.10, 200 out at $10 (per million): $0.0068
        self.assertAlmostEqual(t["usd"], 0.0068, places=6)
        self.assertAlmostEqual(cloud.spent(self.root), 0.0068, places=6)
        self.assertNotIn("sk-proj", open(os.path.join(self.root, cloud.USAGE)).read())

    def test_earlier_steps_go_as_their_calls_and_results_and_pictures_as_images(self):
        step = json.dumps(STEP)
        _, items = cloud.OpenAI.shape_input([
            {"role": "user", "content": "start it"},
            {"role": "assistant", "content": step},
            {"role": "user", "content": [{"type": "text", "text": "Result: it printed 'ok'"},
                                         {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAA"}}]},
            {"role": "assistant", "content": "All done."}], {"run"})
        self.assertEqual(items[1], {"type": "function_call", "call_id": "call_step1", "name": "run",
                                    "arguments": json.dumps({"reason": "Run it.", "command": "bash run.sh"})})
        self.assertEqual(items[2], {"type": "function_call_output", "call_id": "call_step1", "output": "it printed 'ok'"})
        self.assertEqual(items[3]["content"][1:], [{"type": "input_image", "image_url": "data:image/png;base64,AAA"}])
        self.assertIn("The picture your last step's look took", items[3]["content"][0]["text"])  # said to be its own
        self.assertEqual(items[4]["content"][0], {"type": "output_text", "text": "All done."})

    def test_the_budget_and_the_errors_are_said(self):
        cloud.save_settings(self.root, budget_usd=0.001, model="gpt-6.1-sol")
        b = self.backend([OPENAI_REPLY, OPENAI_REPLY])
        b.chat([{"role": "user", "content": "go"}])
        with self.assertRaises(cloud.CloudError) as e:
            b.chat([{"role": "user", "content": "go"}])
        self.assertIn("budget for this project is used up", str(e.exception))
        refused = urllib.error.HTTPError("u", 401, "no", {}, io.BytesIO(b'{"error": {"message": "Incorrect API key"}}'))
        with self.assertRaises(cloud.CloudError) as e:
            cloud.OpenAI(tempfile.mkdtemp(), lambda: "sk-x" * 10, opener=FakeAnthropic([refused])).chat(
                [{"role": "user", "content": "go"}])
        self.assertIn("OpenAI said 401: Incorrect API key", str(e.exception))

    def test_models_prices_names_and_keys(self):
        self.assertEqual(cloud.offered_openai(["gpt-4o", "gpt-6-luna", "gpt-6.1-sol", "whisper-1", "gpt-6-astra"]),
                         ["gpt-6.1-sol", "gpt-6-luna", "gpt-6-astra"])
        self.assertEqual(cloud.label("gpt-6.1-sol"), "GPT-6.1 Sol")
        self.assertEqual(cloud.provider_of("gpt-6-luna"), "openai")
        self.assertEqual(cloud.provider_of("claude-haiku-4-5-20251001"), "anthropic")
        self.assertEqual(cloud.price_of("gpt-6-luna")[:2], (0.10, 0.50))
        self.assertTrue(cloud.price_checked("gpt-6.1-sol"))
        cloud.save_settings(self.root, model="gpt-6-luna")
        self.assertEqual(cloud.settings(self.root)["provider"], "openai")  # the provider follows the model
        self.assertIsInstance(cloud.backend(self.root, "openai", "gpt-6-luna"), cloud.OpenAI)
        import re
        self.assertTrue(re.fullmatch(accounts.CLOUD["openai"]["shape"], "sk-proj-" + "a" * 40))
        self.assertFalse(re.fullmatch(accounts.CLOUD["openai"]["shape"], "sk-ant-" + "a" * 40))  # an Anthropic key


class ListedInputs(unittest.TestCase):
    def test_a_list_sent_as_text_is_a_list(self):
        """2026-10-27 (test27): Haiku 5.5 gave distill's sources as the text '["sources/…"]', and the rulebook's path
        was read letter by letter."""
        tools = [{"name": "distill", "input_schema": {"properties": {"sources": {"type": "array"},
                                                                      "intent": {"type": "string"}}}}]
        got = cloud.listed({"sources": '["sources/rules.txt", "sources/b.txt"]', "intent": "[the rules]"}, tools,
                           "distill")
        self.assertEqual(got, {"sources": ["sources/rules.txt", "sources/b.txt"], "intent": "[the rules]"})
        self.assertEqual(cloud.listed({"sources": "sources/rules.txt"}, tools, "distill")["sources"],
                         ["sources/rules.txt"])  # one item, as it is
        self.assertEqual(cloud.listed({"sources": ["a"]}, tools, "distill")["sources"], ["a"])


class PdfWhole(unittest.TestCase):
    def test_a_pdf_goes_as_a_document(self):
        """Ian, 2026-10-27 (test28): "Cloud models have their own tools to read pdfs"."""
        part = {"type": "file", "file": {"filename": "rules.pdf", "file_data": "data:application/pdf;base64,JVBERi0="}}
        doc = cloud.blocks([part, {"type": "text", "text": "The whole PDF, every page."}])
        self.assertEqual(doc[0], {"type": "document", "source": {"type": "base64", "media_type": "application/pdf",
                                                                 "data": "JVBERi0="}})
        _, items = cloud.OpenAI.shape_input([{"role": "system", "content": "Distill."},
                                             {"role": "user", "content": [part]}])
        self.assertIn({"type": "input_file", "filename": "rules.pdf",
                       "file_data": "data:application/pdf;base64,JVBERi0="}, items[0]["content"])


class PictureInResult(unittest.TestCase):
    def test_a_looks_picture_goes_inside_its_result(self):
        """2026-10-27 (test29): beside the result, Haiku looked four times ("the look tool keeps returning only a
        path") and stopped "rather than editing blind"."""
        step = json.dumps({"thinking": "See it.", "action": {"tool": "look", "target": "picture", "address": "a.png"}})
        pic = {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}}
        msgs = [{"role": "system", "content": "rules"}, {"role": "user", "content": "go"},
                {"role": "assistant", "content": step},
                {"role": "user", "content": [{"type": "text", "text": "Result: this result holds the picture"}, pic]}]
        _, turns = cloud.Anthropic.shape(msgs, {"look"})
        result = turns[-1]["content"]
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["type"], "tool_result")
        self.assertEqual([b["type"] for b in result[0]["content"]], ["text", "image"])
        _, items = cloud.OpenAI.shape_input(msgs, {"look"})
        self.assertIn("The picture your last step's look took", json.dumps(items))
