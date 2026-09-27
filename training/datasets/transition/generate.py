#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Generate the Windows -> Linux transition corpus (PLAN D32; training/guide/README.md, phase 2).

Teacher: a local open model behind llama-server (OpenAI-compatible) — never a proprietary API.
For each knowledge-base topic (training/kb/transition.py) and language:

  1. the teacher writes N questions a Windows user might ask (beginner wording, typos, Windows words);
  2. questions too close to any eval task (public or held-out, all languages) are dropped
     (decontamination), as are near-duplicates within the corpus;
  3. the teacher, under the guide's own runtime prompt (run_eval.py prompt v2), writes the
     lookup_help call; the help card goes back as the tool result; the teacher writes the reply;
  4. the reply must pass the eval's own checks (language, Mint's names in that language, numbered
     steps where the topic has steps, no terminal commands, length); one retry, else rejected.

Output (JSONL, one example per line, in the runtime chat format) + rejects + stats:

    python3 generate.py --url http://127.0.0.1:18091 --model Qwen3-14B-Q4_K_M --out DIR
        [--topics install,notepad] [--langs en,ja] [--per 5] [--seed 1]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import random
import re
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "training", "kb"))
sys.path.insert(0, os.path.join(ROOT, "training", "eval", "guide"))
sys.argv, _argv = [sys.argv[0]], sys.argv  # run_eval reads sys.argv at import
import run_eval as R  # noqa: E402
import transition as KB  # noqa: E402
sys.argv = _argv

R.PROMPT = "v2"
LANG_NAMES = {"en": "English", "es": "Spanish", "pt": "Brazilian Portuguese", "fr": "French", "de": "German",
              "ja": "Japanese"}
NO_CMD = ["sudo", r"\bapt(-get)?\s+(install|remove)", r"\brm\s+-", r"\bchmod\b"]


def label(key: str, lang: str) -> str:
    row = R.LABELS[key]
    return row.get(lang) or (row["en"] if key in KB.BRANDS else None)


def resolve(text: str, lang: str) -> str:
    return re.sub(r"\{(\w+)\}", lambda m: label(m.group(1), lang), text)


# --- decontamination -------------------------------------------------------------------------------

def grams(text: str, n: int = 3) -> set:
    w = re.findall(r"\w+", text.lower())
    if len(w) < n:
        return {tuple(w)} if w else set()
    return {tuple(w[i:i + n]) for i in range(len(w) - n + 1)}


def cjk_grams(text: str, n: int = 3) -> set:  # Japanese has no spaces: character trigrams
    t = re.sub(r"\s+", "", text)
    return {t[i:i + n] for i in range(max(len(t) - n + 1, 1))}


def similar(a: str, b: str) -> float:
    ga, gb = (cjk_grams(a), cjk_grams(b)) if R.language(a) == "ja" else (grams(a), grams(b))
    return len(ga & gb) / len(ga | gb) if ga and gb else 0.0


def eval_questions() -> list[str]:
    import importlib.util
    out = []
    for path in ("training/eval/guide/tasks.py", "training/eval/guide-hidden/tasks.py"):
        spec = importlib.util.spec_from_file_location("t", os.path.join(ROOT, path))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        out += [q for t in mod.TASKS for q in t["q"].values()]
    return out


# --- teacher -----------------------------------------------------------------------------------------

class Teacher:
    def __init__(self, url: str, model: str):
        self.url, self.model = url.rstrip("/"), model

    def chat(self, messages, schema=None, temperature=0.0, max_tokens=700, seed=0) -> str:
        body = {"model": self.model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens,
                "seed": seed, "chat_template_kwargs": {"enable_thinking": False}}
        if schema:
            body["response_format"] = {"type": "json_schema", "json_schema": {"name": "out", "schema": schema}}
        req = urllib.request.Request(self.url + "/v1/chat/completions", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=600) as r:
            text = json.load(r)["choices"][0]["message"]["content"] or ""
        return re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()


QUESTION_PROMPT = """You help build a help assistant for people who just moved from Windows to Linux Mint. \
Many are older or new to computers.

Write {n} messages that people might type into the assistant, in {language}, about: {windows}.
Write them the way these people would (one message each, in this order), but never mention who they
are and never add labels, numbers, or brackets — only the words they would type:
{personas}
- They use the Windows words they know, not Linux words.
- Each message is only the person's question — no answer, no greeting from the assistant.
- The messages must differ in wording, length, and what exactly is asked.
- Every message must be written in {language}, not in English (unless {language} is English): \
natural {language}, the way a native speaker would type it."""

PERSONAS = [
    "an older person who types slowly, all lowercase, no punctuation",
    "a worried person who thinks they broke something",
    "a very polite person who writes a full sentence with please and thank you",
    "someone in a hurry: three or four words only",
    "someone vague who doesn't know the right words and describes what they see",
    "someone who used Windows at work for years and names the exact Windows feature",
    "someone who makes a few typos",
    "someone asking where to find it",
    "someone whose grandchild told them to ask",
    "someone who tried something and it didn't work",
]


def questions(t: Teacher, topic: dict, lang: str, n: int, seed: int) -> list[str]:
    schema = {"type": "array", "items": {"type": "string", "minLength": 3, "maxLength": 300},
              "minItems": n, "maxItems": n}
    who = random.Random(seed).sample(PERSONAS, n)
    personas = "\n".join(f"{i + 1}. {p}" for i, p in enumerate(who))
    raw = t.chat([{"role": "user", "content": QUESTION_PROMPT.format(n=n, language=LANG_NAMES[lang],
                                                                     windows=topic["windows"],
                                                                     personas=personas)}],
                 schema=schema, temperature=0.7, max_tokens=1200, seed=seed)
    return [q for q in (clean_question(x) for x in json.loads(raw)) if q]


# The teacher sometimes copies the persona numbering into the message ("[ user5 ] …", "Person 3: …").
WHO = r"(?:user|person|persona|message|ユーザー|人物)"
LABEL = re.compile(rf"^\s*(?:[\[(（【]\s*{WHO}?\s*\d+\s*[\])）】]|{WHO}\s*\d+\s*[:：.\-–]|\d+\s*[.)]\s)\s*", re.I)


PREFIX = re.compile(r"^\s*(?:text|user|message|question|pregunta|frage|question|pergunta)\s*[:：]\s*", re.I)


HEAD = re.compile(r"^[^\[\]\n]{0,160}\]\s*(?:->|:)?\s*")  # "user1] …", "texte 1 – par une personne … ] : …"


def clean_question(q: str) -> str:
    q = HEAD.sub("", q.strip()).strip()
    q = LABEL.sub("", q).strip()
    q = re.sub(r"\s*\]\s*$", "", q)  # stray closing bracket
    q = HEAD.sub("", q).strip()  # a label half-removed above ("]: …")
    q = PREFIX.sub("", q).strip()
    return re.sub(r"\*\*(.+?)\*\*", r"", q).strip()


JUNK = re.compile(r"%[sd]|\{\}|^\W*$|^[\[\]{}(),.:;\s\d]+$|^(errors?|fmt|text|group\d*|user\d*|strconv|subtitle:.*)$",
                  re.I)


GLUED = re.compile(r"\[\s*\d+\s*[.:\]]|\s\d+\.\s.*\s\d+\.\s")  # "[ 2. …", "1. … 2. …"


TRACES = re.compile(r"\[\s*user|\buser\s*\d|\bpersona\b|\bpersonne\b|\bpessoa\b|\bperson \d|mensaje k|message k|"
                    r"<br>|palabras en negrita|debe ser natural|respeta el estilo|（[^）]{0,20}人）|"
                    r"向けのメッセージ|が特徴|様子が伝わ|人向け|^\s*label\s*\d", re.I)  # Japanese teacher notes too


def mixed_language(text: str, lang: str) -> bool:
    """True if a non-English reply has a line in English (seen: "It sounds like you want to…" opening a
    Portuguese reply, "Which would you like?" closing a Japanese one). Program names don't count."""
    if lang == "en":
        return False
    for line in (x.strip() for x in text.splitlines()):
        if len(line) < 12:
            continue
        if lang == "ja":
            letters = [c for c in line if c.isalpha()]
            if letters and sum(c.isascii() for c in letters) / len(letters) > 0.7:
                return True
        else:
            sc = R.language_scores(line)
            if sc.get("en", 0) >= 2 and sc["en"] > sc.get(lang, 0):
                return True
    return False


def valid_question(q: str, lang: str) -> bool:
    """Reject what the teacher emits when it derails under the list format (seen in the cycle-0 run:
    'fmt', '%s,%s', 'errors', 'sdfsdf', '[', 'user1', 'subtitle: …'): too short, placeholders, no real
    words, or a language that isn't confidently the requested one."""
    if JUNK.search(q.strip()) or GLUED.search(q) or re.search(r"(\S)(?:\s*\1){5,}", q):  # 6+ repeats: 😊😊😊…
        return False
    low = q.lower()
    if any(p.lower()[:25] in low for p in PERSONAS):  # the persona description leaked into the message
        return False
    if TRACES.search(q):  # labels, persona words, or the teacher's own commentary left in the message
        return False
    if lang == "ja":
        kana = sum("぀" <= c <= "ヿ" for c in q)
        return len(q) >= 6 and kana >= 2 and R.language(q) == "ja"
    words = re.findall(r"[^\W\d_]{2,}", q)
    if len(q) < 12 or len(words) < 3:
        return False
    if any(len(w) > 4 and not re.search(r"[aeiouyàâäéèêëïîôöùûüáíóúãõ]", w, re.I) for w in words):
        return False  # keyboard mash like 'sdfsdf'
    scores = R.language_scores(q)  # reject only when another language clearly wins (by 2+ words):
    if "ja" in scores:
        return False  # Japanese script under a non-Japanese language
    other = max((v for k, v in scores.items() if k != lang), default=0)  # short questions and ones
    return other - scores.get(lang, 0) < 2  # with English product names ("Fax and Scan") stay


def example(t: Teacher, topic: dict, lang: str, q: str, seed: int) -> tuple[dict | None, list[str]]:
    task = {"doc": None}
    system = R.system_prompt(task)
    only_lookup = {"anyOf": [s for s in R.schema(None)["anyOf"]
                             if s["properties"]["tool"]["const"] == "lookup_help"]}
    call = t.chat([{"role": "system", "content": system}, {"role": "user", "content": q}],
                  schema=only_lookup, temperature=0.2, max_tokens=120, seed=seed)
    card = resolve(topic["card"], lang)
    must = [[label(k, lang) for k in (m if isinstance(m, list) else [m])] for m in topic["must"]]
    it = {"lang": lang, "must": must, "must_not": NO_CMD,
          "steps": 2 if topic["steps"] else 0}
    messages = [{"role": "system", "content": system}, {"role": "user", "content": q},
                {"role": "assistant", "content": call},
                {"role": "user", "content": f"Result of lookup_help:\n{card}\n\n{R.STYLE_V2}"}]
    fails = []
    for attempt, temp in enumerate((0.3, 0.7)):
        reply = t.chat(messages, temperature=temp, max_tokens=600, seed=seed + attempt)
        fails = R.stage_b(it, reply)
        if not fails:
            return {"messages": messages + [{"role": "assistant", "content": reply}],
                    "meta": {"topic": topic["id"], "lang": lang, "attempt": attempt + 1}}, []
    return None, fails


def safe_example(t: Teacher, topic: dict, lang: str, q: str, seed: int) -> tuple[dict | None, list[str]]:
    """One failed request (timeout, server hiccup) becomes a rejection, not the end of an overnight run."""
    try:
        return example(t, topic, lang, q, seed)
    except Exception as e:
        return None, [f"error {type(e).__name__}"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True), ap.add_argument("--model", required=True)
    ap.add_argument("--out", required=True), ap.add_argument("--topics"), ap.add_argument("--langs")
    ap.add_argument("--per", type=int, default=5), ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--contam", type=float, default=0.5, help="drop questions this similar to an eval task")
    ap.add_argument("--workers", type=int, default=1,
                    help="parallel teacher requests (match llama-server --parallel)")
    o = ap.parse_args()
    random.seed(o.seed)
    t = Teacher(o.url, o.model)
    topics = [x for x in KB.TOPICS if not o.topics or x["id"] in o.topics.split(",")]
    langs = o.langs.split(",") if o.langs else KB.ALL
    evalq = eval_questions()
    os.makedirs(o.out, exist_ok=True)
    stats = {"teacher": o.model, "started": dt.datetime.now().isoformat(timespec="seconds"), "per": o.per,
             "seed": o.seed, "contam_threshold": o.contam, "questions": 0, "contaminated": 0, "duplicates": 0,
             "workers": o.workers, "accepted": 0, "rejected": 0, "retried_ok": 0, "reject_reasons": {}, "by_lang": {}}
    kept: list[str] = []
    with open(os.path.join(o.out, "examples.jsonl"), "a", encoding="utf-8") as fx, \
         open(os.path.join(o.out, "rejects.jsonl"), "a", encoding="utf-8") as fr:
        for topic in topics:
            for lang in topic.get("langs", KB.ALL):
                if lang not in langs:
                    continue
                seed = random.randrange(1 << 30)
                try:
                    qs = questions(t, topic, lang, o.per, seed)
                except Exception as e:  # a failed batch is logged, not fatal
                    fr.write(json.dumps({"topic": topic["id"], "lang": lang, "error": repr(e)}) + "\n")
                    continue
                todo = []
                for q in qs:
                    stats["questions"] += 1
                    if not valid_question(q, lang):  # junk, or written in another language
                        stats["invalid_questions"] = stats.get("invalid_questions", 0) + 1
                        fr.write(json.dumps({"topic": topic["id"], "lang": lang, "q": q, "reason": "invalid question"},
                                            ensure_ascii=False) + "\n")
                        continue
                    worst = max((similar(q, e) for e in evalq), default=0)
                    if worst >= o.contam:
                        stats["contaminated"] += 1
                        fr.write(json.dumps({"topic": topic["id"], "lang": lang, "q": q, "reason": "contaminated",
                                             "similarity": round(worst, 2)}, ensure_ascii=False) + "\n")
                        continue
                    if any(similar(q, k) >= 0.8 for k in kept + [x for x, _ in todo]):
                        stats["duplicates"] += 1
                        continue
                    todo.append((q, worst))
                # filtering above is sequential; the teacher calls run in parallel (--workers), and results
                # are written in question order
                with ThreadPoolExecutor(max_workers=o.workers) as pool:
                    results = list(pool.map(lambda qw: safe_example(t, topic, lang, qw[0], seed), todo))
                for (q, worst), (ex, fails) in zip(todo, results):
                    bl = stats["by_lang"].setdefault(lang, {"accepted": 0, "rejected": 0})
                    if ex:
                        ex["meta"].update({"teacher": o.model, "max_eval_similarity": round(worst, 2)})
                        fx.write(json.dumps(ex, ensure_ascii=False) + "\n")
                        fx.flush()
                        kept.append(q)
                        stats["accepted"] += 1
                        bl["accepted"] += 1
                        stats["retried_ok"] += ex["meta"]["attempt"] == 2
                    else:
                        stats["rejected"] += 1
                        bl["rejected"] += 1
                        for f in fails:
                            key = re.sub(r"missing .*", "missing name/fact", re.sub(r"\(\d+\)", "", f))
                            stats["reject_reasons"][key] = stats["reject_reasons"].get(key, 0) + 1
                        fr.write(json.dumps({"topic": topic["id"], "lang": lang, "q": q, "reason": fails},
                                            ensure_ascii=False) + "\n")
                        fr.flush()
                print(f"{time.strftime('%H:%M:%S')} {topic['id']:<18} {lang}  accepted {stats['accepted']}  "
                      f"rejected {stats['rejected']}  contaminated {stats['contaminated']}", flush=True)
    stats["finished"] = dt.datetime.now().isoformat(timespec="seconds")
    json.dump(stats, open(os.path.join(o.out, "stats.json"), "w"), indent=1)
    print(json.dumps(stats, indent=1))


if __name__ == "__main__":
    main()
