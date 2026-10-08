# SPDX-License-Identifier: GPL-3.0-or-later
"""Back onto the graphics card (Ian's PC, 2026-10-08): the guide fell back to the processor while AICUI's 27B held the
card, and stayed there after AICUI closed and the card was empty. Now it moves back once the card has room."""

import os
import tempfile
import types
import unittest
from unittest import mock

from cin_minai.inference import llamacpp
from cin_minai.inference.llamacpp import Profile

try:
    from cin_minai.daemon import service
except ImportError:  # no PyGObject
    service = None


class Room(unittest.TestCase):
    def backend(self, profile):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        model = os.path.join(d.name, "guide.gguf")
        with open(model, "wb") as f:
            f.write(b"\0" * 1024)
        b = llamacpp.LlamaCppBackend({"model": model, "server_dir": d.name, "desktop_reserve_mib": 1536},
                                     log=lambda m: None)
        b.profile = profile
        b.alive = lambda: True
        return b

    CPU = Profile("cpu", "none", 4096, "0", "on the processor (slower): the graphics card's memory is busy")
    CUDA = [Profile("cuda", "CUDA0", 8192, "all"), CPU]

    def test_room_when_the_card_is_free_again(self):
        b = self.backend(self.CPU)
        with mock.patch.object(b, "ladder", return_value=self.CUDA), \
             mock.patch.object(b, "free_mib", return_value=11000), \
             mock.patch.object(llamacpp.gguf, "read", side_effect=ValueError), \
             mock.patch.object(llamacpp, "need_mib", return_value=2582):
            self.assertTrue(b.card_has_room())
        with mock.patch.object(b, "ladder", return_value=self.CUDA), \
             mock.patch.object(b, "free_mib", return_value=0), \
             mock.patch.object(llamacpp.gguf, "read", side_effect=ValueError), \
             mock.patch.object(llamacpp, "need_mib", return_value=2582):
            self.assertFalse(b.card_has_room())  # the other model still holds it

    def test_never_without_a_usable_card_or_when_already_on_it(self):
        b = self.backend(self.CPU)
        with mock.patch.object(b, "ladder", return_value=[self.CPU]):
            self.assertFalse(b.card_has_room())  # no driver / no engine: the processor is right
        self.assertFalse(self.backend(self.CUDA[0]).card_has_room())


@unittest.skipIf(service is None, "needs PyGObject")
class Daemon(unittest.TestCase):
    def daemon(self, room, busy=False):
        backend = mock.Mock()
        backend.card_has_room.return_value = room
        backend.status.return_value = types.SimpleNamespace(state="ready")
        return types.SimpleNamespace(backend=backend, busy=busy, loading=False, start_load=mock.Mock())

    def test_moves_back_when_idle(self):
        s = self.daemon(room=True)
        service.Service.maybe_step_up(s)
        s.backend.unload.assert_called_once()
        s.start_load.assert_called_once()

    def test_never_mid_answer_or_without_room(self):
        for s in (self.daemon(room=True, busy=True), self.daemon(room=False)):
            service.Service.maybe_step_up(s)
            s.backend.unload.assert_not_called()


if __name__ == "__main__":
    unittest.main()
