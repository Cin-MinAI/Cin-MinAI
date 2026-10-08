# SPDX-License-Identifier: GPL-3.0-or-later
"""The live USB's model load (found on Ian's PC, 2026-10-07): the model is read once from start to finish before the
server starts — a stick is very slow at the server's scattered reads — and the sidebar shows how far it is."""

import os
import tempfile
import unittest
from unittest import mock

from cin_minai.inference import llamacpp
from cin_minai.sidebar import words


class StraightRead(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.dir = d.name + "/"
        self.model = os.path.join(d.name, "guide.gguf")
        with open(self.model, "wb") as f:
            f.write(os.urandom(20 << 20))  # 20 MiB: three 8 MiB reads
        self.b = llamacpp.LlamaCppBackend({"model": self.model, "server_dir": d.name}, log=lambda m: None)
        self.seen = []
        self.b.on_progress = lambda: self.seen.append(self.b.status().detail)

    def test_the_stick_is_read_once_with_progress(self):
        with mock.patch.object(llamacpp, "LIVE_MEDIA", (self.dir,)):
            self.b.warm(self.model)
        self.assertEqual(self.seen[-1], "stick:100")
        self.assertTrue(all(s.startswith("stick:") for s in self.seen))
        self.assertLessEqual(len(self.seen), 21)  # every 5 % at most

    def test_an_installed_model_is_not_read_first(self):
        self.b.warm(self.model)  # not under /cdrom or /run/live/medium
        self.assertEqual(self.seen, [])

    def test_a_read_error_doesnt_stop_the_load(self):
        with mock.patch.object(llamacpp, "LIVE_MEDIA", (self.dir,)), \
             mock.patch("builtins.open", side_effect=OSError("I/O error")):
            self.b.warm(self.model)  # no exception: the server still tries
        self.assertEqual(self.seen, [])


class Header(unittest.TestCase):
    def test_the_header_shows_the_read_in_each_language(self):
        for lang in ("en", "es", "pt", "fr", "de", "ja"):
            with mock.patch.object(words, "ui_lang", return_value=lang):
                _, _, second = words.status_line("loading", {"model": "Cin-MinAI guide", "detail": "stick:45"})
                self.assertIn("45", second, lang)
                self.assertTrue(words.waiting("loading", "", "stick:45"), lang)
        with mock.patch.object(words, "ui_lang", return_value="en"):
            self.assertIn("Reading the assistant from the USB stick: 45%",
                          words.status_line("loading", {"model": "x", "detail": "stick:45"})[2])
            self.assertEqual(words.waiting("loading", ""),
                             "Getting the assistant ready. The first time can take a minute or two.")


if __name__ == "__main__":
    unittest.main()
