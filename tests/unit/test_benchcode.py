# SPDX-License-Identifier: GPL-3.0-or-later
"""The Benchmark's coding run (aicui/benchcode.py): its tasks must be fair — every test passes for a correct answer
and fails for the stubs — and what it measures sets the junior's limits (inference/benchmark.py)."""

import os
import shutil
import tempfile
import unittest

from cin_minai.aicui import benchcode as C
from cin_minai.inference import benchmark as B

REFERENCE = '''
from collections import Counter


def clamp(x, lo, hi):
    return max(lo, min(hi, x))


def word_count(text):
    return len(text.split())


def is_palindrome(s):
    t = [c.lower() for c in s if c.isalnum()]
    return t == t[::-1]


def fizzbuzz(n):
    return ["FizzBuzz" if i % 15 == 0 else "Fizz" if i % 3 == 0 else "Buzz" if i % 5 == 0 else str(i)
            for i in range(1, n + 1)]


def rle_encode(s):
    out, i = [], 0
    while i < len(s):
        j = i
        while j < len(s) and s[j] == s[i]:
            j += 1
        out.append(f"{j - i}{s[i]}")
        i = j
    return "".join(out)


def rle_decode(s):
    out, num = [], ""
    for c in s:
        if c.isdigit():
            num += c
        else:
            out.append(c * int(num))
            num = ""
    return "".join(out)


def to_roman(n):
    vals = [(1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"), (50, "L"), (40, "XL"),
            (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")]
    out = ""
    for v, r in vals:
        while n >= v:
            out, n = out + r, n - v
    return out


def flatten(items):
    out = []
    for x in items:
        out.extend(flatten(x) if isinstance(x, list) else [x])
    return out


def chunk(items, n):
    return [items[i:i + n] for i in range(0, len(items), n)]


def merge_intervals(intervals):
    out = []
    for a, b in sorted(intervals):
        if out and a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out


def top_words(text, k):
    c = Counter(text.lower().split())
    return [w for w, _ in sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))[:k]]


def caesar(s, shift):
    out = []
    for c in s:
        if c.isalpha() and c.isascii():
            base = ord("A") if c.isupper() else ord("a")
            out.append(chr((ord(c) - base + shift) % 26 + base))
        else:
            out.append(c)
    return "".join(out)


def parse_pairs(text):
    return dict(p.split("=", 1) for p in text.split(";") if p)


def transpose(matrix):
    return [list(r) for r in zip(*matrix)]


def binary_search(items, x):
    lo, hi = 0, len(items) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        if items[mid] == x:
            return mid
        if items[mid] < x:
            lo = mid + 1
        else:
            hi = mid - 1
    return -1


def balanced(s):
    pairs, stack = {")": "(", "]": "[", "}": "{"}, []
    for c in s:
        if c in "([{":
            stack.append(c)
        elif c in pairs:
            if not stack or stack.pop() != pairs[c]:
                return False
    return not stack
'''


class CodingRunTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, True)

    def test_the_stubs_fail_and_a_correct_answer_passes(self):
        task = C.lay_out(self.root, 16)
        self.assertIn("binary_search(items, x)", task)  # the specifics, as a senior gives them
        self.assertFalse(C.passes(self.root)[0])
        with open(os.path.join(self.root, "utils.py"), "w") as f:
            f.write(REFERENCE)
        ok, why = C.passes(self.root)
        self.assertTrue(ok, why)
        self.assertGreater(C.written(self.root), 60)

    def test_each_round_asks_for_its_own_functions(self):
        C.lay_out(self.root, 2)
        with open(os.path.join(self.root, "test_utils.py")) as f:
            tests = f.read()
        self.assertIn("test_clamp", tests)
        self.assertNotIn("test_fizzbuzz", tests)

    def test_the_largest_passing_round_sets_the_limits(self):
        store = os.path.join(self.root, "benchmarks.json")
        self.assertEqual(B.coding_limits("m.gguf", "card", store), {"lines": 150, "steps": 25, "measured": False})
        B.record_coding("m.gguf", "card", 2, True, store, lines=9, steps=6)
        B.record_coding("m.gguf", "card", 4, True, store, lines=27, steps=14)
        B.record_coding("m.gguf", "card", 8, False, store, lines=40, steps=60)
        self.assertEqual(B.coding_limits("m.gguf", "card", store), {"lines": 40, "steps": 21, "measured": True})


class CodingRunEndToEndTest(unittest.TestCase):
    def test_a_round_is_run_checked_and_recorded(self):
        import json
        import sys
        from unittest import mock
        sys.path.insert(0, os.path.dirname(__file__))
        from test_aicui_agent import Scripted, step

        from cin_minai.aicui import bench
        from cin_minai.inference.matcher import CATALOG, Machine
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        code = ('"""Small helpers."""\n\n\ndef clamp(x, lo, hi):\n    return max(lo, min(hi, x))\n\n\n'
                'def word_count(text):\n    return len(text.split())\n')
        model = Scripted([step("Write both.", tool="write", path="utils.py", content=code),
                          step("Done.", tool="answer", text="Both filled in; the tests pass.")])
        fake = mock.Mock(chat=model, unload=lambda: None)
        nine = next(m for ms in CATALOG.values() for m in ms if m.file == "Qwen3.5-9B-Q4_K_M.gguf")
        machine = Machine([{"name": "Test card", "api": "CUDA0", "total_mib": 11264, "free_mib": 11000}],
                          32, 26, 4, True, 5.0, 50)
        store = os.path.join(d, "benchmarks.json")
        with mock.patch.dict(os.environ, {"XDG_DATA_HOME": d}), mock.patch.object(bench, "backend_for",
                                                                                  return_value=fake):
            os.makedirs(os.path.join(d, "cinminai"))
            lines = bench.coding_run(None, machine, nine.file, nine, "the 9B", say=lambda s: None, rounds=(2,))
        self.assertIn("2 functions: passed — ", lines[1])
        with open(os.path.join(d, "cinminai", "benchmarks.json")) as f:
            runs = json.load(f)[B.coding_key(nine.file, "Test card")]
        self.assertEqual((runs[0]["functions"], runs[0]["ok"], runs[0]["steps"]), (2, True, 2))
        self.assertIn("(measured)", lines[0])
        self.assertTrue(store)


if __name__ == "__main__":
    unittest.main()
