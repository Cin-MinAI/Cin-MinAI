#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Office corpus (cycle 0, 2026-09-26): the guide with a LibreOffice document shared, one request each.

Why: the session-tuned guide (run HF, 92 % public) lost two office items to stock — with the spreadsheet
already in its context it called read_range / inspect_system instead of answering from it. The sessions
never share a document, so nothing taught "answer from what's shown". This corpus does, and also the edits
(write the new row, put the formula under the column, replace the selection, retitle a slide) and the
cases where reading IS right (the data isn't in the context).

How (same division of labour as the other corpora):
  - the teacher invents each document (theme, titles, labels, sentences) in the user's language — never an
    eval document; numbers are ours;
  - WE decide the right action and compute every argument (which cell, which formula, which paragraphs,
    which slide); the teacher only writes the user's message and free text (an answer, a rewritten sentence);
  - checks: the message carries the literal values the action needs, answers contain the computed fact,
    corrected text stays close to the original, declines refuse, language, decontamination against all evals;
  - some requests with a document open are about the computer (lookup_help) or off-topic (decline), so a
    shared document doesn't turn every message into an office call.
The context format is the product's sidebar format (run_eval.py system_prompt, prompt v2).

    python3 generate.py --url http://127.0.0.1:18091 --model Qwen3-14B-Q4_K_M --out DIR --examples 200
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import importlib.util
import json
import os
import random
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
DATASETS = os.path.join(HERE, "..")
sys.path.insert(0, os.path.join(DATASETS, "transition"))
_argv, sys.argv = sys.argv, [sys.argv[0]]
import generate as T  # noqa: E402  (teacher, labels, cleaning, language checks)
sys.argv = _argv
R = T.R
_spec = importlib.util.spec_from_file_location("sessions_merge", os.path.join(DATASETS, "sessions", "merge.py"))
SM = importlib.util.module_from_spec(_spec)
_saved, sys.argv = sys.argv, [sys.argv[0]]
_spec.loader.exec_module(SM)
sys.argv = _saved
G, I = SM.G, SM.I

LANG_WEIGHTS = {"en": 0.4, "es": 0.12, "pt": 0.12, "fr": 0.12, "de": 0.12, "ja": 0.12}
DOC_WEIGHTS = {"calc": 0.45, "writer": 0.3, "impress": 0.25}
GUARD_SHARE = 0.15  # requests with a document open that aren't about it
# Themes stay clear of the eval's documents (monthly spending, a checkbook, a letter to Maria, a garden club).
THEMES = {
    "calc": ["club members and the yearly dues each one paid", "car trips and the kilometres driven",
             "household bills and their amounts", "shopping items and their prices",
             "books read this year and their number of pages", "a church bazaar: items and how many were sold",
             "grandchildren and the gift budget for each", "walks and the minutes walked",
             "jars of jam made, by fruit", "choir members and the concerts each attended"],
    "writer": ["a note to the neighbours about a street party", "minutes of a small club meeting",
               "instructions for the house-sitter", "a thank-you letter to a nurse",
               "a family history page", "a packing plan for a trip to the coast",
               "a complaint letter to a phone company", "a welcome note for new volunteers"],
    "impress": ["a birthday slideshow for a grandmother", "a talk about safe online banking for a seniors club",
                "a school fundraiser", "a holiday photo evening", "a choir concert programme",
                "a neighbourhood clean-up day"],
}
EVAL_TITLES = {"letter to maria", "checkbook 2027", "our garden club"}
PERSONAS = ["types short and direct", "polite and a little wordy", "all lowercase, no punctuation",
            "uses Windows and Excel/Word words", "a bit unsure, asks carefully", "in a hurry"]


def forced(doc: str | None, tool: str) -> dict:
    return {"anyOf": [s for s in R.schema(doc)["anyOf"] if s["properties"]["tool"]["const"] == tool]}


def teacher_json(t, prompt: str, schema: dict, seed: int, max_tokens: int = 700) -> dict | None:
    try:
        return json.loads(t.chat([{"role": "user", "content": prompt}], schema=schema, temperature=0.8,
                                 max_tokens=max_tokens, seed=seed))
    except Exception:
        return None


S = {"type": "string", "minLength": 1, "maxLength": 80}
LONG = {"type": "string", "minLength": 20, "maxLength": 220}


def arr(item, lo, hi):
    return {"type": "array", "items": item, "minItems": lo, "maxItems": hi}


def obj(**props):
    return {"type": "object", "additionalProperties": False, "required": list(props), "properties": props}


DOC_SCHEMA = {
    "calc": obj(title=S, label_header=S, value_header=S, labels=arr(S, 5, 7), extra_label=S,
                low={"type": "integer", "minimum": 0, "maximum": 100000},
                high={"type": "integer", "minimum": 1, "maximum": 100000}),
    "writer": obj(title=S, headings=arr(S, 2, 4), sentence=LONG, sentence_with_mistakes=LONG),
    "impress": obj(title=S, slides=arr(obj(title=S, lines=arr(S, 2, 3)), 3, 5), new_title=S, new_lines=arr(S, 2, 2)),
}
DOC_PROMPT = {
    "calc": "a small spreadsheet about {theme}: its title, the two column headers (a name column and a number "
            "column), 5 to 7 different names/items for the rows, and one more name that is NOT in the list, and "
            "a realistic lowest and highest whole number for the number column",  # random 3-400 gave "363 concerts"
    "writer": "a short document, {theme}: its title, 2 to 4 section headings, one ordinary sentence from the "
              "text, and the SAME sentence as a hurried person would type it, with 3 or 4 spelling or grammar "
              "mistakes",
    "impress": "a short slide show, {theme}: its title, 3 to 5 slides (each a title and 2-3 short bullet "
               "lines), one new title that could replace a slide title, and two new short bullet lines",
}


def make_doc(t, kind: str, lang: str, rnd: random.Random, seed: int) -> dict | None:
    theme = rnd.choice(THEMES[kind])
    prompt = (f"Invent {DOC_PROMPT[kind].format(theme=theme)}. Everything in {T.LANG_NAMES[lang]}, natural and "
              f"everyday, the way a real person would write it at home. Return JSON. {I.NATIVE[lang]}")
    for k in range(2):
        d = teacher_json(t, prompt, DOC_SCHEMA[kind], seed + k)
        if not d or d["title"].strip().lower() in EVAL_TITLES:
            continue
        text = json.dumps(d, ensure_ascii=False)
        if lang != "en" and lang not in R.language_candidates(re.sub(r'"\w+":', " ", text)):
            continue
        if kind == "calc" and (len({x.lower() for x in d["labels"]}) < len(d["labels"])
                               or d["extra_label"].lower() in {x.lower() for x in d["labels"]}):
            continue
        if kind == "calc" and not 0 <= d["low"] < d["high"] - 4:
            continue
        if kind == "writer" and (T.similar(d["sentence"], d["sentence_with_mistakes"]) < 0.2
                                 or d["sentence"] == d["sentence_with_mistakes"]):
            continue
        d["theme"] = theme
        return d
    return None


# --- contexts in the product's sidebar format --------------------------------------------------------

SHEET1 = {"en": "Sheet1", "es": "Hoja1", "pt": "Planilha1", "fr": "Feuille1", "de": "Tabelle1", "ja": "Sheet1"}


def calc_ctx(d: dict, lang: str, rnd: random.Random, with_data: bool) -> tuple[dict, list]:
    rows = [[lab, rnd.randint(d["low"], d["high"])] for lab in d["labels"]]
    last = len(rows) + 1
    sheet = SHEET1[lang]
    doc = {"type": "calc", "sheets": [sheet], "active": sheet, "selection": "A1"}
    if rnd.random() < 0.5:
        doc["title"] = d["title"]
    ctx = {"document": doc, "used_range": f"A1:B{last}"}
    if with_data:
        ctx["data"] = {"range": f"A1:B{last}", "values": [[d["label_header"], d["value_header"]]] + rows}
    else:  # a long sheet: the sidebar sends only its size
        ctx["used_range"] = f"A1:B{rnd.randrange(60, 400)}"
    return ctx, rows


def writer_ctx(d: dict, rnd: random.Random, selection: str) -> tuple[dict, list]:
    outline, p = [{"level": 1, "text": d["title"], "paragraph": 0}], 1
    for h in d["headings"]:
        outline.append({"level": 2, "text": h, "paragraph": p})
        p += 1 + rnd.randrange(1, 4)
    ctx = {"document": {"type": "writer", "title": d["title"], "paragraphs": p}, "selection": selection,
           "outline": outline}
    return ctx, outline


def impress_ctx(d: dict, with_slides: bool) -> dict:
    slides = [{"slide": 1, "title": d["title"], "body": ""}] + \
             [{"slide": i + 2, "title": s["title"], "body": "\n".join(s["lines"])} for i, s in enumerate(d["slides"])]
    ctx = {"document": {"type": "impress", "slides": len(slides)}}
    if with_slides:
        ctx["slides"] = slides
    return ctx


# --- intents: (what the user asks, the right call, what a free-text part must contain) ------------------

def num_in(text: str, n) -> bool:
    flat = re.sub(r"(?<=\d)[ ,.  '](?=\d{3}\b)", "", text)
    return re.search(rf"(?<![\d.,]){n}(?![\d])", flat) is not None


def plan(kind: str, d: dict, lang: str, rnd: random.Random) -> dict:
    """The intent, context, the user-message instruction, literals it must contain, and the call (or the
    tool + check for a teacher-written part)."""
    if kind == "calc":
        intent = rnd.choice(["ask_max", "ask_min", "ask_total", "ask_count", "ask_value", "ask_value",
                             "add_row", "add_row", "formula_sum", "formula_avg", "read_nodata"])
        ctx, rows = calc_ctx(d, lang, rnd, intent != "read_nodata")
        last, lh, vh = len(rows) + 1, d["label_header"], d["value_header"]
        top = max(rows, key=lambda r: r[1])
        low = min(rows, key=lambda r: r[1])
        if intent in ("ask_max", "ask_min") and sorted(r[1] for r in rows).count((top if intent == "ask_max" else low)[1]) > 1:
            intent = "ask_total"  # a tie has no single answer
        if intent == "ask_max":
            return dict(intent=intent, ctx=ctx, ask=f"a question: which {lh} has the highest {vh}", must=[],
                        tool="answer", check=lambda x: top[0].lower() in x.lower() or num_in(x, top[1]))
        if intent == "ask_min":
            return dict(intent=intent, ctx=ctx, ask=f"a question: which {lh} has the lowest {vh}", must=[],
                        tool="answer", check=lambda x: low[0].lower() in x.lower() or num_in(x, low[1]))
        if intent == "ask_total":
            tot = sum(r[1] for r in rows)
            return dict(intent=intent, ctx=ctx, ask=f"a question: what the {vh} add up to in total (they only "
                        "want to know; they don't ask to put anything into the sheet)", must=[],
                        tool="answer", check=lambda x: num_in(x, tot))
        if intent == "ask_count":
            return dict(intent=intent, ctx=ctx, ask=f"a question: how many {lh} are in the list", must=[],
                        tool="answer", check=lambda x: num_in(x, len(rows)) or bool(re.search(
                            ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight"][len(rows)], x, re.I)))
        if intent == "ask_value":
            r = rnd.choice(rows)
            return dict(intent=intent, ctx=ctx, ask=f"a question: what the {vh} is for \"{r[0]}\"", must=[r[0]],
                        tool="answer", check=lambda x: num_in(x, r[1]))
        if intent == "add_row":
            v = rnd.randint(d["low"], d["high"])
            return dict(intent=intent, ctx=ctx, ask=f"a request to add \"{d['extra_label']}\" with {v} to the list",
                        must=[d["extra_label"], str(v)],
                        call={"tool": "write_range", "args": {"range": f"A{last + 1}:B{last + 1}",
                                                              "cells": [[d["extra_label"], str(v)]]}})
        if intent in ("formula_sum", "formula_avg"):
            f = "SUM" if intent == "formula_sum" else "AVERAGE"
            what = "the total" if f == "SUM" else "the average"
            return dict(intent=intent, ctx=ctx, ask=f"a request to put {what} of the {vh} into the sheet, right under "
                        "the numbers, so it updates by itself", must=[],
                        call={"tool": "set_formula", "args": {"cell": f"B{last + 1}", "formula": f"={f}(B2:B{last})"}})
        return dict(intent=intent, ctx=ctx, ask=f"a question about the {vh} in this long list (for example which "
                    f"{lh} has the most, or the total)", must=[],
                    call={"tool": "read_range", "args": {"range": ctx["used_range"]}})
    if kind == "writer":
        intent = rnd.choice(["fix", "fix", "rewrite", "ask_title", "ask_paragraphs", "show_section", "show_section"])
        sel = d["sentence_with_mistakes"] if intent == "fix" else d["sentence"]
        ctx, outline = writer_ctx(d, rnd, sel)
        if intent == "fix":
            return dict(intent=intent, ctx=ctx, ask="a request to fix the mistakes in the selected text", must=[],
                        tool="replace_selection",
                        check=lambda x: x.strip() != sel.strip() and T.similar(x, d["sentence"]) >= 0.35)
        if intent == "rewrite":
            how = rnd.choice(["more formal", "shorter", "friendlier", "simpler"])
            return dict(intent=intent, ctx=ctx, ask=f"a request to make the selected sentence {how}", must=[],
                        tool="replace_selection", how=how,
                        check=lambda x: x.strip() != sel.strip() and len(x) < 3 * len(sel) + 40)
        if intent == "ask_title":
            return dict(intent=intent, ctx=ctx, ask="a question: what this document is called", must=[],
                        tool="answer", check=lambda x: d["title"].lower() in x.lower())
        if intent == "ask_paragraphs":
            n = ctx["document"]["paragraphs"]
            return dict(intent=intent, ctx=ctx, ask="a question: how many paragraphs the document has", must=[],
                        tool="answer", check=lambda x: num_in(x, n))
        k = rnd.randrange(1, len(outline))
        start = outline[k]["paragraph"] + 1
        end = outline[k + 1]["paragraph"] if k + 1 < len(outline) else ctx["document"]["paragraphs"]
        return dict(intent=intent, ctx=ctx, ask=f"a request to see what is written under the heading \"{outline[k]['text']}\"",
                    must=[outline[k]["text"]],
                    call={"tool": "get_paragraphs", "args": {"start": start, "count": end - start}})
    intent = rnd.choice(["set_title", "set_body", "ask_slide", "ask_slide", "ask_count", "read_noslides"])
    ctx = impress_ctx(d, intent != "read_noslides")
    n_slides = ctx["document"]["slides"]
    n = rnd.randrange(2, n_slides + 1)
    lines = d["slides"][n - 2]["lines"]
    if intent == "set_title":
        return dict(intent=intent, ctx=ctx, ask=f"a request to give slide {n} the title \"{d['new_title']}\"",
                    must=[d["new_title"], str(n)], call={"tool": "set_slide_text", "args": {"slide": n, "title": d["new_title"]}})
    if intent == "set_body":
        a, b = d["new_lines"]
        return dict(intent=intent, ctx=ctx, ask=f"a request to replace the points on slide {n} with these two: "
                    f"\"{a}\" and \"{b}\"", must=[a, b, str(n)],
                    call={"tool": "set_slide_text", "args": {"slide": n, "body": f"{a}\n{b}"}})
    if intent == "ask_count":
        return dict(intent=intent, ctx=ctx, ask="a question: how many slides there are", must=[],
                    tool="answer", check=lambda x: num_in(x, n_slides))
    if intent == "ask_slide":
        return dict(intent=intent, ctx=ctx, ask=f"a question: what is on slide {n}", must=[str(n)], tool="answer",
                    check=lambda x: any(l.lower()[:12] in x.lower() for l in lines))
    return dict(intent=intent, ctx=ctx, ask=f"a question: what is on slide {n}", must=[str(n)],
                call={"tool": "slide_text", "args": {"slide": n}})


def guard_plan(kind: str, d: dict, lang: str, rnd: random.Random) -> dict:
    ctx = {"calc": lambda: calc_ctx(d, lang, rnd, True)[0], "writer": lambda: writer_ctx(d, rnd, d["sentence"])[0],
           "impress": lambda: impress_ctx(d, True)}[kind]()
    if rnd.random() < 0.6:
        topic = rnd.choice(G.TRANSITION)
        return dict(intent="guard_howto", ctx=ctx, ask=f"a question about the computer, not about this document: "
                    f"{G.KB[topic]['windows']}", must=[], tool="lookup_help", check=lambda x: True)
    return dict(intent="guard_offtopic", ctx=ctx, ask=f"a message about {rnd.choice(G.OFF_TOPIC)} — nothing to do "
                "with the computer or the document", must=[], tool="decline", check=None)


def user_message(t, lang: str, kind: str, d: dict, p: dict, seed: int, evalq: list[str]) -> str | None:
    must = "".join(f'\n- it must contain exactly: {m}' for m in p["must"] if not m.isdigit()) + \
           "".join(f"\n- it must contain the number {m}" for m in p["must"] if m.isdigit())
    prompt = (f"Someone has a LibreOffice {kind} document open ({d['title']}: {d['theme']}) and types a message "
              f"to the computer's built-in assistant. The person {rnd_persona(seed)}.\n\nWrite their message: "
              f"{p['ask']}.{must}\nThe assistant already sees the document, so they don't describe it. Only the words they type — no labels, no quotes around the whole message. "
              f"Write it in {T.LANG_NAMES[lang]}. {I.NATIVE[lang]}")
    schema = obj(message={"type": "string", "minLength": 3, "maxLength": 240})
    for k in range(2):
        r = teacher_json(t, prompt, schema, seed + k, 250)
        if not r:
            continue
        q = T.clean_question(r["message"])
        if not T.valid_question(q, lang) and not (len(q) >= 6 and lang in R.language_candidates(q)):
            continue
        if not all((num_in(q, m) if m.isdigit() else m.lower() in q.lower()) for m in p["must"]):
            continue
        if max((T.similar(q, e) for e in evalq), default=0) >= 0.5:
            continue
        return q
    return None


def rnd_persona(seed: int) -> str:
    return PERSONAS[seed % len(PERSONAS)]


def teacher_call(t, doc: str, lang: str, p: dict, system: str, q: str, seed: int) -> dict | None:
    extra = ""
    if p["tool"] == "replace_selection":
        extra = (f"\n\n(Generation note: the replacement text must be in {T.LANG_NAMES[lang]}"
                 + (f" and {p['how']}" if p.get("how") else ", with the mistakes corrected and nothing else changed")
                 + ".)")
    for k in range(2):
        try:
            raw = t.chat([{"role": "system", "content": system + extra}, {"role": "user", "content": q}],
                         schema=forced(doc, p["tool"]), temperature=0.3, max_tokens=400, seed=seed + 31 * k)
            call = json.loads(raw)
        except Exception:
            continue
        text = call["args"].get("text") or call["args"].get("query") or ""
        if p["tool"] in ("answer", "replace_selection", "decline"):
            if lang not in R.language_candidates(text) and R.language(text) != "?" or T.mixed_language(text, lang):
                continue
            if any(re.search(w, text, re.I) for w in G.WRONG_ANY):
                continue
        if p["tool"] == "decline" and (not re.search(SM.REFUSAL[lang], text, re.I) or R.STEP.findall(text)
                                       or len(text.split()) > 70):
            continue
        if p["check"] and not p["check"](text):
            continue
        return call
    return None


def example(t, eid: str, lang: str, rnd: random.Random, evalq: list[str], why: collections.Counter) -> dict | None:
    kind = rnd.choices(list(DOC_WEIGHTS), weights=list(DOC_WEIGHTS.values()))[0]
    seed = rnd.randrange(1 << 30)
    d = make_doc(t, kind, lang, rnd, seed)
    if d is None:
        why["document"] += 1
        return None
    p = (guard_plan if rnd.random() < GUARD_SHARE else plan)(kind, d, lang, rnd)
    system = R.system_prompt({"doc": kind, "ctx": p["ctx"]})
    q = user_message(t, lang, kind, d, p, seed + 1, evalq)
    if q is None:
        why[f"user message ({p['intent']})"] += 1
        return None
    call = p.get("call") or teacher_call(t, kind, lang, p, system, q, seed + 2)
    if call is None:
        why[f"assistant ({p['intent']})"] += 1
        return None
    return {"messages": [{"role": "system", "content": system}, {"role": "user", "content": q},
                         {"role": "assistant", "content": json.dumps(call, ensure_ascii=False)}],
            "meta": {"kind": "office", "id": eid, "lang": lang, "doc": kind, "intent": p["intent"],
                     "theme": d["theme"], "max_eval_similarity": round(max((T.similar(q, e) for e in evalq), default=0), 2)}}


def eval_questions() -> list[str]:
    evalq = T.eval_questions()
    spec = importlib.util.spec_from_file_location("v", os.path.join(T.ROOT, "training", "eval", "guide-interp", "tasks.py"))
    v = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(v)
    return evalq + [q for task in v.TASKS for q in task["q"].values()]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True), ap.add_argument("--model", required=True)
    ap.add_argument("--out", required=True), ap.add_argument("--examples", type=int, default=200)
    ap.add_argument("--seed", type=int, default=91)
    o = ap.parse_args()
    rnd = random.Random(o.seed)
    t = T.Teacher(o.url, o.model)
    evalq = eval_questions()
    os.makedirs(o.out, exist_ok=True)
    why, kept = collections.Counter(), collections.Counter()
    started = dt.datetime.now().isoformat(timespec="seconds")
    with open(os.path.join(o.out, "examples.jsonl"), "a", encoding="utf-8") as f:
        for k in range(o.examples):
            lang = rnd.choices(list(LANG_WEIGHTS), weights=list(LANG_WEIGHTS.values()))[0]
            e = example(t, f"o{o.seed}-{k:04d}", lang, rnd, evalq, why)
            if e:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
                f.flush()
                kept[(e["meta"]["doc"], e["meta"]["intent"])] += 1
            print(f"{time.strftime('%H:%M:%S')} {k + 1}/{o.examples} {lang}  kept {sum(kept.values())}", flush=True)
    stats = {"teacher": o.model, "started": started, "finished": dt.datetime.now().isoformat(timespec="seconds"),
             "seed": o.seed, "kept": sum(kept.values()), "dropped": dict(why),
             "by_intent": {f"{a}/{b}": n for (a, b), n in sorted(kept.items())}}
    json.dump(stats, open(os.path.join(o.out, "stats.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print(json.dumps(stats, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
