# SPDX-License-Identifier: GPL-3.0-or-later
"""The guide eval's optional sampling override belongs only to free-text Stage B."""

import importlib.util
import io
import json
import os
import sys
import unittest
from unittest import mock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SAVED_ARGV = sys.argv
sys.argv = ["run_eval.py"]
try:
    spec = importlib.util.spec_from_file_location("guide_run_eval", os.path.join(
        ROOT, "training", "eval", "guide", "run_eval.py"))
    run_eval = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(run_eval)
finally:
    sys.argv = SAVED_ARGV


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class SamplingTest(unittest.TestCase):
    def test_parse_sampling_rejects_unknown_keys(self):
        with self.assertRaises(run_eval.argparse.ArgumentTypeError):
            run_eval.parse_sampling('{"seed": 1}')

    def test_sampling_is_free_text_only(self):
        bodies = []

        def urlopen(req, timeout):
            bodies.append(json.loads(req.data))
            return Response(json.dumps({"choices": [{"message": {"content": "ok"}}]}).encode())

        sampling = {"temperature": 0, "dry_multiplier": 0.8, "dry_base": 1.75,
                    "dry_allowed_length": 3, "dry_penalty_last_n": 512}
        srv = run_eval.Server("http://localhost:1", "", "guide", sampling)
        with mock.patch.object(run_eval.urllib.request, "urlopen", side_effect=urlopen):
            srv.chat([], {"type": "object"}, 10)
            srv.chat([], None, 10)

        self.assertNotIn("dry_multiplier", bodies[0])
        self.assertIn("response_format", bodies[0])
        self.assertEqual(bodies[1]["dry_multiplier"], 0.8)
        self.assertNotIn("response_format", bodies[1])


class RepeatedTextTest(unittest.TestCase):
    def test_a_loop_under_the_length_limit_fails(self):
        # Codex's L03-ja (2026-10-07): finite, under the 500-character limit, and stuck in a loop
        loop = ("USBメモリーを安全に取り外すには、以下の手順を踏んでください。\n1. ファイルの左側にUSBメモリーが表示されているので、"
                "その名前をクリックします。\n3. USBメモリーが「eject」ボタンをクリックした後に「eject」ボタンが「eject」ボタンを"
                "クリックした後に「eject」ボタンが「eject」ボタンが「eject」ボタンが「eject」ボタンが「eject」ボタンをクリックした後に"
                "「eject」ボタンが「eject」ボタンをクリックした後に「eject」というメッセージが表示されます。")
        self.assertTrue(run_eval.repeated(loop))
        it = {"lang": "ja", "must": [], "q": "x"}
        self.assertTrue(any(f.startswith("repeats") for f in run_eval.stage_b(it, loop)))

    def test_normal_steps_pass(self):
        steps = ("Formatting a USB stick erases all files on it, so save any files you want first.\n"
                 "1. Open USB Stick Formatter from the Menu.\n2. Choose the USB stick you want to format.\n"
                 "3. Type a name for the new file system.\n4. Pick the Filesystem type.\n"
                 "5. Click Format to erase the stick.\n6. Type your password when prompted.")
        self.assertEqual(run_eval.repeated(steps), "")
        venv = ("1. Run `sudo apt install python3.12-venv` to install the missing package.\n"
                "2. Remove the incomplete folder with `rm -rf .venv`.\n"
                "3. Create the virtual environment again with `python3 -m venv .venv`.")
        self.assertEqual(run_eval.repeated(venv), "")


if __name__ == "__main__":
    unittest.main()
