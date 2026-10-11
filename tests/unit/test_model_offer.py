# SPDX-License-Identifier: GPL-3.0-or-later
"""The model offer (D60/D93): read the machine the first time it's asked, whatever the clock says. Found on Ian's PC
(2026-10-07): for 10 minutes after every boot no offer was ever made, because "never read" was time 0 on a clock that
counts from the boot."""

import types
import unittest
from unittest import mock

try:
    from cin_minai.daemon import service
except ImportError:  # no PyGObject
    service = None

PLAN = {"model": "Qwen3.8-27B IQ3_XXS", "file": "Qwen3.8-27B-UD-IQ3_XXS.gguf", "why": "", "mode": "all on the card",
        "tok_s": (12, 23), "size": 10934860704, "source": "unsloth/Qwen3.8-27B-GGUF@4ca7207"}


@unittest.skipIf(service is None, "needs PyGObject")
class Offer(unittest.TestCase):
    def daemon(self):
        store = mock.Mock()
        store.in_use.return_value = None
        store.state.return_value = {"declined": []}
        store.has.return_value = False
        store.where.return_value = {}
        store.free_bytes.return_value = 400 << 30
        return types.SimpleNamespace(offers={}, store=store)

    def test_just_after_boot_the_machine_is_read(self):
        s = self.daemon()
        with mock.patch.object(service.time, "monotonic", return_value=235.0), \
             mock.patch.object(service.matcher, "read_machine"), \
             mock.patch.object(service.matcher, "match", return_value={"coding": PLAN}) as match:
            out = service.Service.model_offer(s, "coding")
        match.assert_called_once()
        self.assertEqual(out["offer"]["model"], "Qwen3.8-27B IQ3_XXS")

    def test_read_again_only_after_ten_minutes(self):
        s = self.daemon()
        with mock.patch.object(service.matcher, "read_machine"), \
             mock.patch.object(service.matcher, "match", return_value={"coding": PLAN}) as match:
            for t in (100.0, 400.0, 699.0, 701.0):
                with mock.patch.object(service.time, "monotonic", return_value=t):
                    service.Service.model_offer(s, "coding")
        self.assertEqual(match.call_count, 2)  # at 100 and at 701


if __name__ == "__main__":
    unittest.main()


@unittest.skipIf(service is None, "needs PyGObject")
class Replies(unittest.TestCase):
    """2026-10-11: ProjectInfo with no writing project open returned nothing where it's declared to answer, and the
    sidebar got "Type of return value is incorrect: expected '(s)', got '()'" — the writing tool glitched."""

    def test_a_method_declared_to_answer_always_answers(self):
        self.assertTrue(service.OUT_ARGS["ProjectInfo"])
        self.assertFalse(service.OUT_ARGS["ProjectClose"])
        sent = []
        inv = types.SimpleNamespace(return_value=sent.append)
        service.Service.answer(None, inv, "ProjectInfo", None)
        self.assertEqual(sent[-1].unpack(), ("null",))  # null, which the sidebar reads as nothing to show
        service.Service.answer(None, inv, "ProjectInfo", {"title": "The Bottle"})
        self.assertEqual(sent[-1].unpack(), ('{"title": "The Bottle"}',))
        service.Service.answer(None, inv, "ProjectClose", None)
        self.assertIsNone(sent[-1])
