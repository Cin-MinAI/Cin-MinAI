#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Guide eval runner (PLAN §3 guide track, SPEC §10.6). Talks to a running llama-server
(OpenAI-compatible); stdlib only.

    python3 run_eval.py --dry-run                         # check tasks + labels, count items
    python3 run_eval.py --url http://127.0.0.1:8081 [--model NAME] [--api-key-env VAR]
    python3 run_eval.py --config ~/.config/cinminai/config.toml     # url/api_key/model from [inference]
      options: --only T01,D02  --lang ja  --out FILE  -v

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
import importlib.util  # noqa: E402

TASKS_FILE = os.path.join(HERE, "tasks.py")
if "--tasks" in sys.argv:  # e.g. the hidden eval (training/eval/guide-hidden/tasks.py)
    TASKS_FILE = os.path.abspath(sys.argv[sys.argv.index("--tasks") + 1])
_spec = importlib.util.spec_from_file_location("guide_tasks", TASKS_FILE)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
TASKS, BRANDS = _mod.TASKS, _mod.BRANDS

LABELS = json.load(open(os.path.join(HERE, "labels.json"), encoding="utf-8"))["labels"]
LANGS = ["en", "es", "pt", "fr", "de", "ja"]

# --- tools ---------------------------------------------------------------------------------------

S, I = {"type": "string"}, {"type": "integer", "minimum": 0}
TOPICS = ["overview", "storage", "network", "updates", "printers", "sound", "display", "battery", "drivers"]
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


def tools_for(doc: str | None) -> dict:
    return {**GUIDE_TOOLS, **(OFFICE_TOOLS[doc] if doc else {})}


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
PROMPT = "v1"
HELP = None  # --help-json: the daemon's help index (src/cin_minai/daemon/helpcards.py)


def system_prompt(task: dict) -> str:
    doc = task.get("doc")
    tools = "\n".join(f"- {n}: {d}" for n, (_, d) in tools_for(doc).items())
    ctx = task.get("ctx")
    if doc and PROMPT == "v2" and "data" in ctx:
        # integration fix: the sidebar tells the model where new rows go (SPEC §7.11) instead of the
        # model working it out from the used range
        last = int(re.search(r"(\d+)$", ctx["used_range"]).group(1))
        ctx = {**ctx, "next_empty_row": last + 1}
    if doc:
        document = (f"\nThe user shared a LibreOffice {doc} document with you. Read tools run immediately; "
                    "EDIT tools are shown to the user as a preview and only happen if they approve. Prefer "
                    "doing the edit over describing it; use answer when the context already has what's "
                    f"needed.\nDocument context:\n{json.dumps(ctx, ensure_ascii=False)}\n")
        if PROMPT == "v2":
            document += ("When the data is in the context above, answer from it or edit directly; don't look "
                         "it up or read it again. New entries go in next_empty_row.\n")
    else:
        document = "\nNo document is shared.\n"
    return (SYSTEM_V2 if PROMPT == "v2" else SYSTEM).format(document=document, tools=tools)


# --- items: one per (task, language) --------------------------------------------------------------

def label(key: str, lang: str) -> str:
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
            out.append(it)
    return out


# --- model calls ---------------------------------------------------------------------------------

class Server:
    def __init__(self, url: str, key: str, model: str):
        self.url, self.key, self.model = url.rstrip("/"), key, model

    def chat(self, messages: list, schema_: dict | None, max_tokens: int) -> tuple[str, float]:
        body = {"model": self.model, "temperature": 0, "max_tokens": max_tokens, "messages": messages,
                "chat_template_kwargs": {"enable_thinking": False}}
        if schema_:
            body["response_format"] = {"type": "json_schema", "json_schema": {"name": "call", "schema": schema_}}
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
    return fails


def run_item(srv: Server, it: dict) -> dict:
    messages = [{"role": "system", "content": system_prompt(it)}, {"role": "user", "content": it["q"]}]
    raw, ta = srv.chat(messages, schema(it.get("doc")), 700)
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
    elif tool == "lookup_help" and "card" in it and HELP is not None:
        # --help-json: the card the product's retrieval finds for the model's own query (not the task's)
        cid, result = HELP.lookup(str(args.get("query", "")), it["lang"])
        rec["help_card"] = cid
    elif tool == "lookup_help" and "card" in it:
        result = it["card"]
    elif tool == "inspect_system" and "result" in it:
        result = json.dumps(it["result"], ensure_ascii=False)
    else:
        result = None
    if reply is None and result is not None:
        messages += [{"role": "assistant", "content": raw},
                     {"role": "user", "content": f"Result of {tool}:\n{result}\n\n{STYLE_V2 if PROMPT == 'v2' else STYLE}"}]
        reply, tb = srv.chat(messages, None, 600)
        rec["t_b"] = round(tb, 2)
    if reply is not None and ("card" in it or "result" in it or it["cat"] in ("decline", "interpret")):
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
    ap.add_argument("--tasks", help="tasks file (default: tasks.py here)")
    ap.add_argument("--prompt", choices=["v1", "v2"], default="v1")
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
    srv = Server(url, key, model)
    out = o.out or os.path.join("bench-results", "guide",
                                f"{re.sub(r'[^\w.-]+', '_', model or 'model')}-{PROMPT}-{dt.datetime.now():%Y%m%d-%H%M}.jsonl")
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    recs = []
    with open(out, "w", encoding="utf-8") as f:
        for it in its:
            rec = run_item(srv, it)
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
