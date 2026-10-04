# SPDX-License-Identifier: GPL-3.0-or-later
"""The built-in help (`lookup_help`): find the help card for a query the guide wrote.

Cards are English with Mint's names filled in per language (training/kb/). The guide writes its query in
English or in the user's language, so each card is indexed with its text, the Windows habit it answers,
Mint's labels in all six languages, and hand-written search words in all six (training/kb/search.py).
Ranking is BM25 over simple word stems (a plural "s" dropped, then the first five letters: "instalar",
"installer", "installieren" meet at "insta") and, for Japanese, character pairs. Stdlib only; the index is built once at start.
"""

from __future__ import annotations

import json
import math
import re
import unicodedata
from collections import Counter

# Words that say nothing about which card: question words, "Linux Mint", "Windows", "computer"...
# ("windows" is dropped, "window" isn't: the switch-windows card needs it.)
STOP = set("""
a an the and or of to in on at for with from by as is are be it its this that these my me i you your we
how what where which who why when can could do does did make get use using want need please help find
there here some any about like into up out not no so if then than just also very
linux mint cinminai cin-minai windows computer pc laptop system ubuntu
el la los las lo un una unos unas de del al y o en con por para mi mis tu su sus que qué como cómo donde
dónde cuál puedo quiero hacer se es está esto este esta hay ordenador computadora equipo
o a os as um uma de do da dos das no na nos nas em com por para meu minha que como onde qual posso
quero fazer é está isso este esta computador
le la les l un une des de du d au aux et ou en dans avec par pour sur mon ma mes que qu comment où
quel quelle puis je veux faire est ce cet cette ordinateur sous
der die das den dem des ein eine einen einem und oder in im an am auf mit von zu zum zur für mein
meine meinen wie wo was welche kann ich will machen ist es ist dies diese dieser unter computer rechner
""".split())
FIELD_WEIGHT = {"id": 2, "keywords": 2, "windows": 2, "labels": 1, "card": 1}
CJK = re.compile(r"[぀-ヿ㐀-鿿ｦ-ﾟ]+")


def _fold(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).lower()
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def tokens(text: str) -> list[str]:
    """Stems of the words (stop words dropped) plus Japanese character pairs."""
    text = unicodedata.normalize("NFKC", text)
    out = []
    for run in CJK.findall(text):
        out += [run] if len(run) == 1 else [run[i:i + 2] for i in range(len(run) - 1)]
    for word in re.findall(r"[a-z0-9]+(?:[+'][a-z0-9]+)*", _fold(CJK.sub(" ", text))):
        word = word.split("'")[-1]  # l'écran -> écran
        if word in STOP or len(word) < 2:
            continue
        if word[0].isdigit():
            out.append(word)
            continue
        if len(word) > 3 and word.endswith("s"):
            word = word[:-1]  # sends -> send, programs -> program
        out.append(word[:5])
    return out


def resolve(card: str, labels: dict, lang: str) -> str:
    """Fill {key} with Mint's name in `lang` (English if Mint has no translation for it)."""
    def name(m):
        row = labels.get(m.group(1), {})
        return row.get(lang) or row.get("en") or m.group(0)
    return re.sub(r"\{(\w+)\}", name, card)


class HelpIndex:
    K1, B = 1.2, 0.75

    def __init__(self, data: dict) -> None:
        self.labels = data["labels"]
        self.cards = {c["id"]: c for c in data["cards"]}
        self.docs: dict[str, Counter] = {}
        for c in data["cards"]:
            keys = re.findall(r"\{(\w+)\}", c["card"])
            fields = {
                "id": c["id"].replace("_", " "),
                "keywords": c.get("keywords", ""),
                "windows": c.get("windows", ""),
                "labels": " ".join(v for k in keys for v in self.labels.get(k, {}).values()),
                "card": re.sub(r"\{(\w+)\}", " ", c["card"]),
            }
            tf = Counter()
            for field, text in fields.items():
                for t in tokens(text):
                    tf[t] += FIELD_WEIGHT[field]
            self.docs[c["id"]] = tf
        n = len(self.docs)
        df = Counter(t for tf in self.docs.values() for t in tf)
        self.idf = {t: math.log(1 + (n - d + 0.5) / (d + 0.5)) for t, d in df.items()}
        self.avglen = sum(sum(tf.values()) for tf in self.docs.values()) / max(n, 1)

    @classmethod
    def load(cls, path: str) -> "HelpIndex":
        with open(path, encoding="utf-8") as f:
            return cls(json.load(f))

    def rank(self, query: str) -> list[tuple[str, float]]:
        q = Counter(tokens(query))
        scores = []
        for cid, tf in self.docs.items():
            length = sum(tf.values())
            s = 0.0
            for t in q:
                f = tf.get(t, 0)
                if f:
                    s += self.idf[t] * f * (self.K1 + 1) / (f + self.K1 * (1 - self.B + self.B * length / self.avglen))
            if s > 0:
                scores.append((cid, s))
        return sorted(scores, key=lambda x: -x[1])

    def lookup(self, query: str, lang: str, min_score: float = 1.0) -> tuple[str | None, str]:
        """(card id, text for the model). No match: id None and a short note. min_score: how sure a match must be
        (terminal errors ask for more: an unknown error otherwise finds a wrong card by a stray word)."""
        if not tokens(query) and re.search(r"linux|mint|cin-?minai|ubuntu", query, re.I) and "what_is_linux" in self.cards:
            # nothing left but the system's name: "what is Linux (Mint)?"
            return "what_is_linux", resolve(self.cards["what_is_linux"]["card"], self.labels, lang)
        ranked = self.rank(query)
        if not ranked or ranked[0][1] < min_score:
            return None, "Nothing in the built-in help matches this."
        cid = ranked[0][0]
        return cid, resolve(self.cards[cid]["card"], self.labels, lang)
