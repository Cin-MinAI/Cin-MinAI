# SPDX-License-Identifier: GPL-3.0-or-later
"""Standing watches (D88) and keys for sources that need one (D92): set up once, only what's new; a key goes to the
keyring and nowhere else."""

import datetime as dt
import json
import os
import tempfile
import threading
import types
import unittest
from unittest import mock

from cin_minai.daemon import intent, keys, newsscan, standing

try:
    from cin_minai.daemon import service
except ImportError:  # no PyGObject
    service = None

NOW = dt.datetime(2026, 10, 7, 9, 30)


class FakeKeyring:
    def __init__(self):
        self.items = {}

    def get(self, source):
        return self.items.get(source, "")

    def store(self, source, label, key):
        self.items[source] = key

    def forget(self, source):
        self.items.pop(source, None)


SOURCE = keys.Source("the test office", "https://example.org/signup", ("Make an account.", "Copy the key."),
                     use="test records")


class Keys(unittest.TestCase):
    def setUp(self):
        self.ring = FakeKeyring()
        patches = [mock.patch.object(keys, "keyring", self.ring), mock.patch.dict(keys.SOURCES, {"test": SOURCE})]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def test_a_key_is_kept_in_the_keyring_and_the_card_never_shows_it(self):
        self.assertEqual(keys.store("test", "  abcd1234EFGH5678ijkl  "), "the test office")
        self.assertEqual(self.ring.items["test"], "abcd1234EFGH5678ijkl")
        card = keys.card("test")
        self.assertNotIn("abcd1234EFGH5678ijkl", json.dumps(card))
        self.assertTrue(card["saved"])
        self.assertEqual(card["steps"], ["Make an account.", "Copy the key."])

    def test_a_wrong_key_is_refused_without_repeating_it(self):
        with self.assertRaises(keys.KeyError_) as e:
            keys.store("test", "not a key with spaces")
        self.assertNotIn("not a key", str(e.exception))
        with self.assertRaises(keys.KeyError_):
            keys.store("nobody", "abcd1234EFGH5678ijkl")

    def test_no_keyring_means_no_key_not_a_crash(self):
        class Broken:
            def get(self, source):
                raise RuntimeError("no Secret Service")
        with mock.patch.object(keys, "keyring", Broken()):
            self.assertEqual(keys.get("test"), "")

    def test_keyed_sources_use_the_key_or_say_it_is_needed(self):
        fetch = mock.Mock(return_value=[{"kind": "official", "source": "example.org", "title": "Record 1",
                                         "url": "https://example.org/1", "what": "patent records"}])
        with mock.patch.dict(newsscan.KEYED, {"test": (lambda topic: "patent" in topic, fetch)}):
            self.assertEqual(newsscan.keyed("Pfizer patents"), ([], ["test"]))
            self.assertEqual(newsscan.keyed("the weather"), ([], []))
            self.ring.items["test"] = "abcd1234EFGH5678ijkl"
            items, needed = newsscan.keyed("Pfizer patents")
        fetch.assert_called_once_with("Pfizer patents", "en", "abcd1234EFGH5678ijkl")
        self.assertEqual((len(items), needed), (1, []))
        text = newsscan.report("x", [], "en", [], "", None, None, ["test"])
        self.assertIn("(Not searched: the test office — it needs a free key; the card below shows how to get one.)",
                      text)


class PastedKey(unittest.TestCase):
    def test_keys_and_tokens(self):
        for t in ("sk-ant-api03-Zx9wQ8vR7tU6sP5oN4mL3kJ2", "ghp_16C7e42F292c6912E7710c838347Ae178B4a",
                  "3f2a9c7d1e8b4a6f0c5d2e9b7a1f4c8d", "  AKIAIOSFODNN7EXAMPLE1234  "):
            self.assertTrue(keys.looks_like_key(t), t)

    def test_questions_files_and_addresses_are_not_keys(self):
        for t in ("Linux Mint", "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "/home/ian/Documents/report2026.odt",
                  "ubuntu-24.04-desktop-amd64.iso", "supercalifragilisticexpialidocious",
                  "what-is-the-best-distro-for-gaming", "keep me up to date on Pfizer patents", "12345"):
            self.assertFalse(keys.looks_like_key(t), t)


class Watches(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.file = os.path.join(d.name, "cinminai", "standing.json")
        self.store = standing.Store(self.file)

    def test_due_once_a_day_at_its_time_and_kept_on_disk(self):
        t = self.store.add("Pfizer", "08:00", "en", NOW)
        self.assertEqual(self.store.due(NOW), [t])  # never run: due
        self.store.ran(t["id"], NOW, [], "Google News", "")
        self.assertEqual(self.store.due(NOW + dt.timedelta(hours=10)), [])  # 19:30, same day
        self.assertEqual(len(self.store.due(NOW + dt.timedelta(hours=23))), 1)  # 8:30 next day
        self.assertEqual(standing.Store(self.file).tasks[0]["topic"], "Pfizer")

    def test_a_computer_that_was_off_runs_it_once_when_back(self):
        t = self.store.add("x", "08:00", "en", NOW)
        self.store.ran(t["id"], NOW, [], "", "")
        later = NOW + dt.timedelta(days=3, hours=-3)  # 3 days later, 6:30: yesterday's 8:00 was missed
        self.assertEqual(len(self.store.due(later)), 1)
        self.store.ran(t["id"], later, [], "", "")
        self.assertEqual(self.store.due(later + dt.timedelta(hours=1)), [])

    def test_only_what_was_not_shown_before(self):
        t = self.store.add("x", "08:00", "en", NOW)
        a, b = {"url": "https://a/", "title": "A"}, {"url": "https://b/", "title": "B"}
        self.store.ran(t["id"], NOW, [a], "Google News", "report")
        self.assertEqual(self.store.fresh(self.store.get(t["id"]), [a, b]), [b])
        task = self.store.get(t["id"])
        self.assertEqual((task["last_new"], task["runs"][-1]["sent_to"]), (1, "Google News"))
        self.assertNotIn("seen", self.store.listing()[0])

    def test_pause_resume_delete(self):
        t = self.store.add("x", "08:00", "en", NOW)
        self.store.change(t["id"], "pause")
        self.assertEqual(self.store.due(NOW), [])
        self.store.change(t["id"], "resume")
        self.assertEqual(len(self.store.due(NOW)), 1)
        self.store.change(t["id"], "delete")
        self.assertEqual(self.store.tasks, [])
        self.assertIsNone(self.store.change("nope", "pause"))
        with self.assertRaises(ValueError):
            self.store.change("nope", "explode")


class WatchRequest(unittest.TestCase):
    def test_requests_in_six_languages(self):
        cases = {"Keep me up to date on Pfizer patents": ("Pfizer patents", "08:00"),
                 "news about the hurricane every evening at 7pm": ("hurricane", "19:00"),
                 "Let me know when there's news about Rockstar": ("Rockstar", "08:00"),
                 "Tell me the news every day at 6:30": ("", "06:30"),
                 "Mantenme al día sobre Pfizer": ("Pfizer", "08:00"),
                 "Me mantenha informado sobre a Petrobras": ("Petrobras", "08:00"),
                 "Tiens-moi au courant de Airbus": ("Airbus", "08:00"),
                 "Halte mich auf dem Laufenden über Siemens": ("Siemens", "08:00"),
                 "毎朝トヨタのニュースを教えて": ("トヨタ", "08:00")}
        for text, (topic, at) in cases.items():
            self.assertEqual(intent.watch_request(text), {"topic": topic, "at": at}, text)

    def test_from_reddit_is_the_source_not_the_topic(self):
        # round 5 on the test SSD: "local AI from reddit" was searched as the topic, everywhere
        self.assertEqual(intent.watch_request("Keep me up to date on local AI from reddit"),
                         {"topic": "local AI", "at": "08:00", "only": "Reddit"})
        self.assertEqual(intent.watch_request("Me mantenha informado sobre IA local no Reddit"),
                         {"topic": "IA local", "at": "08:00", "only": "Reddit"})
        self.assertIsNone(intent.watch_request("Keep me up to date on reddit"))

    def test_not_watches(self):
        for text in ("let me know how to install Steam", "Keep my computer updated", "What's the news about Linux Mint?",
                     "How do I keep my news feed updated?", "keep me up to date"):
            self.assertIsNone(intent.watch_request(text), text)


@unittest.skipIf(service is None, "needs PyGObject")
class WatchRuns(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.store = standing.Store(os.path.join(d.name, "standing.json"))
        self.s = types.SimpleNamespace(standing=self.store, cancel=threading.Event(), guide=types.SimpleNamespace(
            tools=types.SimpleNamespace(lang="en", online=lambda: True), history=[]))
        for name in ("scan_links", "scan_report", "sent_to"):
            setattr(self.s, name, getattr(service.Service, name))

    def scan(self, *urls):
        return {"items": [{"outlet": "XDA", "title": f"T {u}", "url": u, "date": None} for u in urls],
                "posts": [], "failed": [], "found": [], "trouble": "", "needed": []}

    def test_a_scheduled_run_shows_only_what_is_new(self):
        t = self.store.add("Linux Mint", "08:00", "en", NOW)
        self.store.ran(t["id"], NOW, [{"url": "https://a/"}], "", "")
        self.s.news_scan = mock.Mock(return_value=self.scan("https://a/", "https://b/"))
        out = service.Service.run_watch(self.s, self.store.get(t["id"]))
        self.s.news_scan.assert_called_once_with("Linux Mint", "en", person=False, only="")
        self.assertEqual(out["new"], 1)
        self.assertIn("“T https://b/”", out["report"])
        self.assertNotIn("T https://a/", out["report"])
        self.s.news_scan = mock.Mock(return_value=self.scan("https://a/", "https://b/"))
        self.assertIsNone(service.Service.run_watch(self.s, self.store.get(t["id"])))  # nothing new: no report
        self.assertEqual(self.store.get(t["id"])["runs"][-1]["new"], 0)

    def test_setting_up_runs_once_and_says_so(self):
        self.s.news_scan = mock.Mock(return_value=self.scan("https://a/"))
        self.s.key_cards = lambda needed, on_action: None
        text, events = [], []
        out = service.Service.start_watch(self.s, {"at": "08:00"}, "Linux Mint", text.append,
                                          lambda *a: events.append(a))
        self.assertTrue(text[0].startswith("Set up: every day at 08:00 I'll show you only what's new."))
        self.assertEqual(out["shown"], 1)
        self.assertEqual(self.store.tasks[0]["seen"], ["https://a/"])

    def test_a_watch_on_one_network_asks_only_that_network(self):
        self.s.news_scan = mock.Mock(return_value={**self.scan(), "posts": [], "only": "Reddit"})
        self.s.key_cards = lambda needed, on_action: None
        text = []
        service.Service.start_watch(self.s, {"at": "08:00", "only": "Reddit"}, "local AI", text.append, lambda *a: None)
        self.s.news_scan.assert_called_once_with("local AI", "en", self.s.cancel, only="Reddit")
        task = self.store.tasks[0]
        self.assertEqual((task["only"], task["runs"][-1]["sent_to"]), ("Reddit", "Reddit"))
        self.assertIn("Only Reddit, as you asked.", text[0])
        self.assertNotIn("Press:", text[0])

    def test_a_key_pasted_into_the_chat_never_reaches_the_model(self):
        replies = []
        s = types.SimpleNamespace(guide=types.SimpleNamespace(tools=types.SimpleNamespace(lang="en"), history=[],
                                                              turn=mock.Mock()), journal=None, project=None)
        s.job = lambda rid, fn: replies.append(fn(replies.append, lambda *a: None))
        service.Service.ask(s, 1, "sk-ant-api03-Zx9wQ8vR7tU6sP5oN4mL3kJ2")
        s.guide.turn.assert_not_called()
        self.assertTrue(replies[0].startswith("That looks like a key or a password"))
        self.assertEqual(s.guide.history, [])


if __name__ == "__main__":
    unittest.main()
