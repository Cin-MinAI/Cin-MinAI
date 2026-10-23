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


class Shelves(unittest.TestCase):
    def test_named_by_kiwix(self):
        with tempfile.TemporaryDirectory() as d:
            for name in ("wikipedia_es_all_mini_2026-10.zim", "wikipedia_en_top_nopic_2026-09.zim",
                         "wikipedia_en_all_mini_2026-08.zim", "devdocs_en_python_2026-10.zim", "notes.txt"):
                open(os.path.join(d, name), "w").close()
            found = library.shelves((d,))
            self.assertEqual([(s["lang"], s["date"]) for s in found], [("es", "2026-10"), ("en", "2026-09"),
                                                                       ("en", "2026-08")])
            self.assertEqual(library.shelf_for("en", (d,))["title"], "wikipedia_en_top_nopic_2026-09")  # the newest


if __name__ == "__main__":
    unittest.main()
