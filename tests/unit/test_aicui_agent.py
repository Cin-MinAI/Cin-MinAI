# SPDX-License-Identifier: GPL-3.0-or-later
"""cinminai-code (PLAN D61) with a scripted model: tools, permission prompts, the changelog, goals, events.

    python3 -m unittest tests.unit.test_aicui_agent -v        (from the repo root)
"""

import json
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))

from cin_minai.aicui.agent import Agent, check_file, doing, outline, py_map, salvage, schema, undefined_calls  # noqa: E402


class Scripted:
    """A model that answers from a list: a step (dict), or (raw text, timings) for what a real server might send."""
    def __init__(self, steps):
        self.steps, self.sent = list(steps), []

    def __call__(self, messages, schema=None, max_tokens=0, cancel=None, on_text=None):
        self.sent.append(messages)
        s = self.steps.pop(0)
        raw, timings = s if isinstance(s, tuple) else (json.dumps(s), {})
        if on_text:
            for piece in raw.split(" "):
                on_text(piece + " ")
        return raw, timings


def step(thinking, **action):
    return {"thinking": thinking, "action": action}


@unittest.skipUnless(shutil.which("git"), "the changelog needs git")
class AgentTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        with open(os.path.join(self.root, "app.py"), "w", encoding="utf-8", newline="\n") as f:
            f.write("def add(a, b):\n    return a - b\n")
        self.said = []

    def agent(self, steps, replies=("y",), mode="ask"):
        replies = list(replies)
        return Agent(self.root, Scripted(steps), "Qwen3.8-27B", mode,
                     ask=lambda prompt: replies.pop(0) if replies else "n", say=self.said.append)

    def events(self):
        with open(os.path.join(self.root, ".cinminai", "events.jsonl"), encoding="utf-8") as f:
            return [json.loads(line) for line in f]

    def test_read_edit_tick_answer(self):
        with open(os.path.join(self.root, "test_app.py"), "w", encoding="utf-8") as f:  # a goal needs a test to tick
            f.write("from app import add\nassert add(2, 3) == 5\n")
        a = self.agent([step("Look first.", tool="read", path="app.py"),
                        step("Wrong operator.", tool="edit", path="app.py", old="a - b", new="a + b"),
                        step("Note the goal.", tool="goal_add", text="Fix add()"),
                        step("Done with it.", tool="goal_done", id=1),
                        step("Report.", tool="answer", text="Fixed add(): it subtracted.")])
        self.assertEqual(a.turn("add() is broken"), "Fixed add(): it subtracted.")
        with open(os.path.join(self.root, "app.py"), encoding="utf-8") as f:
            self.assertIn("return a + b", f.read())
        e = a.log.entries()
        self.assertEqual((len(e), e[0]["file"], e[0]["model"]), (1, "app.py", "Qwen3.8-27B"))
        kinds = [x["kind"] for x in self.events() if x["kind"] not in ("timing", "busy", "idle")]  # diagnostics, indicator
        self.assertEqual(sum(1 for x in self.events() if x["kind"] == "timing"), 5)
        self.assertEqual(kinds, ["user", "thinking", "thinking", "change", "thinking", "goals", "thinking", "goals",
                                 "thinking", "answer"])
        self.assertTrue(a.goals.load()[0]["done"])
        self.assertTrue(any("+    return a + b" in s for s in self.said))  # the diff was shown before asking

    def test_no_means_no_and_always_means_always(self):
        a = self.agent([step("", tool="edit", path="app.py", old="a - b", new="a * b"),
                        step("", tool="answer", text="ok")], replies=["n"])
        a.turn("change it")
        with open(os.path.join(self.root, "app.py"), encoding="utf-8") as f:
            self.assertIn("a - b", f.read())
        self.assertEqual(a.log.entries(), [])
        b = self.agent([step("", tool="write", path="x.txt", content="1\n"),
                        step("", tool="write", path="y.txt", content="2\n"),
                        step("", tool="answer", text="ok")], replies=["a"])
        b.turn("two files")
        self.assertTrue(os.path.exists(os.path.join(self.root, "y.txt")))  # asked once, then always

    def test_always_means_no_more_questions_and_aicui_choices_hold_mid_task(self):
        """2026-10-03: "always" was per tool (the next kind of action asked again), and AICUI's Auto never reached
        an agent in the middle of a task."""
        asked = []
        a = Agent(self.root, Scripted([step("", tool="write", path="x.txt", content="1\n"),
                                       step("", tool="run", command="true"),
                                       step("", tool="edit", path="app.py", old="a - b", new="a + b"),
                                       step("", tool="answer", text="ok")]), "m", "ask",
                  ask=lambda p: asked.append(p) or "a", say=self.said.append)
        a.turn("go")
        self.assertEqual(len(asked), 1)
        self.assertEqual(a.mode, "auto")
        self.assertIn({"kind": "session", "mode": "auto", "admin": False},
                      [{k: v for k, v in e.items() if k != "t"} for e in self.events()])
        # AICUI switches back to ask while the agent works: the next change asks again
        b = Agent(self.root, Scripted([step("", tool="write", path="y.txt", content="2\n"),
                                       step("", tool="answer", text="ok")]), "m", "auto",
                  ask=lambda p: asked.append(p) or "n", say=self.said.append)
        with open(os.path.join(self.root, ".cinminai", "session.json"), "w", encoding="utf-8") as f:
            json.dump({"mode": "ask", "admin": False}, f)
        b.turn("go")
        self.assertEqual(len(asked), 2)
        self.assertFalse(os.path.exists(os.path.join(self.root, "y.txt")))

    def test_auto_mode_asks_nothing(self):
        asked = []
        a = Agent(self.root, Scripted([step("", tool="write", path="z.txt", content="z\n"),
                                       step("", tool="answer", text="ok")]), "m", "auto",
                  ask=lambda p: asked.append(p) or "n", say=self.said.append)
        a.turn("go")
        self.assertEqual(asked, [])
        self.assertTrue(os.path.exists(os.path.join(self.root, "z.txt")))

    def test_the_project_folder_is_the_limit(self):
        a = self.agent([step("", tool="read", path="../../etc/passwd"),
                        step("", tool="write", path=".cinminai/goals.json", content="{}"),
                        step("", tool="answer", text="ok")])
        a.turn("try")
        results = [m["content"] for m in a.chat.sent[-1] if m["role"] == "user" and m["content"].startswith("Result")]
        self.assertIn("outside the project folder", results[0])
        self.assertIn("AICUI's own", results[1])

    def test_no_admin_refuses_sudo(self):
        a = self.agent([])
        self.assertIn("aren't allowed", a.run("sudo rm -rf /"))

    def test_a_written_file_is_not_sent_again(self):
        big = "\n".join(f"line {i} " + "x" * 60 for i in range(300))
        a = self.agent([step("Write it.", tool="write", path="big.py", content=big),
                        step("Done.", tool="answer", text="ok")], replies=["y"])
        a.turn("make a big file")
        second = " ".join(m["content"] for m in a.chat.sent[1])
        self.assertNotIn("line 150", second)
        self.assertIn("Earlier I wrote big.py, 300 lines", second)
        self.assertNotIn('"content"', second)  # nothing that looks like file content to imitate

    def test_a_small_context_shrinks_the_history(self):
        steps = [step(f"Look {i}.", tool="read", path="app.py") for i in range(8)] + [step("", tool="answer", text="ok")]
        a = Agent(self.root, Scripted(steps), "m", "ask", ask=lambda p: "y", say=self.said.append, ctx=2400)
        a.turn("read a lot")
        last = a.chat.sent[-1]
        # the system text is ~2,400 characters with the tools of 2026-10-08/09 (need, decline, replace_lines, look);
        # what this checks is the history shrinking, at a context no setup of ours uses (the floor is 8K)
        self.assertLessEqual(sum(len(m["content"]) for m in last), (2400 - 1800 - 300) * 3.3 + 2400)
        self.assertTrue(any(m["content"].startswith("Earlier in this task:") for m in last))

    def test_a_model_error_is_answered_not_a_crash(self):
        def broken(messages, **kw):
            raise RuntimeError("the request exceeds the available context size")
        a = Agent(self.root, broken, "m", "ask", ask=lambda p: "y", say=self.said.append)
        msg = a.turn("go")
        self.assertIn("couldn't go on", msg)
        self.assertIn("exceeds the available context", msg)

    def test_one_progress_rule(self):
        """PLAN §1b closure 3: progress is a change of state; no progress for 6 steps is said (and recorded), again at
        12; a change resets it — one rule instead of separate counters for reads, listings and repeated plans."""
        from cin_minai.aicui.agent import NUDGE_STEPS
        reads = [step(f"Look {i}.", tool="read", path="app.py") for i in range(NUDGE_STEPS)]
        a = Agent(self.root, Scripted(reads + [step("Fix.", tool="edit", path="app.py", old="a - b", new="a + b")]
                                      + [step("Again.", tool="list", path=".") for _ in range(NUDGE_STEPS - 1)]
                                      + [step("", tool="answer", text="ok")]),
                  "m", "auto", say=self.said.append, ctx=16384)
        a.turn("look")
        self.assertEqual(a.read_lines, 200)
        told = [m["content"] for m in a.chat.sent[NUDGE_STEPS] if m["role"] == "user"]
        self.assertTrue(any(f"No progress in the last {NUDGE_STEPS} steps" in t for t in told))
        notes = [e for e in self.events() if e["kind"] == "note" and "No progress" in e["text"]]
        self.assertEqual(len(notes), 1)  # recorded; the edit reset it, and the 5 listings after it stayed under 6
        self.assertIn("return a - b", [m["content"] for m in a.chat.sent[1] if m["role"] == "user"][-1])

    def test_all_steps_kept_when_they_fit(self):
        steps = [step(f"Look {i}.", tool="list", path=".") for i in range(8)] + [step("", tool="answer", text="ok")]
        a = Agent(self.root, Scripted(steps), "m", "ask", ask=lambda p: "y", say=self.said.append, ctx=16384)
        a.turn("look around")
        self.assertFalse(any(m["content"].startswith("Earlier in this task:") for m in a.chat.sent[-1]))

    def test_a_placeholder_is_never_written(self):
        a = self.agent([step("", tool="write", path="gui.py", content="<219 lines written>"),
                        step("", tool="answer", text="ok")], replies=["y"])
        a.turn("write the gui")
        self.assertFalse(os.path.exists(os.path.join(self.root, "gui.py")))
        results = [m["content"] for m in a.chat.sent[-1] if m["role"] == "user" and m["content"].startswith("Result")]
        self.assertIn("isn't file content", results[0])

    def test_schema_lists_every_tool(self):
        tools = [v["properties"]["tool"]["const"] for v in schema()["properties"]["action"]["anyOf"]]
        self.assertEqual(tools, ["read", "list", "search", "edit", "replace_lines", "write", "append", "run",
                                 "web_search", "fetch", "goal_add", "goal_done", "need", "look", "decline", "ask", "answer"])

    def cut_write(self, path, lines, tool="write"):
        """What the server sends when a write runs into the token limit: JSON that stops inside the content."""
        content = "".join(f"line {i}\n" for i in range(1, lines + 1))
        raw = json.dumps(step("The whole GUI.", tool=tool, path=path, content=content + "last half-li"))
        return raw[:raw.rindex("last half-li") + len("last half-li")], {"predicted_n": 4096}

    def test_a_cut_off_write_is_saved_and_continued_with_append(self):
        a = Agent(self.root, Scripted([self.cut_write("gui.py", 40),
                                       step("Go on.", tool="append", path="gui.py", content="line 41\nline 42\n"),
                                       step("", tool="answer", text="ok")]), "m", "auto", say=self.said.append,
                  ctx=16384)
        self.assertEqual((a.answer_tokens, a.write_lines), (4096, 160))
        a.turn("write the gui")
        with open(os.path.join(self.root, "gui.py"), encoding="utf-8") as f:
            text = f.read()
        self.assertEqual(text, "".join(f"line {i}\n" for i in range(1, 43)))  # the half line was left out
        note = a.chat.sent[1][-1]["content"]
        self.assertIn("cut off", note)
        self.assertIn("gui.py now has 40 lines", note)
        self.assertIn("   40 line 40", note)
        self.assertIn("append", note)
        self.assertEqual([e["file"] for e in a.log.entries()], ["gui.py", "gui.py"])  # both in the changelog, with undo
        self.assertEqual([x["kind"] for x in self.events()].count("note"), 1)

    def test_a_cut_off_rewrite_never_replaces_a_good_file(self):
        """2026-10-08: a cut-off new version of a 144-line file was saved over it as 76 lines; later the same day a cut
        rewrite was dropped and tried again three times (6½ min each). Now it's a draft and the file stays whole; the
        draft belongs to its task — finished there, it replaces the file; left unfinished, it's set aside (a 421-line
        draft from a stopped task would have replaced a 732-line file on the next append)."""
        filler = "".join(f"filler line number {i} of the draft\n" for i in range(41, 241))
        a = Agent(self.root, Scripted([self.cut_write("app.py", 40),
                                       step("More.", tool="append", path="app.py", content=filler),
                                       step("Last part.", tool="append", path="app.py",
                                            content="def main():\n    pass\n"),
                                       step("", tool="answer", text="done")]), "m", "auto",
                  say=self.said.append, ctx=16384)
        a.turn("rewrite app.py")
        note = a.chat.sent[1][-1]["content"]
        self.assertIn("being kept as a draft: 40 lines so far; app.py stays as it was", note)
        self.assertIn("240 lines so far", a.chat.sent[2][-1]["content"])  # a full-size part: still the draft
        self.assertEqual(len(os.listdir(os.path.join(self.root, ".cinminai", "cutoffs"))), 1)  # kept for diagnosis
        with open(os.path.join(self.root, "app.py"), encoding="utf-8") as f:
            now = f.read()
        self.assertTrue(now.startswith("line 1\n") and now.endswith("number 240 of the draft\ndef main():\n    pass\n"),
                        now[-80:])  # the part that didn't fill a step completed it, through the changelog
        self.assertFalse(os.path.exists(a.draft_path("app.py")))
        self.assertEqual(a.log.entries()[-1]["file"], "app.py")
        # a task that stops with its draft unfinished: the draft is set aside, the file untouched, the next append real
        a.chat = Scripted([self.cut_write("app.py", 40), step("", tool="answer", text="later")])
        out = a.turn("rewrite it again")
        self.assertIn("was set aside (.cinminai/drafts-stale/)", out)
        self.assertFalse(os.path.exists(a.draft_path("app.py")))
        with open(os.path.join(self.root, "app.py"), encoding="utf-8") as f:
            self.assertEqual(f.read(), now)
        a.chat = Scripted([step("Add.", tool="append", path="app.py", content="# end\n"),
                           step("", tool="answer", text="ok")])
        a.turn("add a line")
        with open(os.path.join(self.root, "app.py"), encoding="utf-8") as f:
            self.assertEqual(f.read(), now + "# end\n")

    def test_a_write_past_the_cap_is_ended_by_aicui(self):
        """2026-10-08: llama-server keeps a string's maxLength only for small values (500 held; 3,000 and 8,800 didn't),
        so the cap is enforced while the reply streams."""
        from cin_minai.inference.backend import Cancelled
        content = "".join(f"    int line{i} = {i};\n" for i in range(400))
        raw = json.dumps(step("Write it.", tool="write", path="big.cpp", content=content))

        def streaming(messages, schema=None, max_tokens=0, cancel=None, on_text=None):
            if "Write it" in json.dumps(messages[-1:]):
                return json.dumps(step("", tool="answer", text="ok")), {}
            for i in range(0, len(raw), 8):
                on_text(raw[i:i + 8])
                if cancel.is_set():
                    raise Cancelled("cancelled")
            return raw, {"predicted_n": len(raw) // 3}
        a = Agent(self.root, streaming, "m", "auto", say=self.said.append, ctx=16384)
        a.content_max = 2000
        a.turn("write big.cpp")
        with open(os.path.join(self.root, "big.cpp"), encoding="utf-8") as f:
            saved = f.read()
        self.assertTrue(1500 < len(saved) <= 2300 and saved.endswith(";\n"), len(saved))  # ended at a whole line
        notes = [e["text"] for e in self.events() if e["kind"] == "note"]
        self.assertIn("filled what one step can hold, so it was ended at its last whole line", notes[0])

    def test_every_write_fits_a_step_and_says_what_the_file_holds(self):
        a = Agent(self.root, Scripted([]), "m", "auto", say=self.said.append, ctx=32768)
        writes = [v for v in schema(a.content_max)["properties"]["action"]["anyOf"]
                  if v["properties"]["tool"]["const"] in ("write", "append")]
        self.assertEqual({w["properties"]["content"]["maxLength"] for w in writes}, {a.content_max})
        self.assertNotIn("maxLength", json.dumps(schema()["properties"]["action"]["anyOf"][0]))  # the default: none
        # a part that reached the cap keeps its whole lines and says to go on
        content = "".join(f"line {i}\n" for i in range(1, 2000))[:a.content_max]
        r = a.change({"tool": "write", "path": "big.txt", "content": content})
        with open(os.path.join(self.root, "big.txt"), encoding="utf-8") as f:
            self.assertTrue(f.read().endswith("\n"))
        self.assertIn("continue with append", r)
        self.assertIn("The file now has", r)

    def test_invented_looking_rows_are_pointed_out(self):
        from cin_minai.aicui.agent import summary
        rows = "".join(f'  {{{i}, "Great Moon of {w}", 7, 2500, 2100}},\n'
                       for i, w in enumerate(["Wind", "Fire", "Ice", "Storm", "Frost", "Gale"]))
        self.assertIn("identical except for one name", summary(rows, rows))
        real = '  {1, "Hydrogen", "H", 1.008},\n  {6, "Carbon", "C", 12.011},\n'
        self.assertEqual(summary(real, real), " The file now has 2 lines.")

    def test_fetching_a_page_always_asks_even_in_auto(self):
        """D86: always asked. What comes is kept whole in the project (2026-10-08: the text alone of a gallery page kept
        7 of 126 entries, and only what fit one step was saved): a page as .txt and .html under sources/, a file as it
        came under assets/; the model is told where."""
        from unittest import mock
        from cin_minai.aicui import intake
        replies = ["n", "a"]
        a = Agent(self.root, Scripted([]), "m", "auto", say=self.said.append, ask=lambda p: replies.pop(0))
        a.goals.add("A list from the source")
        a.given("Use https://example.org/list.")  # the person's own address (the picture comes from the page)
        self.assertIn("only https", a.fetch("http://example.org/x"))
        self.assertEqual(a.fetch("https://example.org/list"), "the person said no to fetching https://example.org/list")
        page = b"<html><body><table><tr><td>1</td><td>Hydrogen</td></tr></table><img alt='Helium' src='he.png'>"
        answers = {"https://example.org/list": (page, "text/html; charset=utf-8"),
                   "https://example.org/he.png": (b"\x89PNG...", "image/png")}
        with mock.patch.object(intake, "get", side_effect=lambda url: answers[url]) as got:
            r = a.fetch("https://example.org/list.")          # "always": this session; the sentence's dot isn't the URL's
            r2 = a.fetch("https://example.org/he.png")          # not asked again
        self.assertEqual(got.call_count, 2)
        self.assertIn("saved https://example.org/list as sources/list.txt and sources/list.html", r)
        self.assertIn("Hydrogen", r)
        with open(os.path.join(self.root, "sources", "list.html"), encoding="utf-8") as f:
            self.assertIn("alt='Helium'", f.read())  # what the text loses, the page keeps
        self.assertIn("saved https://example.org/he.png as assets/he.png", r2)
        self.assertEqual(a.goals.load()[0]["evidence"]["sources"],
                         ["sources/list.txt", "sources/list.html", "assets/he.png"])
        self.assertIn("fetch", [e["kind"] for e in self.events()])
        self.assertIn("beats your memory", a.system())
        self.assertIn("Its 1 pictures are listed at the end of sources/list.txt; the first: https://example.org/he.png", r)

    def test_a_fetch_needs_an_address_from_somewhere(self):
        """2026-10-09: asked for a photo, the coder fetched picture addresses made up from
        memory, the same one seven times, then used a placeholder picture. An address must come from the person, a
        search result or a kept page; the same fetch twice gives the first answer; stand-in sites are refused."""
        from unittest import mock
        from cin_minai.aicui import intake
        from cin_minai.daemon import websearch
        a = Agent(self.root, Scripted([]), "m", "auto", say=self.said.append, ask=lambda p: "a")
        made_up = a.fetch("https://i.imgur.com/abc123.jpg")
        self.assertIn("didn't come from anywhere here", made_up)
        self.assertIn("web_search", made_up)
        self.assertIn("stand-in", a.fetch("https://via.placeholder.com/800x600.png"))
        found = [{"title": "Mountain lakes", "url": "https://pictures.example/wiki/Mountain_lakes", "snippet": "the art"}]
        with mock.patch.object(websearch, "search", return_value=found):
            r = a.web_search("mountain lake photo")
        self.assertIn("kept as sources/search-mountain-lake-photo.txt", r)
        page = b"<html><body><p>Mountain lakes</p><img src='/img/lake.jpg' alt='A lake'></body></html>"
        answers = {"https://pictures.example/wiki/Mountain_lakes": (page, "text/html"),
                   "https://pictures.example/img/lake.jpg": (b"JFIF jpeg", "image/jpeg")}
        with mock.patch.object(intake, "get", side_effect=lambda url: answers[url]) as got:
            self.assertIn("saved", a.fetch("https://pictures.example/wiki/Mountain_lakes"))  # a search result
            self.assertIn("assets/lake.jpg", a.fetch("https://pictures.example/img/lake.jpg"))  # a picture on that page
            again = a.fetch("https://pictures.example/img/lake.jpg")
        self.assertEqual(got.call_count, 2)
        self.assertIn("already fetched", again)

    def test_pytest_style_tests_are_never_passed_unrun(self):
        """Run as a script, a file of bare test_ functions defines them and exits 0: that isn't a pass."""
        with open(os.path.join(self.root, "test_ball.py"), "w") as f:
            f.write("def test_speed():\n    assert 1 == 2\n")
        a = Agent(self.root, Scripted([]), "m", "auto", say=self.said.append)
        ok, report = a.verify()
        self.assertFalse(ok)
        self.assertIn("test_ball.py: NOT RUN — its tests are pytest style", report)

    def test_the_file_list_has_line_counts(self):
        a = Agent(self.root, Scripted([]), "m", "auto", say=self.said.append)
        self.assertIn("app.py (2 lines)", a.system())

    def test_a_failed_step_is_never_shown_as_an_action(self):
        """2026-10-03: shown as an "answer" with the broken text, the model answered with that text and stopped."""
        a = Agent(self.root, Scripted([('{"thinking": "Now I have a full picture', {"predicted_n": 1800}),
                                       ("not json at all", {"predicted_n": 5}),
                                       step("", tool="answer", text="ok")]), "m", "auto", say=self.said.append)
        self.assertEqual(a.turn("go"), "ok")
        sent = a.chat.sent[-1]
        self.assertFalse(any("full picture" in m["content"] for m in sent))
        self.assertFalse(any(m["role"] == "assistant" for m in sent[2:]))
        self.assertIn("cut off", sent[-2]["content"])
        self.assertIn("Nothing was saved", sent[-2]["content"])
        self.assertIn("wasn't valid JSON", sent[-1]["content"])

    def test_salvage_and_doing(self):
        self.assertIsNone(salvage('{"thinking": "x", "action": {"tool": "write", "path": "a.py", "content": "one'))
        whole = json.dumps(step("", tool="write", path="a.py", content="1\n2\n3\n4\n5\n6\n"))
        self.assertIsNone(salvage(whole[:-1]))  # the content is whole: something after it was cut, not the file
        tricky = 'x = "a\\nb"\n' * 6 + 'print("\\\\'  # escaped quotes and backslashes, cut inside an escape
        raw = json.dumps(step("", tool="append", path='b"q.js', content=tricky))
        tool, path, content = salvage(raw[:raw.rindex("\\\\") + 1]) or ("", "", "")
        self.assertEqual((tool, path, content), ("append", 'b"q.js', 'x = "a\\nb"\n' * 6))
        self.assertEqual(doing('{"thinking": "hm", "action": {"tool": "write", "path": "gui.py", "con'), "writing gui.py")
        self.assertEqual(doing('{"thinking": "hm'), "thinking")

    def test_the_projects_venv_is_used(self):
        venv = os.path.join(self.root, ".venv")
        os.makedirs(os.path.join(venv, "bin"))
        for d in ("pygame_ce-2.5.8.dist-info", "pip-24.0.dist-info"):
            os.makedirs(os.path.join(venv, "lib", "python3.12", "site-packages", d))
        open(os.path.join(venv, "bin", "python"), "w").close()
        a = self.agent([])
        self.assertIn("installed: pygame_ce 2.5.8)", a.system())
        self.assertNotIn("pip 24.0", a.system())
        if shutil.which("bash") and os.name == "posix":
            a.mode, a.sandbox = "auto", False
            out = a.run('echo "$VIRTUAL_ENV|$SDL_VIDEODRIVER"; echo "$PATH" | cut -d: -f1')
            self.assertIn(f"{venv}|dummy", out)
            self.assertIn(os.path.join(venv, "bin"), out)

    def test_the_prompt_start_stays_put_for_the_cache(self):
        """The server reuses what's unchanged from the start of the prompt: a new file (in the system text's file
        list) and a summary that grows every step both made it re-read everything (2026-10-03)."""
        steps = [step(f"Write {i}.", tool="write", path=f"f{i}.py", content=f"x = {i}\n" + "# pad\n" * 120)
                 for i in range(14)] + [step("", tool="answer", text="ok")]
        a = Agent(self.root, Scripted(steps), "m", "auto", say=self.said.append, ctx=6000)
        a.answer_tokens = 1000
        a.turn("many files")
        sent = a.chat.sent
        self.assertTrue(all(s[0] == sent[0][0] for s in sent))  # the system text, as at the start
        summaries = [next((m["content"] for m in s if m["content"].startswith("Earlier in this task:")), None)
                     for s in sent]
        changes = sum(1 for x, y in zip(summaries, summaries[1:]) if x != y)
        self.assertGreaterEqual(summaries.count(None), 2)  # nothing summarized while everything fits
        self.assertLessEqual(changes, len(sent) // 3)  # then in jumps, not every step

    def test_characters_a_token_from_the_server(self):
        class Counted(Scripted):
            def __call__(self, messages, **kw):
                raw, _ = super().__call__(messages, **kw)
                return raw, {"prompt_n": sum(len(m["content"]) for m in messages) / 3, "cache_n": 0}
        a = Agent(self.root, Counted([step("", tool="list", path="."), step("", tool="answer", text="ok")]), "m",
                  "auto", say=self.said.append)
        a.turn("go")
        self.assertAlmostEqual(a.cpt, 2.85)  # 3 characters a token as counted, less 5 % to be safe

    def test_outline_keeps_the_map_of_a_read(self):
        py = "\n".join(f"{n:5} {l}" for n, l in enumerate(
            ["import os", "", "class Game:", "    def __init__(self):", "        self.x = 1", "", "def main():",
             "    Game()"], 1)) + "\n… 40 more lines (read from line 9)"
        self.assertEqual(outline(py), "3: class Game:\n4: def __init__(self):\n7: def main():\n"
                                      "(+40 more lines not read)")
        html = "\n".join(f"{n:5} {l}" for n, l in enumerate(
            ["<html>", "<style>", ".card {", "  color: red;", "}", "</style>", "<h1>Anna &amp; Ben</h1>",
             '<section id="rsvp">', "<form>", "</form>", "</section>"], 1))
        self.assertIn("3: .card {", outline(html))
        self.assertIn("7: <h1>Anna &amp; Ben</h1>", outline(html))
        self.assertIn('8: <section id="rsvp">', outline(html))
        self.assertIn("9: <form>", outline(html))

    def test_old_reads_become_maps_before_steps_are_cut(self):
        """2026-10-03: a whole project didn't fit 16K, and compaction dropped every read; now the oldest reads
        become their maps first, the reasoning stays, and the last two reads stay whole."""
        body = "\n".join([f"def f{i}():\n    return {i}" + ("\n    # pad " + "x" * 25) * 30 for i in range(12)])
        for i in range(7):  # 7 reads overflow 8K; 2 whole reads and 5 maps fit under 60 %
            with open(os.path.join(self.root, f"m{i}.py"), "w", encoding="utf-8") as f:
                f.write(body)
        steps = [step(f"Read m{i}.", tool="read", path=f"m{i}.py") for i in range(7)] + \
            [step("", tool="answer", text="ok")]
        a = Agent(self.root, Scripted(steps), "m", "auto", say=self.said.append, ctx=8192)
        a.answer_tokens = 1800
        a.turn("read them all")
        last = a.chat.sent[-1]
        results = [m["content"] for m in last if m["content"].startswith("Result: ")]
        self.assertEqual(a.cut, 0)  # nothing summarized away: maps were enough
        self.assertTrue(results[0].startswith("Result: (shortened to its map"))
        self.assertIn("1: def f0():", results[0])
        self.assertNotIn("# pad", results[0])
        self.assertIn("# pad", results[-1])  # the newest read stays whole

    def test_a_summarized_read_keeps_its_map_and_can_be_read_again(self):
        a = Agent(self.root, Scripted([]), "m", "auto", say=self.said.append, ctx=16384)
        read = {"tool": "read", "path": "app.py"}
        a.steps.append({"did": {"thinking": "", "action": read}, "result": a.do(read)})
        a.steps.append({"did": {"thinking": "", "action": read}, "result": a.do(read)})
        summary = a.messages("go", a.steps, cut=2)[2]["content"]
        self.assertIn("read app.py → map:", summary)
        self.assertIn("1: def add(a, b):", summary)
        a.lite = 2  # both now maps: reading again is allowed
        self.assertIn("return a - b", a.do(read))

    def test_every_change_is_checked(self):
        a = Agent(self.root, Scripted([]), "m", "auto", say=self.said.append)
        dup = "class UI:\n    def draw(self):\n        pass\n\n    def draw(self):\n        return 1\n"
        r = a.change({"tool": "write", "path": "ui.py", "content": dup})
        self.assertIn("logged as change", r)  # the salvage path looks for this
        self.assertIn("draw is defined twice in class UI (lines 2-3 and 5-6)", r)
        r = a.change({"tool": "write", "path": "half.py", "content": "def f(:\n"})
        self.assertIn("doesn't compile", r)
        self.assertIn("finish it first", r)
        self.assertIn("nothing defined twice", a.change({"tool": "write", "path": "ok.py", "content": "x = 1\n"}))
        page = "<html><body>\n<section id='rsvp'>\n<form>\n<p>Name\n</section>\n</div>\n</body></html>\n"
        r = a.change({"tool": "write", "path": "index.html", "content": page})
        self.assertIn("<form> on line 3 is never closed", r)
        self.assertIn("</div> on line 6 closes nothing", r)
        self.assertNotIn("Check", a.change({"tool": "write", "path": "notes.txt", "content": "hi\n"}))

    @unittest.skipUnless(shutil.which("bash") and os.name == "posix", "runs commands")
    def test_a_goal_is_ticked_only_when_the_checks_pass(self):
        """2026-10-03: "all four split tests pass" with one never run; tests green while the game crashed at start."""
        with open(os.path.join(self.root, "test_app.py"), "w", encoding="utf-8") as f:
            f.write("from app import add\nassert add(2, 2) == 4, 'add is wrong'\n")
        with open(os.path.join(self.root, "main.py"), "w", encoding="utf-8") as f:
            f.write("import app\nprint(app.add(1, 1))\n")
        g = Agent(self.root, Scripted([]), "m", "auto", say=self.said.append).goals.add("Fix add")
        a = Agent(self.root, Scripted([step("", tool="goal_done", id=g["id"]),
                                       step("", tool="edit", path="app.py", old="a - b", new="a + b"),
                                       step("", tool="goal_done", id=g["id"]),
                                       step("", tool="answer", text="ok")]), "m", "auto", say=self.said.append)
        a.bwrap = False  # the test machine may have no bwrap
        a.turn("fix it")
        results = [m["content"] for m in a.chat.sent[-1] if m["content"].startswith("Result: ")]
        self.assertIn("NOT ticked", results[0])
        self.assertIn("test_app.py: FAILED", results[0])
        self.assertIn("add is wrong", results[0])
        self.assertIn("ticked. Checks:", results[2])
        self.assertIn("main.py: started and finished", results[2])
        self.assertTrue(a.goals.load()[0]["done"])

    def test_it_keeps_going_while_it_makes_progress(self):
        """Ian, 2026-10-03: as automated as possible — no hard step limit while it makes progress; a handover in the
        chat every 60 steps."""
        steps = [step(f"Change {i}.", tool="write", path=f"f{i % 5}.py", content=f"x = {i}\n") for i in range(65)] \
            + [step("", tool="answer", text="all done")]
        a = Agent(self.root, Scripted(steps), "m", "auto", say=self.said.append)
        self.assertEqual(a.turn("lots of work"), "all done")
        handovers = [e["text"] for e in self.events() if e["kind"] == "handover"]
        self.assertEqual(len(handovers), 1)
        self.assertIn("60 steps so far", handovers[0])
        self.assertIn("f4.py (change 60:", handovers[0])

    def test_it_stops_when_stuck_and_says_where_it_is(self):
        g = Agent(self.root, Scripted([]), "m", "auto", say=self.said.append).goals.add("Fix add")
        steps = [step("Change it.", tool="edit", path="app.py", old="a - b", new="a + b")] + \
            [step("Looking again.", tool="list", path=".") for _ in range(20)]
        a = Agent(self.root, Scripted(steps), "m", "auto", say=self.said.append)
        msg = a.turn("go")
        self.assertIn("I've gone 15 steps without changing a file", msg)
        self.assertIn("app.py (change 1: +1 −1)", msg)
        self.assertIn(f"Goals: 0 of 1 done; next: {g['id']}. Fix add", msg)
        self.assertIn("Last thing I was doing: Looking again.", msg)
        self.assertEqual(len(a.chat.sent), 16)  # 1 change + 15 steps without progress

    def test_a_big_file_shows_its_shape_and_a_block_goes_by_its_lines(self):
        """2026-10-08: one class held two generations of methods and main() called a class that didn't exist; read in
        pieces for 12 steps, the model never saw it. The map and the check say it from the code; replace_lines removes
        the old block without copying it."""
        old_gen = "".join(f"    def handle_{i}(self):\n        return {i}\n\n" for i in range(60))
        new_gen = "".join(f"    def handle_{i}(self, pos):\n        return pos\n\n" for i in range(3))
        text = ("import pygame\n\n\nclass GameWindow:\n    def __init__(self):\n        self.x = 1\n\n" + old_gen
                + new_gen + "\ndef main():\n    app = GameApp()\n    app.run()\n")
        with open(os.path.join(self.root, "gui.py"), "w") as f:
            f.write(text)
        a = Agent(self.root, Scripted([]), "m", "auto", say=self.said.append)
        a.reads, a.cut, a.lite, a.steps = {}, 0, 0, []
        shape = py_map(text)
        self.assertIn("class GameWindow 4-", shape)
        self.assertIn("handle_0 8+", shape)
        self.assertIn("(TWICE)", shape)
        self.assertIn("def main", shape)
        problems = check_file(os.path.join(self.root, "gui.py"))
        self.assertIn("handle_0 is defined twice in class GameWindow", problems)
        self.assertIn("GameApp (called on line", problems)
        read = a.do({"tool": "read", "path": "gui.py"})
        self.assertTrue(read.startswith("Map of gui.py ("), read[:80])  # the whole shape first
        first, last = 8, 7 + old_gen.count("\n")
        out = a.do({"tool": "replace_lines", "path": "gui.py", "first": first, "last": last, "new": ""})
        self.assertIn("logged as change", out)
        self.assertIn(f"Lines after {last} are now {last - first + 1} lower (old line {last + 1} is line {first})", out)
        self.assertNotIn("defined twice", out)
        self.assertIn("GameApp", out)  # still said until it's fixed
        with open(os.path.join(self.root, "gui.py")) as f:
            now = f.read()
        self.assertEqual(now.count("def handle_0"), 1)
        self.assertIn("def handle_0(self, pos)", now)
        self.assertIn("aren't in it", a.do({"tool": "replace_lines", "path": "gui.py", "first": 5, "last": 999,
                                            "new": "x"}))
        self.assertIn("isn't defined or imported", check_file(os.path.join(self.root, "gui.py")))
        self.assertEqual(undefined_calls("from x import *\nfoo()\n"), [])  # can't know: say nothing
        self.assertEqual(undefined_calls("def f(cb):\n    cb()\n    print(len([]))\n"), [])

    def test_a_new_turn_starts_with_the_projects_map_and_its_problems(self):
        """2026-10-08: told to continue, the model re-read six files in pieces and spent its 15 steps before changing
        anything, twice; the problem it had to fix was in a file it never reached."""
        os.makedirs(os.path.join(self.root, "src"))
        with open(os.path.join(self.root, "src", "engine.cpp"), "w") as f:
            f.write("#include \"engine.h\"\n\nstruct Match {\n    int lp;\n};\n\nint Engine::draw(int p) {\n"
                    "    if (p) {\n        return 1;\n    }\n    return 0;\n}\n\nvoid start_turn(Match& d)\n{\n}\n")
        with open(os.path.join(self.root, "gui.py"), "w") as f:
            f.write("class GameWindow:\n    def run(self):\n        pass\n\n    def run(self):\n        pass\n\n\n"
                    "def main():\n    GameApp().run()\n")
        a = Agent(self.root, Scripted([]), "m", "auto", say=self.said.append, ctx=16384)
        text = a.system()
        problems = text.index("Problems the checks find in the files now:")
        self.assertIn("run is defined twice in class GameWindow", text[problems:])
        self.assertIn("GameApp (called on line 10)", text[problems:])
        self.assertIn("class GameWindow 1-6: 1 method; TWICE: run 2-3 and 5-6", text)
        self.assertIn("struct Match 3, Engine::draw 7, start_turn 14", text)
        self.assertLess(problems, text.index("The project's map"))  # problems first: what "continue" needs

    def test_the_write_cap_follows_what_the_model_measures(self):
        """2026-10-08: dense list data ran ~2.1 characters a token; the cap assumed 2.6 and a write overran the step."""
        data = '    {"Steel Hammer", 3000, 2500, 8},\n' * 60
        dense = step("Data.", tool="append", path="items.cpp", content=data)
        raw = json.dumps(dense)
        a = Agent(self.root, Scripted([(raw, {"predicted_n": int(len(raw) / 2.1)}), step("", tool="answer", text="ok")]),
                  "m", "auto", say=self.said.append, ctx=16384)
        before = a.content_max
        a.turn("go")
        self.assertLess(a.content_max, before)
        self.assertAlmostEqual(a.content_cpt, 0.92 * 2.1, places=1)
        self.assertLessEqual(a.content_max, (a.answer_tokens - 700) * 2.0)  # what fits 4,096 tokens of it

    def test_a_listing_shows_the_whole_project(self):
        """2026-10-08: the 27B listed "." 13 times — it saw only two folders, never the files in them."""
        os.makedirs(os.path.join(self.root, "include"))
        os.makedirs(os.path.join(self.root, "src"))
        with open(os.path.join(self.root, "include", "item.h"), "w") as f:
            f.write("struct Item {};\n")
        with open(os.path.join(self.root, "src", "items.cpp"), "w") as f:
            f.write("#include \"item.h\"\n")
        a = Agent(self.root, Scripted([]), "m", "auto", say=self.said.append)
        first = a.do({"tool": "list", "path": "."})
        self.assertIn("include/item.h  (16 bytes)", first)
        self.assertIn("src/items.cpp", first)

    def test_a_web_pages_files_must_use_each_others_names(self):
        """2026-10-03, the wedding page: CSS for .nav/.menu/.menu-btn, HTML with #menu/#menu-toggle, a script that
        looked up #menu-btn and stopped there — the RSVP button never worked, and goals 3 and 5 were ticked."""
        a = Agent(self.root, Scripted([]), "m", "auto", say=self.said.append)
        a.change({"tool": "write", "path": "index.html", "content":
                  '<nav id="menu"><button id="menu-toggle">=</button><ul id="menu-links"></ul></nav>\n'
                  '<form id="rsvp-form" class="card"></form>\n'})
        r = a.change({"tool": "write", "path": "style.css", "content":
                      ".card { padding: 1rem; }\n.menu-btn { display: none; }\n#menu-links.open { display: flex; }\n"
                      "@media (max-width: 700px) {\n  .nav .menu-btn { display: block; }\n}\n"})
        self.assertIn("style.css styles .menu-btn, .nav", r)
        self.assertNotIn(".open", r)  # added by the script below: not a problem
        r = a.change({"tool": "write", "path": "script.js", "content":
                      "const b = document.getElementById('menu-btn');\n"
                      "document.querySelector('#menu-links').classList.toggle('open');\n"})
        self.assertIn("script.js looks up #menu-btn — not in the HTML", r)
        self.assertNotIn(".open", r)
        ok, report = a.verify()
        self.assertFalse(ok)
        self.assertIn("index.html and its CSS/JS: PROBLEMS", report)
        a.change({"tool": "write", "path": "style.css", "content": ".card { padding: 1rem; }\n#menu-toggle { }\n"
                                                                   "#menu-links.open { display: flex; }\n"})
        a.change({"tool": "write", "path": "script.js", "content":
                  "document.getElementById('menu-toggle');\n"
                  "document.querySelector('#menu-links').classList.toggle('open');\n"})
        ok, report = a.verify()
        self.assertTrue(ok, report)
        self.assertIn("names and tags line up", report)

    def test_the_card_is_asked_for_before_every_load_and_a_slow_fallback_is_said(self):
        """2026-10-03: the daemon reloaded its guide between the agent's start and its first request; the 27B went
        to the processor at 1.1 tok/s and nothing said so."""
        from cin_minai.aicui import agent as mod
        unloads, events, said = [], [], []

        class Backend:
            def __init__(self):
                self.loaded, self.profile = False, None

            def alive(self):
                return self.loaded

            def chat(self, *a, **k):
                self.loaded = True
                self.profile = mod_profile
                return "{}", {}
        from cin_minai.inference.llamacpp import Profile
        mod_profile = Profile("cpu", "none", 4096, "0", "on the processor (slower): the graphics card's memory is busy")
        real = mod.unload_guide
        mod.unload_guide = lambda: unloads.append(1)
        try:
            b = Backend()
            chat = mod.card_minded(b, lambda kind, **d: events.append((kind, d)), said.append)
            chat([])
            chat([])
            b.loaded = False  # the server stopped (Stop, a crash): asked again before the reload
            chat([])
        finally:
            mod.unload_guide = real
        self.assertEqual(len(unloads), 2)
        self.assertEqual([k for k, _ in events], ["note"])  # said once, not every step
        self.assertIn("on the processor", events[0][1]["text"])
        self.assertIn("graphics card's memory is busy", events[0][1]["text"])

    def test_progress_events_and_idle(self):
        a = Agent(self.root, Scripted([step("", tool="answer", text="ok")]), "m", "auto", say=self.said.append)
        a.turn("go")
        kinds = [x["kind"] for x in self.events()]
        self.assertEqual(kinds[-1], "idle")
        self.assertIn("busy", kinds)


if __name__ == "__main__":
    unittest.main()
