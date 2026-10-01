# SPDX-License-Identifier: GPL-3.0-or-later
"""What the sidebar says (src/cin_minai/sidebar/words.py): every tool the guide can use has plain words,
and the header says where the model runs and why it's reduced (SPEC §4.2, §5.5).

    python3 -m unittest tests.unit.test_sidebar_words -v        (from the repo root)
"""

import json
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "distro", "packages", "cinminai-daemon"))

from cin_minai.sidebar import words  # noqa: E402
import gen_data  # noqa: E402


class Words(unittest.TestCase):
    def test_every_tool_and_topic_has_words(self):
        guide = gen_data.build(ROOT)["guide.json"]
        for tool in guide["tools"]:
            if tool in ("answer", "decline"):
                continue  # the answer itself, no action line
            icon, text = words.action(tool, {})
            self.assertFalse(text.startswith("Used "), tool)
        for topic in guide["topics"]:
            self.assertIn(topic, words.TOPICS)

    def test_open_app_says_what_opened(self):
        self.assertEqual(words.action("open_app", {"app": "files"}, json.dumps({"opened": "Files"}))[1], "Opened Files")
        self.assertIn("couldn't", words.action("open_app", {}, json.dumps({"opened": None, "error": "x"}))[1])

    def test_header_says_where_and_why(self):
        dot, first, second = words.status_line("idle", {"model": "Cin-MinAI guide", "build": "cpu", "context": 4096,
                                                        "reduced": "on the processor (slower): the graphics card's driver isn't installed yet"})
        self.assertEqual((dot, first), ("ok", "Ready"))
        self.assertIn("processor · 4K", second)
        self.assertIn("driver isn't installed", second)
        self.assertEqual(words.status_line("offline", {})[0], "bad")

    def test_waiting_warns_about_the_processor(self):
        self.assertIn("minute", words.waiting("thinking", "cpu"))
        self.assertNotIn("minute", words.waiting("thinking", "cuda"))


class CommandCards(unittest.TestCase):
    """D53: commands to copy, with what they do."""

    RESULT = json.dumps({"problems_found": [{"code": "I301", "command": "echo 1280 | sudo tee /sys/block/sda/queue/max_sectors_kb",
                                             "command_explained": "Limits each write.", "undo": "Restart."}]})

    def test_check_line_says_problems_were_found(self):
        icon, text = words.action("inspect_system", {"topic": "storage"}, self.RESULT)
        self.assertEqual(icon, "dialog-warning-symbolic")
        self.assertIn("found 1 problem", text)

    def test_cards_from_result_and_text_merge(self):
        text = "Run:\n```\necho 1280 | sudo tee /sys/block/sda/queue/max_sectors_kb\n```\nThen `uname -r` to check."
        cards = words.merge_cards(words.commands_in_result(self.RESULT), words.commands_in_text(text))
        self.assertEqual([c["command"] for c in cards],
                         ["echo 1280 | sudo tee /sys/block/sda/queue/max_sectors_kb", "uname -r"])
        self.assertEqual(cards[0]["explain"], "Limits each write.")  # the explained one wins

    def test_notes_say_what_undo_and_password(self):
        notes = words.card_notes(words.commands_in_result(self.RESULT)[0])
        self.assertTrue(any(n.startswith("What it does") for n in notes))
        self.assertTrue(any("undo" in n for n in notes))
        self.assertTrue(any("password" in n for n in notes))
        self.assertFalse(any("password" in n for n in words.card_notes({"command": "uname -r"})))

    def test_plain_text_has_no_cards(self):
        self.assertEqual(words.commands_in_text("Open Update Manager and click Install."), [])



class ProposalCard(unittest.TestCase):
    """SPEC §7.8: a document edit shown before it happens."""

    def test_grid_for_ranges_is_cut_to_fit(self):
        pv = {"summary": "Write 10×7 cells at A1", "before": [[""] * 7] * 10, "after": [[f"r{r}c{c}" for c in range(7)] for r in range(10)]}
        p = words.preview_parts(pv)
        self.assertEqual(p["kind"], "grid")
        self.assertEqual(len(p["after"]), words.GRID_ROWS + 1)  # + the … row
        self.assertEqual(p["after"][0][-1], "…")
        self.assertEqual(words.preview_parts({"before": [[388.0]], "after": [["=SUM(B2:B7)"]]})["before"], [["388"]])

    def test_text_and_slide(self):
        self.assertEqual(words.preview_parts({"before": "teh", "after": "the"})["kind"], "text")
        s = words.preview_parts({"before": {"title": "", "body": ""}, "after": {"title": "Join us", "body": ""}})
        self.assertEqual((s["kind"], s["after"]), ("slide", "Join us"))

    def test_outcome_words(self):
        self.assertIn("Ctrl+Z", words.decided({"applied": True}, None))
        self.assertIn("unchanged", words.decided({"applied": False}, None))
        self.assertIn("changed since", words.decided(None, "the document changed since the preview"))

    def test_header_says_what_it_sees(self):
        second = words.status_line("idle", {"model": "Cin-MinAI guide", "document": "Budget.ods"})[2]
        self.assertIn('Sees: document "Budget.ods"', second)
        self.assertNotIn("Sees", words.status_line("idle", {"model": "x"})[2])


class PutInWriter(unittest.TestCase):
    """2026-10-01 hands-on: "it won't write in Writer" — a button under real answers."""

    def test_real_answers_only(self):
        poem = "Autumn's gentle touch begins, as leaves turn gold and crimson shine. " * 3
        self.assertTrue(words.worth_a_document(poem))
        self.assertFalse(words.worth_a_document("Your Wi-Fi is switched off."))
        self.assertFalse(words.worth_a_document("I can look that up on the web. " + "Below is exactly what would be sent " * 5))

    def test_title_from_the_first_line(self):
        self.assertEqual(words.document_title("**Autumn Leaves:**"), "Autumn Leaves")
        self.assertEqual(words.document_title(""), "From the assistant")


if __name__ == "__main__":
    unittest.main()
