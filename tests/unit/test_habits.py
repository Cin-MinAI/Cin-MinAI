# SPDX-License-Identifier: GPL-3.0-or-later
"""Habits (PLAN D96, SPEC §23.2): the format, the shipped habits, keeping one, and AICUI's habit tools."""

import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "..", "src"))
SHIPPED = os.path.realpath(os.path.join(HERE, "..", "..", "distro", "packages", "cinminai-daemon", "root", "usr",
                                        "share", "cinminai", "habits"))

from cin_minai import habits  # noqa: E402

# the smallest PDF with one page of text (two words), written by hand
TINY_PDF = (b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
            b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 300 200]/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>"
            b">>endobj\n4 0 obj<</Length 44>>stream\nBT /F1 18 Tf 20 100 Td (RULES OF PLAY) Tj ET\nendstream endobj\n"
            b"5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n")


class Base(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, True)
        self.addCleanup(shutil.rmtree, self.home, True)
        self.env = {k: os.environ.get(k) for k in ("CINMINAI_HABITS", "XDG_DATA_HOME")}
        os.environ["CINMINAI_HABITS"] = SHIPPED
        os.environ["XDG_DATA_HOME"] = self.home
        self.addCleanup(self.restore)

    def restore(self):
        for k, v in self.env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def write(self, rel, text):
        full = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as f:
            f.write(text)
        return rel


class Format(Base):
    def test_the_shipped_habits_are_found(self):
        names = {h["name"]: h for h in habits.every(self.root)}
        self.assertEqual(set(names), {"pdf-sections", "web-page", "table-rows", "video-segments"})
        self.assertTrue(names["web-page"]["network"])
        self.assertEqual(names["table-rows"]["place"], "shipped")

    def test_a_table_becomes_checked_rows_and_a_ragged_one_fails(self):
        self.write("data/cards.csv", "name,atk,def\nStone Giant,1300,2000\nDark Hole,,\n")
        got = habits.run("table-rows", {"path": "data/cards.csv"}, self.root)
        self.assertTrue(got["ok"], got["said"])
        with open(os.path.join(self.root, got["output"]), encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["rows"][0], {"name": "Stone Giant", "atk": "1300", "def": "2000"})
        self.write("data/bad.csv", "name,atk\nStone Giant,1300,extra\n")
        bad = habits.run("table-rows", {"path": "data/bad.csv"}, self.root)
        self.assertFalse(bad["ok"])
        self.assertIn("FAILED its check", bad["said"])
        self.assertIn("don't have one cell per column", bad["said"])
        with open(os.path.join(self.home, "cinminai", "habits", "runs.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["table-rows"]["runs"], 2)

    def test_a_kept_page_needs_no_network_an_address_does(self):
        self.write("sources/page.html", "<html><head><title>Rules</title></head><body><h2>Battle</h2><p>Each monster "
                                        "attacks once.</p><table><tr><th>Phase</th><th>Step</th></tr><tr><td>Battle"
                                        "</td><td>Damage</td></tr></table></body></html>")
        got = habits.run("web-page", {"path": "sources/page.html"}, self.root)
        self.assertTrue(got["ok"], got["said"])
        with open(os.path.join(self.root, got["output"]), encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["title"], "Rules")
        self.assertEqual(data["tables"][0]["rows"], [["Phase", "Step"], ["Battle", "Damage"]])
        self.assertIn({"kind": "heading", "text": "Battle"}, data["blocks"])
        refused = habits.run("web-page", {"url": "https://example.org/"}, self.root)
        self.assertIn("needs the network, and it isn't allowed here", refused["said"])

    @unittest.skipUnless(shutil.which("pdfinfo") and shutil.which("pdftotext"), "needs poppler-utils")
    def test_a_pdf_becomes_pages_and_headings(self):
        with open(os.path.join(self.root, "rules.pdf"), "wb") as f:
            f.write(TINY_PDF)
        got = habits.run("pdf-sections", {"path": "rules.pdf"}, self.root)
        self.assertTrue(got["ok"], got["said"])
        with open(os.path.join(self.root, got["output"]), encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(len(data["pages"]), 1)
        self.assertEqual(data["sections"], [{"title": "RULES OF PLAY", "page": 1}])

    def test_the_video_check_on_its_own(self):
        out = self.write("out.json", json.dumps({"duration": 300, "segments": [{"start": 1, "text": "hello"},
                                                                                {"start": 0.5, "text": "late"}]}))
        code, printed = habits.local_runner(self.root)(
            f"python3 {os.path.join(SHIPPED, 'video-segments', 'check.py')} {out} x", 30, False)
        self.assertEqual(code, 1)
        self.assertIn("aren't in time order", printed)

    def test_keeping_a_script_as_a_habit(self):
        self.write("tools/make.py", "import json\njson.dump([1, 2, 3], open('data/n.json', 'w'))\n")
        self.write("tools/check_n.py", "import json, sys\nsys.exit(0 if len(json.load(open('data/n.json'))) == 3 else 1)\n")
        os.makedirs(os.path.join(self.root, "data"))
        self.assertIn("lowercase", habits.keep(self.root, "Bad Name", "x", "tools/make.py", "tools/check_n.py")["said"])
        kept = habits.keep(self.root, "three-numbers", "three numbers", "tools/make.py", "tools/check_n.py",
                           output="data/n.json")
        self.assertTrue(kept["ok"], kept["said"])
        self.assertEqual(habits.find("three-numbers", self.root)["place"], "project")
        got = habits.run("three-numbers", {}, self.root)
        self.assertTrue(got["ok"], got["said"])
        self.assertEqual(got["output"], "data/n.json")


class InAICUI(Base):
    def test_a_lead_runs_a_habit_and_offers_one(self):
        from cin_minai.aicui.agent import Agent, schema
        a = Agent(self.root, None, "m", "auto", say=lambda s: None, ctx=32768)
        self.write("data/cards.csv", "name,atk\nStone Giant,1300\n")
        said = a.do({"tool": "habit", "name": "table-rows", "inputs": {"path": "data/cards.csv"}})
        self.assertIn("habit table-rows passed its check", said)
        self.assertTrue(a.progressed({"tool": "habit"}, said))
        self.assertIn("isn't a file in the project", a.do({"tool": "habit", "name": "table-rows",
                                                           "inputs": {"path": "../elsewhere.csv"}}))
        self.assertIn("table-rows (A table file", a.system())
        self.write("tools/make.py", "print('made')\n")
        self.write("tools/check_ok.py", "raise SystemExit(0)\n")
        self.write("tools/check_bad.py", "raise SystemExit(1)\n")
        self.assertIn("doesn't pass now", a.do({"tool": "offer_habit", "name": "made", "for": "x",
                                                "script": "tools/make.py", "check": "tools/check_bad.py"}))
        said = a.do({"tool": "offer_habit", "name": "made", "for": "makes it", "script": "tools/make.py",
                     "check": "tools/check_ok.py"})
        self.assertIn("it's kept only if they say so", said)
        with open(os.path.join(self.root, ".cinminai", "events.jsonl"), encoding="utf-8") as f:
            offers = [json.loads(l) for l in f if '"habit_offer"' in l]
        self.assertEqual(offers[0]["script"], "tools/make.py")
        self.assertIsNone(habits.find("made", self.root))  # offered, not kept: the person decides
        small = Agent(self.root, None, "m", "auto", say=lambda s: None, ctx=8192)
        self.assertTrue({"habit", "offer_habit"} <= small.excluded())  # an 8K context hasn't the room
        self.assertNotIn("Habits:", small.system())
        tools = {v["properties"]["tool"]["const"] for v in schema(None, a.excluded())["properties"]["action"]["anyOf"]}
        self.assertTrue({"habit", "offer_habit"} <= tools)


if __name__ == "__main__":
    unittest.main()
