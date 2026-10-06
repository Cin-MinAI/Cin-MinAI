# SPDX-License-Identifier: GPL-3.0-or-later
"""Browser content stays inert data at the native-message boundary."""

import io
import json
import os
import struct
import tempfile
import unittest

from cin_minai.firefox.host import Host, read_message


class Invocation:
    def __init__(self):
        self.value = None

    def return_value(self, value):
        self.value = value.unpack()[0]


class BrowserBoundaryTests(unittest.TestCase):
    def test_browser_text_cannot_turn_into_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = os.path.join(directory, "executed")
            attack = f"$(touch {marker}); `touch {marker}`; ; touch {marker}"
            payload = {"type": "video", "req": 1, "title": attack, "transcript": [[0, attack]]}
            raw = json.dumps(payload).encode()
            decoded = read_message(io.BytesIO(struct.pack("=I", len(raw)) + raw))
            invocation = Invocation()
            host = Host(out=io.BytesIO())
            host.waiting[1] = invocation
            host.handle(decoded)
            self.assertFalse(os.path.exists(marker))
            self.assertIn(attack, invocation.value)

    def test_oversized_native_message_is_not_read(self):
        stream = io.BytesIO(struct.pack("=I", (8 << 20) + 1))
        self.assertEqual(read_message(stream), {"type": "invalid"})


if __name__ == "__main__":
    unittest.main()
