"""Model side of the LibreOffice toolkit (M0 spike): tool schemas, prompt, one constrained call.

Shared by eval.py (scripted requests) and lo_assist.py (the hands-on demo). The daemon will own this
in M6. Output is constrained to a JSON schema (llama.cpp grammar): {"tool": ..., "args": {...}}.
"""

from __future__ import annotations

import json
import os
import time
import tomllib
import urllib.request

CFG = tomllib.load(open(os.path.expanduser("~/.config/cinminai/config.toml"), "rb"))["inference"]

# --- tools offered per document type ------------------------------------------------------------

S, I = {"type": "string"}, {"type": "integer", "minimum": 0}
CELL = {"anyOf": [{"type": "string"}, {"type": "number"}]}
TOOLS = {
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
                        "or a formula starting with =); rows × columns must match the range"),
    },
    "impress": {
        "doc_info": ({}, "number of slides"),
        "slide_text": ({"slide": {"type": "integer", "minimum": 1}}, "title and body text of a slide (1-based)"),
        "set_slide_text": ({"slide": {"type": "integer", "minimum": 1}, "title": S, "body": S},
                           "EDIT: set the title and/or body of a slide; body lines are bullets separated by \\n; "
                           "give only the parts to change"),
    },
}
ANSWER = ({"text": S}, "reply to the user directly, when the context above already has what's needed")


def schema(kind: str) -> dict:
    options = []
    for name, (props, _) in {**TOOLS[kind], "answer": ANSWER}.items():
        required = [k for k in props if not (kind == "impress" and name == "set_slide_text" and k != "slide")]
        options.append({"type": "object", "additionalProperties": False, "required": ["tool", "args"],
                        "properties": {"tool": {"const": name},
                                       "args": {"type": "object", "additionalProperties": False,
                                                "properties": props, "required": required}}})
    return {"oneOf": options}


def prompt(kind: str, context: dict) -> str:
    tools = "\n".join(f"- {n}: {d}" for n, (_, d) in {**TOOLS[kind], "answer": ANSWER}.items())
    return (f"You are the assistant built into this computer, working on a LibreOffice {kind} document "
            "the user shared with you. Reply with exactly one JSON object {\"tool\": ..., \"args\": {...}} "
            "that does what the user asked. Read tools run immediately; EDIT tools are shown to the user "
            "as a preview and only happen if they approve. Prefer doing the edit over describing it. "
            "Use 'answer' only when the context below already contains what's needed; if you need data "
            "that isn't in the context, call a read tool first.\n\n"
            f"Tools:\n{tools}\n\nDocument context:\n{json.dumps(context, ensure_ascii=False)}")


def ask(kind: str, context: dict, request: str, retry: tuple[dict, str] | None = None) -> tuple[dict, float]:
    messages = [{"role": "system", "content": prompt(kind, context)}, {"role": "user", "content": request}]
    if retry:  # the daemon hands tool errors back to the model; so does the eval, once
        messages += [{"role": "assistant", "content": json.dumps(retry[0])},
                     {"role": "user", "content": f"That call failed: {retry[1]}. Send a corrected call."}]
    body = {"model": CFG.get("model", ""), "temperature": 0, "max_tokens": 600,
            "messages": messages,
            "response_format": {"type": "json_schema", "json_schema": {"name": "call", "schema": schema(kind)}}}
    req = urllib.request.Request(CFG["url"].rstrip("/") + "/v1/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json",
                                          "Authorization": f"Bearer {CFG.get('api_key', '')}"})
    t0 = time.monotonic()
    with urllib.request.urlopen(req, timeout=300) as r:
        out = json.load(r)
    return json.loads(out["choices"][0]["message"]["content"]), time.monotonic() - t0



def context(kind: str, read) -> dict:
    """What the model sees about the document. `read(tool, args)` runs a read tool (directly or
    over D-Bus). Small sheets go in whole."""
    ctx = {"document": read("doc_info", {})}
    if kind == "writer":
        try:
            ctx["selection"] = read("get_selection", {})["text"]
        except Exception:
            ctx["selection"] = ""
        ctx["outline"] = read("outline", {})["headings"]
    elif kind == "calc":
        ctx["selection"] = read("get_selection", {})
        used = read("used_range", {})["range"]
        ctx["used_range"] = used
        data = read("read_range", {"range": used})
        if sum(len(r) for r in data["values"]) <= 200:
            ctx["data"] = data
    else:
        n = ctx["document"]["slides"]
        ctx["slides"] = [read("slide_text", {"slide": i}) for i in range(1, min(n, 10) + 1)]
    return ctx
