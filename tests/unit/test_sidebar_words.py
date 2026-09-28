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


if __name__ == "__main__":
    unittest.main()
