# SPDX-License-Identifier: GPL-3.0-or-later
"""Keeping the computer updated, asked in the person's own words (PLAN D88): daily updates on or off (and the wait, when
they name it), proposed as the Updates window's own settings (D89) on the Allow card, then the password; the daily
updates listed under Standing tasks."""

import string
import types
import unittest
from unittest import mock

from cin_minai.actions import admin
from cin_minai.daemon import intent, say
from cin_minai.sidebar import words

try:
    from cin_minai.daemon import service
except ImportError:  # no PyGObject
    service = None

ON = ["keep my computer updated", "Keep my laptop up to date please", "turn on automatic updates",
      "can you update automatically from now on?", "Mantén mi ordenador actualizado",
      "activa las actualizaciones automáticas", "mantenha meu computador atualizado", "garde mon ordinateur à jour",
      "Halte meinen Computer aktuell", "automatische Updates einschalten", "パソコンを常に最新の状態に保って",
      "自動更新をオンにして"]
OFF = ["turn off automatic updates", "stop automatic updates", "desactiva las actualizaciones automáticas",
       "desative as atualizações automáticas", "désactive les mises à jour automatiques",
       "automatische Updates ausschalten", "自動更新をオフにして"]
NEITHER = ["how do I keep my computer updated?", "keep me up to date on Linux Mint",  # a news watch (Standing tasks)
           "check for updates", "my updates failed", "what are automatic updates?", "me mantenha atualizado sobre o Linux",
           "Halte mich auf dem Laufenden über Linux Mint", "Linux Mintの最新情報を知らせて", "update my nvidia driver"]


class TheRequest(unittest.TestCase):
    def test_on(self):
        for text in ON:
            self.assertEqual(intent.updates_request(text), {"auto": True, "days": None}, text)

    def test_off(self):
        for text in OFF:
            self.assertEqual(intent.updates_request(text), {"auto": False, "days": None}, text)

    def test_neither(self):
        for text in NEITHER:
            self.assertIsNone(intent.updates_request(text), text)
        self.assertIsNotNone(intent.watch_request("keep me up to date on Linux Mint"))  # still a watch

    def test_the_wait_when_named(self):
        self.assertEqual(intent.updates_request("keep my computer updated, but wait 3 days first")["days"], 3)
        self.assertIsNone(intent.updates_request("keep my computer updated and wait 90 days")["days"])  # 1-60 only


class TheCard(unittest.TestCase):
    def test_says_what_it_does(self):
        summary = admin.VERBS["admin.update_settings"][4]
        self.assertEqual(summary({"settings": {"auto": True, "hold_days": 2}}),
                         "install updates by themselves once a day, each new one waiting 2 days first")
        self.assertEqual(summary({"settings": {"auto": False, "hold_days": 2}}), "stop installing updates by themselves")

    def test_every_language(self):
        def fields(text):
            return {f for _, f, _, _ in string.Formatter().parse(text) if f}
        for lang in ("es", "pt", "fr", "de", "ja"):
            for key in [k for k in say.SAY["en"] if k.startswith("upd_")]:
                self.assertEqual(fields(say.SAY[lang][key]), fields(say.SAY["en"][key]), (lang, key))
            for key in words.T_DAILY["en"]:
                self.assertEqual(fields(words.T[lang][key]), fields(words.T["en"][key]), (lang, key))

    def test_the_standing_line(self):
        self.assertIn("not run yet", words.daily_line({"hold_days": 0, "last": 0}, "en"))
        line = words.daily_line({"hold_days": 2, "last": 1_800_000_000, "installed": 4, "error": ""}, "en")
        self.assertIn("wait 2 days", line)
        self.assertIn("4 installed", line)
        self.assertIn("stopped", words.daily_line({"last": 1_800_000_000, "error": "install"}, "en"))


@unittest.skipIf(service is None, "needs PyGObject")
class TheOffer(unittest.TestCase):
    NOW = {"hold_days": 0, "auto": False, "own": [{"name": "firefox", "version": ""}], "looked": ["xz-utils=5.6.1"]}

    def offer(self, wanted, now=None):
        s = types.SimpleNamespace(actions=mock.Mock(kinds={"admin.update_settings": object()}),
                                  guide=types.SimpleNamespace(tools=types.SimpleNamespace(lang="en")))
        text = []
        with mock.patch("cin_minai.admin.updates.load_settings", return_value=dict(now or self.NOW)), \
             mock.patch.object(service.os.path, "exists", return_value=True):
            out = service.Service.offer_updates(s, wanted, text.append)
        return s, out, text[0]

    def test_on_keeps_everything_else(self):
        s, out, text = self.offer({"auto": True, "days": None})
        s.actions.propose.assert_called_once()
        self.assertEqual(s.actions.propose.call_args.args, ("admin.update_settings", {"settings": dict(self.NOW, auto=True)}))
        self.assertIn("click Allow, then type your password", text.replace("Click", "click"))
        self.assertIn("wait a few days first", text)  # the wait is offered, not decided (D30)
        self.assertTrue(out["proposed"])

    def test_the_wait_named(self):
        s, out, text = self.offer({"auto": True, "days": 2})
        self.assertEqual(s.actions.propose.call_args.args[1]["settings"]["hold_days"], 2)
        self.assertIn("wait 2 days first", text)

    def test_already_and_off(self):
        s, out, text = self.offer({"auto": True, "days": None}, dict(self.NOW, auto=True))
        s.actions.propose.assert_not_called()
        self.assertIn("already on", text)
        s, out, text = self.offer({"auto": False, "days": None}, dict(self.NOW, auto=True))
        self.assertFalse(s.actions.propose.call_args.args[1]["settings"]["auto"])
        self.assertIn("stops the daily updates", text)


if __name__ == "__main__":
    unittest.main()
