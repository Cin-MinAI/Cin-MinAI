#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Guide eval runner (PLAN §3 guide track, SPEC §10.6). Talks to a running llama-server
(OpenAI-compatible); stdlib only.

    python3 run_eval.py --dry-run                         # check tasks + labels, count items
    python3 run_eval.py --url http://127.0.0.1:8081 [--model NAME] [--api-key-env VAR]
    python3 run_eval.py --config ~/.config/cinminai/config.toml     # url/api_key/model from [inference]
      options: --only T01,D02  --lang ja  --out FILE  --sampling '{"dry_multiplier":0.8,...}'  -v

Stage A: one schema-constrained call — which tool, with which arguments (scored against `expect`).
Stage B: the fixed help card / system result goes back, the model writes the reply in plain text,
scored on language, the Mint names the user sees, required facts, numbered steps, length, and no
terminal commands. See README.md.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import statistics
import sys
import time
import tomllib
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))
import importlib.util  # noqa: E402
from cin_minai.daemon.repetition import find_repeat, repair  # noqa: E402
from cin_minai.daemon.intent import narrow  # noqa: E402  (the tools a request may use: as the daemon does)

TASKS_FILE = os.path.join(HERE, "tasks.py")
if "--tasks" in sys.argv:  # e.g. the hidden eval (training/eval/guide-hidden/tasks.py)
    TASKS_FILE = os.path.abspath(sys.argv[sys.argv.index("--tasks") + 1])
_spec = importlib.util.spec_from_file_location("guide_tasks", TASKS_FILE)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
TASKS, BRANDS = _mod.TASKS, _mod.BRANDS

with open(os.path.join(HERE, "labels.json"), encoding="utf-8") as _f:
    _L = json.load(_f)
LABELS = _L["labels"]       # programs and settings pages (open_app can open these)
UI = _L.get("ui", {})      # names inside programs: menus, buttons ({ui_…} in cards)
LANGS = ["en", "es", "pt", "fr", "de", "ja"]
SAMPLING_KEYS = {"temperature", "top_p", "top_k", "min_p", "repeat_penalty", "dry_multiplier", "dry_base",
                 "dry_allowed_length", "dry_penalty_last_n"}


def parse_sampling(value: str) -> dict:
    """Parse a llama.cpp sampling override. It is sent only for unconstrained Stage B replies."""
    try:
        sampling = json.loads(value)
    except json.JSONDecodeError as e:
        raise argparse.ArgumentTypeError(f"invalid JSON: {e.msg}") from e
    if not isinstance(sampling, dict):
        raise argparse.ArgumentTypeError("must be a JSON object")
    unknown = set(sampling) - SAMPLING_KEYS
    if unknown:
        raise argparse.ArgumentTypeError("unknown sampling key(s): " + ", ".join(sorted(unknown)))
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in sampling.values()):
        raise argparse.ArgumentTypeError("sampling values must be numbers")
    return sampling

# --- tools ---------------------------------------------------------------------------------------

S, I = {"type": "string"}, {"type": "integer", "minimum": 0}
TOPICS = ["overview", "storage", "network", "updates", "printers", "sound", "display", "battery", "drivers", "account",
          "memory", "temperature", "time"]
GUIDE_TOOLS = {
    "lookup_help": ({"query": S}, "search the built-in help about this computer: Windows -> Linux Mint, how-to "
                                  "lessons, its programs and settings. Use it before explaining how to do something."),
    "open_app": ({"app": {"enum": sorted(LABELS)}}, "open a program or settings page for the user"),
    "inspect_system": ({"topic": {"enum": TOPICS}}, "read facts about this computer (changes nothing): "
                                                    + ", ".join(TOPICS)),
    "request_install": ({"package": S}, "install a program (package name); the user confirms with their password"),
    "answer": ({"text": S}, "reply directly, only when no tool is needed"),
    "decline": ({"text": S}, "politely say this is outside what you help with, and what you do help with"),
}
# Same toolkit as spikes/libreoffice/assist.py (kept in sync by hand; that module needs a live config).
OFFICE_TOOLS = {
    "writer": {
        "doc_info": ({}, "type, title, number of paragraphs and characters"),
        "get_selection": ({}, "the selected text"),
        "outline": ({}, "the headings (level, text, paragraph index)"),
        "get_paragraphs": ({"start": I, "count": I}, "paragraphs by 0-based index"),
        "replace_selection": ({"text": S}, "EDIT: replace the selected text with new text"),
    },
    "calc": {
        "doc_info": ({}, "sheets, active sheet, selected range"),
        "get_selection": ({}, "the selected cells: values and formulas"),
        "read_range": ({"range": S}, "values/formulas of a range like A1:C10 or Sheet1.A1:C10"),
        "used_range": ({}, "the used area of the active sheet"),
        "set_formula": ({"cell": S, "formula": S}, "EDIT: put one formula (e.g. =AVERAGE(B2:B7)) into one cell"),
        "write_range": ({"range": S, "cells": {"type": "array", "items": {"type": "array", "items": S}}},
                        "EDIT: fill a range; cells is a list of rows, each a list of cell texts (text, a number, "
                        "or a formula starting with =); rows x columns must match the range"),
    },
    "impress": {
        "doc_info": ({}, "number of slides"),
        "slide_text": ({"slide": {"type": "integer", "minimum": 1}}, "title and body text of a slide (1-based)"),
        "set_slide_text": ({"slide": {"type": "integer", "minimum": 1}, "title": S, "body": S},
                           "EDIT: set the title and/or body of a slide; body lines are bullets separated by \\n; "
                           "give only the parts to change"),
    },
}
OPTIONAL = {("impress", "set_slide_text"): {"title", "body"}}


# Prompt v2.1 (2026-09-30, D53): v2 plus one tool, make a new spreadsheet. Only the tool list changes; A/B
# against v2 before the product adopts it (D33).
CREATE_TOOLS = {
    "make_spreadsheet": ({"title": S, "columns": {"type": "array", "items": S, "minItems": 1, "maxItems": 12},
                          "rows": {"type": "array", "items": {"type": "array", "items": S}},
                          "total": {"enum": ["none", "sum", "by_month"]}},
                         "make a new spreadsheet file in Documents and open it: a title, the column names, example "
                         "rows (dates as YYYY-MM-DD; may be empty), and total: none, sum (a total of the amount "
                         "column) or by_month (a total for each month, from a date column)"),
}
OPTIONAL[(None, "make_spreadsheet")] = {"rows"}


# Prompt v2.4 (2026-10-07, D88): v2.3 plus one tool — the guide writes the email itself and opens it as a draft in the
# person's mail program (hands-on round 2: asked to write a letter in Thunderbird, it gave steps with a made-up
# address). No address field: the person adds it and clicks Send; nothing is sent by the assistant.
EMAIL_TOOLS = {
    "compose_email": ({"subject": S, "body": S},
                      "when the user asks for an email (or a letter they want to send by email): write it and open it "
                      "as a draft in their mail program: the subject and the whole text, ready to send (they add the "
                      "address and click Send themselves). A letter to print or keep: write it with answer"),
}


def tools_for(doc: str | None) -> dict:
    # appended last, the way the office tools follow answer/decline: the v2 list itself stays as trained
    extra = {}
    if PROMPT in ("v2.1", "v2.2", "v2.3", "v2.4") and not doc:
        extra = {**CREATE_TOOLS, **(WEB_TOOLS if PROMPT in ("v2.2", "v2.3", "v2.4") else {}),
                 **(EMAIL_TOOLS if PROMPT == "v2.4" else {})}
    return {**GUIDE_TOOLS, **(OFFICE_TOOLS[doc] if doc else {}), **extra}


def schema(doc: str | None) -> dict:
    options = []
    for name, (props, _) in tools_for(doc).items():
        required = [k for k in props if k not in OPTIONAL.get((doc, name), set())]
        options.append({"type": "object", "additionalProperties": False, "required": ["tool", "args"],
                        "properties": {"tool": {"const": name},
                                       "args": {"type": "object", "additionalProperties": False,
                                                "properties": props, "required": required}}})
    return {"anyOf": options}


SYSTEM = """You are the helper built into this computer (Cin-MinAI, based on Linux Mint). The person you \
help most likely came from Windows and may be new to computers.

Reply with exactly one JSON object {{"tool": ..., "args": {{...}}}}.
- To explain how to do something on this computer, call lookup_help first; never guess the names of \
programs, menus or settings.
- To check something about this computer, call inspect_system. To open a program or settings page, \
call open_app.
- You help with this computer, its programs and the user's documents. For anything else (history, \
school subjects, health, money, news, writing texts for people) use decline, kindly, in one or two \
sentences.
- Write every text in the language the user writes in. Use the names of programs and settings exactly as the help or the tools give them. Short, simple sentences; mouse steps first, as a numbered list when there is more than one step; no terminal commands.
{document}
Tools:
{tools}"""

STYLE = "Now write your reply to the user as plain text (not JSON), following the rules above."

# Prompt v2 (training/guide/README.md, phase 1): aimed at the failures measured in cycle 0, written as
# general rules (no eval task is quoted). v1 above stays as the recorded baseline.
SYSTEM_V2 = """You are the helper built into this computer (Cin-MinAI, based on Linux Mint). The person you \
help most likely came from Windows and may be new to computers. Be patient and kind.

Reply with exactly one JSON object {{"tool": ..., "args": {{...}}}}. Choose like this:
1. About this computer, its programs, settings, files, documents, or staying safe on it — including \
passwords the computer asks for, privacy, and suspicious emails, calls, pop-ups or websites (scams): \
this is your job. If it's a how-to or a "where is…" question, call lookup_help first; never guess \
the names of programs, menus or settings. To check this computer, call inspect_system. To open \
something, call open_app. To install a program, call request_install.
2. Anything else — history, politics, school subjects, maths, health, law, money advice, news, \
weather, sports, recipes, or writing texts for people: call decline directly (no lookup), kindly, \
in one or two sentences, and say what you can help with.
3. If you're unsure whether it's about the computer, it probably is: help.

Every text you write:
- is in the same language as the user's message, even when a help card or tool result is in English;
- uses the names of programs, settings and menu items exactly as the help or the tools give them;
- uses short, simple sentences; when there are two or more steps, writes them as a numbered list \
("1. … 2. … 3. …"), one mouse action per step;
- never contains terminal commands.
{document}
Tools:
{tools}"""

STYLE_V2 = ("Now write your reply to the user as plain text (not JSON), in the language of their message: "
            "one short sentence, then numbered steps if there are two or more, using the names exactly as "
            "they appear above.")
STYLE_V23 = ("Now write your reply to the user as plain text (not JSON), in the language of their message: "
             "one short sentence, then numbered steps if there are two or more, using the names exactly as "
             "they appear above. Keep the help's everyday comparison and every caution it gives.")
# Prompt v2.2 (2026-10-01, D54 + D55): v2.1 with rule 2 rewritten — knowledge questions go to web_search (the
# user sees the query and clicks Search before anything is sent), writing is in scope, advice that decides for
# the person stays declined. Only rule 2 changes (asserted); one tool more.
_RULE2_V2 = ("2. Anything else — history, politics, school subjects, maths, health, law, money advice, news, weather, "
             "sports, recipes, or writing texts for people: call decline directly (no lookup), kindly, in one or two "
             "sentences, and say what you can help with.")
_RULE2_V22 = ("2. Questions about the world — history, politics, school subjects, maths, science, recipes, news, "
              "weather, sports: call web_search with a short search query in the user's language (nothing is sent "
              "until the user agrees; you answer from the pages they let you fetch). Writing — stories, poems, "
              "letters, essays, speeches: help, and write it with answer. Advice that decides for the person — "
              "health and medicine, law, money and investments: call decline, kindly, in one or two sentences, and "
              "say what you can help with.")
assert SYSTEM_V2.count(_RULE2_V2) == 1
SYSTEM_V22 = SYSTEM_V2.replace(_RULE2_V2, _RULE2_V22)
# Prompt v2.3 (2026-10-06, D84): v2.2 with two changes, measured on D84 batch 1 — "what is…" about this computer or
# an idea behind it (a VPN, the keyring) goes to the help, not the web; and the reply keeps the help's explanation,
# its everyday comparison and its cautions (v2.2's "one short sentence, then steps" dropped them). Three wordings of
# the reply instruction were measured; longer ones made the 4B write prose without numbered steps (public 138), so
# it is v2.2's sentence plus one clause (public 144/157 vs 141, D84 30/33 vs 23).
_RULE1_V22 = 'If it\'s a how-to or a "where is…" question, call lookup_help first'
_RULE1_V23 = ('If it\'s a how-to, a "where is…", or a "what is…" question about something on this computer or an '
              'idea behind it (a VPN, a firewall, the keyring, drivers, backups…), call lookup_help first')
assert SYSTEM_V22.count(_RULE1_V22) == 1
SYSTEM_V23 = SYSTEM_V22.replace(_RULE1_V22, _RULE1_V23)
WEB_TOOLS = {
    "web_search": ({"query": S}, "search the web for a question about the world: a short search query in the user's "
                                 "language (the user sees it and agrees before anything is sent)"),
}
PROMPT = "v1"


def style() -> str:
    return STYLE_V23 if PROMPT in ("v2.3", "v2.4") else STYLE_V2 if PROMPT.startswith("v2") else STYLE


HELP = None  # --help-json: the daemon's help index (src/cin_minai/daemon/helpcards.py)


def system_prompt(task: dict) -> str:
    doc = task.get("doc")
    tools = "\n".join(f"- {n}: {d}" for n, (_, d) in tools_for(doc).items())
    ctx = task.get("ctx")
    if doc and PROMPT.startswith("v2") and "data" in ctx:
        # integration fix: the sidebar tells the model where new rows go (SPEC §7.11) instead of the
        # model working it out from the used range
        last = int(re.search(r"(\d+)$", ctx["used_range"]).group(1))
        ctx = {**ctx, "next_empty_row": last + 1}
    if doc:
        document = (f"\nThe user shared a LibreOffice {doc} document with you. Read tools run immediately; "
                    "EDIT tools are shown to the user as a preview and only happen if they approve. Prefer "
                    "doing the edit over describing it; use answer when the context already has what's "
                    f"needed.\nDocument context:\n{json.dumps(ctx, ensure_ascii=False)}\n")
        if PROMPT.startswith("v2"):
            document += ("When the data is in the context above, answer from it or edit directly; don't look "
                         "it up or read it again. New entries go in next_empty_row.\n")
    else:
        document = "\nNo document is shared.\n"
    system = (SYSTEM_V23 if PROMPT in ("v2.3", "v2.4") and not doc else SYSTEM_V22 if PROMPT == "v2.2" and not doc
              else SYSTEM_V2 if PROMPT.startswith("v2") else SYSTEM)
    return system.format(document=document, tools=tools)


# --- items: one per (task, language) --------------------------------------------------------------

def label(key: str, lang: str) -> str:
    if key in UI:  # no translation in the catalogue: the program shows the English, so that's the name
        return UI[key].get(lang) or UI[key]["en"]
    row = LABELS[key]
    if lang in row:
        return row[lang]
    if key in BRANDS:
        return row["en"]
    raise KeyError(f"no {lang} label for {key}")


def resolve(text: str, lang: str) -> str:
    return re.sub(r"\{(\w+)\}", lambda m: label(m.group(1), lang), text)


def items() -> list[dict]:
    out = []
    for t in TASKS:
        for lang, q in t["q"].items():
            it = {**t, "lang": lang, "q": q}
            if "card" in t:
                it["card"] = resolve(t["card"], lang)
            if "result" in t:
                it["result"] = json.loads(resolve(json.dumps(t["result"], ensure_ascii=False), lang))
            it["must"] = [[resolve(a, lang) for a in group] for group in t.get("must", [])]
            if PROMPT in ("v2.2", "v2.3", "v2.4") and "v22" in t:
                # D54/D55: no longer a decline; the action is checked, the decline's reply checks don't apply
                it.update(expect=t["v22"]["expect"], must=[], must_not=[], b_skip=True)
            out.append(it)
    return out


# --- model calls ---------------------------------------------------------------------------------

class Server:
    def __init__(self, url: str, key: str, model: str, sampling: dict | None = None):
        self.url, self.key, self.model, self.sampling = url.rstrip("/"), key, model, sampling or {}

    def chat(self, messages: list, schema_: dict | None, max_tokens: int) -> tuple[str, float]:
        body = {"model": self.model, "temperature": 0, "max_tokens": max_tokens, "messages": messages,
                "chat_template_kwargs": {"enable_thinking": False}}
        if schema_ is not None:
            body["response_format"] = {"type": "json_schema", "json_schema": {"name": "call", "schema": schema_}}
        else:
            body.update(self.sampling)
        req = urllib.request.Request(self.url + "/v1/chat/completions", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json",
                                              "Authorization": f"Bearer {self.key}"})
        t0 = time.monotonic()
        with urllib.request.urlopen(req, timeout=600) as r:
            out = json.load(r)
        text = out["choices"][0]["message"]["content"] or ""
        return re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip(), time.monotonic() - t0


# --- scoring -------------------------------------------------------------------------------------

def arg_ok(rule, value) -> bool:
    if isinstance(rule, list):
        return value in rule
    if isinstance(rule, str) and rule.startswith("~"):
        return value is not None and re.search(rule[1:], str(value), re.I) is not None
    return value == rule


def stage_a(call: dict, expect: list) -> bool:
    for e in expect:
        if call.get("tool") == e["tool"] and all(arg_ok(r, call.get("args", {}).get(k))
                                                 for k, r in e.get("args", {}).items()):
            return True
    return False


STOP = {  # distinctive function words; words shared between two of these languages are left out
    # (2026-09-25: "do"/"das"/"e"/"o" removed from pt — English "do", German "das" — and the common
    # question words added, found while filtering the transition corpus's short questions)
    "en": ("the and you your to is it this that click open with for of on in how my what where can "
           "please need").split(),
    "es": ("el los las lo y con tu tus sus usted puede puedo haga clic está del una por pero también muy hay "
           "son al ayudarte hacer mi qué cómo dónde hago quiero necesito ordenador").split(),
    "pt": ("você não pode posso clique está uma também muito da dos em ao pelo os com seu sua "
           "são ou mas ajudar fazer isso meu minha faço pra onde quero preciso").split(),
    "fr": ("le les vous pour sur cliquez est une des dans pas avec votre et du au je mon ma comment où "
           "faire veux ordinateur").split(),
    "de": ("der die das und sie ist zu auf klicken mit den ein eine nicht ihr ihre im ich wie wo mein meine "
           "kann mach mache").split(),
}


def language_scores(text: str) -> dict:
    """Function-word counts per language ({"ja": 1} for Japanese script)."""
    letters = [c for c in text if c.isalpha()]
    if letters and sum("぀" <= c <= "ヿ" or "一" <= c <= "鿿" for c in letters) / len(letters) > 0.2:
        return {"ja": 1}
    words = re.findall(r"[a-zà-ÿ]+", text.lower())
    scores = {lang: sum(w in set(sw) for w in words) for lang, sw in STOP.items()}
    scores["es"] += 3 * sum(c in "ñ¿¡" for c in text)   # letters only one of the two uses
    scores["pt"] += 3 * sum(c in "ãõ" for c in text)
    return scores


def language_candidates(text: str) -> set:
    """The languages tied for the best score ({"?"} if no evidence at all)."""
    scores = language_scores(text)
    top = max(scores.values())
    return {"?"} if not top else {k for k, v in scores.items() if v == top}


def language(text: str) -> str:
    c = language_candidates(text)
    return next(iter(c)) if len(c) == 1 else "?"  # a tie: don't guess


STEP = re.compile(r"^\s*(?:\*\*)?(?:[0-9０-９]+[.)．、:]|[①-⑩])", re.M)


def stage_b(it: dict, text: str) -> list[str]:
    fails = []
    if it["lang"] not in language_candidates(text):  # a tie that includes the right language passes
        fails.append(f"language {language(text)}")
    low = text.lower()
    for group in it["must"]:
        if not any(re.search(a[1:], text, re.I) if a.startswith("~") else a.lower() in low for a in group):
            fails.append("missing " + " | ".join(group))
    for pat in it.get("must_not", []):
        if re.search(pat, text, re.I):
            fails.append(f"contains /{pat}/")
    if it.get("steps") and len(STEP.findall(text)) < it["steps"]:
        fails.append("no numbered steps")
    size = len(text) if it["lang"] == "ja" else len(text.split())
    if size > (500 if it["lang"] == "ja" else 200):
        fails.append(f"too long ({size})")
    loop = repeated(text, names=names_for(it["lang"]))
    if loop:
        fails.append(f"repeats {loop!r}")
    return fails


def repeated(text: str, length: int = 24, times: int = 3, names=()) -> str:
    """A stretch of `length` characters that occurs `times` times or more, not overlapping: a reply stuck in a loop.
    Codex (2026-10-07) found looping replies that passed because they stayed under the length limit. Mint's own names
    are taken out first: "o Gerenciador de Aplicativos" three times is a normal Portuguese answer."""
    match = find_repeat(text, length=length, times=times, names=names)
    return match.piece if match else ""


def names_for(lang: str) -> set[str]:
    return {row.get(lang) or row.get("en", "") for row in list(LABELS.values()) + list(UI.values())}


def run_item(srv: Server, it: dict, loop_detector: bool = False) -> dict:
    messages = [{"role": "system", "content": system_prompt(it)}, {"role": "user", "content": it["q"]}]
    sch = schema(it.get("doc"))
    raw, ta = srv.chat(messages, sch if it.get("doc") else narrow(sch, it["q"]), 700)
    try:
        call = json.loads(raw)
    except json.JSONDecodeError:
        call = {"tool": "?", "args": {}, "raw": raw[:300]}
    rec = {"id": it["id"], "cat": it["cat"], "lang": it["lang"], "prompt": PROMPT, "call": call, "a_ok": stage_a(call, it["expect"]),
           "t_a": round(ta, 2), "b_ok": None, "reply": None, "b_fails": []}
    tool, args = call.get("tool"), call.get("args", {})
    reply = None
    if tool in ("answer", "decline"):
        reply = args.get("text", "")
    elif tool == "lookup_help" and HELP is not None and ("card" in it or it["cat"] == "terminal"):
        # --help-json: the card the product's retrieval finds for the model's own query (not the task's)
        from cin_minai.daemon.guide import TERMINAL_MIN_SCORE  # the daemon's rules for terminal errors
        query = str(args.get("query", ""))
        if it.get("terminal"):
            from cin_minai.daemon.terminal import lookup_hint
            query = f"{query} {lookup_hint(it['terminal'])}"
        cid, result = HELP.lookup(query, it["lang"], TERMINAL_MIN_SCORE if it["cat"] == "terminal" else 1.0)
        rec["help_card"] = cid
    elif tool == "lookup_help" and "card" in it:
        result = it["card"]
    elif tool == "inspect_system" and "result" in it:
        result = json.dumps(it["result"], ensure_ascii=False)
    else:
        result = None
    if reply is None and result is not None:
        messages += [{"role": "assistant", "content": raw},
                     {"role": "user", "content": f"Result of {tool}:\n{result}\n\n{style()}"}]
        reply, tb = srv.chat(messages, None, 600)
        rec["t_b"] = round(tb, 2)
    if reply is not None and loop_detector:
        reply, match = repair(reply, names_for(it["lang"]))
        rec["loop_stopped"] = match is not None
        if match is not None:
            rec["loop_piece"] = match.piece
    if reply is not None and not it.get("b_skip") and ("card" in it or "result" in it or it["cat"] in ("decline", "interpret", "terminal")):
        rec["reply"] = reply
        rec["b_fails"] = stage_b(it, reply)
        rec["b_ok"] = not rec["b_fails"]
    rec["ok"] = rec["a_ok"] and rec["b_ok"] is not False
    return rec


def summary(recs: list[dict]) -> str:
    def row(name, rs):
        a = sum(r["a_ok"] for r in rs)
        b = [r for r in rs if r["b_ok"] is not None]
        ok = sum(r["ok"] for r in rs)
        return (f"{name:<12} {ok:>3}/{len(rs):<3} ({100 * ok / len(rs):3.0f} %)   A {a}/{len(rs)}   "
                f"B {sum(r['b_ok'] for r in b)}/{len(b)}")
    lines = [row("ALL", recs), ""]
    for cat in dict.fromkeys(r["cat"] for r in recs):
        lines.append(row(cat, [r for r in recs if r["cat"] == cat]))
    lines.append("")
    for lang in LANGS:
        rs = [r for r in recs if r["lang"] == lang]
        if rs:
            lines.append(row(lang, rs))
    ts = [r["t_a"] + r.get("t_b", 0) for r in recs]
    lines.append(f"\nmedian time per item {statistics.median(ts):.1f} s, total {sum(ts):.0f} s")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url"), ap.add_argument("--model", default=""), ap.add_argument("--api-key-env")
    ap.add_argument("--config"), ap.add_argument("--only"), ap.add_argument("--lang"), ap.add_argument("--out")
    ap.add_argument("--sampling", type=parse_sampling, default={},
                    help="JSON llama.cpp sampling overrides for free-text Stage B only")
    ap.add_argument("--loop-detector", action="store_true",
                    help="score the deterministic repaired reply the product shows when generation loops")
    ap.add_argument("--tasks", help="tasks file (default: tasks.py here)")
    ap.add_argument("--prompt", choices=["v1", "v2", "v2.1", "v2.2", "v2.3", "v2.4"], default="v1")
    ap.add_argument("--help-json", help="look help up for real: the daemon's help.json (distro/packages/"
                                        "cinminai-daemon/gen_data.py); needs cin_minai on PYTHONPATH")
    ap.add_argument("--dry-run", action="store_true"), ap.add_argument("-v", action="store_true")
    o = ap.parse_args()
    global PROMPT, HELP
    PROMPT = o.prompt
    if o.help_json:
        from cin_minai.daemon.helpcards import HelpIndex
        HELP = HelpIndex.load(o.help_json)

    its = items()  # resolves every label: a missing translation fails here, before any model call
    if o.only:
        its = [i for i in its if i["id"] in o.only.split(",")]
    if o.lang:
        its = [i for i in its if i["lang"] == o.lang]
    if o.dry_run:
        by = {}
        for i in its:
            by.setdefault(i["cat"], {}).setdefault(i["lang"], 0)
            by[i["cat"]][i["lang"]] += 1
        print(f"{len(TASKS)} tasks, {len(its)} items")
        for cat, langs in by.items():
            print(f"  {cat:<11}", "  ".join(f"{lang} {n}" for lang, n in langs.items()))
        return

    url, key, model = o.url, os.environ.get(o.api_key_env, "") if o.api_key_env else "", o.model
    if o.config:
        cfg = tomllib.load(open(os.path.expanduser(o.config), "rb"))["inference"]
        url, key, model = url or cfg["url"], key or cfg.get("api_key", ""), model or cfg.get("model", "")
    if not url:
        ap.error("--url or --config needed")
    srv = Server(url, key, model, o.sampling)
    out = o.out or os.path.join("bench-results", "guide",
                                f"{re.sub(r'[^\w.-]+', '_', model or 'model')}-{PROMPT}-{dt.datetime.now():%Y%m%d-%H%M}.jsonl")
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    recs = []
    with open(out, "w", encoding="utf-8") as f:
        for it in its:
            rec = run_item(srv, it, o.loop_detector)
            recs.append(rec)
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()
            mark = "PASS" if rec["ok"] else "FAIL"
            print(f"{mark} {rec['id']}-{rec['lang']} {rec['call'].get('tool')}"
                  + ("" if rec["a_ok"] else "  (A: wrong action)")
                  + (f"  (B: {'; '.join(rec['b_fails'])})" if rec["b_fails"] else ""), flush=True)
            if o.v:
                print("   ", json.dumps(rec["call"], ensure_ascii=False)[:300])
                if rec["reply"]:
                    print("    reply:", rec["reply"][:500].replace("\n", "\n           "))
    print("\n" + summary(recs))
    print(f"\nresults: {out}")


if __name__ == "__main__":
    main()
