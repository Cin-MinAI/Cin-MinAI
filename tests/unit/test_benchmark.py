# SPDX-License-Identifier: GPL-3.0-or-later
"""The Benchmark button's store and what uses it (inference/benchmark.py): sizes that failed on this card are never
offered again; a crash at work is recorded and steps down to Cin-MinAI's own size, not 4K (test14, 2026-10-14: the
27B at 84K crashed out of graphics memory and was started at 84K five times)."""

import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from cin_minai.inference import benchmark as B
from cin_minai.inference import llamacpp


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.file = os.path.join(self.dir.name, "cinminai", "benchmarks.json")
        self.key = B.setup_key(["Qwen3.8-27B-UD-IQ3_XXS.gguf"], "NVIDIA GeForce GTX 1080 Ti", "0.0.1+git1")

    def tearDown(self):
        self.dir.cleanup()

    def test_not_measured_changes_nothing(self):
        self.assertEqual(B.cap([86016], self.key, self.file), ([86016], ""))
        self.assertIn("Not measured", B.summary(self.key, self.file))

    def test_a_size_that_failed_is_never_offered_again(self):
        B.record(self.key, 32768, True, self.file, gen_tps=17.2, card_mib=10700)
        B.record(self.key, 49152, True, self.file, gen_tps=15.9)
        B.record(self.key, 65536, False, self.file, why="out of graphics memory")
        self.assertEqual(B.cap([86016], self.key, self.file)[0], [49152])
        self.assertIn("64K failed", B.cap([86016], self.key, self.file)[1])
        self.assertEqual(B.cap([40960], self.key, self.file), ([40960], ""))  # below the failure: as chosen
        self.assertEqual(B.summary(self.key, self.file),
                         "Measured on this card: held up to 48K (16 words a second), 64K failed.")

    def test_a_new_measurement_replaces_the_old_one(self):
        B.record(self.key, 65536, False, self.file, why="crashed")
        B.record(self.key, 65536, True, self.file)  # after a new engine or a freed card, it held
        self.assertEqual(B.limits(self.key, self.file)["failed"], None)
        self.assertEqual(len(B.limits(self.key, self.file)["runs"]), 1)

    def test_a_pair_is_capped_per_model(self):
        key = B.setup_key(["Qwen3.5-9B-Q4_K_M.gguf", "Qwen3.6-35B-A3B-Q4_K_M.gguf"], "1080 Ti", "x")
        B.record(key, [65536, 65536], True, self.file)
        B.record(key, [98304, 98304], False, self.file)
        self.assertEqual(B.cap([90112, 126976], key, self.file)[0], [65536, 65536])

    def test_a_new_engine_or_card_is_measured_again(self):
        self.assertNotEqual(self.key, B.setup_key(["Qwen3.8-27B-UD-IQ3_XXS.gguf"], "NVIDIA GeForce GTX 1080 Ti",
                                                   "0.0.1+git2"))


class StepDownTest(unittest.TestCase):
    def backend(self, **cfg):
        b = llamacpp.LlamaCppBackend({"server_dir": "/nowhere", "context": 86016, **cfg}, lambda m: None)
        return b

    def test_the_ladder_steps_down_to_cinminais_own_size_first(self):
        gpu = mock.Mock(driver="nvidia", vendor="nvidia")
        with mock.patch.object(llamacpp.hardware, "gpus", return_value=[gpu]), \
                mock.patch.object(llamacpp.os.path, "exists", return_value=True):
            steps = self.backend(fallback_context=32768, build="cuda").ladder()
        self.assertEqual([p.context for p in steps][:3], [86016, 32768, 4096])
        self.assertIn("84K didn't hold", steps[1].reduced)

    @unittest.skipUnless(sys.platform.startswith("linux"), "process tests need Linux")
    def test_a_crash_is_waited_for_recorded_and_the_next_start_is_smaller(self):
        b = self.backend(fallback_context=32768)
        b.sock = os.path.join(tempfile.gettempdir(), "cinminai-test-no-such.sock")
        p86 = llamacpp.Profile("cuda", "CUDA0", 86016, "all")
        b.profile, b.load = p86, (lambda: None)
        b.ladder = lambda: [p86, llamacpp.Profile("cuda", "CUDA0", 32768, "all", "smaller")]
        b.proc = subprocess.Popen(["sleep", "1"])  # still dying when the connection is refused
        seen = []
        b.on_crash = seen.append
        with self.assertRaises(llamacpp.BackendError) as e:
            b.chat([{"role": "user", "content": "hi"}], max_tokens=1)
        self.assertIn("smaller setting", str(e.exception))
        self.assertEqual(seen, [86016])
        self.assertEqual(b.skip, 1)  # the next load starts at the 32K step


if __name__ == "__main__":
    unittest.main()
