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

from cin_minai.aicui.agent import Agent, doing, salvage, schema  # noqa: E402


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
        self.assertLessEqual(sum(len(m["content"]) for m in last), (2400 - 1800 - 300) * 3.3 + 2000)
        self.assertTrue(any(m["content"].startswith("Earlier in this task:") for m in last))

    def test_a_model_error_is_answered_not_a_crash(self):
        def broken(messages, **kw):
            raise RuntimeError("the request exceeds the available context size")
        a = Agent(self.root, broken, "m", "ask", ask=lambda p: "y", say=self.said.append)
        msg = a.turn("go")
        self.assertIn("couldn't go on", msg)
        self.assertIn("exceeds the available context", msg)

    def test_the_loop_guard(self):
        steps = [step("", tool="read", path="app.py") for _ in range(3)] + [step("", tool="answer", text="ok")]
        a = Agent(self.root, Scripted(steps), "m", "ask", ask=lambda p: "y", say=self.said.append, ctx=16384)
        a.turn("look")
        results = [m["content"] for m in a.chat.sent[-1] if m["role"] == "user" and m["content"].startswith("Result")]
        self.assertIn("return a - b", results[0])
        self.assertIn("already read app.py", results[2])
        self.assertEqual(a.read_lines, 200)

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
        self.assertEqual(tools, ["read", "list", "search", "edit", "write", "append", "run", "goal_add", "goal_done",
                                 "ask", "answer"])

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

    def test_progress_events_and_idle(self):
        a = Agent(self.root, Scripted([step("", tool="answer", text="ok")]), "m", "auto", say=self.said.append)
        a.turn("go")
        kinds = [x["kind"] for x in self.events()]
        self.assertEqual(kinds[-1], "idle")
        self.assertIn("busy", kinds)


if __name__ == "__main__":
    unittest.main()
