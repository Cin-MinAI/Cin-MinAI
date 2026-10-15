# SPDX-License-Identifier: GPL-3.0-or-later
"""The Benchmark's coding run: what a model does as a junior, measured (Ian, 2026-10-15: the junior's script limit and
step limit "should be part of benchmark").

A task like a senior's — utils.py with K functions laid out as stubs, each named with its signature and what it must
do, the tests already written — for K = 2, 4, 8, 16, until one fails. Passed means every test passes. Each round keeps
the lines the model wrote and the steps it took; the largest that passed sets its limits (benchmark.coding_limits)."""

from __future__ import annotations

import os
import subprocess
import sys

ROUNDS = (2, 4, 8, 16)

# (name, signature, what it must do, the test lines)
FUNCTIONS = [
    ("clamp", "clamp(x, lo, hi)", "x limited to the range lo..hi (lo if below, hi if above)",
     ["clamp(5, 0, 3) == 3", "clamp(-1, 0, 3) == 0", "clamp(2, 0, 3) == 2"]),
    ("word_count", "word_count(text)", "the number of words, split on any whitespace; 0 for an empty text",
     ["word_count('a b  c') == 3", "word_count('') == 0", "word_count(' one\\ttwo\\n') == 2"]),
    ("is_palindrome", "is_palindrome(s)", "True if s reads the same backwards, ignoring case and anything that isn't a "
     "letter or digit", ["is_palindrome('A man, a plan, a canal: Panama')", "not is_palindrome('abc')",
                         "is_palindrome('')"]),
    ("fizzbuzz", "fizzbuzz(n)", "a list of strings for 1..n: 'Fizz' for multiples of 3, 'Buzz' of 5, 'FizzBuzz' of "
     "both, else the number", ["fizzbuzz(5) == ['1', '2', 'Fizz', '4', 'Buzz']", "fizzbuzz(15)[-1] == 'FizzBuzz'",
                               "fizzbuzz(0) == []"]),
    ("rle_encode", "rle_encode(s)", "run-length encoding: each run as its count then its character ('aaabcc' -> "
     "'3a1b2c'); '' -> ''", ["rle_encode('aaabcc') == '3a1b2c'", "rle_encode('') == ''", "rle_encode('x') == '1x'"]),
    ("rle_decode", "rle_decode(s)", "the inverse of rle_encode; counts may have several digits ('12x' -> twelve x)",
     ["rle_decode('3a1b2c') == 'aaabcc'", "rle_decode('12x') == 'x' * 12", "rle_decode('') == ''"]),
    ("to_roman", "to_roman(n)", "n (1..3999) in Roman numerals, with the subtractive forms (IV, IX, XL, XC, CD, CM)",
     ["to_roman(1994) == 'MCMXCIV'", "to_roman(4) == 'IV'", "to_roman(3999) == 'MMMCMXCIX'"]),
    ("flatten", "flatten(items)", "a flat list of everything in a list nested to any depth, in order",
     ["flatten([1, [2, [3, 4]], 5]) == [1, 2, 3, 4, 5]", "flatten([]) == []", "flatten([[[]]]) == []"]),
    ("chunk", "chunk(items, n)", "the list cut into lists of n items, the last one shorter if needed",
     ["chunk([1, 2, 3, 4, 5], 2) == [[1, 2], [3, 4], [5]]", "chunk([], 3) == []", "chunk([1, 2], 5) == [[1, 2]]"]),
    ("merge_intervals", "merge_intervals(intervals)", "overlapping or touching [start, end] pairs merged, sorted by "
     "start", ["merge_intervals([[1, 3], [2, 6], [8, 10]]) == [[1, 6], [8, 10]]",
               "merge_intervals([[5, 6], [1, 2], [2, 3]]) == [[1, 3], [5, 6]]", "merge_intervals([]) == []"]),
    ("top_words", "top_words(text, k)", "the k most common words (lowercased, split on whitespace), most common "
     "first, ties in alphabetical order", ["top_words('b a b c a b', 2) == ['b', 'a']",
                                           "top_words('Dog cat dog', 1) == ['dog']", "top_words('', 3) == []"]),
    ("caesar", "caesar(s, shift)", "letters shifted by shift places in the alphabet, wrapping round, keeping case; "
     "anything else unchanged", ["caesar('Abc, z!', 1) == 'Bcd, a!'", "caesar('abc', -1) == 'zab'",
                                 "caesar('Hi', 26) == 'Hi'"]),
    ("parse_pairs", "parse_pairs(text)", "a dict from 'key=value' parts separated by ';', values as strings, empty "
     "parts skipped", ["parse_pairs('a=1;b=2') == {'a': '1', 'b': '2'}", "parse_pairs('') == {}",
                       "parse_pairs('a=1;;') == {'a': '1'}"]),
    ("transpose", "transpose(matrix)", "rows turned into columns of a list of equal-length lists",
     ["transpose([[1, 2], [3, 4]]) == [[1, 3], [2, 4]]", "transpose([]) == []",
      "transpose([[1, 2, 3]]) == [[1], [2], [3]]"]),
    ("binary_search", "binary_search(items, x)", "the index of x in the sorted list, or -1 if it isn't there, by "
     "halving (not list.index)", ["binary_search([1, 3, 5, 7], 5) == 2", "binary_search([1, 3, 5, 7], 4) == -1",
                                  "binary_search([], 1) == -1"]),
    ("balanced", "balanced(s)", "True if every (, [ and { closes in the right order; other characters ignored",
     ["balanced('([]{})')", "not balanced('(]')", "not balanced('((')"]),
]


def lay_out(root: str, k: int) -> str:
    """The project for round k: utils.py with the stubs, test_utils.py with the tests. The task, as a senior gives it."""
    funcs = FUNCTIONS[:k]
    os.makedirs(root, exist_ok=True)
    with open(os.path.join(root, "utils.py"), "w", encoding="utf-8") as f:
        f.write('"""Small helpers."""\n\n')
        for name, sig, what, _ in funcs:
            f.write(f"\ndef {sig}:\n    \"\"\"{what[0].upper() + what[1:]}.\"\"\"\n    # TODO\n    raise NotImplementedError\n\n")
    with open(os.path.join(root, "test_utils.py"), "w", encoding="utf-8") as f:
        f.write("import unittest\n\nfrom utils import *  # noqa: F401,F403\n\n\nclass UtilsTest(unittest.TestCase):\n")
        for name, _, _, tests in funcs:
            f.write(f"    def test_{name}(self):\n" + "".join(f"        self.assertTrue({t})\n" for t in tests) + "\n")
        f.write("\nif __name__ == '__main__':\n    unittest.main()\n")
    spec = "\n".join(f"- {sig}: {what}" for _, sig, what, _ in funcs)
    return (f"Fill in the {k} functions in utils.py — each is laid out as a stub (its signature, a docstring, "
            f"# TODO, raise NotImplementedError). Replace each stub's body; keep the names and signatures; use only "
            f"Python's standard library.\n{spec}\nThe tests are in test_utils.py (don't change them): run "
            f"`python3 -m unittest test_utils` and fix what fails, then answer with what you did.")


def passes(root: str) -> tuple[bool, str]:
    """Every test in test_utils.py, run by us (not the model's word)."""
    try:
        r = subprocess.run([sys.executable, "-m", "unittest", "test_utils"], cwd=root, capture_output=True, text=True,
                           timeout=120)
    except subprocess.TimeoutExpired:
        return False, "the tests didn't finish in 2 minutes"
    tail = (r.stderr or r.stdout).strip().splitlines()
    return r.returncode == 0, (tail[-1] if tail else "")


def written(root: str) -> int:
    """Lines of code in utils.py beyond the stubs: what the model wrote."""
    try:
        with open(os.path.join(root, "utils.py"), encoding="utf-8") as f:
            code = [line for line in f if line.strip() and not line.strip().startswith(("#", '"""'))]
    except OSError:
        return 0
    return len([line for line in code if not line.lstrip().startswith("def ")])
