# SPDX-License-Identifier: GPL-3.0-or-later

import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))

from cin_minai.daemon.repetition import LoopDetected, ReplyGuard, find_repeat, repair  # noqa: E402


class RepetitionTest(unittest.TestCase):
    def test_repairs_known_japanese_loop_at_complete_sentence(self):
        text = ("USBメモリーを安全に取り外すには、以下の手順を踏んでください。\n"
                "1. ファイルの左側にUSBメモリーが表示されているので、その名前をクリックします。\n"
                "3. USBメモリーが「eject」ボタンをクリックした後に「eject」ボタンが「eject」ボタンを"
                "クリックした後に「eject」ボタンが「eject」ボタンが「eject」ボタンが「eject」ボタンが"
                "「eject」ボタンをクリックした後に「eject」ボタンが「eject」ボタンをクリックした後に"
                "「eject」というメッセージが表示されます。")
        fixed, match = repair(text)
        self.assertIsNotNone(match)
        self.assertTrue(fixed.endswith("その名前をクリックします。"), fixed)
        self.assertNotIn("\n3.", fixed)
        self.assertIsNone(find_repeat(fixed))

    def test_keeps_one_complete_sentence_when_whole_sentence_repeats(self):
        sentence = "Open the app, choose the drive, and click Eject."
        fixed, match = repair(" ".join([sentence] * 3))
        self.assertIsNotNone(match)
        self.assertEqual(fixed, sentence)

    def test_normal_steps_and_mint_names_are_not_loops(self):
        steps = ("Formatting a USB stick erases all files on it.\n1. Open USB Stick Formatter.\n"
                 "2. Choose the USB stick.\n3. Click Format.\n4. Type your password when prompted.")
        self.assertIsNone(find_repeat(steps))
        names = {"Software Manager"}
        normal = "Open Software Manager. Search in Software Manager. Install it from Software Manager."
        self.assertIsNone(find_repeat(normal, names=names))

    def test_stream_guard_replaces_visible_text_then_stops(self):
        class Output:
            def __init__(self):
                self.text = ""

            def __call__(self, piece):
                self.text += piece

            def replace(self, text):
                self.text = text

        sentence = "Open the app, choose the drive, and click Eject."
        output = Output()
        guard = ReplyGuard(output)
        with self.assertRaises(LoopDetected) as caught:
            for piece in (" ".join([sentence] * 3)[i:i + 5] for i in range(0, len(" ".join([sentence] * 3)), 5)):
                guard.feed(piece)
        self.assertEqual(output.text, sentence)
        self.assertEqual(caught.exception.reply, sentence)


if __name__ == "__main__":
    unittest.main()
