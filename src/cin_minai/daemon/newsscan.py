# SPDX-License-Identifier: GPL-3.0-or-later
"""The news scan (PLAN D92): who says what — press, social, official — never what happened.

Press: news feeds give each article's outlet, date and headline. The report quotes the headline word for word with its
outlet and date: no model in between, so nothing can be paraphrased into a claim the outlet didn't make. Outlets aren't
judged or picked; one outlet can't crowd out the rest (two headlines each at most). Social: posts quoted with poster,
place and date, marked as unchecked claims. Official: the subject's own pages, government sites, patent records.
"""

from __future__ import annotations

import datetime as dt
import email.utils
import html
import json
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
PROVIDERS_WITH_OFFICIAL = "Google News, Bing News, Reddit, Mastodon and DuckDuckGo"
ONLY_HEAD = {"en": "Only {only}, as you asked.", "es": "Solo {only}, como pediste.", "pt": "Só {only}, como você pediu.",
             "fr": "Seulement {only}, comme demandé.", "de": "Nur {only}, wie gewünscht.", "ja": "ご指定どおり {only} のみです。"}


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


# --- social: what people post, attributed to the poster (D92) ----------------------------------------------------------
# Only networks that can be searched without an account (checked 2026-10-07). X and Bluesky need a signed-in account to
# search, so they're named as not covered instead of being skipped silently; X comes back with Grok (Ian, 2026-10-07).
SOCIAL_ITEMS = 8
SOCIAL_PER_PLACE = 2
POST_CHARS = 200
ATOM = "{http://www.w3.org/2005/Atom}"
MASTODON = "https://mastodon.social"


def _iso(text: str):
    try:
        return dt.datetime.fromisoformat(text)
    except (TypeError, ValueError):
        return None


def _clip(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= POST_CHARS else text[:POST_CHARS].rsplit(" ", 1)[0] + " …"


def reddit(topic: str, lang: str = "en") -> list[dict]:
    """This week's top Reddit posts about the topic: community, poster, date, the post's own title."""
    url = "https://www.reddit.com/search.rss?" + urllib.parse.urlencode(
        {"q": topic, "sort": "top", "t": "week", "type": "link"})
    xml, _ = websearch._get(url, accept="application/atom+xml")
    out = []
    for e in ET.fromstring(xml).iter(ATOM + "entry"):
        cat, link = e.find(ATOM + "category"), e.find(ATOM + "link")
        place = cat.get("label", "") if cat is not None else ""
        if not place.startswith("r/"):
            continue  # a community or a user, not a post
        poster = (e.findtext(ATOM + "author/" + ATOM + "name") or "").strip().removeprefix("/")
        out.append({"kind": "social", "network": "Reddit", "outlet": place, "who": f"{poster} on {place}" if poster
                    else place, "title": _clip(e.findtext(ATOM + "title") or ""),
                    "url": link.get("href", "") if link is not None else "", "date": _iso(e.findtext(ATOM + "updated"))})
    return out


def _hashtag(topic: str) -> str:
    return "".join(re.findall(r"\w+", topic.lower()))


def mastodon(topic: str, lang: str = "en") -> list[dict]:
    """Recent Mastodon posts under the topic's hashtag (#linuxmint), as mastodon.social sees them; full-text search
    needs an account. Posts marked sensitive are left out; posts in another language too, when they say theirs."""
    tag = _hashtag(topic)
    if not tag:
        return []
    raw, _ = websearch._get(f"{MASTODON}/api/v1/timelines/tag/{urllib.parse.quote(tag)}?limit=20", "application/json")
    out = []
    for p in json.loads(raw):
        if p.get("sensitive") or p.get("spoiler_text") or (p.get("language") or lang) != lang:
            continue
        # a line break or paragraph is a space; any other tag (a link around @name or #tag) is nothing
        text = html.unescape(re.sub(r"<[^>]+>", "", re.sub(r"<br\s*/?>|</p>", " ", p.get("content", ""))))
        if text.strip():
            acct = p.get("account", {}).get("acct", "?")
            out.append({"kind": "social", "network": "Mastodon", "outlet": acct, "who": f"@{acct} on Mastodon",
                        "title": _clip(text), "url": p.get("url") or p.get("uri", ""), "date": _iso(p.get("created_at"))})
    return out


TOPIC_STOP = {"the", "and", "news", "about", "with", "from", "for", "a", "an", "of", "on", "in", "to", "is",
              "de", "la", "le", "el", "der", "die", "das"}


def _stem(word: str) -> str:
    return word if len(word) < 5 else word[:max(4, len(word) - 2)]  # models -> mode, patents -> pate


def relevant(text: str, topic: str) -> bool:
    """At least half of the topic's words are in the post: Reddit's "top of the week" search matches loosely (round 5,
    "local AI models": a frog cake, a nightmare, a dinner date). Short words count as whole words ("AI" isn't "said");
    longer ones by their stem anywhere ("Ice Cube" finds "#IceCube"); words in scripts without spaces as they are."""
    words = [w for w in re.findall(r"\w+", topic.lower()) if w not in TOPIC_STOP]
    if not words:
        return True
    low = text.lower()
    found = sum(1 for w in words if (re.search(rf"(?<![^\W_]){re.escape(w)}(?![^\W_])", low) if len(w) < 4 and w.isascii()
                                    else _stem(w) in low))
    return found * 2 >= len(words)


def social(topic: str, lang: str = "en", only: str = "") -> tuple[list[dict], list[str]]:
    """(posts, networks that couldn't be reached). Only posts about the topic; two per community or poster at most,
    half the places per network so one network can't fill the section, then newest first. only: "Reddit" or
    "Mastodon" when the person asked for that one."""
    if not topic:
        return [], []
    feeds = tuple((n, f) for n, f in (("Reddit", reddit), ("Mastodon", mastodon)) if not only or n == only)
    items, failed = [], []
    for name, feed in feeds:
        try:
            posts = [p for p in feed(topic, lang) if relevant(p["title"] + " " + p["outlet"], topic)]
            items += balance(posts, SOCIAL_PER_PLACE, SOCIAL_ITEMS // len(feeds))
        except (websearch.SearchError, ET.ParseError, ValueError) as e:
            failed.append(f"{name} ({e})")
    return balance(items, SOCIAL_PER_PLACE, SOCIAL_ITEMS), failed


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


# Official sources that need a key (keys.SOURCES): source id -> (does it apply to this topic?, fetch(topic, lang, key)).
# Empty until a source is wired (the patent office waits for Ian's go, 2026-10-07).
KEYED: dict[str, tuple] = {}


def keyed(topic: str, lang: str = "en") -> tuple[list[dict], list[str]]:
    """(official items from keyed sources, sources skipped for a missing key). The key is read here, for the request,
    and goes nowhere else."""
    from . import keys
    items, needed = [], []
    for source, (applies, fetch) in KEYED.items():
        if not topic or not applies(topic):
            continue
        key = keys.get(source)
        if not key:
            needed.append(source)
            continue
        try:
            items += fetch(topic, lang, key)
        except (websearch.SearchError, ET.ParseError, ValueError):
            pass  # said like any other source that didn't answer: by its absence and the "nothing found" line
    return items, needed


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


SOCIAL = {  # heading, nothing found, couldn't reach, not covered
    "en": ("Social media (what people post; claims, not checked)", "No posts found.", "Couldn't reach",
           "Not covered: X and Bluesky (searching them needs an account)."),
    "es": ("Redes sociales (lo que publica la gente; afirmaciones sin verificar)", "No se encontraron publicaciones.",
           "No se pudo consultar", "No incluidos: X y Bluesky (buscar en ellos requiere una cuenta)."),
    "pt": ("Redes sociais (o que as pessoas publicam; afirmações não verificadas)", "Nenhuma publicação encontrada.",
           "Não foi possível consultar", "Não incluídos: X e Bluesky (pesquisar neles exige uma conta)."),
    "fr": ("Réseaux sociaux (ce que les gens publient ; affirmations non vérifiées)", "Aucune publication trouvée.",
           "Impossible de consulter", "Non couverts : X et Bluesky (y chercher demande un compte)."),
    "de": ("Soziale Medien (was Leute posten; Behauptungen, ungeprüft)", "Keine Beiträge gefunden.",
           "Nicht erreichbar", "Nicht abgedeckt: X und Bluesky (die Suche dort braucht ein Konto)."),
    "ja": ("SNS（個人の投稿。未確認の主張です）", "投稿は見つかりませんでした。", "接続できませんでした",
           "対象外：X と Bluesky（検索にはアカウントが必要です）。"),
}


NEEDS_KEY = {"en": "(Not searched: {names} — it needs a free key; the card below shows how to get one.)",
             "es": "(Sin consultar: {names} — necesita una clave gratuita; la tarjeta de abajo explica cómo obtenerla.)",
             "pt": "(Não consultado: {names} — precisa de uma chave gratuita; o cartão abaixo mostra como obtê-la.)",
             "fr": "(Non consulté : {names} — il faut une clé gratuite ; la carte ci-dessous explique comment l'obtenir.)",
             "de": "(Nicht abgefragt: {names} — braucht einen kostenlosen Schlüssel; die Karte unten zeigt, wie.)",
             "ja": "（未検索：{names} — 無料のキーが必要です。下のカードに取得方法があります。）"}


def report(topic: str, items: list[dict], lang: str = "en", official_items: list[dict] | None = None,
           official_trouble: str = "", social_items: list[dict] | None = None,
           social_failed: list[str] | None = None, needs_key: list[str] | None = None, only: str = "") -> str:
    """Every line attributed and quoted, by kind of source; the frame is code, never the model's. only: one network
    the person asked for — then no press or official sections, and no "not covered" line."""
    head, press_word, none, says = HEAD.get(lang, HEAD["en"])
    lines = [head.format(topic=f"“{topic}”" if topic else "today's news")]
    if only:
        lines.append(ONLY_HEAD.get(lang, ONLY_HEAD["en"]).format(only=only))
    else:
        lines += ["", f"{press_word}:"]
        if not items:
            lines.append(none)
    for it in items:
        lines.append(f"- {it['outlet']} ({say_date(it['date'], lang)}): “{it['title']}”")
    if social_items is not None:
        heading, nothing, unreachable, not_covered = SOCIAL.get(lang, SOCIAL["en"])
        lines += ["", f"{heading}:"]
        if not social_items:
            lines.append(nothing)
        for it in social_items:
            lines.append(f"- {it['who']} ({say_date(it['date'], lang)}): “{it['title']}”")
        if social_failed:
            lines.append(f"({unreachable}: {', '.join(social_failed)}.)")
        if not only:
            lines.append(not_covered)
    if official_items is not None:
        heading, nothing, kinds = OFFICIAL.get(lang, OFFICIAL["en"])
        lines += ["", f"{heading}:"]
        if official_trouble:
            lines.append(official_trouble)
        elif not official_items:
            lines.append(nothing)
        for it in official_items:
            lines.append(f"- {it['source']} ({kinds.get(it['what'], it['what'])}): “{it['title']}”")
        if needs_key:
            from . import keys
            names = ", ".join(keys.SOURCES[k].name for k in needs_key if k in keys.SOURCES)
            lines.append(NEEDS_KEY.get(lang, NEEDS_KEY["en"]).format(names=names))
    return "\n".join(lines)
