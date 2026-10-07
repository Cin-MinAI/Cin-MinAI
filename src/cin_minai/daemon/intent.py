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


def narrow(schema: dict, text: str) -> dict:
    """The schema with only the tools this request may use. Unchanged when it has no email tool (other prompts)."""
    options = schema.get("anyOf", [])
    names = [o["properties"]["tool"]["const"] for o in options]
    if "compose_email" not in names:
        return schema
    keep = {"compose_email", "decline"} if wants_email(text) else set(names) - {"compose_email"}
    return {**schema, "anyOf": [o for o in options if o["properties"]["tool"]["const"] in keep]}
