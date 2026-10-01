# SPDX-License-Identifier: GPL-3.0-or-later
"""Writing projects (PLAN D54): the store (projects.py), the document (odt.py) and the pipeline (writer.py)
against a scripted model. The real model's chapter is tests/integration/check_writer.py.

    python3 -m unittest tests.unit.test_writer -v        (from the repo root)
"""

import json
import os
import sys
import tempfile
import threading
import unittest
import xml.etree.ElementTree as ET
import zipfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))

from cin_minai.daemon import odt  # noqa: E402
from cin_minai.daemon.projects import Project  # noqa: E402
from cin_minai.daemon.writer import Writer  # noqa: E402

TEXT = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}"


class Store(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()

    def test_new_open_list(self):
        p = Project.new("The Bottle", root=self.root)
        p.add_notes({"facts": ["The message was written by Elias himself."], "characters": ["Rosa: a neighbour"]})
        q = Project.open(p.folder)
        self.assertEqual(q.notes["facts"], ["The message was written by Elias himself."])
        self.assertEqual(Project.list(self.root)[0]["notes"], 2)
        self.assertFalse([f for f in os.listdir(p.folder) if f.startswith(".project-")])  # atomic, no leftovers

    def test_same_title_gets_its_own_folder(self):
        a, b = Project.new("The Bottle", root=self.root), Project.new("The Bottle", root=self.root)
        self.assertNotEqual(a.folder, b.folder)
        self.assertTrue(b.folder.endswith("The Bottle (2)"))

    def test_notes_merge_without_repeats(self):
        p = Project.new("x", root=self.root)
        self.assertEqual(p.add_notes({"facts": ["A storm is coming.", "a storm is coming", "  "]}), 1)
        self.assertEqual(p.add_notes({"facts": ["A storm is coming."], "places": ["the harbour"]}), 1)
        self.assertIn("Facts (always true in this story):\n- A storm is coming.", p.notes_text())

    def test_title_cant_escape(self):
        p = Project.new("../../etc", root=self.root)
        self.assertEqual(os.path.dirname(p.folder), self.root)


class Document(unittest.TestCase):
    def test_a5_header_italics_breaks(self):
        d = tempfile.mkdtemp()
        path = odt.write(d, "The Bottle", "The Bottle", ["He walked.\n\n*Dear Future Me,* it said.", "She ran."],
                         header="Rough draft — The Bottle")
        with zipfile.ZipFile(path) as z:
            first = z.infolist()[0]
            self.assertEqual((first.filename, first.compress_type), ("mimetype", zipfile.ZIP_STORED))
            styles, content = z.read("styles.xml").decode(), ET.fromstring(z.read("content.xml"))
        self.assertIn('fo:page-width="14.8cm"', styles)
        self.assertIn("Rough draft — The Bottle", styles)
        texts = ["".join(p.itertext()) for p in content.iter(TEXT + "p")]
        self.assertEqual(texts, ["The Bottle", "He walked.", "Dear Future Me, it said.", "*   *   *", "She ran."])
        self.assertEqual(len(list(content.iter(TEXT + "span"))), 1)  # the italics
        self.assertTrue(odt.write(d, "The Bottle", "t", ["x"]).endswith("The Bottle (2).odt"))  # never overwrites

    def test_lines(self):
        self.assertEqual(odt.estimate_lines(["word " * 25]), 3)  # 25 words, 10 a line


class Scripted:
    """A model that answers by what it's asked for; records every prompt."""

    def __init__(self, scene_words=60):
        self.sent, self.scene_words, self.n = [], scene_words, 0

    def __call__(self, messages, schema=None, max_tokens=600, on_text=None, cancel=None, sampling=None):
        self.sent.append({"messages": messages, "schema": schema, "sampling": sampling})
        last = messages[-1]["content"]
        if schema and "chapter_title" in json.dumps(schema):  # the plan: the steps it's given, minItems scenes each
            steps = schema["properties"]["steps"]
            return json.dumps({"chapter_title": "The Bottle", "steps": {
                k: [{"title": f"{k} {i}", "what_happens": f"{k} thing {i} happens"}
                    for i in range(1, steps["properties"][k]["minItems"] + 1)] for k in steps["required"]}}), {}
        if schema:
            return json.dumps({"facts": ["The message is from his younger self."], "characters": [], "places": [],
                               "ideas": [], "circle": {"you": ["Elias, a retired lighthouse keeper."]}}), {}
        if last.startswith("Summarize this chapter"):
            return "The whole chapter happened.", {}
        if last.startswith("Summarize"):
            return "Something happened.", {}
        if "Now write scene" in last:
            self.n += 1
            return (f"Opening of scene {self.n}. " + "word " * self.scene_words + f"End of scene {self.n}."), {}
        on_text and on_text("Got it. Who is Rosa?")
        return "Got it. Who is Rosa?", {}


class Pipeline(unittest.TestCase):
    def setUp(self):
        self.p = Project.new("The Bottle", root=tempfile.mkdtemp())
        self.m = Scripted()
        self.w = Writer(self.m)

    def test_gathering_replies_and_takes_notes(self):
        reply = self.w.reply(self.p, "The message was written by Elias himself.", lambda t: None, threading.Event())
        self.assertEqual(reply, "Got it. Who is Rosa?")
        self.assertEqual(self.p.notes["facts"], ["The message is from his younger self."])
        self.assertEqual([m["role"] for m in self.p.data["messages"]], ["user", "assistant"])
        self.assertIsNotNone(self.m.sent[0]["sampling"])   # the reply: a little randomness
        self.assertIsNone(self.m.sent[1]["sampling"])      # the notes: exact

    def test_every_scene_gets_the_facts_and_the_previous_ending(self):
        self.p.add_notes({"facts": ["The message is from his younger self."]})
        res = self.w.draft(self.p, self.w.outline(self.p), lambda *a: None, threading.Event())
        scenes = [s["messages"][-1]["content"] for s in self.m.sent if "Now write scene" in s["messages"][-1]["content"]]
        self.assertEqual(len(scenes), 8)  # a story in one chapter: the whole circle, one scene a step
        self.assertTrue(all("The message is from his younger self." in s for s in scenes))
        self.assertNotIn("already written", scenes[0])
        self.assertIn("already written; begin right after them and don't repeat them:\n\"Opening of scene 2.", scenes[2])
        self.assertIn('the circle\'s step "Take": and pay a heavy price for it', scenes[5])
        self.assertEqual((res["scenes"], res["stopped"]), (8, False))
        self.assertTrue(os.path.isfile(res["file"]))
        self.assertEqual(self.p.data["drafts"][0]["title"], "The Bottle")

    def test_clean_scene_drops_loops_echoes_and_stray_chinese(self):
        from cin_minai.daemon.writer import clean_scene
        loop = "Stan tried once more, pushing with all his might, but the door just wouldn't budge fully."
        end = "The happy character laughed loudly again, shaking his head at both of them."
        text = "\n\n".join([end, "A new thing happened at the lanes.", loop, "The friends cheered.",
                            loop, loop.replace("once more", "again"), "The sound was sharp and清脆 like glass."])
        out, fixed = clean_scene(text, end, cjk_ok=False)
        self.assertEqual(out.split("\n\n"), ["A new thing happened at the lanes.", loop, "The friends cheered.",
                                             "The sound was sharp and like glass."])
        self.assertEqual(fixed, {"repeats_dropped": 3, "cjk_removed": 1})
        self.assertIn("清脆", clean_scene("彼は清脆な音を聞いた。", "", cjk_ok=True)[0])  # a Japanese story keeps it

    def test_stop_keeps_what_was_written(self):
        cancel = threading.Event()

        def progress(n, total, what):
            if n == 3:
                cancel.set()
        res = self.w.draft(self.p, self.w.outline(self.p), progress, cancel)
        self.assertTrue(res["stopped"])
        self.assertLessEqual(res["scenes"], 3)
        self.assertTrue(os.path.isfile(res["file"]))

    def test_stop_mid_scene_keeps_the_scenes_before(self):
        from cin_minai.inference.backend import Cancelled
        m = Scripted()

        def chat(messages, **kw):
            if "Now write scene 3" in messages[-1]["content"]:
                raise Cancelled()  # what the backend does when Stop interrupts a reply
            return m(messages, **kw)
        w = Writer(chat)
        res = w.draft(self.p, w.outline(self.p), lambda *a: None, threading.Event())
        self.assertEqual(res["scenes"], 2)
        self.assertTrue(os.path.isfile(res["file"]))

    def test_the_line_budget_caps_the_chapter(self):
        w = Writer(Scripted(scene_words=2500))  # a model that won't stop: 250 lines a scene
        res = w.draft(self.p, w.outline(self.p), lambda *a: None, threading.Event())
        self.assertLess(res["scenes"], 8)
        self.assertLessEqual(res["lines"], 600 + 260)  # the budget stops it after the scene that crosses 600


class Circle(unittest.TestCase):
    """Dan Harmon's Story Circle (PLAN D56): a story in one chapter, or a piece of the circle per chapter."""

    def setUp(self):
        self.p = Project.new("The Coming War", root=tempfile.mkdtemp())
        self.m = Scripted()
        self.w = Writer(self.m)

    def test_steps_split_over_chapters(self):
        from cin_minai.daemon.projects import STEPS, chapter_steps
        for n in range(2, 9):
            parts = [chapter_steps(k, n) for k in range(1, n + 1)]
            self.assertEqual(sum(parts, ()), STEPS)  # every step once, in order
        self.assertEqual([len(chapter_steps(k, 3)) for k in (1, 2, 3)], [3, 3, 2])
        self.assertEqual(chapter_steps(2, 4), ("go", "search"))

    def test_scenes_per_step(self):
        from cin_minai.daemon.writer import scenes_per_step
        self.assertEqual(scenes_per_step(8), (1, 1))
        self.assertEqual(scenes_per_step(2), (3, 4))
        self.assertEqual(scenes_per_step(3), (2, 2))
        self.assertEqual(scenes_per_step(1), (6, 8))

    def test_the_partner_asks_about_the_next_empty_step(self):
        self.w.reply(self.p, "Elias is a retired lighthouse keeper.", lambda t: None, threading.Event())
        self.assertIn('next empty step is "You"', self.m.sent[0]["messages"][0]["content"])
        self.assertEqual(self.p.circle["you"], ["Elias, a retired lighthouse keeper."])  # the notes filled it
        self.assertEqual(self.p.open_step(), "need")
        self.w.reply(self.p, "More.", lambda t: None, threading.Event())
        self.assertIn('next empty step is "Need"', self.m.sent[2]["messages"][0]["content"])
        self.assertIn("The story's circle so far:\n- You", self.p.notes_text())

    def test_one_chapter_plan_is_the_whole_circle(self):
        o = self.w.outline(self.p)
        self.assertEqual([s["step"] for s in o["scenes"]], ["you", "need", "go", "search", "find", "take", "return", "change"])
        self.assertIsNone(o["chapter"])
        self.assertIn("This chapter is the whole story", self.m.sent[-1]["messages"][0]["content"])

    def test_a_story_over_chapters(self):
        self.p.set_shape("chapters", 4)
        o = self.w.outline(self.p)
        self.assertEqual((o["chapter"], o["steps"]), (1, ["you", "need"]))
        self.assertEqual(len(o["scenes"]), 6)  # 3 scenes a step
        self.assertIn("Later chapters will cover Go, Search, Find, Take, Return, Change", self.m.sent[-1]["messages"][0]["content"])
        res = self.w.draft(self.p, o, lambda *a: None, threading.Event())
        self.assertTrue(os.path.basename(res["file"]).startswith("Chapter 1 — "))
        self.assertEqual(self.p.data["drafts"][-1]["summary"], "The whole chapter happened.")
        self.assertEqual(self.p.data["next_chapter"], 2)  # a finished chapter moves on
        o2 = self.w.outline(self.p)
        self.assertEqual(o2["steps"], ["go", "search"])
        plan_prompt = self.m.sent[-1]["messages"][0]["content"]
        self.assertIn("Earlier chapters covered You, Need.", plan_prompt)
        self.assertIn('Chapter 1, "The Bottle" (You, Need): The whole chapter happened.', plan_prompt)
        self.w.draft(self.p, o2, lambda *a: None, threading.Event())
        scene = [s["messages"][-1]["content"] for s in self.m.sent if "Now write scene" in s["messages"][-1]["content"]][-1]
        self.assertIn("chapter 2 of 4", scene)
        self.assertIn("The story so far, chapter by chapter:\nChapter 1", scene)
        self.p.set_shape(next_chapter=4)
        self.assertIn("This is the last chapter", (self.w.outline(self.p), self.m.sent[-1]["messages"][0]["content"])[1])

    def test_the_models_chapter_number_is_dropped(self):
        from cin_minai.daemon.writer import CHAPTER_WORD
        for t in ("Chapter 1: The Warning", "Capítulo 2 — The Warning", "Kapitel drei: The Warning", "第3章 The Warning"):
            self.assertEqual(CHAPTER_WORD.sub("", t), "The Warning")
        self.assertEqual(CHAPTER_WORD.sub("", "The Warning"), "The Warning")

    def test_a_stopped_chapter_doesnt_move_on(self):
        self.p.set_shape("chapters", 4)
        cancel = threading.Event()
        self.w.draft(self.p, self.w.outline(self.p), lambda n, t, w: n == 2 and cancel.set(), cancel)
        self.assertEqual(self.p.data["next_chapter"], 1)

    def test_old_projects_open(self):
        path = os.path.join(self.p.folder, "project.json")
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        for k in ("circle", "shape", "chapters", "next_chapter"):
            d.pop(k)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(d, f)
        q = Project.open(self.p.folder)
        self.assertEqual((q.this_chapter()[0], len(q.this_chapter()[1]), q.open_step()), (None, 8, "you"))

    def test_sidebar_words(self):
        from cin_minai.sidebar import words
        o = self.w.outline(self.p)
        lines = words.outline_lines(o)
        self.assertEqual(lines[:2], ["You:", "  1. you 1: you thing 1 happens"])
        self.assertEqual(words.shape_settings(0), {"shape": "chapter"})
        self.assertEqual(words.shape_settings(3), {"shape": "chapters", "chapters": 4})
        self.assertEqual(words.shape_index({"shape": "chapters", "chapters": 4}), 3)


if __name__ == "__main__":
    unittest.main()
