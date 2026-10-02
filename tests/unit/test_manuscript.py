# SPDX-License-Identifier: GPL-3.0-or-later
"""The manuscript (PLAN D58): chapters as the files are now, in standard manuscript format, .odt and .docx.

    python3 -m unittest tests.unit.test_manuscript -v        (from the repo root)
"""

import os
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))

from cin_minai.daemon import manuscript, odt  # noqa: E402
from cin_minai.daemon.projects import Project  # noqa: E402

TEXT = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}"
WN = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def chapter(p: Project, n: int, title: str, scenes: list[str]) -> str:
    path = odt.write(p.folder, f"Chapter {n} — {title}", f"Chapter {n} — {title}", scenes, header="Rough draft")
    p.add_draft(path, title, 100, chapter=n, steps=["you"], summary="")
    return path


class Manuscript(unittest.TestCase):
    def setUp(self):
        self.p = Project.new("Missed the Moon", root=tempfile.mkdtemp())
        self.p.set_shape("chapters", 3)

    def paras(self, path):
        with zipfile.ZipFile(path) as z:
            root = ET.fromstring(z.read("content.xml"))
            styles = z.read("styles.xml").decode()
        return [(e.get(TEXT + "style-name"), "".join(e.itertext())) for e in root.iter(TEXT + "p")], styles

    def test_chapters_in_order_newest_draft_each_writers_edits_kept(self):
        chapter(self.p, 2, "The Heavy Hand", ["Sarah turned the ship.", "Petr agreed."])
        chapter(self.p, 1, "The Silent Orbit", ["Old first chapter."])
        newer = chapter(self.p, 1, "The Silent Orbit", ["The crew woke early.\n\nChang Xi checked Jupiter."])
        # the writer edits chapter 1 in Writer: here, the file is replaced by their version
        edited = odt.write(tempfile.mkdtemp(), "x", "Chapter 1 — The Silent Orbit",
                           ["The crew woke early, as always.", "Chang Xi checked Jupiter twice."])
        os.replace(edited, newer)
        res = manuscript.make(self.p, "Ian McClenathan", "ian@example.org", letter=True)
        self.assertEqual((res["chapters"], res["paper"]), (2, "Letter"))
        paras, styles = self.paras(res["odt"])
        texts = [t for _, t in paras]
        self.assertEqual(texts[:5], ["Ian McClenathan", "ian@example.org", "about 100 words", "MISSED THE MOON",
                                     "by Ian McClenathan"])
        self.assertEqual(texts[5:8], ["Chapter 1", "The Silent Orbit", "The crew woke early, as always."])
        self.assertNotIn("Old first chapter.", texts)
        self.assertEqual(texts.count("#"), 2)  # one break in each chapter
        self.assertIn(("Chapter", "Chapter 2"), paras)  # a new page for each chapter after the first
        self.assertEqual(paras[5][0], "ChapterFirst")  # the first chapter switches to the page style with a header
        self.assertEqual(texts[-1], "THE END")
        self.assertIn('fo:page-width="21.59cm"', styles)
        self.assertIn("McClenathan / MISSED THE MOON / <text:page-number", styles)
        self.assertIn('fo:line-height="200%"', styles)
        self.assertIn("Times New Roman", styles)
        self.assertTrue(res["docx"].endswith("Missed the Moon — manuscript.docx"))

    def test_docx_is_word_shaped(self):
        chapter(self.p, 1, "The Silent Orbit", ["One.", "Two."])
        chapter(self.p, 2, "The Heavy Hand", ["Three."])
        res = manuscript.make(self.p, "Ian McClenathan", letter=False)
        with zipfile.ZipFile(res["docx"]) as z:
            names = set(z.namelist())
            doc = ET.fromstring(z.read("word/document.xml"))
            hdr = z.read("word/header1.xml").decode()
            for n in names:  # every part is well-formed XML
                ET.fromstring(z.read(n))
        self.assertTrue({"[Content_Types].xml", "_rels/.rels", "word/document.xml", "word/styles.xml",
                         "word/header1.xml", "word/_rels/document.xml.rels"} <= names)
        self.assertEqual(len(list(doc.iter(WN + "pageBreakBefore"))), 2)
        self.assertEqual(len(list(doc.iter(WN + "titlePg"))), 1)
        self.assertEqual(doc.find(f".//{WN}pgSz").get(WN + "w"), "11906")  # A4
        self.assertIn('w:instr=" PAGE "', hdr)
        self.assertIn("McClenathan / MISSED THE MOON / ", hdr)
        texts = ["".join(t.text or "" for t in p.iter(WN + "t")) for p in doc.iter(WN + "p")]
        self.assertEqual(texts[-1], "THE END")
        self.assertIn("#", texts)

    def test_a_story_in_one_chapter_has_no_chapter_heading(self):
        path = odt.write(self.p.folder, "The Warning", "The Warning", ["She read the email.", "She ran."])
        self.p.add_draft(path, "The Warning", 9)
        res = manuscript.make(self.p, "Ian")
        texts = [t for _, t in self.paras(res["odt"])[0]]
        self.assertNotIn("Chapter 1", texts)
        self.assertEqual(texts[-4:], ["She read the email.", "#", "She ran.", "THE END"])

    def test_never_overwrites_and_nothing_written_is_an_error(self):
        with self.assertRaises(ValueError):
            manuscript.make(self.p, "Ian")
        chapter(self.p, 1, "A", ["x"])
        a, b = manuscript.make(self.p, "Ian"), manuscript.make(self.p, "Ian")
        self.assertNotEqual(a["odt"], b["odt"])
        self.assertTrue(b["docx"].endswith("manuscript (2).docx"))

    def test_nested_paragraphs_count_once(self):
        """A footnote the writer added in Writer: its paragraph sits inside the main one (found by Qwen3.8-27B)."""
        path = chapter(self.p, 1, "A", ["x"])
        xml = (f'<?xml version="1.0"?><office:document-content {odt.NS}><office:body><office:text>'
               '<text:p>Chapter 1 — A</text:p>'
               '<text:p>She ran<text:s/>home.<text:note text:note-class="footnote"><text:note-citation>1</text:note-citation>'
               '<text:note-body><text:p>A footnote.</text:p></text:note-body></text:note></text:p>'
               '<text:p>*   *   *</text:p><text:p>Then it rained.</text:p></office:text></office:body></office:document-content>')
        os.remove(path)
        with zipfile.ZipFile(path, "w") as z:
            z.writestr("content.xml", xml)
        title, scenes = manuscript.read_scenes(path)
        self.assertEqual((title, scenes), ("A", [["She ran home."], ["Then it rained."]]))
        self.assertEqual(odt.read(path), ["Chapter 1 — A", "She ran home.", "Then it rained."])

    def test_rounding_and_paper(self):
        self.assertEqual(manuscript.rounded(12314), "about 12,000 words")
        self.assertEqual(manuscript.rounded(4817), "about 4,800 words")
        self.assertEqual(manuscript.header_text("Ian McClenathan", "The Coming War of the Worlds"),
                         "McClenathan / THE COMING WAR OF / ")
        old = os.environ.get("LC_PAPER")
        try:
            os.environ["LC_PAPER"] = "en_US.UTF-8"
            self.assertTrue(manuscript.letter_paper())
            os.environ["LC_PAPER"] = "de_DE.UTF-8"
            self.assertFalse(manuscript.letter_paper())
        finally:
            os.environ.pop("LC_PAPER") if old is None else os.environ.__setitem__("LC_PAPER", old)


if __name__ == "__main__":
    unittest.main()
