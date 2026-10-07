# SPDX-License-Identifier: GPL-3.0-or-later
"""D91, the first chain: "find a video about X and summarize it" — search YouTube, open the first video in Firefox,
wait for our extension to report it, summarize it. Steps tested with stand-ins for the network and Firefox."""

import json
import threading
import types
import unittest
from unittest import mock

from cin_minai.daemon import chains

RESULTS = [
    {"title": "How to Make Donuts at Home - YouTube", "url": "https://www.youtube.com/watch?v=AbCdEfGhIjK", "snippet": ""},
    {"title": "Donut channel", "url": "https://www.youtube.com/@donuts", "snippet": ""},
    {"title": "Same video again", "url": "https://www.youtube.com/watch?v=AbCdEfGhIjK&t=30", "snippet": ""},
    {"title": "Glazed donuts", "url": "https://youtu.be/ZyXwVuTsRqP", "snippet": ""},
    {"title": "A blog", "url": "https://example.com/donuts", "snippet": ""},
]


class Steps(unittest.TestCase):
    def test_only_videos_once_each_in_order(self):
        vids = chains.youtube_videos(RESULTS)
        self.assertEqual([v["id"] for v in vids], ["AbCdEfGhIjK", "ZyXwVuTsRqP"])
        self.assertEqual(vids[0]["title"], "How to Make Donuts at Home")
        self.assertEqual(vids[1]["url"], "https://www.youtube.com/watch?v=ZyXwVuTsRqP")

    def test_waits_for_that_video_with_something_to_read(self):
        readings = iter([{"error": "no_extension"}, {"id": "other"}, {"id": "AbCdEfGhIjK"},
                         {"id": "AbCdEfGhIjK", "transcript": [[0, "hi"]]}])
        info = chains.wait_for_video("AbCdEfGhIjK", threading.Event(), lambda timeout_ms: next(readings), poll=0)
        self.assertEqual(info["transcript"], [[0, "hi"]])

    def test_cancel_stops_the_wait(self):
        cancel = threading.Event()
        cancel.set()
        self.assertIsNone(chains.wait_for_video("x", cancel, lambda timeout_ms: {}, poll=0))


class Throttled(unittest.TestCase):
    def test_the_are_you_a_person_page_is_said_not_read_as_no_results(self):
        from cin_minai.daemon import websearch
        page = "<html><body>If this error persists... anomaly detected ... captcha</body></html>"
        with mock.patch.object(websearch, "_get", return_value=(page, "")),              self.assertRaisesRegex(websearch.SearchError, "pause"):
            websearch.search("donuts site:youtube.com")


try:
    from cin_minai.daemon import service
except ImportError:  # no PyGObject here
    service = None


@unittest.skipIf(service is None, "needs PyGObject")
class VideoChain(unittest.TestCase):
    def fake(self, summarize=True):
        events, text = [], []
        s = types.SimpleNamespace(cancel=threading.Event(), chain_offers={},
                                  guide=types.SimpleNamespace(tools=types.SimpleNamespace(lang="en", online=lambda: True)))
        s.web_video = lambda request, fetch, on_text, on_action: (on_text("SUMMARY"), {"tool": "web_video"})[1]
        offer = {"topic": "how to make donuts", "summarize": summarize, "query": "how to make donuts site:youtube.com",
                 "question": "q"}
        return s, offer, events, text

    def run_chain(self, s, offer, events, text, reading):
        on_action = lambda tool, args, state, result: events.append((tool, state, result))
        with mock.patch("cin_minai.daemon.websearch.search", return_value=RESULTS) as search, \
             mock.patch("cin_minai.daemon.chains.open_in_firefox") as opened, \
             mock.patch("cin_minai.daemon.webvideo.from_firefox", return_value=reading):
            out = service.Service.run_video_chain(s, offer, "", text.append, on_action)
        return out, search, opened

    def test_search_open_summarize(self):
        s, offer, events, text = self.fake()
        out, search, opened = self.run_chain(s, offer, events, text, {"id": "AbCdEfGhIjK", "transcript": [[0, "x"]]})
        search.assert_called_once_with("how to make donuts site:youtube.com", "en")
        opened.assert_called_once_with("https://www.youtube.com/watch?v=AbCdEfGhIjK")
        self.assertEqual([(t, st) for t, st, _ in events],
                         [("web_search", "running"), ("web_search", "done"), ("open_video", "running"),
                          ("open_video", "done")])
        self.assertEqual(len(json.loads(events[1][2])["sources"]), 2)  # the videos found, shown as links
        self.assertEqual(text, ["SUMMARY"])
        self.assertEqual(out["videos"], 2)

    def test_no_transcript_is_said_before_the_summary(self):
        s, offer, events, text = self.fake()
        self.run_chain(s, offer, events, text, {"id": "AbCdEfGhIjK", "storyboard": "spec"})
        self.assertTrue(text[0].startswith("This video has no transcript"))
        self.assertEqual(text[1], "SUMMARY")
        self.assertTrue(json.loads(events[1][2])["videos"])  # the sidebar puts the list above the summary

    def test_just_open_when_no_summary_was_asked(self):
        s, offer, events, text = self.fake(summarize=False)
        self.run_chain(s, offer, events, text, {"id": "AbCdEfGhIjK", "transcript": [[0, "x"]]})
        self.assertIn("I opened “How to Make Donuts at Home” in Firefox", text[0])

    def test_offer_sends_nothing(self):
        s, offer, events, text = self.fake()
        on_action = lambda tool, args, state, result: events.append((tool, state, result))
        with mock.patch("cin_minai.daemon.websearch.search") as search:
            service.Service.offer_video_chain(s, "find a donut video", {"topic": "donuts", "summarize": True},
                                              text.append, on_action)
        search.assert_not_called()
        self.assertEqual(events[0][:2], ("web_search", "proposal"))
        self.assertEqual(len(s.chain_offers), 1)


class NewsRequest(unittest.TestCase):
    def test_requests_and_topics(self):
        from cin_minai.daemon.intent import news_request
        cases = {"Pull up the news about Linux Mint": "Linux Mint",
                 "What's the latest news on the Artemis mission?": "Artemis mission",
                 "Show me today's headlines": "", "Can you pull up the news?": "",
                 "Muestra las últimas noticias sobre la economía": "economía",
                 "Quais são as notícias sobre o Brasil?": "Brasil",
                 "Montre-moi les actualités sur la France": "France",
                 "Zeig mir die Nachrichten über Berlin": "Berlin", "台風についてのニュースを教えて": "台風"}
        for text, topic in cases.items():
            self.assertEqual(news_request(text), {"topic": topic}, text)

    def test_questions_about_news_are_not_requests(self):
        from cin_minai.daemon.intent import news_request
        for text in ("What is fake news?", "How do I turn off news notifications?", "Install a news reader",
                     "Is there a news app for Linux?", "Add a news feed to my panel"):
            self.assertIsNone(news_request(text), text)


@unittest.skipIf(service is None, "needs PyGObject")
class NewsChain(unittest.TestCase):
    def test_press_headlines_attributed_no_model(self):
        import datetime as dt
        items = [{"kind": "press", "outlet": "XDA", "title": "Linux Mint replaced Ubuntu", "via": "Google News",
                  "url": "https://news.google.com/rss/articles/B", "date": dt.datetime(2026, 9, 30)}]
        s = types.SimpleNamespace(cancel=threading.Event(), guide=types.SimpleNamespace(
            tools=types.SimpleNamespace(lang="en"), history=[]))
        events, text = [], []
        offer = {"recipe": "news", "topic": "Linux Mint", "query": "Linux Mint", "question": "news about Linux Mint"}
        official = [{"kind": "official", "source": "linuxmint.com", "title": "Linux Mint 22.3 released",
                     "url": "https://linuxmint.com/rel", "what": "own site"}]
        with mock.patch("cin_minai.daemon.newsscan.press", return_value=items) as press,              mock.patch("cin_minai.daemon.newsscan.official", return_value=official):
            out = service.Service.run_news_chain(s, offer, "Linux Mint", text.append,
                                                 lambda tool, args, state, result: events.append((tool, state, result)))
        press.assert_called_once_with("Linux Mint", "en")
        self.assertIn("- linuxmint.com (own site): “Linux Mint 22.3 released”", text[0])
        self.assertEqual(out["official"], 1)
        self.assertIn("- XDA (Sep 30): “Linux Mint replaced Ubuntu”", text[0])
        self.assertEqual(json.loads(events[1][2])["sources"][0]["url"], "https://news.google.com/rss/articles/B")
        self.assertEqual(out["outlets"], 1)
        self.assertEqual(s.guide.history[-1]["content"], text[0])  # follow-up questions see what was shown

    def test_official_search_trouble_is_said_and_press_still_shown(self):
        from cin_minai.daemon import websearch
        s = types.SimpleNamespace(cancel=threading.Event(), guide=types.SimpleNamespace(
            tools=types.SimpleNamespace(lang="en"), history=[]))
        text = []
        offer = {"recipe": "news", "topic": "x", "query": "x", "question": "news about x"}
        with mock.patch("cin_minai.daemon.newsscan.press", return_value=[]),              mock.patch("cin_minai.daemon.newsscan.official", side_effect=websearch.SearchError("wants a pause")):
            out = service.Service.run_news_chain(s, offer, "x", text.append, lambda *a: None)
        self.assertIn("Couldn't search official pages right now: wants a pause", text[0])
        self.assertTrue(out["official_trouble"])


if __name__ == "__main__":
    unittest.main()
