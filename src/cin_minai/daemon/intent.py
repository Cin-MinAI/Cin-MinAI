# SPDX-License-Identifier: GPL-3.0-or-later
"""Which tools a request may use, decided from its words before the model chooses (D88, toward voice operation).

The guide is a 4B model: given the email tool, it also opened mail drafts for "help me write a letter", and in Spanish
and German it still looked up help instead of writing the email it was asked for (A/B, 2026-10-07). A rule from the
request itself makes this deterministic: the email tool is offered only when the person asks for an email to be
written, and then it's the only choice (with decline); otherwise it isn't offered at all.
"""

from __future__ import annotations

import re

EMAIL = re.compile(r"\b(e-?mails?|mails?|correos?(\s+electr[oó]nicos?)?|courriels?)\b|メール", re.I)
# writing, not sending: "my email won't send" is a problem to look up, not a request to write one
WRITE = re.compile(r"\b(write|draft|compose|escrib\w*|redact\w*|escrev\w*|redij\w*|redig\w*|[ée]cri[sv]\w*|"
                   r"r[ée]dig\w*|schreib\w*|verfass\w*)\b|書いて|書く|作成|下書き", re.I)
SEND_TO = re.compile(r"\bsend (an?|my) (e-?mail|mail|message) to\b|\b(manda|envía|envia|mande|envie|envoie|schick)\w*\b"
                     r"[^.?!]{0,30}\b(e-?mail|correo|courriel)\b", re.I)
# "how do I …": explained, not done. Anchored: Portuguese "como" also means "as" in the middle of a sentence.
HOWTO = re.compile(r"\bhow (do|can|could|should|would) (i|you|we)\b|\bhow to\b|^\W*(c[oó]mo|comment|wie)\b|"
                   r"方法|どうやって|どうすれば", re.I)


def wants_email(text: str) -> bool:
    """The person asks for an email to be written (or a letter put in an email) — not how to write one."""
    if HOWTO.search(text):
        return False
    return bool(EMAIL.search(text) and (WRITE.search(text) or SEND_TO.search(text)))


# the asking itself, not the topic (helpcards.tokens stems: the first five letters; Japanese character pairs)
REQUEST_WORDS = {"searc", "find", "look", "googl", "web", "inter", "onlin", "busca", "busqu", "pesqu", "procu", "cherc",
                 "reche", "suche", "such", "googe", "検索", "探し", "調べ"}


def search_query(proposed: str, message: str) -> str:
    """The query the search card shows. Round 3 (2026-10-07): asked about finding a YouTube video, the guide proposed
    "how to install openvpn on linux mint" — the earlier topic. A query that shares no word with the message is
    replaced by the message itself; a message with no words of its own ("search for that") keeps the model's query."""
    from .helpcards import tokens
    proposed, message = proposed.strip()[:200], message.strip()
    asked = set(tokens(message)) - REQUEST_WORDS
    if not proposed or (asked and not asked & set(tokens(proposed))):
        return message[:200]
    return proposed


# --- chains (D91): "pull up a video about X (and summarize it)" -------------------------------------------------------
VIDEO = re.compile(r"\b(videos?|vídeos?|vidéos?|youtube|clips?)\b|動画|ビデオ", re.I)
THIS_VIDEO = re.compile(r"\b(this|that|este|esta|ese|esa|esse|essa|ce|cette|dieses|diesem|dieser)\s+(youtube\s+)?"
                        r"(video|vídeo|vidéo|clip)\b|この動画|このビデオ", re.I)
FIND = re.compile(r"\b(find|search|look\s+up|look\s+for|pull\s+up|bring\s+up|show\s+me|get\s+me|play|"
                  r"busca\w*|encuentr\w*|pesquis\w*|procur\w*|ach[ae]\w*|cherch\w*|trouv\w*|such\w*|find\w*)\b|"
                  r"探して|検索|見つけて", re.I)
SUMMARIZE = re.compile(r"\b(summari[sz]e|summary|review|sum (it )?up|recap|watch (it|this) for me|r[eé]s[uú]m\w*|"
                       r"résum\w*|zusammenfass\w*|fass\w*\s+\w+\s+zusammen)\b|要約|まとめ", re.I)
# what's left of the request once the asking is taken out is the topic: "how to make donuts"
FILLER = re.compile(r"\b(can|could|would|will)\s+you\b|\bplease\b|\b(and|then|y|e|et|und)\s*$|"
                    r"\b(a|an|the|me|for me|some|one|un|una|uno|um|uma|une|des|ein|eine|einen)\b|"
                    r"\b(about|on|of|for|sobre|de|acerca de|sur|à propos de|über|zu|zum|zur)\b(?=\s)|"
                    r"\b(and|y|e|et|und)\s+(summari[sz]e|review|resum\w*|résum\w*|fass\w*)\b.*$|"
                    r"\bit\b|\bon youtube\b|\ben youtube\b|\bno youtube\b|\bsur youtube\b|\bauf youtube\b|"
                    r"について|の動画|を|して|ください", re.I)


def video_review(text: str) -> dict | None:
    """{"topic", "summarize"} when the person asks to find a video (and maybe have it summarized) — not "this video",
    which is the one already open in Firefox (webvideo.asks_about_video)."""
    if THIS_VIDEO.search(text) or not VIDEO.search(text) or not FIND.search(text):
        return None
    # "how do I find videos in Firefox?" is a question; "find a video on how to change a tire" is a request
    if re.search(r"\bhow (do|can|could|should) (i|you|we)\b|^\W*(c[oó]mo|comment|wie)\b", text, re.I) \
            and not SUMMARIZE.search(text):
        return None
    topic = SUMMARIZE.sub(" ", FIND.sub(" ", VIDEO.sub(" ", text)))
    for _ in range(3):
        topic = FILLER.sub(" ", topic)
    topic = re.sub(r"\s+", " ", re.sub(r"[?!.¿¡,:;。、？！]", " ", topic)).strip()
    topic = re.sub(r"(\s+(and|y|e|et|und))+$|[のをでと]+$", "", topic).strip()
    if len(topic) < 3:
        return None
    return {"topic": topic, "summarize": bool(SUMMARIZE.search(text))}


# --- chains (D91): "pull up the news about X" ------------------------------------------------------------------------
NEWS = re.compile(r"\b(news|headlines?|noticias|notícias|actualit[ée]s|nouvelles|infos|nachrichten|schlagzeilen)\b|"
                  r"ニュース", re.I)
# questions about news itself, not a request for it: "what is fake news?", "how do I turn off news notifications?"
ABOUT_NEWS = re.compile(r"\b(what (is|are)|qu[eé] (es|son|é)|qu'est-ce que|was (ist|sind)|fake|notification\w*|"
                        r"notificaci\w*|notifica\w*|benachrichtigung\w*|install\w*|instal\w*|apps?|program\w*|"
                        r"reader|lector|leitor|lecteur|feeds?|rss|widget|applet)\b|^\W*(how|c[oó]mo|comment|wie)\b|"
                        r"とは|アプリ", re.I)
NEWS_FILLER = re.compile(r"\b(can|could|would|will)\s+you\b|\bplease\b|\b(pull|bring)\s+up\b|\b(show|get|give|tell)\s+"
                         r"me\b|\bwhat'?s\b|\bwhat is\b|\b(the|any|latest|last|recent|today'?s?|new|top|me|on|about|"
                         r"for|with|in|happening|going on|las|los|el|la|les|le|des|die|der|das|os|as|o|a|últimas?|"
                         r"últimos?|dernières?|neuesten?|aktuellen?|sobre|de|acerca de|sur|à propos de|über|zu|zum|zur|"
                         r"muestra\w*|mostra\w*|montre\w*|zeig\w*|busca\w*|pesquis\w*|cherch\w*|such\w*|quais|s[aã]o|"
                         r"moi|mir|mich|dime)\b|-moi\b|"
                         r"の最新|について|を|見せて|教えて|最新", re.I)


def news_request(text: str) -> dict | None:
    """{"topic"} when the person asks for the news (about something, or in general: topic "")."""
    if not NEWS.search(text) or ABOUT_NEWS.search(text):
        return None
    topic = NEWS.sub(" ", text)
    for _ in range(3):
        topic = NEWS_FILLER.sub(" ", topic)
    topic = re.sub(r"\s+", " ", re.sub(r"[?!.¿¡,:;。、？！]", " ", topic)).strip()
    topic = re.sub(r"(\s+(and|y|e|et|und))+$|^(and|y|e|et|und)\s+|[のをでと]+$", "", topic).strip()
    return {"topic": topic}


def narrow(schema: dict, text: str) -> dict:
    """The schema with only the tools this request may use. Unchanged when it has no email tool (other prompts)."""
    options = schema.get("anyOf", [])
    names = [o["properties"]["tool"]["const"] for o in options]
    if "compose_email" not in names:
        return schema
    keep = {"compose_email", "decline"} if wants_email(text) else set(names) - {"compose_email"}
    return {**schema, "anyOf": [o for o in options if o["properties"]["tool"]["const"] in keep]}
