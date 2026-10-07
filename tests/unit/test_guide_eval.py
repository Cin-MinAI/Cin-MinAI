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


if __name__ == "__main__":
    unittest.main()
