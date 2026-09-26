#!/usr/bin/env python3
"""Generate the interpretation corpus (PLAN D32 as amended: the guide's fine-tune teaches the Windows
transition AND understanding people): underspecified requests answered by restating what the guide
understood, offering 2-4 ways it can help, naming any out-of-scope reading honestly, and handing the
choice back with a question. The user is the pilot; the guide doesn't start until they choose.

Same teacher, filters and output format as ../transition/generate.py (whose helpers it reuses).

    python3 generate.py --url http://127.0.0.1:18091 --model Qwen3-14B-Q4_K_M --out DIR [--per 4] [--workers 2]
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
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "transition"))
_argv, sys.argv = sys.argv, [sys.argv[0]]
import generate as T  # noqa: E402  (transition generator: teacher, filters, labels, run_eval)
sys.argv = _argv
R = T.R

# Situations people bring to the guide without saying exactly what they want. Each lists the Mint
# programs that could be part of an answer (label keys) and, where it applies, the part that's outside
# the guide's scope (named honestly in the reply, not done).
THEMES = [
    ("gifts for family this year (a list, a budget, keeping track)", ["writer", "calc", "notes"], "the gift ideas themselves"),
    ("getting photos from this computer to a family member", ["email", "files", "pix", "warpinator"], None),
    ("the computer feels slow or strange lately", ["system_monitor", "update_manager", "disk_usage"], None),
    ("keeping track of monthly bills and expenses", ["calc", "writer", "notes"], "advice about money"),
    ("a newsletter or flyer for a club or church group", ["writer", "impress", "printers"], "writing the text itself"),
    ("a letter that needs to be written and printed", ["writer", "printers"], "writing the text itself"),
    ("a file they worked on and now can't find", ["files", "writer"], None),
    ("making things on the screen easier to see", ["display", "fonts", "accessibility"], None),
    ("video calls with grandchildren", ["firefox", "sound", "software_manager"], None),
    ("making sure nothing important gets lost", ["backup_tool", "timeshift", "files"], None),
    ("learning to use the computer better", ["writer", "files", "firefox"], None),
    ("organising lots of pictures", ["pix", "files", "image_viewer"], None),
    ("listening to music or the radio on the computer", ["music_player", "firefox", "sound"], None),
    ("collecting family recipes in one place", ["writer", "calc", "document_scanner"], "the recipes themselves"),
    ("an invitation for a birthday or party", ["writer", "impress", "printers"], "writing the invitation text"),
    ("papers for taxes or the bank that need scanning", ["document_scanner", "files", "backup_tool"], "tax or banking advice"),
    ("remembering appointments and dates", ["notes", "calc", "writer"], None),
    ("passwords for websites, too many to remember", ["firefox", "notes"], None),
    ("a document that needs to look nicer", ["writer", "fonts"], None),
    ("the internet or Wi-Fi acting up", ["network", "firefox"], None),
    ("a slideshow of photos for a family event", ["impress", "pix", "files"], None),
    ("keeping the computer safe", ["update_manager", "firewall", "backup_tool"], None),
    ("a list of phone numbers and addresses", ["calc", "writer", "notes"], None),
    ("setting the computer up for a grandchild to use", ["users", "startup_apps", "software_manager"], None),
    ("a trip that needs planning", ["calc", "writer", "firefox"], "travel advice or bookings"),
    ("an old printer or scanner to get working", ["printers", "document_scanner", "driver_manager"], None),
    ("the computer making noise or getting hot", ["system_monitor", "power"], None),
    ("writing down family history", ["writer", "document_scanner", "pix"], "researching the history itself"),
]

ASK_PROMPT = """You help build a help assistant built into a Linux Mint computer, used by people who came from \
Windows; many are older or new to computers.

Write {n} messages people might type into the assistant, in {language}, about: {theme}.
Write them the way these people would (one message each, in this order), but never mention who they
are and never add labels, numbers, or brackets — only the words they would type:
{personas}
- Each message is vague or underspecified: it says the situation or the goal, not the exact task
  ("I need to do something about gifts this year", "my pictures need to get to my daughter").
- No greeting from the assistant, no answer — only what the person types.
- Every message must be written in {language}, not in English (unless {language} is English)."""

REPLY_RULES = """The user's message above is vague. Don't start any task yet — the user is the pilot. Reply with \
the answer tool. The text, in the user's language:
1. One short sentence saying what you understood ("It sounds like you want to …").
2. Two to four numbered options, each on its own line starting with "1.", "2.", "3.": concrete ways \
you, the helper built into this computer, can help — \
for example looking up how to do it, opening a program, making a list or a table, checking something \
on the computer. Use these program names exactly where they fit: {names}.
{scope}3. End with one question the user answers themselves ("Which would you like?", or the one detail \
you need) — never offer to choose for them.
Short, simple sentences. No terminal commands. Write the whole text in {language}. {native}"""

# The same instruction in the target language holds the teacher better than an English one alone.
NATIVE = {"en": "", "es": "Escribe toda la respuesta en español.", "pt": "Escreva toda a resposta em português do Brasil.",
          "fr": "Écris toute la réponse en français.", "de": "Schreib die ganze Antwort auf Deutsch.",
          "ja": "返答はすべて日本語で書いてください。"}

SCOPE = ("   If (and only if) they also want {out}, say honestly in one sentence that this isn't something you do, and "
         "that the web or a bigger model can help with it if they connect one — then keep your options "
         "to what you can do.\n")


ASKS = ("\nReply as JSON: asks_out_of_scope = true if the message asks for {out}, else false; text = your "
        "reply.")


def checks(lang: str, text: str) -> list[str]:
    fails = []
    if lang not in R.language_candidates(text):
        fails.append(f"language {R.language(text)}")
    if len(R.STEP.findall(text)) < 2:
        fails.append("fewer than 2 numbered options")
    if len(R.STEP.findall(text)) > 5:
        fails.append("more than 5 options")
    if not re.search(r"[?？]\s*$", text.strip()):
        fails.append("doesn't end with a question")
    for pat in T.NO_CMD:
        if re.search(pat, text, re.I):
            fails.append(f"contains /{pat}/")
    if T.mixed_language(text, lang):
        fails.append("a line in another language")
    size = len(text) if lang == "ja" else len(text.split())
    if size > (450 if lang == "ja" else 170):
        fails.append(f"too long ({size})")
    return fails


def example(t, theme, lang, q, seed):
    desc, keys, out = theme
    names = ", ".join(n for n in (T.label(k, lang) for k in keys) if n)
    system = R.system_prompt({"doc": None})
    # the teacher also says whether the message asks for the out-of-scope part; only then must the reply
    # point to the web / a bigger model (what's stored for training is a plain answer call)
    out_schema = {"type": "object", "additionalProperties": False, "required": ["asks_out_of_scope", "text"],
                  "properties": {"asks_out_of_scope": {"type": "boolean"}, "text": {"type": "string"}}}
    rules = REPLY_RULES.format(names=names, scope=SCOPE.format(out=out) if out else "",
                               language=T.LANG_NAMES[lang], native=NATIVE[lang])
    fails = []
    for attempt, temp in enumerate((0.3, 0.7)):
        raw = t.chat([{"role": "system", "content": system + "\n\n" + rules + ASKS.format(out=out or "-")},
                      {"role": "user", "content": q}],
                     schema=out_schema, temperature=temp, max_tokens=500, seed=seed + attempt)
        got = json.loads(raw)
        text = got["text"]
        fails = checks(lang, text)
        if out and got["asks_out_of_scope"] and not re.search(r"web|ウェブ|インターネット", text, re.I):
            fails.append("out-of-scope part not named")  # it must point to the web/bigger model, not offer it
        if not fails:
            # stored with the plain runtime system prompt: the guide must learn this behaviour, not read it
            call = json.dumps({"tool": "answer", "args": {"text": text}}, ensure_ascii=False)
            return {"messages": [{"role": "system", "content": system}, {"role": "user", "content": q},
                                 {"role": "assistant", "content": call}],
                    "meta": {"kind": "interpretation", "theme": desc, "lang": lang, "attempt": attempt + 1}}, []
    return None, fails


def safe_example(*a):
    try:
        return example(*a)
    except Exception as e:
        return None, [f"error {type(e).__name__}"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True), ap.add_argument("--model", required=True)
    ap.add_argument("--out", required=True), ap.add_argument("--langs")
    ap.add_argument("--per", type=int, default=4), ap.add_argument("--seed", type=int, default=31)
    ap.add_argument("--workers", type=int, default=1), ap.add_argument("--contam", type=float, default=0.5)
    o = ap.parse_args()
    random.seed(o.seed)
    t = T.Teacher(o.url, o.model)
    langs = o.langs.split(",") if o.langs else T.KB.ALL
    evalq = T.eval_questions()
    os.makedirs(o.out, exist_ok=True)
    stats = {"teacher": o.model, "started": dt.datetime.now().isoformat(timespec="seconds"), "per": o.per,
             "workers": o.workers, "questions": 0, "invalid_questions": 0, "contaminated": 0, "duplicates": 0,
             "accepted": 0, "rejected": 0, "reject_reasons": {}, "by_lang": {}}
    kept: list[str] = []
    schema = {"type": "array", "items": {"type": "string", "minLength": 3, "maxLength": 300},
              "minItems": o.per, "maxItems": o.per}
    with open(os.path.join(o.out, "examples.jsonl"), "a", encoding="utf-8") as fx, \
         open(os.path.join(o.out, "rejects.jsonl"), "a", encoding="utf-8") as fr:
        for theme in THEMES:
            for lang in langs:
                seed = random.randrange(1 << 30)
                who = random.Random(seed).sample(T.PERSONAS, o.per)
                prompt = ASK_PROMPT.format(n=o.per, language=T.LANG_NAMES[lang], theme=theme[0],
                                           personas="\n".join(f"{i + 1}. {p}" for i, p in enumerate(who)))
                try:
                    qs = [T.clean_question(x) for x in json.loads(t.chat([{"role": "user", "content": prompt}],
                          schema=schema, temperature=0.7, max_tokens=1200, seed=seed))]
                except Exception as e:
                    fr.write(json.dumps({"theme": theme[0], "lang": lang, "error": repr(e)}) + "\n")
                    fr.flush()
                    continue
                todo = []
                for q in qs:
                    stats["questions"] += 1
                    if not T.valid_question(q, lang):
                        stats["invalid_questions"] += 1
                        continue
                    if max((T.similar(q, e) for e in evalq), default=0) >= o.contam:
                        stats["contaminated"] += 1
                        continue
                    if any(T.similar(q, k) >= 0.8 for k in kept + todo):
                        stats["duplicates"] += 1
                        continue
                    todo.append(q)
                with ThreadPoolExecutor(max_workers=o.workers) as pool:
                    results = list(pool.map(lambda q: safe_example(t, theme, lang, q, seed), todo))
                bl = stats["by_lang"].setdefault(lang, {"accepted": 0, "rejected": 0})
                for q, (ex, fails) in zip(todo, results):
                    if ex:
                        ex["meta"]["teacher"] = o.model
                        fx.write(json.dumps(ex, ensure_ascii=False) + "\n")
                        fx.flush()
                        kept.append(q)
                        stats["accepted"] += 1
                        bl["accepted"] += 1
                    else:
                        stats["rejected"] += 1
                        bl["rejected"] += 1
                        for f in fails:
                            k = re.sub(r"\(\d+\)", "", f).strip()
                            stats["reject_reasons"][k] = stats["reject_reasons"].get(k, 0) + 1
                        fr.write(json.dumps({"theme": theme[0], "lang": lang, "q": q, "reason": fails},
                                            ensure_ascii=False) + "\n")
                        fr.flush()
                print(f"{time.strftime('%H:%M:%S')} {theme[0][:40]:<40} {lang}  accepted {stats['accepted']}  "
                      f"rejected {stats['rejected']}", flush=True)
    stats["finished"] = dt.datetime.now().isoformat(timespec="seconds")
    json.dump(stats, open(os.path.join(o.out, "stats.json"), "w"), indent=1)
    print(json.dumps(stats, indent=1))


if __name__ == "__main__":
    main()
