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
PROVIDERS_WITH_OFFICIAL = "Google News, Bing News and DuckDuckGo"


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


# --- official: what the subject says on its own pages (D92) ------------------------------------------------------------
GOVERNMENT = re.compile(r"(^|\.)(gov|mil|int|europa\.eu|gov\.[a-z]{2}|gob\.[a-z]{2}|gouv\.[a-z]{2}|go\.[a-z]{2}|"
                        r"gc\.ca|bund\.de|admin\.ch|govt\.nz)$")
NEWS_OR_SOCIAL = re.compile(r"(^|\.)(wikipedia\.org|youtube\.com|x\.com|twitter\.com|reddit\.com|facebook\.com|"
                            r"instagram\.com|tiktok\.com|linkedin\.com|medium\.com|msn\.com|yahoo\.com|aol\.com|"
                            r"cnn\.com|foxnews\.com|bbc\.co\.uk|nytimes\.com)$")
PATENT = re.compile(r"\b(patents?|patentes?|brevets?|patente)\b|特許", re.I)
STOP_WORDS = {"the", "and", "news", "official", "about", "with", "from", "for", "inc", "corp", "company"}


def _host(url: str) -> str:
    return (urllib.parse.urlsplit(url).hostname or "").lower().removeprefix("www.")


def own_site(host: str, topic: str) -> bool:
    """The subject's own domain: a name in the topic is in the site's main name ("Rockstar" -> rockstargames.com,
    newsroom.pfizer.com) — never a news outlet or a social network, which are other kinds of source."""
    if NEWS_OR_SOCIAL.search(host):
        return False
    main = ".".join(host.split(".")[-2:]).split(".")[0]
    words = [w for w in re.findall(r"[a-z0-9]+", topic.lower()) if len(w) >= 4 and w not in STOP_WORDS]
    return any(w in main for w in words)


def official(topic: str, lang: str = "en") -> list[dict]:
    """Official pages about the topic: government sites, the subject's own site, patent records. One search; each
    page's own title, word for word."""
    if not topic:
        return []
    patents = bool(PATENT.search(topic))
    subject = PATENT.sub(" ", topic).strip()
    # plain words: DuckDuckGo's HTML search gave nothing for OR with parentheses (2026-10-07)
    query = f"{subject} site:patents.google.com" if patents else f"{topic} official announcement"
    out = []
    for r in websearch.search(query, lang):
        host = _host(r["url"])
        if patents and host == "patents.google.com":
            kind = "patent records"
        elif GOVERNMENT.search(host):
            kind = "government"
        elif own_site(host, subject):
            kind = "own site"
        else:
            continue
        out.append({"kind": "official", "source": host, "title": r["title"], "url": r["url"], "what": kind})
    return out


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


OFFICIAL = {  # heading, nothing found, what kind of page
    "en": ("Official (their own pages)", "No official statement found.",
           {"government": "government site", "own site": "own site", "patent records": "patent records"}),
    "es": ("Oficial (sus propias páginas)", "No se encontró ninguna declaración oficial.",
           {"government": "sitio del gobierno", "own site": "sitio propio", "patent records": "registro de patentes"}),
    "pt": ("Oficial (as próprias páginas)", "Nenhuma declaração oficial encontrada.",
           {"government": "site do governo", "own site": "site próprio", "patent records": "registro de patentes"}),
    "fr": ("Officiel (leurs propres pages)", "Aucune déclaration officielle trouvée.",
           {"government": "site gouvernemental", "own site": "site officiel", "patent records": "registre de brevets"}),
    "de": ("Offiziell (eigene Seiten)", "Keine offizielle Stellungnahme gefunden.",
           {"government": "Regierungsseite", "own site": "eigene Website", "patent records": "Patentregister"}),
    "ja": ("公式（本人・当局のページ）", "公式発表は見つかりませんでした。",
           {"government": "政府サイト", "own site": "公式サイト", "patent records": "特許記録"}),
}


def report(topic: str, items: list[dict], lang: str = "en", official_items: list[dict] | None = None,
           official_trouble: str = "") -> str:
    """Every line attributed and quoted, by kind of source; the frame is code, never the model's."""
    head, press_word, none, says = HEAD.get(lang, HEAD["en"])
    lines = [head.format(topic=f"“{topic}”" if topic else "today's news"), "", f"{press_word}:"]
    if not items:
        lines.append(none)
    for it in items:
        lines.append(f"- {it['outlet']} ({say_date(it['date'], lang)}): “{it['title']}”")
    if official_items is not None:
        heading, nothing, kinds = OFFICIAL.get(lang, OFFICIAL["en"])
        lines += ["", f"{heading}:"]
        if official_trouble:
            lines.append(official_trouble)
        elif not official_items:
            lines.append(nothing)
        for it in official_items:
            lines.append(f"- {it['source']} ({kinds.get(it['what'], it['what'])}): “{it['title']}”")
    return "\n".join(lines)
