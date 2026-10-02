# SPDX-License-Identifier: GPL-3.0-or-later
"""The model store (PLAN D60): download with resume, checksum before use, the user's choices. A fake server.

    python3 -m unittest tests.unit.test_models -v        (from the repo root)
"""

import hashlib
import io
import os
import sys
import tempfile
import threading
import unittest
from dataclasses import dataclass

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))

from cin_minai.daemon import models  # noqa: E402

DATA = os.urandom(3 * models.CHUNK + 123)


@dataclass(frozen=True)
class M:
    file: str = "Test-Q4_K_M.gguf"
    source: str = "someone/Test-GGUF@abc123"
    sha256: str = hashlib.sha256(DATA).hexdigest()
    size: int = len(DATA)


class Fake:
    """A server that honours Range (or not), and remembers the requests."""

    def __init__(self, data=DATA, ranges=True):
        self.data, self.ranges, self.requests = data, ranges, []

    def __call__(self, req, timeout=60):
        self.requests.append((req.full_url, req.headers.get("Range")))
        start = int(req.headers["Range"][6:-1]) if self.ranges and req.headers.get("Range") else 0
        r = io.BytesIO(self.data[start:])
        r.status = 206 if start else 200
        r.__enter__ = lambda: r
        return _Ctx(r)


class _Ctx:
    def __init__(self, r):
        self.r, self.status = r, r.status

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self, n):
        return self.r.read(n)


class Store(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()

    def test_download_checks_and_names_the_file_only_when_it_matches(self):
        fake = Fake()
        s = models.ModelStore(self.root, fake)
        seen = []
        path = s.download(M(), lambda a, b: seen.append(a), threading.Event())
        self.assertEqual(open(path, "rb").read(), DATA)
        self.assertEqual(fake.requests[0][0], "https://huggingface.co/someone/Test-GGUF/resolve/abc123/Test-Q4_K_M.gguf")
        self.assertEqual(seen[-1], len(DATA))
        self.assertFalse(os.path.exists(path + ".part"))

    def test_resume_after_an_interruption(self):
        s = models.ModelStore(self.root, Fake())
        with open(s.path(M().file) + ".part", "wb") as f:
            f.write(DATA[:models.CHUNK])
        fake = Fake()
        s.open = fake
        s.download(M(), lambda a, b: None, threading.Event())
        self.assertEqual(fake.requests[0][1], f"bytes={models.CHUNK}-")
        self.assertEqual(open(s.path(M().file), "rb").read(), DATA)

    def test_a_server_that_ignores_the_range_starts_over(self):
        s = models.ModelStore(self.root, Fake(ranges=False))
        with open(s.path(M().file) + ".part", "wb") as f:
            f.write(DATA[:100])
        s.download(M(), lambda a, b: None, threading.Event())
        self.assertEqual(open(s.path(M().file), "rb").read(), DATA)

    def test_a_wrong_checksum_is_removed_never_used(self):
        s = models.ModelStore(self.root, Fake(data=os.urandom(len(DATA))))
        with self.assertRaises(ValueError):
            s.download(M(), lambda a, b: None, threading.Event())
        self.assertFalse(s.has(M().file))
        self.assertFalse(os.path.exists(s.path(M().file) + ".part"))

    def test_stop(self):
        s = models.ModelStore(self.root, Fake())
        stop = threading.Event()
        stop.set()
        with self.assertRaises(models.Cancelled):
            s.download(M(), lambda a, b: None, stop)
        self.assertFalse(s.has(M().file))

    def test_the_users_choices(self):
        s = models.ModelStore(self.root, Fake())
        self.assertIsNone(s.in_use("writing"))
        s.use("writing", {"file": M().file, "args": ["-ngl", "99"]})
        self.assertIsNone(s.in_use("writing"))  # chosen but not downloaded: not in use
        s.download(M(), lambda a, b: None, threading.Event())
        self.assertEqual(s.in_use("writing")["args"], ["-ngl", "99"])
        s.decline("Other.gguf")
        self.assertEqual(models.ModelStore(self.root).state()["declined"], ["Other.gguf"])
        s.use("writing", None)
        self.assertIsNone(s.in_use("writing"))

    def test_benchmark_reads_llama_cpps_timings(self):
        self.assertEqual(models.benchmark(lambda msgs, max_tokens: ("text", {"predicted_per_second": 21.5})), 21.5)


if __name__ == "__main__":
    unittest.main()
