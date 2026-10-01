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
        if schema and "chapter_title" in json.dumps(schema):
            return json.dumps({"chapter_title": "The Bottle", "scenes": [
                {"title": f"Scene {i}", "what_happens": f"thing {i} happens"} for i in range(1, 7)]}), {}
        if schema:
            return json.dumps({"facts": ["The message is from his younger self."], "characters": [], "places": [],
                               "ideas": []}), {}
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
        self.assertEqual(len(scenes), 6)
        self.assertTrue(all("The message is from his younger self." in s for s in scenes))
        self.assertNotIn("already written", scenes[0])
        self.assertIn("already written; begin right after them and don't repeat them:\n\"Opening of scene 2.", scenes[2])
        self.assertEqual((res["scenes"], res["stopped"]), (6, False))
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
        self.assertLess(res["scenes"], 6)
        self.assertLessEqual(res["lines"], 600 + 260)  # the budget stops it after the scene that crosses 600


if __name__ == "__main__":
    unittest.main()
