# SPDX-License-Identifier: GPL-3.0-or-later
"""The system matcher (PLAN D60, M5) on made-up machines, checked against what we measured on the 1080 Ti.

    python3 -m unittest tests.unit.test_matcher -v        (from the repo root)
"""

import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))

from cin_minai.inference.matcher import Machine, match, report  # noqa: E402


def machine(card=None, total=0, free=0, ram=32, avail=26, bw=5.0):
    cards = [{"name": card, "api": "CUDA0", "total_mib": total, "free_mib": free}] if card else []
    return Machine(cards, ram, avail, 4, True, bw, 50)


class Matcher(unittest.TestCase):
    def test_1080ti_desktop_on_the_board(self):
        # measured: the 27B IQ3_XXS ran fully on the card at 14.1 tok/s with 10,587 MiB free
        r = match(machine("NVIDIA GeForce GTX 1080 Ti", 11264, 10587))
        self.assertEqual(r["coding"]["file"], "Qwen3.8-27B-UD-IQ3_XXS.gguf")
        self.assertIn("-ub", r["coding"]["args"])
        self.assertTrue(10 <= sum(r["coding"]["tok_s"]) / 2 <= 25, r["coding"]["tok_s"])
        self.assertEqual(r["writing"]["file"], "Qwen3-14B-Q4_K_M.gguf")
        self.assertEqual(r["help"]["file"], "Qwen3.5-4B-guide-HO-Q4_K_M.gguf")

    def test_1080ti_desktop_on_the_card(self):
        r = match(machine("NVIDIA GeForce GTX 1080 Ti", 11264, 10354))
        # the 27B no longer fits whole: a near-fit, a few layers' feed-forward weights in RAM (12.9 tok/s with one)
        self.assertEqual(r["coding"]["file"], "Qwen3.8-27B-UD-IQ3_XXS.gguf")
        self.assertIn("-ot", r["coding"]["args"])
        self.assertIn("feed-forward weights in RAM", r["coding"]["mode"])

    def test_8gb_card_16gb_ram(self):
        r = match(machine("NVIDIA GeForce RTX 3060 Ti", 8192, 7600, ram=16, avail=12))
        self.assertEqual(r["writing"]["file"], "Qwen3.5-9B-Q4_K_M.gguf")
        self.assertEqual(r["coding"]["file"], "Qwen3.5-9B-Q4_K_M.gguf")  # not enough RAM for the MoE's experts

    def test_6gb_card_32gb_ram_gets_the_moe_for_coding(self):
        r = match(machine("NVIDIA GeForce GTX 1060 6GB", 6144, 5600, ram=32, avail=28, bw=5))
        self.assertEqual(r["coding"]["file"], "Qwen3.6-35B-A3B-Q4_K_M.gguf")

    def test_the_boot_test_vm(self):  # 8 GB, about 5 free in the live session: the guide still runs there
        r = match(machine(None, ram=8, avail=5, bw=5))
        self.assertEqual((r["help"]["file"], r["help"]["mode"]), ("Qwen3.5-4B-guide-HO-Q4_K_M.gguf", "on the processor"))

    def test_no_graphics_card(self):
        r = match(machine(None, ram=16, avail=12, bw=5))
        self.assertEqual(r["help"]["mode"], "on the processor")
        self.assertEqual(r["writing"]["file"], "Qwen3.5-4B-guide-HO-Q4_K_M.gguf")
        slow = match(machine(None, ram=16, avail=12, bw=1.5))  # a very old machine
        self.assertIn("slow on this computer", slow["writing"]["why"])  # the last resort, said honestly
        self.assertIn("none llama.cpp can use", report(machine(None), r))


if __name__ == "__main__":
    unittest.main()
