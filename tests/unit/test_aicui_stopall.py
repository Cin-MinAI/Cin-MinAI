# SPDX-License-Identifier: GPL-3.0-or-later
"""The master Stop (src/cin_minai/aicui/stopall.py): everything under the session's roots ends at once — children in
their own process groups and sessions too (as the AI's commands and the model servers are) — and nothing else.

    python3 -m unittest tests.unit.test_aicui_stopall -v        (from the repo root, on Linux)
"""

import os
import subprocess
import sys
import time
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))

from cin_minai.aicui import stopall  # noqa: E402


@unittest.skipUnless(os.path.isdir("/proc/self"), "needs Linux /proc")
class StopAll(unittest.TestCase):
    def test_the_whole_tree_ends_its_own_sessions_too_and_nothing_else(self):
        # a session's agent: a shell with a model server and a command in their own sessions, a grandchild under one
        agent = subprocess.Popen(["bash", "-c", "setsid sleep 301 & setsid bash -c 'sleep 302 & wait' & sleep 303"])
        other = subprocess.Popen(["sleep", "304"])  # another window's work: not this session's
        self.addCleanup(other.kill)
        for _ in range(100):
            if len(stopall.tree([agent.pid])) >= 5:
                break
            time.sleep(0.05)
        under = stopall.tree([agent.pid])
        self.assertGreaterEqual(len(under), 5, under)  # bash, its setsid sleep, setsid bash + its sleep, sleep 303
        self.assertEqual(stopall.stop_all([agent.pid], keep={os.getpid()}), len(under))
        agent.wait(timeout=5)
        time.sleep(0.2)
        self.assertEqual([p for p in under if stopall.alive(p)], [])
        self.assertTrue(stopall.alive(other.pid))  # nothing outside the roots' trees

    def test_what_is_kept_stays(self):
        keep = subprocess.Popen(["sleep", "305"])
        self.addCleanup(keep.kill)
        self.assertEqual(stopall.tree([keep.pid], keep={keep.pid}), [])
        self.assertEqual(stopall.stop_all([keep.pid], keep={keep.pid}), 0)
        self.assertTrue(stopall.alive(keep.pid))


if __name__ == "__main__":
    unittest.main()
