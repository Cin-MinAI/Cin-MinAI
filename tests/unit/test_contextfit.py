# SPDX-License-Identifier: GPL-3.0-or-later
"""Context sizes chosen by the person (PLAN D93, contextfit.py), on made-up machines like the matcher's tests."""

import os
import tempfile
import unittest

from cin_minai.inference import contextfit as F
from cin_minai.inference.matcher import CATALOG, Machine

MODELS = {m.file: m for ms in CATALOG.values() for m in ms}
NINE = MODELS["Qwen3.5-9B-Q4_K_M.gguf"]
MOE = MODELS["Qwen3.6-35B-A3B-Q4_K_M.gguf"]
B27 = MODELS["Qwen3.8-27B-UD-IQ3_XXS.gguf"]


def machine(free=11159, total=11264, card="NVIDIA GeForce GTX 1080 Ti", avail=26):
    return Machine([{"name": card, "api": "CUDA0", "total_mib": total, "free_mib": free}], 32, avail, 4, True, 5.0, 50)


class ContextFitTest(unittest.TestCase):
    def test_default_is_what_cinminai_picks(self):
        ctx, p = F.fit(NINE, machine(), F.defaults())
        self.assertEqual(ctx, 32768)
        (a, b), pp = F.fit_pair(NINE, MOE, machine(), F.defaults())
        self.assertEqual((a, b), (32768, 32768))

    def test_fill_one_model_keeps_it_where_it_runs(self):
        base = F.fit(NINE, machine(), F.defaults())[1]
        ctx, p = F.fit(NINE, machine(), {"choice": "fill"})
        self.assertGreater(ctx, 50000)  # Ian: "a respectable 50k with something on the 1080 ti"
        self.assertEqual((p["mode"], p["cache"]), (base["mode"], base["cache"]))
        self.assertLessEqual(ctx, F.MAX)

    def test_room_is_half(self):
        full, _ = F.fit(NINE, machine(), {"choice": "fill"})
        half, p = F.fit(NINE, machine(), {"choice": "room"})
        self.assertEqual(half, F.clamp(full // 2))
        self.assertIsNotNone(p)

    def test_room_leaves_the_card_free_even_beside_a_moe(self):
        """A MoE Senior fills any free card memory with experts: room holds the freed memory back for the person."""
        (a, b), fill = F.fit_pair(NINE, MOE, machine(), {"choice": "fill"})
        (c, d), room = F.fit_pair(NINE, MOE, machine(), {"choice": "room"})
        held = lambda p: p["junior"]["card_gb"] + p["senior"]["card_gb"]  # noqa: E731
        self.assertEqual((c, d), (F.clamp(a // 2), F.clamp(b // 2)))
        self.assertGreater(held(fill) - held(room), 0.5)  # GB the person gets back
        _, one = F.fit(MOE, machine(), {"choice": "fill"})
        _, half = F.fit(MOE, machine(), {"choice": "room"})
        self.assertGreater(one["card_gb"] - half["card_gb"], 0.3)

    def test_fill_never_makes_a_model_much_slower(self):
        base = F.fit(B27, machine(), F.defaults())[1]
        ctx, p = F.fit(B27, machine(), {"choice": "fill"})
        self.assertGreaterEqual(F.speed(p), F.SLOWER * F.speed(base))
        self.assertEqual(p["cache"], base["cache"])  # never a smaller cache type

    def test_two_models_share_by_the_split(self):
        base = F.fit_pair(NINE, MOE, machine(), F.defaults())[1]
        (a, b), p = F.fit_pair(NINE, MOE, machine(), {"choice": "fill", "split": 0.5})
        self.assertIsNotNone(p)
        self.assertGreater(a, 50000)
        self.assertEqual(p["junior"]["mode"], "all on the graphics card")
        self.assertGreaterEqual(F.speed(p["senior"]), F.SLOWER * F.speed(base["senior"]))
        (a2, b2), _ = F.fit_pair(NINE, MOE, machine(), {"choice": "fill", "split": 0.9})
        self.assertGreater(a2, a)  # more for the first
        self.assertLess(b2, b)

    def test_custom_sizes_are_placed_as_they_fit(self):
        ctx, p = F.fit(NINE, machine(), {"choice": "custom", "solo": 65536})
        self.assertEqual(ctx, 65536)
        self.assertEqual(p["mode"], "all on the graphics card")
        sizes, pp = F.fit_pair(NINE, MOE, machine(free=6000, total=6144, card="NVIDIA GeForce RTX 3050"),
                               {"choice": "custom", "first": 131072, "second": 131072})
        self.assertIsNone(pp)  # doesn't fit: the agent says so and uses Cin-MinAI's sizes

    def test_choices_are_kept_and_cleaned(self):
        with tempfile.TemporaryDirectory() as d:
            f = os.path.join(d, "cinminai", "context.json")
            F.save({"choice": "room", "split": 0.7, "first": 50000}, f)
            p = F.load(f)
            self.assertEqual((p["choice"], p["split"], p["first"]), ("room", 0.7, 49152))  # a multiple of 4K
        p = F.clean({"choice": "huge", "split": 9, "solo": 10 ** 9, "second": "x"})
        self.assertEqual((p["choice"], p["split"], p["solo"], p["second"]), ("default", 1.0, F.MAX, F.DEFAULT))

    def test_what_a_size_costs_is_said(self):
        ctx, p = F.fit(NINE, machine(), {"choice": "custom", "solo": 65536})
        line = F.say("Qwen3.5-9B", NINE, ctx, p)
        self.assertIn("64K context", line)
        self.assertIn("GB of cache", line)
        self.assertIn("doesn't fit", F.say("Qwen3.5-9B", NINE, ctx, None))


if __name__ == "__main__":
    unittest.main()
