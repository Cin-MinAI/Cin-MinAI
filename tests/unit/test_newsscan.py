# SPDX-License-Identifier: GPL-3.0-or-later
"""The news scan, press (D92): outlets' own headlines, word for word, with outlet and date; never what happened."""

import datetime as dt
import unittest
from unittest import mock

from cin_minai.daemon import newsscan

GOOGLE_FEED = """<?xml version="1.0"?><rss><channel>
<item><title>Forget Linux Mint, this is the Windows alternative you need - MakeUseOf</title>
<link>https://news.google.com/rss/articles/A</link><pubDate>Wed, 07 Oct 2026 10:00:00 GMT</pubDate>
<source url="https://www.makeuseof.com">MakeUseOf</source></item>
<item><title>Linux Mint replaced Ubuntu as the best first distro - XDA</title>
<link>https://news.google.com/rss/articles/B</link><pubDate>Wed, 30 Sep 2026 10:00:00 GMT</pubDate>
<source url="https://www.xda-developers.com">XDA</source></item>
</channel></rss>"""
BING_FEED = """<?xml version="1.0"?><rss xmlns:News="http://www.bing.com:80/news/search/"><channel>
<item><title>Linux Mint replaced Ubuntu as the best first distro</title>
<link>http://www.bing.com/news/apiclick.aspx?ref=FexRss&amp;url=https%3a%2f%2fwww.msn.com%2fen-us%2fnews%2fx</link>
<pubDate>Tue, 29 Sep 2026 10:00:00 GMT</pubDate><News:Source>msn.com</News:Source></item>
</channel></rss>"""


def item(outlet, title, day):
    return {"kind": "press", "outlet": outlet, "title": title, "url": "https://x/", "via": "t",
            "date": dt.datetime(2026, 10, day, tzinfo=dt.timezone.utc)}


class Feeds(unittest.TestCase):
    def test_google_outlet_date_and_the_headline_without_its_suffix(self):
        with mock.patch.object(newsscan.websearch, "_get", return_value=(GOOGLE_FEED, "")):
            items = newsscan.google_news("Linux Mint")
        self.assertEqual([(i["outlet"], i["title"]) for i in items],
                         [("MakeUseOf", "Forget Linux Mint, this is the Windows alternative you need"),
                          ("XDA", "Linux Mint replaced Ubuntu as the best first distro")])
        self.assertEqual(items[0]["date"].day, 7)

    def test_bing_gives_the_real_address(self):
        with mock.patch.object(newsscan.websearch, "_get", return_value=(BING_FEED, "")):
            (it,) = newsscan.bing_news("Linux Mint")
        self.assertEqual((it["outlet"], it["url"]), ("msn.com", "https://www.msn.com/en-us/news/x"))


class Balance(unittest.TestCase):
    def test_newest_first_once_each_two_per_outlet(self):
        items = [item("A", "a1", 1), item("A", "a2", 5), item("A", "a3", 6), item("B", "b1", 4),
                 item("C", "A2", 7)]  # the same headline as a2, from another feed
        out = newsscan.balance(items)
        self.assertEqual([(i["outlet"], i["title"]) for i in out], [("C", "A2"), ("A", "a3"), ("B", "b1"), ("A", "a1")])


class Report(unittest.TestCase):
    def test_every_line_attributed_and_quoted(self):
        text = newsscan.report("Linux Mint", [item("MakeUseOf", "Forget Linux Mint", 7)], "en")
        self.assertIn("I don't say what happened", text)
        self.assertIn("- MakeUseOf (Oct 7): “Forget Linux Mint”", text)
        self.assertIn("No press articles found.", newsscan.report("x", [], "en"))
        self.assertIn("報道", newsscan.report("台風", [item("NHK", "台風10号", 7)], "ja"))
        self.assertIn("NHK (10月7日)", newsscan.report("台風", [item("NHK", "台風10号", 7)], "ja"))


if __name__ == "__main__":
    unittest.main()
