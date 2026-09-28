# SPDX-License-Identifier: GPL-3.0-or-later
"""LlamaCppBackend pieces that don't need a model (src/cin_minai/inference/llamacpp.py).

    python3 -m unittest tests.unit.test_llamacpp -v        (from the repo root; the process tests need Linux)
"""

import os
import subprocess
import sys
import threading
import time
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))

from cin_minai.inference import llamacpp  # noqa: E402


@unittest.skipUnless(sys.platform.startswith("linux"), "process tests need Linux")
class SpawnerTest(unittest.TestCase):
    def test_child_outlives_the_thread_that_asked(self):
        # regression: with PR_SET_PDEATHSIG the child died when the asking thread ended (2026-09-28)
        sp, box = llamacpp.Spawner(), []
        t = threading.Thread(target=lambda: box.append(sp.popen(["sleep", "30"])))
        t.start()
        t.join()
        time.sleep(0.5)
        try:
            self.assertIsNone(box[0].poll(), "the child died with the thread that started it")
        finally:
            box[0].kill()
            box[0].wait()

    def test_child_dies_with_the_daemon(self):
        code = ("import sys, time; sys.path.insert(0, %r); from cin_minai.inference import llamacpp;"
                "p = llamacpp.Spawner().popen(['sleep', '30']); print(p.pid, flush=True); time.sleep(30)"
                % os.path.join(ROOT, "src"))
        parent = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE, text=True)
        child = int(parent.stdout.readline())
        parent.kill()
        parent.wait()
        time.sleep(0.5)
        with open(f"/proc/{child}/stat") if os.path.exists(f"/proc/{child}/stat") else open(os.devnull) as f:
            state = f.read().split(") ")[-1][:1] if f.name != os.devnull else "gone"
        self.assertIn(state, ("gone", "Z"), "the server outlived the daemon")


class LadderTest(unittest.TestCase):
    def test_device_regex_matches_the_pinned_server(self):
        out = ("Available devices:\n  CUDA0: NVIDIA GeForce GTX 1080 Ti (11162 MiB, 9324 MiB free)\n"
               "  Vulkan0: Intel(R) UHD Graphics 620 (KBL GT2) (7872 MiB, 7000 MiB free)\n"
               "  Vulkan1: AMD Radeon RX 6600 (8176 MiB, 7800 MiB free)\n")  # first line: 7fe450e, Mint box
        devs = [(m[0], m[1], int(m[2]), int(m[3])) for m in llamacpp.DEVICE_RE.findall(out)]
        self.assertEqual(devs[0], ("CUDA0", "NVIDIA GeForce GTX 1080 Ti", 11162, 9324))
        self.assertEqual(llamacpp.LlamaCppBackend.pick_device("vulkan", devs), "Vulkan1")
        self.assertEqual(llamacpp.LlamaCppBackend.pick_device("cuda", devs), "CUDA0")
        self.assertEqual(llamacpp.LlamaCppBackend.pick_device("vulkan", []), "Vulkan0")

    def test_need_mib_matches_the_measured_guide(self):
        # MODEL_CARD.md: 2,783,446,848-byte file, 8K context -> 3,032 MiB peak; the estimate must cover it
        need = llamacpp.need_mib(2783446848, 8192)
        self.assertGreaterEqual(need, 3032)
        self.assertLess(need, 3032 + 300)


if __name__ == "__main__":
    unittest.main()
