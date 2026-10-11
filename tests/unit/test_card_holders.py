# SPDX-License-Identifier: GPL-3.0-or-later
"""Who holds the graphics card, in words the person can act on (src/cin_minai/inference/hardware.py): 2026-10-11, the
writer fell back to the processor while AICUI's team B held the card, and the sidebar said only "the card is busy".

    python3 -m unittest tests.unit.test_card_holders -v        (from the repo root)
"""

import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))

from cin_minai.inference import hardware  # noqa: E402


class Holders(unittest.TestCase):
    def setUp(self):
        self.proc = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.proc, True)
        for pid, cmd in (("100", "/usr/lib/cinminai/llama/llama-server\0--host\0/run/user/1000/cinminai/llama-code.sock"),
                         ("200", "/usr/lib/cinminai/llama/llama-server\0--host\0/run/user/1000/cinminai/llama-senior.sock"),
                         ("300", "/usr/lib/cinminai/llama/llama-server\0--host\0/run/user/1000/cinminai/llama.sock"),
                         ("400", "/usr/bin/blender")):
            os.makedirs(os.path.join(self.proc, pid))
            with open(os.path.join(self.proc, pid, "cmdline"), "w") as f:
                f.write(cmd)

    def test_aicuis_models_and_other_programs_by_name_not_the_assistants_own(self):
        smi = ("100, /usr/lib/cinminai/llama/llama-server, 5856\n200, /usr/lib/cinminai/llama/llama-server, 4608\n"
               "300, /usr/lib/cinminai/llama/llama-server, 2700\n400, /usr/bin/blender, 900\n")
        with mock.patch.object(hardware, "_run", return_value=smi):
            self.assertEqual(hardware.card_holders(self.proc), ["AICUI's coding models", "blender"])
        with mock.patch.object(hardware, "_run", return_value=""):
            self.assertEqual(hardware.card_holders(self.proc), [])  # no nvidia-smi: nothing claimed


if __name__ == "__main__":
    unittest.main()
