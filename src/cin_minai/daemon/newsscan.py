# SPDX-License-Identifier: GPL-3.0-or-later
"""The news scan (PLAN D92): who says what — press, social, official — never what happened.

Press (this module's first part): news feeds give each article's outlet, date and headline. The report quotes the
headline word for word with its outlet and date: no model in between, so nothing can be paraphrased into a claim the
outlet didn't make. Outlets aren't judged or picked; one outlet can't crowd out the rest (two headlines each at most).
"""

from __future__ import annotations

import email.utils
import re
import urllib.parse
import xml.etree.ElementTree as ET

from . import websearch
from .facts import MONTHS

PER_OUTLET = 2
PRESS_ITEMS = 10
# Google News feed edition per language (hl, gl, ceid)
GOOGLE = {"en": ("en-US", "US", "US:en"), "es": ("es-419", "MX", "MX:es-419"), "pt": ("pt-BR", "BR", "BR:pt-419"),
          "fr": ("fr", "FR", "FR:fr"), "de": ("de", "DE", "DE:de"), "ja": ("ja", "JP", "JP:ja")}
BING_NS = "{http://www.bing.com:80/news/search/}"


def _date(text: str):
    try:
        return email.utils.parsedate_to_datetime(text)
    except (TypeError, ValueError):
        return None


def google_news(topic: str, lang: str = "en") -> list[dict]:
    """The feed for a topic, or the top stories when there's none ("show me today's headlines")."""
    hl, gl, ceid = GOOGLE.get(lang, GOOGLE["en"])
    edition = {"hl": hl, "gl": gl, "ceid": ceid}
    url = ("https://news.google.com/rss/search?" + urllib.parse.urlencode({"q": topic, **edition}) if topic
           else "https://news.google.com/rss?" + urllib.parse.urlencode(edition))
    xml, _ = websearch._get(url, accept="application/rss+xml")
    out = []
    for it in ET.fromstring(xml).iter("item"):
        src = it.find("source")
        outlet = (src.text or "").strip() if src is not None else ""
        title = (it.findtext("title") or "").strip()
        if outlet and title.endswith(" - " + outlet):  # Google appends " - Outlet" to every headline
            title = title[: -len(" - " + outlet)].strip()
        out.append({"kind": "press", "outlet": outlet or "?", "title": title, "url": (it.findtext("link") or "").strip(),
                    "date": _date(it.findtext("pubDate") or ""), "via": "Google News"})
    return out


def bing_news(topic: str, lang: str = "en") -> list[dict]:
    url = "https://www.bing.com/news/search?" + urllib.parse.urlencode({"q": topic, "format": "rss"})
    xml, _ = websearch._get(url, accept="application/rss+xml")
    out = []
    for it in ET.fromstring(xml).iter("item"):
        link = (it.findtext("link") or "").strip()
        real = urllib.parse.parse_qs(urllib.parse.urlsplit(link).query).get("url", [""])[0]
        outlet = (it.findtext(BING_NS + "Source") or "").strip() or urllib.parse.urlsplit(real).hostname or "?"
        out.append({"kind": "press", "outlet": outlet.removeprefix("www."), "title": (it.findtext("title") or "").strip(),
                    "url": real or link, "date": _date(it.findtext("pubDate") or ""), "via": "Bing News"})
    return out


def _key(title: str) -> str:
    return re.sub(r"\W+", " ", title.lower()).strip()[:60]


def balance(items: list[dict], per_outlet: int = PER_OUTLET, limit: int = PRESS_ITEMS) -> list[dict]:
    """Newest first, the same headline once, no outlet more than `per_outlet` times."""
    seen, count, out = set(), {}, []
    dated = sorted(items, key=lambda i: i["date"].timestamp() if i["date"] else 0, reverse=True)
    for it in dated:
        k, o = _key(it["title"]), it["outlet"].lower()
        if not it["title"] or k in seen or count.get(o, 0) >= per_outlet:
            continue
        seen.add(k)
        count[o] = count.get(o, 0) + 1
        out.append(it)
        if len(out) >= limit:
            break
    return out


PROVIDERS = "Google News and Bing News"


def press(topic: str, lang: str = "en") -> list[dict]:
    """Both feeds, merged and balanced; a feed that fails is left out (the other may still answer)."""
    items, errors = [], []
    for feed in ((google_news, bing_news) if topic else (google_news,)):
        try:
            items += feed(topic, lang)
        except (websearch.SearchError, ET.ParseError, ValueError) as e:
            errors.append(str(e))
    if not items and errors:
        raise websearch.SearchError(errors[0])
    return balance(items)


def say_date(d, lang: str) -> str:
    if d is None:
        return "no date"
    if lang == "ja":
        return f"{d.month}月{d.day}日"
    month = MONTHS.get(lang, MONTHS["en"])[d.month - 1]
    return f"{month[:3]} {d.day}" if lang == "en" else f"{d.day} {month[:4].rstrip('.')}"


HEAD = {"en": ("What's on hand about {topic}. I don't say what happened: this is what each source says, with its "
               "date. Open them to read more.", "Press", "No press articles found.", "says"),
        "es": ("Lo que hay sobre {topic}. No digo qué pasó: esto es lo que dice cada fuente, con su fecha.",
               "Prensa", "No se encontraron artículos de prensa.", "dice"),
        "pt": ("O que há sobre {topic}. Não digo o que aconteceu: isto é o que cada fonte diz, com a data.",
               "Imprensa", "Nenhum artigo de imprensa encontrado.", "diz"),
        "fr": ("Ce qu'on trouve sur {topic}. Je ne dis pas ce qui s'est passé : voici ce que dit chaque source, avec "
               "sa date.", "Presse", "Aucun article de presse trouvé.", "dit"),
        "de": ("Was es zu {topic} gibt. Ich sage nicht, was passiert ist: Das sagt jede Quelle, mit Datum.",
               "Presse", "Keine Presseartikel gefunden.", "sagt"),
        "ja": ("{topic}について見つかった情報です。何が起きたかは判断しません。各情報源の発言を日付付きで示します。",
               "報道", "報道記事は見つかりませんでした。", "")}


def report(topic: str, items: list[dict], lang: str = "en") -> str:
    """The press section, every line attributed and quoted; the frame is code, never the model's."""
    head, press_word, none, says = HEAD.get(lang, HEAD["en"])
    lines = [head.format(topic=f"“{topic}”" if topic else "today's news"), "", f"{press_word}:"]
    if not items:
        lines.append(none)
    for it in items:
        lines.append(f"- {it['outlet']} ({say_date(it['date'], lang)}): “{it['title']}”")
    return "\n".join(lines)
