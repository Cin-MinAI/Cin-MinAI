# SPDX-License-Identifier: GPL-3.0-or-later
"""The guide's conversation (src/cin_minai/daemon/guide.py) against a scripted backend: the messages must
have exactly the shape the guide was trained on (training/datasets/sessions), answers stream while the
JSON is written, history trims by whole turns.

    python3 -m unittest tests.unit.test_guide -v        (from the repo root)
"""

import json
import os
import sys
import threading
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "distro", "packages", "cinminai-daemon"))

from cin_minai.daemon.guide import Guide, TextStream  # noqa: E402
from cin_minai.daemon.helpcards import HelpIndex  # noqa: E402
from cin_minai.daemon.tools import Tools  # noqa: E402
from cin_minai.inference.backend import Status  # noqa: E402
import gen_data  # noqa: E402

DATA = gen_data.build(ROOT)
CORPUS = os.path.join(ROOT, "training", "datasets", "sessions", "corpus.jsonl")


class Scripted:
    """Returns the scripted replies in order, streamed in small pieces; records what it was sent."""

    def __init__(self, replies, build="cuda"):
        self.replies, self.sent, self.build = list(replies), [], build

    def status(self):
        return Status("ready", "test", self.build, 8192)

    def chat(self, messages, *, schema=None, max_tokens=600, on_text=None, cancel=None):
        self.sent.append({"messages": [dict(m) for m in messages], "schema": schema})
        text = self.replies.pop(0)
        for i in range(0, len(text), 3):
            on_text and on_text(text[i:i + 3])
        return text, {}


class FakeTools(Tools):
    def inspect(self, topic):
        return {"battery": {"charge_pct": 88, "health_pct": 94, "state": "charging"}, "open_with": self.label("power")}


def guide(replies, build="cuda", history_chars=12000):
    b = Scripted(replies, build)
    h = DATA["help.json"]
    g = Guide(b, DATA["guide.json"], HelpIndex(h), FakeTools(h["labels"], h["desktop"], "en"),
              {"history_chars": history_chars, "cpu_history_chars": 3000})
    return g, b


def turn(g, text):
    out, actions = [], []
    res = g.turn(text, out.append, lambda *a: actions.append(a), threading.Event())
    return res, "".join(out), actions


class ReplacingOutput:
    def __init__(self):
        self.text = ""

    def __call__(self, piece):
        self.text += piece

    def replace(self, text):
        self.text = text


def replacing_turn(g, text):
    out, actions = ReplacingOutput(), []
    res = g.turn(text, out, lambda *a: actions.append(a), threading.Event())
    return res, out.text, actions


class TextStreamTest(unittest.TestCase):
    def feed(self, raw, step):
        got = []
        s = TextStream(got.append)
        for i in range(0, len(raw), step):
            s.feed(raw[i:i + step])
        return "".join(got), s

    def test_pieces_of_every_size(self):
        text = 'Hola "amigo" \\ línea\nnueva — ☕ 😀 日本語'
        raw = json.dumps({"tool": "decline", "args": {"text": text}})  # ascii escapes, incl. a surrogate pair
        for step in (1, 2, 3, 7, 100):
            got, s = self.feed(raw, step)
            self.assertEqual(got, text, step)
            self.assertTrue(s.done)

    def test_other_tools_stay_silent(self):
        got, s = self.feed('{"tool": "lookup_help", "args": {"query": "x"}}', 4)
        self.assertEqual(got, "")
        self.assertIsNone(s.pos)


class GuideTest(unittest.TestCase):
    def test_system_prompt_is_the_trained_one(self):
        with open(CORPUS, encoding="utf-8") as f:
            session = json.loads(f.readline())
        trained = session["messages"][0]["content"]
        # prompt v2.2 (2026-10-01, D54/D55): the trained v2 prompt with rule 2 rewritten, plus two tool lines at the
        # end (make_spreadsheet, web_search) — nothing else differs
        import importlib.util
        saved, sys.argv = sys.argv, ["run_eval.py"]
        spec = importlib.util.spec_from_file_location("re2", os.path.join(ROOT, "training", "eval", "guide", "run_eval.py"))
        r = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(r)
        sys.argv = saved
        system = DATA["guide.json"]["system"]
        # v2.3 (2026-10-06, D84): rule 1 also sends "what is…" about this computer to the help
        self.assertEqual(DATA["guide.json"]["prompt"], "v2.3")
        self.assertEqual(trained.count(r._RULE2_V2), 1)
        expected = trained.replace(r._RULE2_V2, r._RULE2_V22).replace(r._RULE1_V22, r._RULE1_V23)
        # 2026-10-07: three more system checks, so the inspect_system line lists three more topics
        expected = expected.replace(": overview, storage, network, updates, printers, sound, display, battery, drivers\n",
                                    ": overview, storage, network, updates, printers, sound, display, battery, drivers, "
                                    "account, memory, temperature, time\n")
        self.assertTrue(system.startswith(expected + "\n- make_spreadsheet: "), system[len(expected) - 40:len(expected) + 60])
        self.assertIn("\n- web_search: ", system)
        self.assertEqual(system.count("\n"), trained.count("\n") + 2)

    def test_schema_asks_for_the_tool_first(self):
        # llama.cpp writes properties in schema order; "args" before "tool" made the model fill in
        # arguments before choosing the tool (every question became a system check, 2026-09-28)
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            sys.argv, saved = ["gen_data.py", d, ROOT], sys.argv
            try:
                gen_data.main()
            finally:
                sys.argv = saved
            with open(os.path.join(d, "guide.json"), encoding="utf-8") as f:
                schema = json.load(f)["schema"]
        for option in schema["anyOf"]:
            self.assertEqual(list(option["properties"]), ["tool", "args"])

    def test_decline_streams_and_keeps_raw_call(self):
        raw = '{"tool": "decline", "args": {"text": "I can only help with this computer."}}'
        g, b = guide([raw])
        res, out, actions = turn(g, "Who should I vote for?")
        self.assertEqual(out, "I can only help with this computer.")
        self.assertEqual(actions, [])
        self.assertIsNotNone(b.sent[0]["schema"])
        self.assertEqual(g.history[-1], {"role": "assistant", "content": raw})

    def test_tool_turn_has_the_training_shape(self):
        call = '{"tool": "inspect_system", "args": {"topic": "battery"}}'
        g, b = guide([call, "The battery is at 88 %."])
        res, out, actions = turn(g, "How is my battery?")
        self.assertEqual(out, "The battery is at 88 %.")
        self.assertEqual([a[2] for a in actions], ["running", "done"])
        follow = b.sent[1]["messages"][-1]["content"]
        self.assertTrue(follow.startswith("Result of inspect_system:\n{"))
        self.assertTrue(follow.endswith("\n\n" + DATA["guide.json"]["style"]))
        self.assertIsNone(b.sent[1]["schema"])
        # the same layout as the corpus: user, call, result, reply
        self.assertEqual([m["role"] for m in g.history], ["user", "assistant", "user", "assistant"])
        with open(CORPUS, encoding="utf-8") as f:
            session = json.loads(f.readline())
        corpus_follow = next(m["content"] for m in session["messages"] if m["content"].startswith("Result of "))
        self.assertEqual(corpus_follow.split("\n", 1)[0], "Result of inspect_system:")
        # v2.3: the trained instruction with one clause after it (keep the comparison and the cautions), nothing else
        trained_style = DATA["guide.json"]["style"].rsplit(" Keep the help's", 1)[0]
        self.assertTrue(corpus_follow.endswith(trained_style), corpus_follow[-200:])
        self.assertEqual(DATA["guide.json"]["style"], trained_style + " Keep the help's everyday comparison and every "
                                                                     "caution it gives.")

    def test_post_tool_loop_is_stopped_replaced_and_saved_repaired(self):
        call = '{"tool": "inspect_system", "args": {"topic": "battery"}}'
        sentence = "The battery is charging normally."
        g, _ = guide([call, " ".join([sentence] * 3)])
        res, out, _ = replacing_turn(g, "How is my battery?")
        self.assertEqual(out, sentence)
        self.assertEqual(res["reply"], sentence)
        self.assertTrue(res["loop_stopped"])
        self.assertEqual(g.history[-1]["content"], sentence)

    def test_direct_answer_loop_is_stopped_and_saved_as_valid_call(self):
        sentence = "I can help with this computer."
        raw = json.dumps({"tool": "answer", "args": {"text": " ".join([sentence] * 3)}})
        g, _ = guide([raw])
        res, out, _ = replacing_turn(g, "What can you do?")
        self.assertEqual(out, sentence)
        self.assertEqual(res["reply"], sentence)
        self.assertTrue(res["loop_stopped"])
        self.assertEqual(json.loads(g.history[-1]["content"])["args"]["text"], sentence)

    def test_lookup_uses_the_desktop_language_names(self):
        h = DATA["help.json"]
        g = Guide(Scripted(['{"tool": "lookup_help", "args": {"query": "installer un programme"}}', "ok"]),
                  DATA["guide.json"], HelpIndex(h), Tools(h["labels"], h["desktop"], "fr"),
                  {"history_chars": 12000, "cpu_history_chars": 3000})
        res, _, actions = turn(g, "Comment installer un programme ?")
        self.assertIn("Logithèque", actions[1][3])

    def test_trim_drops_whole_turns(self):
        call = '{"tool": "inspect_system", "args": {"topic": "battery"}}'
        g, b = guide([call, "x" * 400] * 6, history_chars=2000)
        for i in range(6):
            turn(g, f"question {i}")
            self.assertEqual(g.history[0]["role"], "user")
            self.assertFalse(g.history[0]["content"].startswith("Result of "))
        self.assertLessEqual(sum(len(m["content"]) for m in g.history[:-4]), 2000)

    def terminal_turn(self, query, text="why didn't this work?"):
        """A turn with a shared terminal whose last command just failed (M3)."""
        import time
        from cin_minai.daemon import terminal
        failed = [{"cmd": "frobnicate --now", "cwd": "/tmp", "exit": 1, "output": "frobnicate: quantum flux too low",
                   "start": time.time() - 5, "end": time.time() - 4}]
        real = terminal.latest
        terminal.latest = lambda n=3: failed
        try:
            g, b = guide([json.dumps({"tool": "lookup_help", "args": {"query": query}}), "Here's what happened."])
            res, _, actions = turn(g, text)
        finally:
            terminal.latest = real
        return res, actions, b

    def test_terminal_context_goes_in_front_and_is_said(self):
        res, actions, b = self.terminal_turn("permission denied running a script")
        sent = b.sent[0]["messages"][-1]["content"]
        self.assertIn("$ frobnicate --now", sent)
        self.assertTrue(sent.endswith("why didn't this work?"))
        self.assertEqual(actions[0][0], "terminal")

    def test_unknown_terminal_error_is_marked_unusual(self):
        res, _, _ = self.terminal_turn("frobnicate quantum flux too low")
        self.assertIn("$ frobnicate --now", res.get("unusual", ""))

    def test_known_terminal_error_isnt_unusual(self):
        res, _, _ = self.terminal_turn("permission denied running a script")
        self.assertNotIn("unusual", res)

    def test_no_terminal_no_unusual(self):
        g, _ = guide(['{"tool": "lookup_help", "args": {"query": "frobnicate quantum flux"}}', "ok"])
        res, _, actions = turn(g, "how do I frobnicate?")
        self.assertNotIn("unusual", res)
        self.assertNotIn("terminal", [a[0] for a in actions])

    def test_bad_json_is_an_error(self):
        from cin_minai.inference.backend import BackendError
        g, _ = guide(['{"tool": '])
        with self.assertRaises(BackendError):
            turn(g, "hi")


if __name__ == "__main__":
    unittest.main()
