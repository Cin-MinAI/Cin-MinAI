# SPDX-License-Identifier: GPL-3.0-or-later
"""Wikipedia for the guide (PLAN D68: knowledge from named sources, not the model's memory; Ian, 2026-10-17: "a
library with shelves").

A shelf is a Kiwix file (ZIM: a whole Wikipedia in one file, with its own search) on this computer: in
~/.local/share/cinminai/library/ (downloaded by the person) or /usr/share/cinminai/library/ (shipped). Reading a shelf
sends nothing anywhere. Without a shelf in the person's language, the article is read from Wikipedia itself, through
its API, only after the person agrees on the card (the same rule as Search, SPEC §7.5).

Either way the result has the same shape as a web search's (websearch.gather): {"query", "sources": [{"n", "title",
"url", "text"}], "shelf"}, so the guide answers from it the same way: the text is quoted material, never instructions,
and the reply names the article.
"""

from __future__ import annotations

import glob
import json
import os
import re
import unicodedata
import urllib.parse

SHELVES = (os.path.join(os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share"), "cinminai", "library"),
           "/usr/share/cinminai/library")
ISO639 = {"eng": "en", "spa": "es", "por": "pt", "fra": "fr", "deu": "de", "jpn": "ja"}
ARTICLES = 2            # articles read per question online (Wikipedia's own search; a shelf gives the one named)
PAGE_CHARS = 2400       # the same budget as a web page (websearch.PAGE_CHARS)


class LibraryError(Exception):
    pass


def shelves(dirs: tuple[str, ...] = SHELVES) -> list[dict]:
    """The Wikipedia files on this computer: [{"path", "lang", "date", "title"}], newest first per language."""
    out = []
    for d in dirs:
        for path in glob.glob(os.path.join(d, "wikipedia_*.zim")):
            m = re.match(r"wikipedia_([a-z]{2,3})_.*?_(\d{4}-\d{2})\.zim$", os.path.basename(path))
            if m:
                out.append({"path": path, "lang": ISO639.get(m.group(1), m.group(1)), "date": m.group(2),
                            "title": os.path.basename(path)[:-4]})
    return sorted(out, key=lambda s: s["date"], reverse=True)


def shelf_for(lang: str, dirs: tuple[str, ...] = SHELVES) -> dict | None:
    return next((s for s in shelves(dirs) if s["lang"] == lang), None)


def _text(html: str) -> str:
    from .websearch import _Text
    import html as htmllib
    p = _Text()
    p.feed(html)
    return re.sub(r"\n{2,}", "\n", htmllib.unescape("\n".join(p.parts))).strip()


def article_url(lang: str, title: str) -> str:
    return f"https://{lang}.wikipedia.org/wiki/{urllib.parse.quote(title.replace(' ', '_'))}"


def _same(a: str, b: str) -> bool:
    """The same title, whatever the capitals, accents or underscores: "pho" is "Phở", "marie curie" is "Marie Curie"."""
    def key(s):
        s = unicodedata.normalize("NFKD", s.replace("_", " ").replace("đ", "d").replace("Đ", "D"))
        return " ".join("".join(c for c in s if not unicodedata.combining(c)).casefold().split())
    return key(a) == key(b)


def _article(archive, title: str):
    """The entry for exactly this article (or a name Wikipedia redirects to it), or None. Never the nearest title: a
    shelf without "Dandelion" offers "Dandelion Mind" (a comedy tour) first, and the answer would be about that
    (found on Kiwix's English files, 2026-10-23)."""
    name = title.strip().replace(" ", "_")
    for path in dict.fromkeys((name, name[:1].upper() + name[1:])):
        if archive.has_entry_by_path(path):
            return archive.get_entry_by_path(path)
    from libzim.suggestion import SuggestionSearcher
    for path in SuggestionSearcher(archive).suggest(title).getResults(0, 20):
        entry = archive.get_entry_by_path(path)
        if _same(entry.title, title):
            return entry
    return None


def read_shelf(shelf: dict, query: str) -> dict:
    """The article named by the query from a file on this computer, or LibraryError when the shelf doesn't have it (a
    "top articles" file leaves most things out); the guide then offers Wikipedia itself."""
    try:
        from libzim.reader import Archive
    except ImportError:
        raise LibraryError("the Wikipedia reader (python3-libzim) isn't installed") from None
    try:
        entry = _article(Archive(shelf["path"]), query)
        if entry is None:
            raise LibraryError("this shelf doesn't have that article")
        while entry.is_redirect:
            entry = entry.get_redirect_entry()
        item = entry.get_item()
        text = _text(bytes(item.content).decode("utf-8", "replace")) if item.mimetype.startswith("text/html") else ""
    except (RuntimeError, OSError, KeyError) as e:
        raise LibraryError(f"the Wikipedia file couldn't be read: {e}") from None
    if not text:
        raise LibraryError("this shelf doesn't have that article")
    return {"query": query, "shelf": f"Wikipedia on this computer ({shelf['date']})",
            "sources": [{"n": 1, "title": entry.title, "url": article_url(shelf["lang"], entry.title),
                         "text": text[:PAGE_CHARS]}]}


def read_online(query: str, lang: str, articles: int = ARTICLES) -> dict:
    """The best articles for the query from Wikipedia itself (its search, then each article's text): only the query is
    sent, to Wikipedia in the person's language."""
    from .websearch import SearchError, _get, wikipedia_text
    host = f"{lang if lang in ISO639.values() else 'en'}.wikipedia.org"
    q = urllib.parse.urlencode({"action": "query", "list": "search", "srsearch": query, "srlimit": articles,
                                "format": "json"})
    try:
        raw, _ = _get(f"https://{host}/w/api.php?{q}", "application/json")
        titles = [r["title"] for r in json.loads(raw).get("query", {}).get("search", [])]
    except (SearchError, ValueError, KeyError) as e:
        raise LibraryError(f"Wikipedia couldn't be reached: {e}") from None
    sources = []
    for title in titles:
        url = article_url(host.split(".")[0], title)
        try:
            text = wikipedia_text(url)
        except (SearchError, ValueError):
            continue
        if text:
            sources.append({"n": len(sources) + 1, "title": title, "url": url, "text": text[:PAGE_CHARS]})
    if not sources:
        raise LibraryError("Wikipedia has no article on that")
    return {"query": query, "sources": sources, "shelf": f"Wikipedia ({host})"}
