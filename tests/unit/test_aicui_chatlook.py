# SPDX-License-Identifier: GPL-3.0-or-later
import os
import tempfile
import unittest

from cin_minai.aicui import chatlook as C


class ChatLookTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.file = os.path.join(self.dir.name, "cinminai", "aicui-chat.json")

    def tearDown(self):
        self.dir.cleanup()

    def test_nothing_chosen_is_the_theme(self):
        self.assertEqual(C.load(self.file), C.defaults())
        self.assertEqual(C.css(C.defaults()).strip(), "")  # bubbles as AICUI draws them

    def test_choices_are_kept(self):
        p = C.defaults()
        p.update(style="boxes", background="rgb(10,20,30)")
        p["who"]["junior"].update(color="#33d17a", font="DejaVu Sans Mono Bold 12")
        C.save(p, self.file)
        self.assertEqual(C.load(self.file), p)

    def test_only_colours_and_font_names_reach_the_css(self):
        p = C.clean({"style": "neon", "background": "red; } * { color: red",
                     "who": {"ai": {"color": "url(x)", "font": "Sans}{ 11"}, "nobody": {"color": "#fff"}}})
        self.assertEqual(p["style"], "bubbles")
        self.assertEqual(p["background"], "")
        self.assertEqual(p["who"]["ai"]["color"], "")
        self.assertEqual(p["who"]["ai"]["font"], "Sans 11")
        self.assertNotIn("nobody", p["who"])

    def test_a_font_name_becomes_css(self):
        css = C.font_css("DejaVu Sans Mono Bold Italic 11")
        self.assertIn('font-family: "DejaVu Sans Mono";', css)
        self.assertIn("font-size: 11pt;", css)
        self.assertIn("font-weight: 700;", css)
        self.assertIn("font-style: italic;", css)

    def test_each_speaker_has_its_own_look(self):
        p = C.defaults()
        p["who"]["user"].update(background="rgba(1,2,3,0.5)", color="#ffffff", font="Ubuntu 14")
        css = C.css(p)
        self.assertIn(".chat-pane .bubble-user {", css)
        self.assertIn("background-color: rgba(1,2,3,0.5);", css)
        self.assertIn("font-size: 14pt;", css)

    def test_the_terminal_has_no_bubble_backgrounds(self):
        """Ian: no background in bubbles or boxes, since there are none — only the chat's background has a colour."""
        p = C.defaults()
        p.update(style="terminal", background="#000000")
        p["who"]["ai"].update(background="#ff0000", color="#00ff00")
        css = C.css(p)
        self.assertIn(".chat-pane, .chat-pane row { background-color: #000000; }", css)
        self.assertNotIn("#ff0000", css)
        self.assertIn("color: #00ff00;", css)
        self.assertIn("background: none", css)

    def test_text_stays_readable_on_a_chosen_background(self):
        p = C.defaults()
        p.update(background="rgb(20,20,28)")
        self.assertIn("color: #e8e8e8;", C.css(p))  # light text on a dark chat
        p.update(background="#fafafa")
        self.assertIn("color: #1e1e1e;", C.css(p))
        p.update(color="#ff0000")
        self.assertNotIn("#1e1e1e", C.css(p))  # the person's own choice stands


class TerminalLookTest(unittest.TestCase):
    def test_a_speaker_prints_in_its_chosen_colour(self):
        p = C.defaults()
        p["terminal"]["who"]["junior"]["color"] = "#33d17a"
        out = C.paint("junior", "(junior) wrote \033[1mx\033[0m and more", "\033[2m", p)
        self.assertTrue(out.startswith("\033[38;2;51;209;122m"))
        self.assertIn("\033[0m\033[38;2;51;209;122m and more", out)  # the colour holds after a reset inside
        self.assertTrue(out.endswith("\033[0m"))

    def test_no_colour_chosen_keeps_the_agents_own(self):
        p = C.defaults()
        self.assertEqual(C.paint("junior", "hi", "\033[2m", p), "\033[2mhi\033[0m")
        self.assertEqual(C.paint("ai", "hi", "", p), "hi")

    def test_the_terminal_keeps_one_font_and_no_line_backgrounds(self):
        p = C.clean({"terminal": {"background": "#101010", "font": "Monospace 13",
                                  "who": {"ai": {"color": "#ffffff", "background": "#ff0000", "font": "Serif 20"},
                                          "user": {"color": "nope"}}}})
        self.assertEqual((p["terminal"]["background"], p["terminal"]["font"]), ("#101010", "Monospace 13"))
        self.assertEqual(p["terminal"]["who"]["ai"], {"color": "#ffffff"})
        self.assertEqual(p["terminal"]["who"]["user"], {"color": ""})

    def test_new_colours_hold_from_the_next_line(self):
        with tempfile.TemporaryDirectory() as d:
            os.environ["XDG_CONFIG_HOME"] = d
            try:
                self.assertEqual(C.paint("ai", "a"), "a")
                p = C.defaults()
                p["terminal"]["who"]["ai"]["color"] = "rgb(1,2,3)"
                C.save(p)
                os.utime(C.path(), (1, 1))  # a different time than any read before
                self.assertEqual(C.paint("ai", "a"), "\033[38;2;1;2;3ma\033[0m")
            finally:
                del os.environ["XDG_CONFIG_HOME"]
                C._cache.update(mtime=None, prefs=None)


if __name__ == "__main__":
    unittest.main()
