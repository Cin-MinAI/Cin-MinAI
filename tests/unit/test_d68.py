# SPDX-License-Identifier: GPL-3.0-or-later
"""The guide's own tools for knowledge (PLAN D68): the calculator (exact, from SymPy; the model's text never run as
Python) and Wikipedia (a shelf on this computer, read without sending anything; otherwise the article online, after the
person agrees)."""

import os
import tempfile
import unittest

from cin_minai.daemon import library

try:
    import sympy  # noqa: F401
    from cin_minai.daemon.calc import calculate
except ImportError:  # python3-sympy (a dependency of cinminai-daemon)
    calculate = None

try:
    from libzim.writer import Creator, Hint, Item, StringProvider
except ImportError:  # python3-libzim (a dependency of cinminai-daemon)
    Creator = None


@unittest.skipIf(calculate is None, "needs sympy")
class Calculator(unittest.TestCase):
    def result(self, text):
        return calculate(text).get("result")

    def test_everyday_sums(self):
        for text, want in (("15% of 240", "36"), ("187.50/6", "31.25"), ("60*60*24*7", "604800"),
                           ("18.25*37.5", "684.375"), ("100 - 20%", "80"), ("80 + 25%", "100"), ("2^10", "1024"),
                           ("3,5*2", "7"), ("1,000,000/4", "250000"), ("10/4", "2.5"), ("sqrt(16)", "4")):
            self.assertEqual(self.result(text), want, text)
        self.assertEqual(self.result("1/3"), "1/3 ≈ 0.333333333333")
        self.assertTrue(self.result("sqrt(2)").startswith("1.41421356"))

    def test_equations(self):
        self.assertEqual(calculate("3x + 7 = 25")["solutions"], ["6"])
        self.assertEqual(calculate("x^2 - 5x + 6 = 0")["solutions"], ["2", "3"])
        self.assertEqual(calculate("x^2 + 1 = 0")["solutions"], ["-i", "i"])
        self.assertTrue(calculate("2+2=4")["true"])

    def test_never_run_as_python(self):
        for text in ('__import__("os").system("id")', "open('/etc/passwd')", "().__class__", "x.y", "lambda: 1",
                     "[1]*10**9", "f'{1}'"):
            self.assertIn("error", calculate(text), text)

    def test_bounded(self):
        self.assertIn("error", calculate("2^100000"))
        self.assertIn("error", calculate("factorial(100000)"))
        self.assertIn("error", calculate("5/0"))
        self.assertIn("error", calculate("1" * 500))
        self.assertIn("error", calculate(""))


@unittest.skipIf(Creator is None, "needs libzim")
class Shelf(unittest.TestCase):
    ARTICLES = {"Marie_Curie": ("Marie Curie", "<html><body><p>Marie Curie was a physicist and chemist who did "
                                               "pioneering research on radioactivity.</p><script>x()</script></body></html>"),
                "Radium": ("Radium", "<html><body><p>Radium is a chemical element discovered by the Curies.</p>"
                                     "</body></html>"),
                "Phở": ("Phở", "<html><body><p>Phở is a Vietnamese soup of broth, rice noodles and meat.</p>"
                               "</body></html>"),
                "Dandelion_Mind": ("Dandelion Mind", "<html><body><p>Dandelion Mind was a stand-up comedy tour "
                                                     "that played theatres across Britain in 2010.</p></body></html>")}

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        path = os.path.join(self.dir, "wikipedia_en_test_mini_2026-10.zim")

        class Page(Item):
            def __init__(self, url, title, html):
                super().__init__()
                self.url, self.title, self.html = url, title, html

            def get_path(self): return self.url
            def get_title(self): return self.title
            def get_mimetype(self): return "text/html"
            def get_contentprovider(self): return StringProvider(self.html)
            def get_hints(self): return {Hint.FRONT_ARTICLE: True}

        with Creator(path).config_indexing(True, "eng") as creator:
            creator.set_mainpath("Marie_Curie")
            for url, (title, html) in self.ARTICLES.items():
                creator.add_item(Page(url, title, html))
            creator.add_redirection("Maria_Skłodowska", "Maria Skłodowska", "Marie_Curie", {Hint.FRONT_ARTICLE: True})

    def tearDown(self):
        import shutil
        shutil.rmtree(self.dir, True)

    def test_a_shelf_on_this_computer(self):
        shelf = library.shelf_for("en", (self.dir,))
        self.assertEqual((shelf["lang"], shelf["date"]), ("en", "2026-10"))
        self.assertIsNone(library.shelf_for("fr", (self.dir,)))
        found = library.read_shelf(shelf, "Marie Curie")
        first = found["sources"][0]
        self.assertEqual(first["title"], "Marie Curie")
        self.assertIn("radioactivity", first["text"])
        self.assertNotIn("x()", first["text"])  # scripts are not text
        self.assertEqual(first["url"], "https://en.wikipedia.org/wiki/Marie_Curie")
        self.assertIn("on this computer", found["shelf"])

    def test_only_the_article_asked_for(self):
        # Kiwix's English "top" file has no "Dandelion", and its title search offers "Dandelion Mind" (a comedy tour)
        shelf = library.shelf_for("en", (self.dir,))
        with self.assertRaises(library.LibraryError):
            library.read_shelf(shelf, "Dandelion")
        with self.assertRaises(library.LibraryError):
            library.read_shelf(shelf, "Kimchi")
        for asked, title in (("marie curie", "Marie Curie"), ("Maria Skłodowska", "Marie Curie"), ("Pho", "Phở"),
                             ("pho", "Phở"), ("Dandelion Mind", "Dandelion Mind")):
            self.assertEqual(library.read_shelf(shelf, asked)["sources"][0]["title"], title, asked)


@unittest.skipIf(Creator is None, "needs libzim")
class Pictures(unittest.TestCase):
    # laid out like Kiwix's English files (2026-10-23): the logo before the photo (Eiffel Tower, Raspberry Pi), the
    # locator map in the fact box, more pictures in the sections
    HTML = ('<html><body><table class="infobox"><tr><td><img src="./_assets_/a1/Tower_logo.svg.png" width="279"></td>'
            '</tr><tr><td><img src="./_assets_/a1/Tower%252C_Paris.jpg"></td></tr><tr><td>'
            '<img src="./_assets_/a1/France_locator_map.svg.png"></td></tr></table><p>The tower is a wrought-iron '
            'lattice tower on the Champ de Mars in Paris, France, named after the engineer whose company built it.</p>'
            '<div class="mw-heading mw-heading2"><h2>History</h2></div><img src="./_assets_/a1/Building.jpg">'
            '</body></html>')
    WEBP = b"RIFF\x00\x00\x00\x00WEBPVP8 " + b"\x00" * 20

    def setUp(self):
        import cin_minai.daemon.library as lib
        self.dir = tempfile.mkdtemp()
        self.saved, lib.PICTURES = lib.PICTURES, os.path.join(self.dir, "pictures")
        test = self

        class Blob(Item):
            def __init__(self, path, data, mime, title=""):
                super().__init__()
                self.p, self.d, self.m, self.t = path, data, mime, title

            def get_path(self): return self.p
            def get_title(self): return self.t
            def get_mimetype(self): return self.m
            def get_contentprovider(self): return StringProvider(self.d) if isinstance(self.d, str) else BytesProv(self.d)
            def get_hints(self): return {Hint.FRONT_ARTICLE: self.m == "text/html"}

        from libzim.writer import ContentProvider, Blob as ZBlob

        class BytesProv(ContentProvider):
            def __init__(self, data):
                super().__init__()
                self.data = data

            def get_size(self): return len(self.data)
            def gen_blob(self): yield ZBlob(self.data)

        for kind in ("maxi", "mini"):
            with Creator(os.path.join(self.dir, f"wikipedia_en_top_{kind}_2026-09.zim")).config_indexing(True, "eng") as c:
                c.set_mainpath("Tower")
                c.add_item(Blob("Tower", test.HTML, "text/html", "Tower"))
                for name in ("Tower_logo.svg.png", "Tower%2C_Paris.jpg", "France_locator_map.svg.png", "Building.jpg"):
                    c.add_item(Blob(f"_assets_/a1/{name}", test.WEBP, "image/webp"))

    def tearDown(self):
        import shutil
        import cin_minai.daemon.library as lib
        lib.PICTURES = self.saved
        shutil.rmtree(self.dir, True)

    def test_the_photo_and_the_map(self):
        maxi, mini = library.shelves_for("en", (self.dir,))
        pictures = library.read_shelf(maxi, "Tower")["sources"][0]["pictures"]
        self.assertEqual([p["kind"] for p in pictures], ["photo", "map"])
        for p in pictures:
            with open(p["path"], "rb") as f:
                self.assertEqual(f.read(), self.WEBP)
            self.assertTrue(p["path"].endswith(".webp"))
        self.assertNotIn("pictures", library.read_shelf(mini, "Tower")["sources"][0])  # a summary file has none


class Shelves(unittest.TestCase):
    def test_named_by_kiwix(self):
        with tempfile.TemporaryDirectory() as d:
            for name in ("wikipedia_es_all_mini_2026-10.zim", "wikipedia_en_top_nopic_2026-09.zim",
                         "wikipedia_en_all_mini_2026-08.zim", "devdocs_en_python_2026-10.zim", "notes.txt"):
                open(os.path.join(d, name), "w").close()
            found = library.shelves((d,))
            # whole articles before summaries, then the newest
            self.assertEqual([(s["lang"], s["kind"], s["date"]) for s in found],
                             [("en", "nopic", "2026-09"), ("es", "mini", "2026-10"), ("en", "mini", "2026-08")])
            self.assertEqual(library.shelf_for("en", (d,))["title"], "wikipedia_en_top_nopic_2026-09")

    def test_a_pair_asks_the_whole_article_first(self):
        # Ian's pair (2026-10-23): the best-known articles with pictures, and every article's summary
        with tempfile.TemporaryDirectory() as d:
            for name in ("wikipedia_en_all_mini_2026-09.zim", "wikipedia_en_top_maxi_2026-09.zim",
                         "wikipedia_fr_top_mini_2026-10.zim"):
                open(os.path.join(d, name), "w").close()
            self.assertEqual([s["kind"] for s in library.shelves_for("en", (d,))], ["maxi", "mini"])
            asked = []

            def read(shelf, query):
                asked.append(shelf["kind"])
                if shelf["kind"] == "maxi":
                    raise library.LibraryError("this shelf doesn't have that article")
                return {"sources": [{"title": query}]}
            saved, library.read_shelf = library.read_shelf, read
            try:
                library.read_shelves(library.shelves_for("en", (d,)), "Kimchi")
            finally:
                library.read_shelf = saved
            self.assertEqual(asked, ["maxi", "mini"])
            with self.assertRaises(library.LibraryError):
                library.read_shelves([], "Kimchi")

    def test_simple_english_is_english(self):
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, "wikipedia_en-simple_all_maxi_2026-09.zim"), "w").close()
            s = library.shelves_for("en", (d,))
            self.assertEqual([(x["lang"], x["edition"], x["kind"]) for x in s], [("en", "simple", "maxi")])
            # asked after the real Wikipedia, whatever their sizes (the NVMe, 2026-10-23: both summaries)
            for name in ("wikipedia_en_all_mini_2026-09.zim", "wikipedia_en-simple_all_mini_2026-09.zim",
                         "wikipedia_en_top_maxi_2026-09.zim"):
                open(os.path.join(d, name), "w").close()
            self.assertEqual([(x["edition"], x["kind"]) for x in library.shelves_for("en", (d,))],
                             [("top", "maxi"), ("all", "mini"), ("simple", "maxi"), ("simple", "mini")])


# the shape of Kiwix's catalog and metalinks (read 2026-10-23 from opds.library.kiwix.org and download.kiwix.org)
FEED = """<feed><totalResults>4</totalResults>
<entry><name>wikipedia_en_all</name><flavour>mini</flavour><articleCount>18095848</articleCount>
<link rel="http://opds-spec.org/acquisition/open-access" type="application/x-zim"
 href="https://lb.download.kiwix.org/zim/wikipedia/wikipedia_en_all_mini_2026-09.zim.meta4" length="14390000000" />
</entry>
<entry><name>wikipedia_en_top</name><flavour>maxi</flavour><articleCount>877754</articleCount>
<link rel="http://opds-spec.org/acquisition/open-access" type="application/x-zim"
 href="https://lb.download.kiwix.org/zim/wikipedia/wikipedia_en_top_maxi_2026-09.zim.meta4" length="6990000000" />
</entry>
<entry><name>wikipedia_en_top</name><flavour>mini</flavour><articleCount>703608</articleCount>
<link rel="http://opds-spec.org/acquisition/open-access" type="application/x-zim"
 href="https://lb.download.kiwix.org/zim/wikipedia/wikipedia_en_top_mini_2026-09.zim.meta4" length="300000000" />
</entry>
<entry><name>wikipedia_en_medicine</name><flavour>maxi</flavour><articleCount>70000</articleCount>
<link rel="http://opds-spec.org/acquisition/open-access" type="application/x-zim"
 href="https://lb.download.kiwix.org/zim/wikipedia/wikipedia_en_medicine_maxi_2026-09.zim.meta4" length="2000000000" />
</entry></feed>"""


class Reply:
    def __init__(self, data: bytes, status: int = 200):
        self.data, self.status = data, status

    def read(self, n=-1):
        out, self.data = (self.data, b"") if n < 0 else (self.data[:n], self.data[n:])
        return out

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class GettingShelves(unittest.TestCase):
    """The Library view's side of library.py: Kiwix's list, the metalink, the checked, resumed download."""
    DATA = b"a whole wikipedia" * 1000

    def meta4(self, data, mirrors=("https://one.example/f.zim", "https://two.example/f.zim")):
        import hashlib
        urls = "".join(f'<url location="x" priority="{i + 1}">{u}</url>' for i, u in enumerate(mirrors))
        return (f'<metalink><file name="f.zim"><size>{len(data)}</size><hash type="md5">00</hash>'
                f'<hash type="sha-256">{hashlib.sha256(data).hexdigest()}</hash>{urls}</file></metalink>').encode()

    def test_the_list_offers_the_editions_and_suggests_the_pair(self):
        sent = []

        def opener(req, timeout=0):
            sent.append(req.full_url)
            return Reply(FEED.encode())
        files = library.catalog("en", opener)
        self.assertEqual(sent, [library.CATALOG.format(lang="eng")])  # only the language goes
        self.assertEqual([(f["edition"], f["kind"], f["suggested"]) for f in files],
                         [("top", "mini", False), ("top", "maxi", True), ("all", "mini", True)])  # no topic files
        self.assertEqual(files[1]["file"], "wikipedia_en_top_maxi_2026-09")
        self.assertEqual(files[1]["articles"], 877754)

    def download(self, root, replies, cancel=None):
        import threading
        calls = []

        def opener(req, timeout=0):
            calls.append((req.full_url, req.headers.get("Range")))
            r = replies.pop(0)
            if isinstance(r, Exception):
                raise r
            return r
        entry = {"file": "wikipedia_en_top_mini_2026-09", "meta4": "https://kiwix.example/f.meta4"}
        path = library.download(entry, lambda have, total: None, cancel or threading.Event(), root, opener)
        return path, calls

    def test_checked_and_put_on_the_shelf(self):
        with tempfile.TemporaryDirectory() as d:
            path, calls = self.download(d, [Reply(self.meta4(self.DATA)), Reply(self.DATA)])
            self.assertEqual(path, os.path.join(d, "wikipedia_en_top_mini_2026-09.zim"))
            with open(path, "rb") as f:
                self.assertEqual(f.read(), self.DATA)
            self.assertFalse(os.path.exists(path + ".part"))
            self.assertEqual([u for u, _ in calls], ["https://kiwix.example/f.meta4", "https://one.example/f.zim"])

    def test_a_stopped_download_carries_on_from_the_next_mirror(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "wikipedia_en_top_mini_2026-09.zim.part"), "wb") as f:
                f.write(self.DATA[:5000])
            self.assertEqual(library.partial(d), {"wikipedia_en_top_mini_2026-09": 5000})
            path, calls = self.download(d, [Reply(self.meta4(self.DATA)), OSError("mirror down"),
                                            Reply(self.DATA[5000:], status=206)])
            self.assertEqual(calls[1:], [("https://one.example/f.zim", "bytes=5000-"),
                                         ("https://two.example/f.zim", "bytes=5000-")])
            with open(path, "rb") as f:
                self.assertEqual(f.read(), self.DATA)

    def test_a_file_that_doesnt_match_is_removed(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(library.LibraryError):
                self.download(d, [Reply(self.meta4(self.DATA)), Reply(b"x" * len(self.DATA))])
            self.assertEqual(os.listdir(d), [])

    def test_no_checksum_no_download(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(library.LibraryError):
                self.download(d, [Reply(b"<metalink><file><size>3</size></file></metalink>")])

    def test_stop_keeps_what_came(self):
        import threading
        stop = threading.Event()
        stop.set()
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(library.Stopped):
                self.download(d, [Reply(self.meta4(self.DATA)), Reply(self.DATA)], stop)
            self.assertIn("wikipedia_en_top_mini_2026-09", library.partial(d))

    def test_only_downloaded_shelves_are_removed(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as other:
            mine = os.path.join(d, "wikipedia_en_top_mini_2026-09.zim")
            shipped = os.path.join(other, "wikipedia_en_top_mini_2026-09.zim")
            for p in (mine, shipped):
                open(p, "w").close()
            with self.assertRaises(library.LibraryError):
                library.remove(shipped, d)
            library.remove(mine, d)
            self.assertFalse(os.path.exists(mine))
            self.assertTrue(os.path.exists(shipped))


if __name__ == "__main__":
    unittest.main()
