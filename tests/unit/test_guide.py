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
        # v2.3 (2026-10-06, D84): rule 1 also sends "what is…" about this computer to the help;
        # v2.4 (2026-10-07, D88): one more tool line at the end, compose_email;
        # v2.6 (2026-10-22, D68): rule 2's world questions split (calculate, wikipedia, web_search), two more tool lines;
        # v2.7 (2026-10-23): rule 2's subjects widened (things, animals, foods, looks), only rule 2 changes
        self.assertEqual(DATA["guide.json"]["prompt"], "v2.7")
        self.assertEqual(trained.count(r._RULE2_V2), 1)
        expected = trained.replace(r._RULE2_V2, r._RULE2_V22).replace(r._RULE1_V22, r._RULE1_V23)
        self.assertEqual(expected.count(r._RULE2_WORLD_V22), 1)
        expected = expected.replace(r._RULE2_WORLD_V22, r._RULE2_WORLD_V27)
        # 2026-10-07: three more system checks, so the inspect_system line lists three more topics
        expected = expected.replace(": overview, storage, network, updates, printers, sound, display, battery, drivers\n",
                                    ": overview, storage, network, updates, printers, sound, display, battery, drivers, "
                                    "account, memory, temperature, time\n")
        self.assertTrue(system.startswith(expected + "\n- make_spreadsheet: "), system[len(expected) - 40:len(expected) + 60])
        self.assertIn("\n- web_search: ", system)
        self.assertIn("\n- compose_email: ", system)
        self.assertIn("\n- calculate: ", system)
        self.assertIn("\n- wikipedia: ", system)
        self.assertEqual(system.count("\n"), trained.count("\n") + 5)

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

    def test_decline_streams_and_keeps_the_reply(self):
        raw = '{"tool": "decline", "args": {"text": "I can only help with this computer."}}'
        g, b = guide([raw])
        res, out, actions = turn(g, "Who should I vote for?")
        self.assertEqual(out, "I can only help with this computer.")
        self.assertEqual(actions, [])
        self.assertIsNotNone(b.sent[0]["schema"])
        self.assertEqual(g.history[-1], {"role": "assistant", "content": "I can only help with this computer."})

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
        # the turn itself in the corpus layout (user, call, result); the history keeps the talk alone (2026-10-23)
        self.assertEqual([m["role"] for m in b.sent[1]["messages"][1:]], ["user", "assistant", "user"])
        self.assertEqual(g.history, [{"role": "user", "content": "How is my battery?"},
                                     {"role": "assistant", "content": "The battery is at 88 %."}])
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

    def test_direct_answer_loop_is_stopped_and_saved_repaired(self):
        sentence = "I can help with this computer."
        raw = json.dumps({"tool": "answer", "args": {"text": " ".join([sentence] * 3)}})
        g, _ = guide([raw])
        res, out, _ = replacing_turn(g, "What can you do?")
        self.assertEqual(out, sentence)
        self.assertEqual(res["reply"], sentence)
        self.assertTrue(res["loop_stopped"])
        self.assertEqual(g.history[-1]["content"], sentence)

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


class NotOnThisComputerTest(unittest.TestCase):
    """Ian, 2026-10-23: questions go to Wikipedia on this computer first; without it, "This is what I have in memory
    about x" and more offered online: Wikipedia itself for a subject, then the web; the web when the help had nothing."""

    ARTICLE = {"query": "Raspberry Pi", "shelf": "Wikipedia (on this computer)",
               "sources": [{"n": 1, "title": "Raspberry Pi", "url": "https://en.wikipedia.org/wiki/Raspberry_Pi",
                            "text": "The Raspberry Pi is a series of small single-board computers."}]}

    def setUp(self):
        from cin_minai.daemon import guide as G, library, offline
        self.lib, self.offline = library, offline
        self.saved = (library.shelves_for, library.read_shelves, library.read_online, offline.on, FakeTools.online)
        self.shelf = {}  # title -> article; {} = a shelf without the article
        library.shelves_for = lambda lang: [{"lang": lang}]
        library.read_shelves = lambda shelves, q: self.found(q)
        offline.on = lambda: False
        FakeTools.online = lambda self: True

    def tearDown(self):
        (self.lib.shelves_for, self.lib.read_shelves, self.lib.read_online, self.offline.on,
         FakeTools.online) = self.saved

    def found(self, q):
        if q not in self.shelf:
            raise self.lib.LibraryError("not on the shelf")
        return self.shelf[q]

    def test_wikipedia_on_this_computer(self):
        self.shelf = {"Raspberry Pi": self.ARTICLE}
        g, b = guide(['{"tool": "wikipedia", "args": {"title": "Raspberry Pi"}}', "A small computer [1]."])
        res, text, actions = turn(g, "What's a Raspberry Pi?")
        self.assertEqual(text, "A small computer [1].")
        self.assertNotIn("proposal", res)
        self.assertIn("Raspberry Pi", b.sent[1]["messages"][0]["content"])  # answered from the article

    def test_not_on_the_shelf_from_memory_then_wikipedia(self):
        g, b = guide(['{"tool": "wikipedia", "args": {"title": "Coral snake"}}', "It has red, yellow and black bands."])
        res, text, actions = turn(g, "What does a coral snake look like?")
        self.assertTrue(text.startswith("This is what I have in memory about Coral snake:\n\nIt has red"), text)
        self.assertIn("look online for more information?", text)
        self.assertEqual(res["reply"], text)
        offer = [a for a in actions if a[2] == "proposal"]
        self.assertEqual(json.loads(offer[0][3])["provider"], "Wikipedia")
        self.assertEqual(g.searches[res["proposal"]]["tool"], "wikipedia")
        sent = b.sent[1]["messages"][-1]["content"]
        self.assertIn("no article on that", sent)
        self.assertIn("a few plain sentences", sent)

    def test_nothing_in_the_help_reads_the_shelf(self):
        self.shelf = {"Raspberry Pi": self.ARTICLE}
        g, b = guide(['{"tool": "lookup_help", "args": {"query": "Raspberry Pi"}}', "A small computer [1]."])
        res, text, actions = turn(g, "Whats a Raspberry Pi?")
        self.assertEqual(res["tool"], "wikipedia")
        self.assertEqual([a[:3] for a in actions if a[0] == "wikipedia"][0], ("wikipedia", {"query": "Raspberry Pi"},
                                                                               "running"))

    def test_nothing_in_the_help_or_the_shelf_offers_the_web(self):
        g, b = guide(['{"tool": "lookup_help", "args": {"query": "newborn weight"}}', "About 3.5 kg."])
        res, text, actions = turn(g, "How much does the average newborn weigh?")
        self.assertTrue(text.startswith("This is what I have in memory about newborn weight:"), text)
        self.assertEqual(json.loads([a for a in actions if a[2] == "proposal"][0][3])["provider"] != "Wikipedia", True)
        self.assertEqual(g.searches[res["proposal"]]["tool"], "web_search")

    def test_a_card_that_fits_is_answered_as_before(self):
        g, b = guide(['{"tool": "lookup_help", "args": {"query": "install a program"}}', "1. Open Software Manager."])
        res, text, actions = turn(g, "How do I install a program?")
        self.assertEqual(text, "1. Open Software Manager.")
        self.assertNotIn("proposal", res)

    def test_offline_mode_says_how_to_go_online(self):
        self.offline.on = lambda: True
        g, b = guide(['{"tool": "wikipedia", "args": {"title": "Coral snake"}}', "It has bands."])
        res, text, actions = turn(g, "What does a coral snake look like?")
        self.assertIn("It has bands.", text)
        self.assertNotIn("proposal", res)
        self.assertFalse([a for a in actions if a[2] == "proposal"])

    def test_the_article_doesnt_say_from_memory_then_wikipedia(self):
        self.shelf = {"Coral snake": {**self.ARTICLE, "sources": [{**self.ARTICLE["sources"][0], "title": "Coral snake",
                                                                    "text": "Coral snakes are elapid snakes."}]}}
        g, b = guide(['{"tool": "wikipedia", "args": {"title": "Coral snake"}}', "NOT_IN_PAGES",
                      "Red, yellow and black bands."])
        res, text, actions = turn(g, "What does a coral snake look like?")
        self.assertTrue(text.startswith("The article doesn't say. This is what I have in memory about Coral snake:\n\n"
                                        "Red, yellow"), text)
        self.assertNotIn("NOT_IN", text)
        self.assertEqual(g.searches[res["proposal"]]["tool"], "wikipedia")  # Wikipedia itself next
        self.assertEqual(res["reply"], text)
        self.assertEqual(g.history[-1]["content"], text)
        self.assertEqual(g.history[0], {"role": "user", "content": "What does a coral snake look like?"})

    def test_the_web_pages_dont_say_from_memory_nothing_more(self):
        g, b = guide(['{"tool": "web_search", "args": {"query": "pho"}}', "  NOT_IN_PAGES", "A noodle soup."])
        res, _, _ = turn(g, "What is pho?")
        from cin_minai.daemon import websearch
        saved = websearch.gather
        websearch.gather = lambda q, lang: {"query": q, "sources": [{"n": 1, "title": "Make", "url": "https://make.com/",
                                                                      "text": "Automation."}]}
        try:
            out = []
            res2 = g.search(res["proposal"], "", out.append, lambda *a: None, threading.Event())
        finally:
            websearch.gather = saved
        self.assertTrue("".join(out).startswith("The pages don't say. This is what I have in memory about pho:"))
        self.assertNotIn("proposal", res2)
        self.assertNotIn("look online", "".join(out))

    def test_the_history_is_the_talk_alone(self):
        # 2026-10-23: calls kept in the history were copied (after one web search, every subject went to the web)
        g, b = guide(['{"tool": "web_search", "args": {"query": "Cuban Missile Crisis"}}', "It began in 1962 [1].",
                      '{"tool": "inspect_system", "args": {"topic": "battery"}}', "The battery is at 88 %."])
        res, offered, _ = turn(g, "Why did the Cuban Missile Crisis happen?")
        from cin_minai.daemon import websearch
        saved = websearch.gather
        websearch.gather = lambda q, lang: {"query": q, "sources": [{"n": 1, "title": "Cuban Missile Crisis",
                                                                      "url": "https://example.org/", "text": "1962."}]}
        try:
            g.search(res["proposal"], "", lambda t: None, lambda *a: None, threading.Event())
        finally:
            websearch.gather = saved
        self.assertNotEqual(offered, "It began in 1962 [1].")
        # Search answered in the offer's place: one turn, the question and the answer
        self.assertEqual(g.history, [{"role": "user", "content": "Why did the Cuban Missile Crisis happen?"},
                                     {"role": "assistant", "content": "It began in 1962 [1]."}])
        turn(g, "How is my battery?")
        self.assertEqual(g.history[2:], [{"role": "user", "content": "How is my battery?"},
                                         {"role": "assistant", "content": "The battery is at 88 %."}])
        for m in g.history:
            self.assertFalse(m["content"].startswith(("{", "Result of ")), m)

    def test_a_follow_up_is_searched_with_its_subject(self):
        # NVMe 2026-10-23: "Did he ever say why he did it?" was searched as typed, and answered from the wrong pages
        standalone = "Did Mark David Chapman ever say why he shot John Lennon?"
        g, b = guide(['{"tool": "answer", "args": {"text": "Mark David Chapman shot John Lennon."}}',
                      '{"tool": "web_search", "args": {"query": "Did he ever say why he did it?"}}', standalone,
                      "He said he wanted to be famous [1]."])
        turn(g, "Who shot John Lennon?")
        self.assertEqual(len(b.sent), 1)  # a first question: no rewrite
        res, _, _ = turn(g, "Did he ever say why he did it?")
        self.assertIn("User: Who shot John Lennon?\nAssistant: Mark David Chapman shot John Lennon.",
                      b.sent[2]["messages"][0]["content"])
        self.assertIsNone(b.sent[2]["schema"])
        self.assertEqual(g.searches[res["proposal"]]["query"], standalone)  # the card shows what is sent
        from cin_minai.daemon import websearch
        saved = websearch.gather
        websearch.gather = lambda q, lang: {"query": q, "sources": [{"n": 1, "title": "Murder of John Lennon",
                                                                      "url": "https://example.org/", "text": "Fame."}]}
        try:
            g.search(res["proposal"], "", lambda t: None, lambda *a: None, threading.Event())
        finally:
            websearch.gather = saved
        self.assertIn("The user's question: " + standalone, b.sent[3]["messages"][0]["content"])
        # the history keeps the person's own words
        self.assertEqual(g.history[2], {"role": "user", "content": "Did he ever say why he did it?"})

    def test_a_follow_up_query_naming_the_subject_is_kept(self):
        from cin_minai.daemon.intent import follow_up_query
        self.assertEqual(follow_up_query("Where was John Lennon shot?", "Where did he get shot?",
                                         "Where did Mark David Chapman shoot John Lennon?"), "Where was John Lennon shot?")
        self.assertEqual(follow_up_query("Did he ever say why he did it?", "Did he ever say why he did it?",
                                         "Did Chapman ever say why he shot Lennon?"),
                         "Did Chapman ever say why he shot Lennon?")
        self.assertEqual(follow_up_query("weather Madrid", "What's the weather in Madrid today?",
                                         "What's the weather in Madrid today?"), "weather Madrid")

    def test_a_late_marker_clears_what_was_shown(self):
        # the 4B on the NVMe (2026-10-23): "The pages do not answer the question. NOT_IN_PAGES"
        self.shelf = {"Infant": {**self.ARTICLE, "sources": [{**self.ARTICLE["sources"][0], "title": "Infant"}]}}
        g, b = guide(['{"tool": "wikipedia", "args": {"title": "Infant"}}',
                      "The pages do not answer the question. NOT_IN_PAGES", "About 3.5 kg."])
        res, text, _ = replacing_turn(g, "How much does the average newborn weigh?")
        self.assertTrue(text.startswith("The article doesn't say. This is what I have in memory about Infant:\n\n"
                                        "About 3.5 kg."), text)
        self.assertNotIn("pages do not", text)

    def test_a_reply_that_only_starts_like_the_marker_is_shown(self):
        from cin_minai.daemon.guide import Gate
        for reply in ("NOTE: the bands are red.", "No, it isn't.", "N"):
            got = []
            gate = Gate(got.append)
            for i in range(0, len(reply), 2):
                gate(reply[i:i + 2])
            gate.finish()
            self.assertEqual("".join(got), reply)
            self.assertFalse(gate.marked)

    def test_a_long_conversation_goes_back_to_its_last_turns(self):
        g, b = guide(['{"tool": "answer", "args": {"text": "ok"}}'] * 10)
        for i in range(9):
            turn(g, f"question {i}")
        self.assertEqual(g.turns(), 9)
        turn(g, "question 9")  # trimmed first: 9 > 8 turns, back to the last 4, then this one
        self.assertEqual(g.turns(), 5)
        self.assertEqual(g.history[0]["content"], "question 5")
        sent = [m["content"] for m in b.sent[-1]["messages"] if m["role"] == "user"]
        self.assertEqual(sent, ["question 5", "question 6", "question 7", "question 8", "question 9"])

    def test_wikipedia_online_has_nothing_then_the_web(self):
        def none(q, lang):
            raise self.lib.NoArticle("Wikipedia has no article on that")
        self.lib.read_online = none
        g, b = guide(['{"tool": "wikipedia", "args": {"title": "Zzyzx gadget"}}', "I don't know much."])
        res, _, _ = turn(g, "What is a zzyzx gadget?")
        out, actions = [], []
        res2 = g.search(res["proposal"], "", out.append, lambda *a: actions.append(a), threading.Event())
        self.assertIn("Wikipedia has no article on that", "".join(out))
        self.assertEqual(g.searches[res2["proposal"]]["tool"], "web_search")
        self.assertEqual(res2["sources"], 0)


if __name__ == "__main__":
    unittest.main()
