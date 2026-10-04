# SPDX-License-Identifier: GPL-3.0-or-later
"""Answers shown formatted, not as raw Markdown (2026-10-04: "**[0:30]**" and "* " all through a video summary)."""

import unittest

from cin_minai.sidebar import words


class Markdown(unittest.TestCase):
    def test_bold_bullets_headings(self):
        md = words.markdown("## Steps\n* **[0:30]** A cartoon *Rick*\n  - nested `ls -la`")
        self.assertEqual(md.split("\n"), ["<b>Steps</b>", "• <b>[0:30]</b> A cartoon <i>Rick</i>",
                                          "  • nested <tt>ls -la</tt>"])

    def test_escaped_and_code_untouched(self):
        self.assertEqual(words.markdown("a <b> & c"), "a &lt;b&gt; &amp; c")
        self.assertEqual(words.markdown("`**not bold**`"), "<tt>**not bold**</tt>")
        self.assertEqual(words.markdown("```\nrm -rf <x>\n```"), "<tt>rm -rf &lt;x&gt;</tt>")

    def test_ordinary_text_left_alone(self):
        for t in ("snake_case_name", "2 * 3 * 4", "1. first\n2. second", "a ** b"):
            self.assertEqual(words.markdown(t), t)

    def test_links(self):
        self.assertEqual(words.markdown("[docs](https://example.org/a?b=1&c=2)"),
                         '<a href="https://example.org/a?b=1&amp;c=2">docs</a>')
        self.assertEqual(words.markdown("[x](javascript:alert(1))"), "[x](javascript:alert(1))")


if __name__ == "__main__":
    unittest.main()
