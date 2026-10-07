# SPDX-License-Identifier: GPL-3.0-or-later
"""The time, said by the daemon in the person's language (no model; round 3, 2026-10-07)."""

import datetime as dt
import json
import unittest

from cin_minai.daemon.facts import direct_reply, say_time

T = dt.datetime(2026, 10, 7, 16, 5)


class Time(unittest.TestCase):
    def test_six_languages(self):
        self.assertEqual(say_time(T, "en"), "It's 4:05 PM, Wednesday 7 October 2026.")
        self.assertEqual(say_time(T, "es"), "Son las 16:05 del miércoles 7 de octubre de 2026.")
        self.assertEqual(say_time(T, "pt"), "São 16:05 de quarta-feira, 7 de outubro de 2026.")
        self.assertEqual(say_time(T, "fr"), "Il est 16 h 05, le mercredi 7 octobre 2026.")
        self.assertEqual(say_time(T, "de"), "Es ist 16:05 Uhr, Mittwoch, 7. Oktober 2026.")
        self.assertEqual(say_time(T, "ja"), "今は2026年10月7日（水）16時05分です。")
        self.assertEqual(say_time(T.replace(hour=1), "es")[:9], "Es la 1:0")
        self.assertEqual(say_time(T.replace(hour=0), "en")[:12], "It's 12:05 A")

    def test_only_for_the_time(self):
        res = json.dumps({"iso": "2026-10-07T16:05-04:00"})
        self.assertEqual(direct_reply("inspect_system", {"topic": "time"}, res, "en"),
                         "It's 4:05 PM, Wednesday 7 October 2026.")
        self.assertIsNone(direct_reply("inspect_system", {"topic": "memory"}, res, "en"))
        self.assertIsNone(direct_reply("lookup_help", {}, "card", "en"))
        self.assertIsNone(direct_reply("inspect_system", {"topic": "time"}, "{}", "en"))


if __name__ == "__main__":
    unittest.main()
