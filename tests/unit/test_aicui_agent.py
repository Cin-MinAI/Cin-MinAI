# SPDX-License-Identifier: GPL-3.0-or-later
"""cinminai-code (PLAN D61) with a scripted model: tools, permission prompts, the changelog, goals, events.

    python3 -m unittest tests.unit.test_aicui_agent -v        (from the repo root)
"""

import json
import os
import shutil
import sys
import tempfile
import time
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

    def test_git_that_changes_the_repository_is_aicuis_and_looking_stays_the_models(self):
        # test20 (2026-10-20): the Senior's `git init && git add .` staged .cinminai/ for publishing
        a = self.agent([])
        for command in ("git init && git add .", "git add -A", "cd site && git commit -m x", "git -C . push",
                        "git remote add origin https://github.com/x/y.git", "ls; git config user.name x"):
            self.assertIn("AICUI's GitHub menu", a.run(command), command)
        self.assertFalse(os.path.isdir(os.path.join(self.root, ".git")))
        for command in ("git status", "git log --oneline -3", "git diff", "echo digit add"):
            self.assertNotIn("AICUI's GitHub menu", a.run(command), command)

    def test_a_model_writes_no_github_workflow(self):
        a = self.agent([step("", tool="write", path=".github/workflows/deploy.yml", content="on: push\n"),
                        step("", tool="write", path="./.github/workflows/x.yml", content="on: push\n"),
                        step("", tool="answer", text="ok")], replies=["y"])
        a.turn("publish it")
        results = [m["content"] for m in a.chat.sent[-1] if m["role"] == "user" and m["content"].startswith("Result")]
        self.assertTrue(all("GitHub workflows run code" in r for r in results[:2]), results)
        self.assertFalse(os.path.exists(os.path.join(self.root, ".github")))

    def test_a_written_file_is_not_sent_again(self):
        big = "\n".join(f"line {i} " + "x" * 60 for i in range(300))
        a = self.agent([step("Write it.", tool="write", path="big.py", content=big),
                        step("Done.", tool="answer", text="ok")], replies=["y"])
        a.turn("make a big file")
        second = " ".join(m["content"] for m in a.chat.sent[1])
        self.assertNotIn("line 150", second)
        self.assertIn("Earlier I wrote big.py, 300 lines", second)
        self.assertNotIn('"content"', second)  # nothing that looks like file content to imitate

    def test_the_system_text_leaves_room_at_8k(self):
        """The coder's tools and rules, before the project's files: a list of tools, never a procedure (2026-10-10: written
        as "three steps" and a numbered method, the Senior recited the plan as its thinking every step; test4's tool
        list got a new thought each step). 3,156 on 2026-10-09; 3,689 with distill and the facts rule."""
        from cin_minai.aicui.agent import JUNIOR_SYSTEM, SENIOR_B, SYSTEM
        self.assertLessEqual(len(SYSTEM), 4000)
        self.assertLessEqual(len(SENIOR_B), 1300)  # 1,218 with follow_up, brief, lfd, permit (tool lines, not steps)
        self.assertLessEqual(len(JUNIOR_SYSTEM), 1400)
        for words in ("- distill (", "never type them from memory", "a site you've fetched"):
            self.assertIn(words, SYSTEM)
        for words in ("FETCH:", "three steps", "1. "):
            self.assertNotIn(words, SYSTEM + SENIOR_B)

    def test_a_small_context_shrinks_the_history(self):
        steps = [step(f"Look {i}.", tool="read", path="app.py") for i in range(8)] + [step("", tool="answer", text="ok")]
        a = Agent(self.root, Scripted(steps), "m", "ask", ask=lambda p: "y", say=self.said.append, ctx=2400)
        a.turn("read a lot")
        last = a.chat.sent[-1]
        # what this checks is the history shrinking, at a context no setup of ours uses (the floor is 8K): the
        # messages after the system text (bounded on its own: test_the_system_text_leaves_room_at_8k)
        self.assertEqual(last[0]["role"], "system")
        self.assertLessEqual(sum(len(m["content"]) for m in last[1:]), (2400 - 1800 - 300) * 3.3)
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
                                 "web_search", "fetch", "download", "distill", "errand", "goal_add", "goal_done", "need", "look", "ask",
                                 "answer"])

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
        self.assertIn("saved https://example.org/list as sources/list.txt (page text: read and distill this) and "
                      "sources/list.html (page markup: for a script, not for reading)", r)
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

    def test_download_checks_every_address_and_asks_once(self):
        """Ian, 2026-10-09: the web through tools only, each with its own safeguards. Many files, one approval; each
        address checked as a fetch's; kept under assets/ in the folder asked for."""
        from unittest import mock
        from cin_minai.aicui import intake
        asked = []
        a = Agent(self.root, Scripted([]), "m", "auto", say=self.said.append,
                  ask=lambda p: (asked.append(p), "y")[1])
        a.given("the pictures: https://pics.example/a.jpg and https://pics.example/b.jpg")
        urls = ["https://pics.example/a.jpg", "https://pics.example/b.jpg", "https://made.up.example/c.jpg",
                "http://pics.example/d.jpg", "https://via.placeholder.com/1.png"]
        with mock.patch.object(intake, "get", side_effect=lambda u: (b"JFIF" + u.encode(), "image/jpeg")):
            said = a.do({"tool": "download", "urls": urls, "folder": "cards"})
        self.assertEqual(len(asked), 1)
        self.assertIn("Download 2 files from pics.example into assets/cards/", asked[0])
        self.assertIn("downloaded 2 of 5 into assets/cards/", said)
        self.assertIn("refused 3", said)
        self.assertIn("didn't come from anywhere here", said)
        self.assertEqual(sorted(os.listdir(os.path.join(self.root, "assets", "cards"))), ["a.jpg", "b.jpg"])
        nothing = a.do({"tool": "download", "urls": ["https://made.up.example/c.jpg"], "folder": "../../etc"})
        self.assertIn("nothing downloaded", nothing)

    def test_a_pdf_comes_in_with_its_text_as_a_source(self):
        """For style B's rulebook (Ian, 2026-10-10: "make sure the full ruleset is there and get it offline"): a PDF is
        kept as it came, and its text kept beside it under sources/ for either model to read."""
        from unittest import mock
        from cin_minai.aicui import intake
        a = Agent(self.root, Scripted([]), "m", "auto", say=self.said.append, ask=lambda p: "a")
        a.given("the rules: https://rules.example/rulebook.pdf")
        with mock.patch.object(intake, "get", return_value=(b"%PDF-1.4 ...", "application/pdf")), \
                mock.patch.object(intake, "pdf_text", return_value="PHASES\nDraw Phase: draw 1 card.\n"):
            said = a.fetch("https://rules.example/rulebook.pdf")
        self.assertIn("saved https://rules.example/rulebook.pdf as assets/rulebook.pdf", said)
        self.assertIn("its text (3 lines) is in sources/rulebook.txt", said)
        with open(os.path.join(self.root, "sources", "rulebook.txt"), encoding="utf-8") as f:
            text = f.read()
        self.assertTrue(text.startswith("From https://rules.example/rulebook.pdf"))
        self.assertIn("Draw Phase: draw 1 card.", text)

    @unittest.skipUnless(shutil.which("pdftotext"), "needs pdftotext (poppler-utils)")
    def test_a_real_pdfs_text(self):
        from cin_minai.aicui import intake
        pdf = (b"%PDF-1.1\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
               b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 300 100]/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>"
               b">>endobj\n4 0 obj<</Length 44>>stream\nBT /F1 12 Tf 10 50 Td (Battle Phase rules) Tj ET\nendstream "
               b"endobj\n5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF")
        kept = intake.save(self.root, "https://rules.example/rules.pdf", pdf, "application/pdf")
        self.assertEqual(kept["files"], ["assets/rules.pdf", "sources/rules.txt"])
        self.assertIn("Battle Phase rules", kept["text"])

    def test_where_the_ai_stands_is_kept_after_every_step(self):
        """Ian, 2026-10-09: power cuts from storms. The request, its state and its last steps are on disk after every
        step; a finished request says so; one cut off mid-way still says "working"."""
        a = Agent(self.root, Scripted([step("Fix it.", tool="write", path="b.py", content="x = 1\n"),
                                       step("", tool="answer", text="done")]), "m", "auto", say=self.said.append)
        a.turn("make b.py")
        with open(os.path.join(self.root, ".cinminai", "checkpoint.json")) as f:
            cp = json.load(f)
        self.assertEqual((cp["request"], cp["state"], cp["changed"]), ("make b.py", "finished", ["b.py"]))
        self.assertIn("Fix it.", cp["thoughts"])
        a.checkpoint("the next request", "working", [])
        with open(os.path.join(self.root, ".cinminai", "checkpoint.json")) as f:
            self.assertEqual(json.load(f)["state"], "working")  # what AICUI finds after a power cut

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

    def test_a_picture_in_the_project_is_looked_at_never_read_as_text(self):
        """2026-10-12: the person put screenshots in the project; the cloud model had no way to see them."""
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("no PIL")
        os.makedirs(os.path.join(self.root, "screenshots"))
        Image.new("RGB", (40, 30), "green").save(os.path.join(self.root, "screenshots", "board.png"))
        a = Agent(self.root, Scripted([]), "m", "auto", say=self.said.append)
        self.assertIn("is a picture: look at it", a.do({"tool": "read", "path": "screenshots/board.png"}))
        seen = []
        a.reader = lambda: (lambda messages, **kw: (seen.append(messages) or "A blank green board.", {}))
        report = a.do({"tool": "look", "target": "picture", "address": "screenshots/board.png",
                       "question": "What does the board show?"})
        self.assertIn("A blank green board.", report)
        self.assertEqual(seen[0][0]["content"][0]["type"], "image_url")

    def test_no_errands_offered_without_a_helper(self):
        a = Agent(self.root, Scripted([]), "m", "auto", say=self.said.append)
        self.assertIn("errand", a.excluded())
        a.errand = lambda *args: "queued"
        self.assertNotIn("errand", a.excluded())

    def test_an_empty_answer_is_sent_back_never_shown_blank(self):
        """2026-10-12: Haiku put its answer in its thinking and answered with no text; the person saw a blank reply."""
        a = Agent(self.root, Scripted([step("The deck needs three kinds.", tool="answer", text=""),
                                       step("", tool="answer", text="The deck needs a card of each kind.")]),
                  "m", "auto", say=self.said.append)
        self.assertEqual(a.turn("what's wrong?"), "The deck needs a card of each kind.")
        self.assertIn("Your answer was empty", a.chat.sent[-1][-1]["content"])
        b = Agent(self.root, Scripted([step("All three kinds are missing.", tool="answer", text="")] * 3),
                  "m", "auto", say=self.said.append)
        self.assertEqual(b.turn("what's wrong?"), "All three kinds are missing.")  # its thinking, never a blank

    def test_a_lead_works_the_open_goals_before_it_answers(self):
        """Ian, 2026-10-25 (test16): told to complete the session goals, Haiku re-planned (refused twice), fixed one,
        said "Goal 10 is done" without ticking it, and answered "Next I will…"; the run ended there."""
        with open(os.path.join(self.root, "test_app.py"), "w", encoding="utf-8") as f:
            f.write("from app import add\nassert add(2, 3) == 5\n")
        a = Agent(self.root, Scripted([step("A new plan.", tool="plan", goals=[
                                           {"text": "Fix add()", "from_outside": [], "files": [], "who": "senior"}]),
                                       step("Wrong operator.", tool="edit", path="app.py", old="a - b", new="a + b"),
                                       step("Report.", tool="answer", text="add() is fixed. Next I will do the docs."),
                                       step("It's done.", tool="goal_done", id=1),
                                       step("Report.", tool="answer", text="Goal 1 ticked."),  # new progress: again
                                       step("Report.", tool="answer", text="add() is fixed; goal 1 ticked."),
                                       ]), "m", "auto", say=self.said.append)
        a.role = "senior"
        a.goals.add("Fix add()", by="user")
        a.goals.add("Write the docs", by="user")
        self.assertEqual(a.turn("complete the session goals"), "add() is fixed; goal 1 ticked.")
        sent = "\n".join(m["content"] for m in a.chat.sent[-1])
        self.assertIn("2 open; the next: 1. Fix add()", sent)  # the plan's refusal points at the goals
        self.assertIn("Goals are still open: 1. Fix add(); 2. Write the docs", sent)
        self.assertTrue(a.goals.load()[0]["done"])
        b = Agent(self.root, Scripted([step("", tool="answer", text="The docs come next.")]), "m", "auto",
                  say=self.said.append)
        b.role = "senior"
        self.assertEqual(b.turn("what's next?"), "The docs come next.")  # a question, no work: answered at once

    def test_a_goal_is_held_to_its_own_files_and_the_last_to_the_whole_project(self):
        """Ian, 2026-10-25 (test16): "fix the engine's compile errors" stayed open: tests/ was empty and the GUI ran off
        the screen, nothing that goal's work could change."""
        with open(os.path.join(self.root, "gui.py"), "w", encoding="utf-8") as f:
            f.write("raise SystemExit('no window toolkit')\n")
        with open(os.path.join(self.root, "main.py"), "w", encoding="utf-8") as f:
            f.write("import gui\n")
        with open(os.path.join(self.root, "test_app.py"), "w", encoding="utf-8") as f:
            f.write("from app import add\nassert add(2, 3) == 5\n")  # names app.py: it fails while add subtracts
        a = Agent(self.root, Scripted([]), "m", "auto", say=self.said.append)
        engine = a.goals.add("The engine builds", by="user", files=["engine.py"])
        app = a.goals.add("add() adds", by="user", files=["app.py"])
        a.goals.add("The window opens", by="user", files=["gui.py"])
        ok, report = a.verify(engine)
        self.assertTrue(ok, report)  # no test names engine.py, and the stop isn't in its files: said, not held
        self.assertIn("no test names this goal's files", report)
        self.assertIn("not in this goal's files", report)
        self.assertFalse(a.verify(app)[0])  # its own test fails
        with open(os.path.join(self.root, "gui.py"), "w", encoding="utf-8") as f:
            f.write("raise RuntimeError('no display')\n")  # its traceback names gui.py
        ok, report = a.verify(a.goals.load()[2])
        self.assertFalse(ok)
        self.assertIn("CRASHED in this goal's files", report)
        for g in (engine, app):
            a.goals.set_done(g["id"], True)
        ok, report = a.verify(a.goals.load()[2])  # the last goal open: the whole project's checks
        self.assertFalse(ok)
        self.assertIn("test_app.py: FAILED", report)
        self.assertIn("CRASHED (exit 1)", report)

    def test_a_source_kept_for_one_goal_counts_for_all(self):
        """Ian, 2026-10-25 (test16): the deck pages came in for goal 1, and goal 13's parser that reads them was locked."""
        a = Agent(self.root, Scripted([]), "m", "auto", say=self.said.append)
        a.goals.add("Parse the decks", by="ai", files=["parse.py"], from_outside=[{"what": "deck lists", "kind": "text"}])
        self.assertIn("belongs to goal 1", a.needs_block("parse.py"))
        os.makedirs(os.path.join(self.root, "sources"))
        with open(os.path.join(self.root, "sources", "Starter-Deck.txt"), "w", encoding="utf-8") as f:
            f.write("Stone Giant\n")
        self.assertEqual(a.needs_block("parse.py"), "")

    def test_a_draft_that_grows_is_progress(self):
        a = Agent(self.root, Scripted([]), "m", "auto", say=self.said.append)
        a.drafted = {}
        part = {"tool": "append", "path": "big.py"}
        self.assertTrue(a.progressed(part, "The new version of big.py … kept as a draft: 70 lines so far"))
        self.assertTrue(a.progressed(part, "The new version of big.py … kept as a draft: 140 lines so far"))
        self.assertFalse(a.progressed(part, "The new version of big.py … kept as a draft: 140 lines so far"))

    def test_a_lead_reads_without_nags_and_its_juniors_question_comes_first(self):
        """2026-10-25 (test16): "no progress" fired on a lead checking its junior's work; Haiku answered its junior's
        question with answer, which goes to the person."""
        a = Agent(self.root, Scripted([step("", tool="read", path="app.py")] * 8 + [
                                       step("", tool="answer", text="Use the text files."),
                                       step("", tool="answer", text="Waiting on you for the card details.")]),
                  "m", "auto", say=self.said.append)
        a.role = "senior"
        a.inbox = [(640, "task", "task 640 (write parse.py) — STUCK POINT from your junior (asks the senior). It said: "
                                 "use the text files?")]
        self.assertEqual(a.turn("go on"), "Waiting on you for the card details.")
        sent = "\n".join(m["content"] for m in a.chat.sent[-1])
        self.assertNotIn("No progress in the last", sent)
        self.assertIn("Your junior's question (task 640) waits for your word", sent)

    def test_one_version_of_a_file_a_draft_and_the_file(self):
        """2026-10-25 (test16): read gave only a draft's end, to the lead and to the junior asking for line 234; an edit
        to the file was then undone when a part finished the old draft over it (379 lines became 269); a second write
        restarted a 514-line draft at 249."""
        a = Agent(self.root, Scripted([]), "m", "auto", say=self.said.append)
        a.role = "junior"
        a.content_max = 200
        line = "# " + "x" * 60 + "\n"
        self.assertIn("kept as a draft", a.do({"tool": "write", "path": "app.py", "content": line * 4}))
        self.assertIn("isn't started over", a.do({"tool": "write", "path": "app.py", "content": line * 4}))
        self.assertIn("The draft from line 2:\n    2 # xx", a.do({"tool": "read", "path": "app.py", "start": 2}))
        lead = Agent(self.root, Scripted([]), "m", "auto", say=self.said.append)
        lead.role = "senior"
        seen = lead.do({"tool": "read", "path": "app.py"})
        self.assertIn("being drafted by your junior", seen)
        self.assertIn("    2     return a - b", seen)  # the file as it is
        with open(os.path.join(self.root, "app.py"), "a", encoding="utf-8") as f:
            f.write("# changed meanwhile\n")
        self.assertIn("changed since its draft began", a.do({"tool": "append", "path": "app.py", "content": "y = 1\n"}))
        with open(os.path.join(self.root, "app.py"), encoding="utf-8") as f:
            self.assertIn("# changed meanwhile", f.read())  # the file stands
        self.assertFalse(os.path.exists(a.draft_path("app.py")))
        a.do({"tool": "write", "path": "app.py", "content": line * 4})  # a new draft…
        self.assertIn("logged as change", a.do({"tool": "edit", "path": "app.py", "old": "a - b", "new": "a + b"}))
        self.assertFalse(os.path.exists(a.draft_path("app.py")))  # …out of date once the file is edited

    def test_edits_for_files_that_exist_parts_for_new_ones(self):
        a = Agent(self.root, Scripted([]), "m", "auto", say=self.said.append)
        a.edits_only, a.made_here = True, set()
        self.assertIn("app.py exists: change it with edit", a.do({"tool": "write", "path": "app.py", "content": "x\n"}))
        self.assertIn("logged as change", a.do({"tool": "write", "path": "new.py", "content": "a = 1\n"}))
        self.assertIn("logged as change", a.do({"tool": "append", "path": "new.py", "content": "b = 2\n"}))

    def test_a_replan_merges_with_the_goals_there(self):
        """2026-10-25 (test16): after LFD the new plan copied the person's nine goals as 14–21."""
        a = Agent(self.root, Scripted([]), "m", "auto", ask=lambda p: "y", say=self.said.append)
        a.role = "senior"
        a.goals.add("Design and implement the C++ engine with turn phases", by="user", files=["engine/old.h"])
        a.replan_ok = True
        said = a.make_plan([{"text": "Design and implement the C++ engine with turn phases.", "from_outside": [],
                             "files": ["engine/phases.cpp"], "who": "junior"},
                            {"text": "Write the README", "from_outside": [], "files": ["README.md"], "who": "senior"}])
        goals = a.goals.load()
        self.assertEqual([g["text"][:12] for g in goals], ["Design and i", "Write the RE"])
        self.assertEqual(goals[0]["files"], ["engine/phases.cpp"])  # the person's goal, with the plan's files
        self.assertIn("Already goals, kept as they are", said)

    def test_the_web_tools_say_what_the_session_allows(self):
        """2026-10-25 (test16): in No permissions Haiku stopped to ask for a download; the list said "each asked first"."""
        self.assertIn("each asked first", Agent(self.root, Scripted([]), "m", "ask", say=self.said.append).system())
        for mode in ("auto", "none"):
            self.assertIn("allowed in this session: go ahead",
                          Agent(self.root, Scripted([]), "m", mode, say=self.said.append).system())

    def test_the_checkpoint_is_the_leads(self):
        """2026-10-25 (test16): Resume gave Haiku the junior's old task 643 as the person's request."""
        a = Agent(self.root, Scripted([]), "m", "auto", say=self.said.append)
        a.role = "junior"
        a.checkpoint("[goal] Task 643 from your senior", "stopped", [])
        self.assertFalse(os.path.exists(os.path.join(self.root, ".cinminai", "checkpoint.json")))

    def test_a_new_project_keeps_its_first_request_and_a_screenshots_folder(self):
        """Ian, 2026-10-12: he kept both by hand for test10 (origprompt, screenshots/), and the cloud finished from them."""
        a = Agent(self.root, Scripted([step("", tool="answer", text="ok"), step("", tool="answer", text="ok")]),
                  "m", "auto", say=self.said.append)
        a.turn("Make a card game.")
        a.turn("Make the cards bigger.")
        with open(os.path.join(self.root, "original-request.txt"), encoding="utf-8") as f:
            self.assertEqual(f.read(), "Make a card game.\n")  # the first request only, in the person's words
        self.assertTrue(os.path.isdir(os.path.join(self.root, "screenshots")))
        self.assertIn("isn't changed", a.do({"tool": "write", "path": "original-request.txt", "content": "x"}))
        self.assertIn("original-request.txt is the person's first request", a.system())
        self.assertIn("screenshots/ is for pictures of the program", a.system())
        with open(os.path.join(self.root, "screenshots", "board.png"), "wb") as f:
            f.write(b'PNG')  # only its name counts here
        self.assertIn("screenshots/ has 1 picture of the program from the person (newest: board.png)", a.system())

    def test_the_next_request_knows_what_the_last_one_read_and_changed(self):
        """2026-10-12: Haiku stopped at the step limit and, told to continue, re-read main.py 17 times in 12 minutes."""
        a = Agent(self.root, Scripted([step("Read the adder.", tool="read", path="app.py"),
                                       step("It subtracts.", tool="edit", path="app.py", old="a - b", new="a + b"),
                                       step("", tool="answer", text="Fixed."),
                                       step("Check it again.", tool="read", path="app.py"),
                                       step("", tool="answer", text="ok")]), "m", "auto", say=self.said.append)
        a.turn("fix add")
        a.turn("continue")
        last = a.chat.sent[-1]
        carried = [m["content"] for m in last if m["role"] == "assistant" and "What I did in that request" in m["content"]]
        self.assertTrue(carried)
        self.assertIn("read: app.py", carried[0])
        self.assertIn("changed: app.py", carried[0])
        self.assertIn("It subtracts.", carried[0])
        # a new session (a restart: the cloud, another team) starts from the checkpoint
        b = Agent(self.root, Scripted([step("", tool="answer", text="ok")]), "m", "auto", say=self.said.append)
        b.turn("go on")
        self.assertIn("Where the last session left off", b.chat.sent[-1][-1]["content"])
        self.assertIn("go on", b.chat.sent[-1][-1]["content"])

    def test_a_screenshot_older_than_the_last_change_is_said_to_be_old(self):
        os.makedirs(os.path.join(self.root, "screenshots"))
        shot = os.path.join(self.root, "screenshots", "board.png")
        with open(shot, "wb") as f:
            f.write(b"PNG")
        os.utime(shot, (time.time() - 600, time.time() - 600))
        a = Agent(self.root, Scripted([]), "m", "auto", say=self.said.append)
        self.assertIn("it shows the program as it was", a.system())
        os.utime(shot, None)
        self.assertNotIn("it shows the program as it was", a.system())

    def test_a_question_to_the_person_waits_for_one_result_at_most(self):
        """2026-10-13: Haiku's question waited unseen while its contributor worked on a brief; 2026-10-14 (Ian): it asked
        the person how its junior's task was going. A question waits for the junior's next result, ASK_WAIT_S at most."""
        from unittest import mock
        from cin_minai.aicui import agent as A
        mock.patch.object(A, "ASK_WAIT_S", 1).start()
        self.addCleanup(mock.patch.stopall)
        a = Agent(self.root, Scripted([step("", tool="ask", question="Which decks?")]), "m", "auto",
                  say=self.said.append)
        a.errands_pending = lambda: True  # a contributor still working, for as long as it takes
        start = time.time()
        self.assertEqual(a.turn("get the images"), "Which decks?")
        self.assertLess(time.time() - start, 15)  # one second of waiting, plus a busy machine's slack (5.6 s seen)

    def test_an_address_in_a_kept_json_answer_is_known(self):
        os.makedirs(os.path.join(self.root, "sources"))
        with open(os.path.join(self.root, "sources", "cardinfo.txt"), "w") as f:
            f.write('{"image_url":"https:' + chr(92) + '/' + chr(92) + '/images.example.com' + chr(92) + '/cards'
                    + chr(92) + '/1.jpg"}')
        a = Agent(self.root, Scripted([]), "m", "auto", say=self.said.append)
        self.assertTrue(a.known_address("https://images.example.com/cards/1.jpg"))
        self.assertFalse(a.known_address("https://elsewhere.example.org/cards/1.jpg"))

    def test_reading_a_file_with_a_draft_in_progress_shows_the_draft(self):
        """2026-10-13, test13: a long write was kept as a draft; the model read the old, empty file, decided nothing
        had happened and wrote it all again — three times, 150 s each."""
        with open(os.path.join(self.root, "cards.json"), "w") as f:
            f.write("[]\n")
        a = Agent(self.root, Scripted([]), "m", "auto", say=self.said.append)
        a.content_max = 200
        big = "[\n" + "".join(f'  {{"name": "Card {i}"}},\n' for i in range(40))
        said = a.do({"tool": "write", "path": "cards.json", "content": big})
        self.assertIn("kept as a draft", said)
        seen = a.do({"tool": "read", "path": "cards.json"})
        self.assertIn("has a draft in progress", seen)
        self.assertIn("Don't start over", seen)
        self.assertIn("the file on disk still has its old 1 lines", seen)
        self.assertIn('"name": "Card', seen)

    def test_work_given_to_a_contributor_is_progress(self):
        """2026-10-12: Haiku leading gave seven tasks in fifteen steps and was stopped for "no progress"."""
        a = Agent(self.root, Scripted([]), "m", "auto", say=self.said.append)
        self.assertTrue(a.progressed({"tool": "assign"}, "task 3 given to your junior (write rules.py); rules.py is held"))
        self.assertTrue(a.progressed({"tool": "brief"}, "task 4 given to your junior (brief: a.py — what's in it)"))
        self.assertTrue(a.progressed({"tool": "follow_up"}, "sent to your junior: it reads it at its next step on task 3"))
        self.assertTrue(a.progressed({"tool": "review_task"}, "task 3 accepted"))
        self.assertFalse(a.progressed({"tool": "assign"}, "error: rules.py is already held by task 3"))

    def test_three_unusable_replies_in_a_row_end_the_task(self):
        """2026-10-12: a cloud model sent 25 unusable replies in a row, each one paid for, until the stuck limit."""
        a = Agent(self.root, Scripted([("not json", {})] * 3 + [step("", tool="answer", text="never")]), "m", "auto",
                  say=self.said.append)
        self.assertIn("last three replies weren't steps I could use", a.turn("go"))
        self.assertEqual(len(a.chat.sent), 3)
        self.assertEqual(a.stopped, "error")

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
        for i in range(7):  # 7 reads overflow 8K; 2 whole reads and 5 maps fit under 60 % of the history's room
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

    def test_an_address_may_follow_the_pattern_of_a_site_already_fetched(self):
        """Ian, 2026-10-10: "let it find patterns." Fetched /pack/<one set>, a model may try /pack/<another set> on the same
        site; an address on a site nothing came from is still one from memory."""
        from cin_minai.aicui import intake
        a = Agent(self.root, Scripted([]), "m", "auto", say=self.said.append)
        intake.save(self.root, "https://cards.example/pack/Set%20One", b"<html><body>one</body></html>", "text/html")
        self.assertTrue(a.known_address("https://cards.example/pack/Starter%20Deck"))
        self.assertFalse(a.known_address("https://made.up.example/pack/Starter%20Deck"))

    def test_commands_reach_the_internet_never_in_ask_and_after_one_question_in_auto(self):
        """Ian, 2026-10-10 (test9, run with no permissions: the coder wrote its own downloader): "make sure that doesnt
        happen in normal ask mode. In auto, probably one time ask for that tool." """
        from unittest import mock
        ran, asked = [], []
        ask = Agent(self.root, Scripted([]), "m", "ask", say=self.said.append, ask=lambda p: "y")
        ask.sandbox = True
        with mock.patch.object(ask, "execute", side_effect=lambda *a, **k: (ran.append((a, k)), (0, "ok"))[1]):
            self.assertIn("commands have no internet here", ask.do({"tool": "run", "command": "curl x", "network": True}))
            ask.do({"tool": "run", "command": "ls"})
        self.assertEqual(ran[-1][1], {"network": False})  # Ask: never the internet
        self.assertNotIn("`network` true", ask.system())
        auto = Agent(self.root, Scripted([]), "m", "auto", say=self.said.append,
                     ask=lambda p: (asked.append(p), "y")[1])
        auto.sandbox = True
        self.assertIn("`network` true for a command that needs the internet", auto.system())
        with mock.patch.object(auto, "execute", side_effect=lambda *a, **k: (ran.append((a, k)), (0, "ok"))[1]):
            auto.do({"tool": "run", "command": "python3 get.py", "network": True})
            auto.do({"tool": "run", "command": "python3 get.py --more", "network": True})
            auto.do({"tool": "run", "command": "ls"})
        self.assertEqual(len([p for p in asked if "use the internet" in p]), 1)  # asked once for the session
        self.assertEqual([k["network"] for _, k in ran[-3:]], [True, True, False])
        no = Agent(self.root, Scripted([]), "m", "auto", say=self.said.append, ask=lambda p: "n")
        no.sandbox = True
        self.assertIn("the person said no to internet for commands",
                      no.do({"tool": "run", "command": "curl x", "network": True}))
        argv = []
        with mock.patch("subprocess.Popen", side_effect=lambda a, **k: (argv.append(a), mock.Mock(
                returncode=0, pid=0, communicate=lambda timeout=None: ("", "")))[1]):
            auto.execute("true", 5, True)
            auto.execute("true", 5, True, network=True)
        self.assertIn("--unshare-net", argv[0])
        self.assertNotIn("--unshare-net", argv[1])

    def test_a_sandboxed_command_sees_no_keys(self):
        """The keyring's bus, key folders and files, the person's screen and key-named variables are out of reach of a
        sandboxed command (2026-10-20: one reached the keyring service); the project still shows through."""
        from unittest import mock
        from cin_minai.aicui import agent as ag
        home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, home, True)
        os.makedirs(os.path.join(home, ".ssh"))
        os.makedirs(os.path.join(home, ".local/share/keyrings"))
        open(os.path.join(home, ".git-credentials"), "w").close()
        walls = ag.secret_walls(home, uid=os.getpid() + 10**6)  # a /run/user that doesn't exist: no wall for it
        self.assertEqual(walls, ["--tmpfs", os.path.join(home, ".ssh"), "--tmpfs", os.path.join(home, ".local/share/keyrings"),
                                 "--ro-bind", "/dev/null", os.path.join(home, ".git-credentials")])
        env = ag.without_secrets({"PATH": "/usr/bin", "HOME": home, "DBUS_SESSION_BUS_ADDRESS": "unix:path=/run/user/1/bus",
                                  "DISPLAY": ":0", "OPENAI_API_KEY": "x", "GH_TOKEN": "x", "MY_SECRET": "x",
                                  "KEYBOARD_LAYOUT": "us", "LANG": "C.UTF-8"})
        self.assertEqual(sorted(env), ["HOME", "KEYBOARD_LAYOUT", "LANG", "PATH"])
        a = Agent(self.root, Scripted([]), "m", "auto", say=self.said.append, ask=lambda p: "y")
        argv = []
        with mock.patch("subprocess.Popen", side_effect=lambda a, **k: (argv.append((a, k["env"])), mock.Mock(
                returncode=0, pid=0, communicate=lambda timeout=None: ("", "")))[1]), \
             mock.patch.dict(os.environ, {"DBUS_SESSION_BUS_ADDRESS": "unix:path=/x", "ANTHROPIC_API_KEY": "x"}), \
             mock.patch.object(ag, "secret_walls", return_value=["--tmpfs", "/run/user/1"]):
            a.execute("true", 5, True)
        cmd, cenv = argv[0]
        self.assertLess(cmd.index("/run/user/1"), cmd.index("--bind"))  # the project mounted over the walls
        self.assertNotIn("DBUS_SESSION_BUS_ADDRESS", cenv)
        self.assertNotIn("ANTHROPIC_API_KEY", cenv)

    def test_a_picture_search_puts_the_projects_own_sites_first(self):
        """Image search (Cin-MinAI's own search): each picture's address, size and page; pictures from a site the project
        already fetched from first (a set keeps its look); kept as a source, so download may take the addresses."""
        from unittest import mock
        from cin_minai.aicui import intake
        from cin_minai.daemon import websearch
        intake.save(self.root, "https://cards.example/pack/Set%20One", b"<html><body>one</body></html>", "text/html")
        a = Agent(self.root, Scripted([]), "m", "auto", say=self.said.append, ask=lambda p: "y")
        found = [{"title": "Stone Giant (resold)", "url": "https://shop.example/giant.jpg", "page": "https://shop.example/",
                  "size": "958x1600", "via": "bing images"},
                 {"title": "Stone Giant", "url": "https://img.cards.example/giant.jpg", "page": "https://cards.example/c/1",
                  "size": "813x1185", "via": "duckduckgo images"}]
        with mock.patch.object(websearch, "images", return_value=found):
            said = a.do({"tool": "web_search", "query": "Stone Giant card", "kind": "images"})
        self.assertLess(said.index("img.cards.example"), said.index("shop.example"))
        self.assertIn("picture 813x1185 on https://cards.example/c/1", said)
        self.assertIn("kept as sources/search-images-stone-giant-card.txt", said)
        self.assertTrue(a.known_address("https://shop.example/giant.jpg"))  # it came from a search

    def test_different_addresses_never_write_over_each_other(self):
        """2026-10-10 (test5): three card lists, card_search.action?pid=…, each wrote over the last as one source."""
        from cin_minai.aicui import intake
        page = lambda s: f"<html><body><p>{s}</p></body></html>".encode()  # noqa: E731
        one = intake.save(self.root, "https://db.example/card_search.action?pid=111", page("set one"), "text/html")
        two = intake.save(self.root, "https://db.example/card_search.action?pid=222", page("set two"), "text/html")
        again = intake.save(self.root, "https://db.example/card_search.action?pid=111", page("set one, new"), "text/html")
        self.assertEqual(one["files"], ["sources/card_search.txt", "sources/card_search.html"])
        self.assertEqual(two["files"], ["sources/card_search-222.txt", "sources/card_search-222.html"])
        self.assertEqual(again["files"], one["files"])  # the same address takes its own file again
        with open(os.path.join(self.root, "sources", "card_search-222.txt"), encoding="utf-8") as f:
            self.assertIn("set two", f.read())
        os.makedirs(os.path.join(self.root, "assets", "cards"))
        with open(os.path.join(self.root, "assets", "cards", "back.png"), "wb") as f:
            f.write(b"the project's own")
        got = intake.save(self.root, "https://pics.example/back.png", b"PNG", "image/png", "assets/cards")
        self.assertNotEqual(got["files"], ["assets/cards/back.png"])  # a project's own file is never written over
        with open(os.path.join(self.root, "assets", "cards", "back.png"), "rb") as f:
            self.assertEqual(f.read(), b"the project's own")

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

    def test_a_command_that_couldnt_reach_the_internet_says_how_to_ask(self):
        """2026-10-17, test19: cargo couldn't reach crates.io in the sandbox, and the senior planned to rewrite the
        game without its libraries — nothing said the internet was one question away."""
        a = Agent(self.root, Scripted([]), "m", "auto", say=self.said.append)
        a.sandbox = True
        cargo = ("    Updating crates.io index\nerror: failed to get `eframe` as a dependency of package `tetris`\n"
                 "Caused by: [6] Could not resolve host: index.crates.io")
        a.execute = lambda *args, **kw: (101, cargo)
        said = a.run("cargo build")
        self.assertIn("This command tried to reach the internet", said)
        self.assertIn("run it again with `network` true", said)
        a.execute = lambda *args, **kw: (1, "error[E0425]: cannot find value `x` in this scope")
        self.assertNotIn("reach the internet", a.run("cargo build"))  # a real compile error: no such note
        a.mode = "ask"
        a.execute = lambda *args, **kw: (101, cargo)
        a.allowed = lambda *args: True
        self.assertIn("Auto mode lets the person allow it once", a.run("cargo build"))

    def test_elements_the_script_makes_have_names_too(self):
        """2026-10-15, test18: game.js made each card with className = 'card' and wrote its rank as <div class="rank">
        inside a string; the check said .card styled nothing, and no goal of the finished game could be ticked."""
        from cin_minai.aicui.agent import web_names
        with open(os.path.join(self.root, "index.html"), "w") as f:
            f.write('<div id="player-cards"></div>\n<script src="game.js"></script>\n')
        with open(os.path.join(self.root, "styles.css"), "w") as f:
            f.write(".card { }\n.card.red { }\n.rank { }\n.suit { }\n#result { }\n.chip { }\n")
        with open(os.path.join(self.root, "game.js"), "w") as f:
            f.write("const c = document.createElement('div');\nc.className = 'card';\nc.classList.add('red');\n"
                    "c.innerHTML = `<div class=\"rank\">${r}</div><div class=\"suit\">${s}</div>`;\n"
                    "const m = document.createElement('p');\nm.id = 'result';\n")
        r = web_names(self.root)
        self.assertNotIn(".card", r)
        self.assertNotIn(".rank", r)
        self.assertNotIn("#result", r)
        self.assertIn("styles.css styles .chip", r)  # still caught: nothing makes it

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


class VirtualScreen(unittest.TestCase):
    """Ian, 2026-10-11: commands get a screen of their own, so a tkinter or Qt program fails (or runs) the way it would
    for the person — test10's game crashed on start while the model, without a display, called its error expected."""

    def test_the_command_runs_inside_its_own_screen_and_keeps_its_exit_code(self):
        from cin_minai.aicui.agent import with_screen
        wrapped = with_screen("python3 app.py  # a comment", (1920, 1080, 1))
        self.assertIn("Xvfb -displayfd 9 -screen 0 1920x1080x24 -nolisten tcp -extension GLX", wrapped)
        self.assertIn("( python3 app.py  # a comment\n)", wrapped)  # a trailing comment can't swallow the bracket
        self.assertTrue(wrapped.endswith("exit $_rc"))

    @unittest.skipUnless(shutil.which("Xvfb") and shutil.which("xdpyinfo"), "needs Xvfb")
    def test_live_a_display_is_there_and_goes_away(self):
        import subprocess
        from cin_minai.aicui.agent import with_screen
        r = subprocess.run(["bash", "-c", with_screen("xdpyinfo | grep -c dimensions; exit 3", (800, 600, 1))],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual((r.returncode, r.stdout.strip()), (3, "1"))


@unittest.skipUnless(shutil.which("git") and os.name == "posix", "the changelog needs git; runs commands")
class Robust(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, True)

    def test_a_step_that_isnt_one_is_a_note_not_a_crash(self):
        """2026-10-12: a cloud model's action arrived as a string; act["tool"] ended the agent."""
        a = Agent(self.root, Scripted([(json.dumps({"thinking": "Look.", "action": "list ."}), {}),
                                       step("", tool="answer", text="done")]), "m", "auto", say=lambda s: None)
        self.assertEqual(a.turn("go"), "done")  # it went on to its next reply

    def test_a_command_cut_off_at_its_limit_leaves_nothing_running(self):
        """2026-10-12: a game window and its virtual screen kept running after the command was stopped."""
        a = Agent(self.root, Scripted([]), "m", "none", say=lambda s: None)
        pidfile = os.path.join(self.root, "child.pid")
        code, _ = a.execute(f"sleep 301 & echo $! > {pidfile}; sleep 302", 2, False)
        self.assertIsNone(code)
        with open(pidfile) as f:
            pid = int(f.read())
        import time
        time.sleep(0.2)
        self.assertFalse(os.path.exists(f"/proc/{pid}") and "sleep" in open(f"/proc/{pid}/cmdline").read())

    def test_a_timeout_says_the_program_was_still_running(self):
        a = Agent(self.root, Scripted([]), "m", "none", say=lambda s: None)
        self.assertIn("exit 124: still running when the timeout stopped it", a.run("timeout 1 sleep 5"))
