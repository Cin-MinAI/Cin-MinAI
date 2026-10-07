# SPDX-License-Identifier: GPL-3.0-or-later
"""Update 5's words in the six v1 languages (D25): the daemon's (say.py) and the sidebar's (words.T) — every language
has every phrase, and every phrase fills in."""

import string
import unittest

from cin_minai.daemon import say
from cin_minai.sidebar import words

LANGS = ["en", "es", "pt", "fr", "de", "ja"]


def fields(text: str) -> set[str]:
    return {f for _, f, _, _ in string.Formatter().parse(text) if f}


class Daemon(unittest.TestCase):
    def test_every_language_has_every_phrase_with_the_same_blanks(self):
        for lang in LANGS:
            self.assertEqual(set(say.SAY[lang]), set(say.SAY["en"]), lang)
            for key, text in say.SAY["en"].items():
                self.assertEqual(fields(say.SAY[lang][key]), fields(text), (lang, key))

    def test_the_offer_names_the_button_the_card_shows(self):
        for lang in LANGS:
            button = words.t("search", lang)
            self.assertIn(button, say.say(lang, "search_offer"), lang)
            self.assertIn(button, say.say(lang, "send_online"), lang)
            self.assertIn(words.t("set_up", lang), say.say(lang, "watch_offer", what="x", at="08:00"), lang)

    def test_unknown_language_is_english(self):
        self.assertEqual(say.say("xx", "watch_top"), "the top stories")


class Sidebar(unittest.TestCase):
    def test_every_language_has_every_phrase_with_the_same_blanks(self):
        for lang in LANGS:
            self.assertEqual(set(words.T[lang]), set(words.T["en"]), lang)
            for key, text in words.T["en"].items():
                self.assertEqual(fields(words.T[lang][key]), fields(text), (lang, key))

    def test_cards_in_each_language(self):
        task = {"topic": "Linux Mint", "only": "Reddit", "at": "08:00", "paused": True,
                "runs": [{"at": "2026-10-07T08:00", "new": 3}]}
        for lang in LANGS:
            line = words.standing_line(task, lang)
            self.assertIn("Linux Mint", line)
            self.assertIn("3", line)
            self.assertIn("08:00", words.watch_head({"at": "08:00", "only": "Reddit"}, lang))
            note = words.watch_note({"provider": "Google News, Bing (news and web), Reddit and Mastodon"}, lang)
            self.assertIn("Mastodon", note)
            self.assertIn("Linux Mint", words.standing_head({"topic": "Linux Mint", "new": 2}, lang))
            self.assertIn("the test office", words.key_head({"name": "the test office", "use": "records"}, lang))
        self.assertEqual(words.search_note({"provider": "DuckDuckGo (or Bing, if DuckDuckGo asks for a pause)"}, "de"),
                         "Nur diese Wörter werden gesendet, an DuckDuckGo (oder Bing, wenn DuckDuckGo um eine Pause "
                         "bittet). Die gefundenen Seiten werden gelesen, um Ihnen zu antworten. Nichts über Sie oder "
                         "diesen Computer wird gesendet.")

    def test_the_examples_in_the_empty_list_really_set_up_a_watch(self):
        # "Ask for one in your own words, for example: …" — each example must be recognized in its language
        import re
        from cin_minai.daemon.intent import watch_request
        for lang in LANGS:
            examples = re.findall(r"[“«„「]\s*([^”»“」]+?)\s*[”»“」]", words.t("standing_none", lang))
            self.assertEqual(len(examples), 2, (lang, examples))
            for ex in examples:
                self.assertIsNotNone(watch_request(ex), (lang, ex))


if __name__ == "__main__":
    unittest.main()
