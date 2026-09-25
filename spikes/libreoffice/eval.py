#!/usr/bin/env python3
"""Toolkit eval (M0 exit: ≥ 90 % of 30 scripted requests): does the local model pick the right
LibreOffice tool with usable arguments? Run on the Mint box (llama-server from
~/.config/cinminai/config.toml, headless LibreOffice with a throwaway profile):

    python3 eval.py [-v]

Output is constrained to a JSON schema (llama.cpp grammar), so every reply is a well-formed call;
what's scored is the choice of tool and the arguments. Each call is then run for real (read, or
preview for edits) on the document to prove the arguments work.
"""

from __future__ import annotations

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "extension", "pythonpath"))
sys.path.insert(0, HERE)

import cinminai_tools as T  # noqa: E402
import lo  # noqa: E402
from assist import ask, context as build_context  # noqa: E402

VERBOSE = "-v" in sys.argv

# --- cases -------------------------------------------------------------------------------------

def low(s) -> str:
    return str(s).lower()


def rng(a, *accept) -> bool:
    r = str(a.get("range", a.get("cell", ""))).upper().replace("$", "").split(".")[-1]
    return r in accept


def rows(a) -> list:
    if "formula" in a:  # set_formula
        f = str(a["formula"]).strip()
        return [[f if f.startswith("=") else "=" + f]]
    return a.get("cells") or a.get("values") or [[]]


W, C, P = "writer", "calc", "impress"
SEL = "teh firmware is writen in MicroPython and posts readings every five minuts."
CASES = [
    (W, "Fix the spelling in the selected text.", {"replace_selection"},
     lambda a: all(w in low(a["text"]) for w in ("the firmware", "written", "minutes"))),
    (W, "What are the section headings in this document?", {"outline"}, None),
    (W, "Rewrite the selection so it sounds more formal.", {"replace_selection"},
     lambda a: "micropython" in low(a["text"]) and a["text"] != SEL),
    (W, "Make the selected sentence shorter.", {"replace_selection"}, lambda a: 0 < len(a["text"]) < len(SEL)),
    (W, "How many paragraphs does this document have?", {"doc_info"}, None),
    (W, "Show me the first three paragraphs.", {"get_paragraphs"}, lambda a: a["start"] == 0 and a["count"] == 3),
    (W, "Translate the selected text into Spanish.", {"replace_selection"},
     lambda a: "micropython" in low(a["text"]) and any(w in low(a["text"]) for w in ("minutos", "escrito", "lecturas"))),
    (W, "What does the selected text say?", {"get_selection", "answer"}, None),
    (W, "Replace the selection with: Firmware: MicroPython, readings every 5 minutes.", {"replace_selection"},
     lambda a: a["text"].strip() == "Firmware: MicroPython, readings every 5 minutes."),
    (W, "Read me paragraphs 5 to 8.", {"get_paragraphs"}, lambda a: a["start"] in (4, 5) and a["count"] >= 3),

    (C, "Explain the formula in the selected cell.", {"answer", "get_selection"},
     lambda a: "text" not in a or "sum" in low(a["text"])),
    (C, "What is in A1 to C3?", {"read_range"}, lambda a: rng(a, "A1:C3")),
    (C, "Put the average rainfall in B9.", {"write_range", "set_formula"},
     lambda a: rng(a, "B9", "B9:B9") and re.fullmatch(r"=AVERAGE\(B2:B7\)", str(rows(a)[0][0]).upper().replace(" ", ""))),
    (C, "In column D, add the header 'Rain in' in D1 and convert the rainfall in B2:B7 to inches in D2:D7.",
     {"write_range"},
     lambda a: rng(a, "D1:D7") and len(rows(a)) == 7 and "B2" in str(rows(a)[1][0]).upper() and "25.4" in str(rows(a)[1][0])),
    (C, "Which month had the highest max temperature?", {"read_range", "answer"},
     lambda a: "text" in a and "jun" in low(a["text"]) or rng(a, "A1:C7", "A2:C7", "C2:C7", "C1:C7", "A1:C8", "A1:C8")),
    (C, "How much of this sheet is filled in?", {"used_range", "doc_info", "answer"},
     lambda a: "text" not in a or "C8" in a["text"].upper()),
    (C, "Write 'Checked' into E1.", {"write_range"}, lambda a: rng(a, "E1", "E1:E1") and rows(a) == [["Checked"]]),
    (C, "Change the total in B8 so it only adds up B2 to B6.", {"write_range", "set_formula"},
     lambda a: rng(a, "B8", "B8:B8") and str(rows(a)[0][0]).upper().replace(" ", "") == "=SUM(B2:B6)"),
    (C, "Show me the formulas in column B, rows 1 to 8.", {"read_range"}, lambda a: rng(a, "B1:B8")),
    (C, "Put 'Average' in A9 and the average of B2:B7 in B9.", {"write_range"},
     lambda a: rng(a, "A9:B9") and rows(a)[0][0] == "Average" and "AVERAGE(B2:B7)" in str(rows(a)[0][1]).upper()),

    (P, "What's on slide 2?", {"slide_text", "answer"}, lambda a: a.get("slide", 2) == 2),
    (P, "Change the title of slide 1 to 'Kestrel: two weeks of weather'.", {"set_slide_text"},
     lambda a: a["slide"] == 1 and a.get("title") == "Kestrel: two weeks of weather"
     and a.get("body", "Two weeks of data") == "Two weeks of data"),  # resending the unchanged body is fine
    (P, "How many slides are there?", {"doc_info", "answer"}, lambda a: "text" not in a or "2" in a["text"] or "two" in low(a["text"])),
    (P, "Make the bullet points on slide 2 more descriptive.", {"set_slide_text"},
     lambda a: a["slide"] == 2 and "bme280" in low(a.get("body", "")) and a.get("body", "").count("\n") >= 2),
    (P, "Add 'Solar panel' as another bullet on slide 2.", {"set_slide_text"},
     lambda a: a["slide"] == 2 and "solar panel" in low(a.get("body", "")) and "bme280" in low(a.get("body", ""))),
    (P, "Read me the first slide.", {"slide_text", "answer"}, lambda a: a.get("slide", 1) == 1),
    (P, "Set the subtitle of slide 1 to 'Data from June 2026'.", {"set_slide_text"},
     lambda a: a["slide"] == 1 and a.get("body") == "Data from June 2026"),
    (P, "Shorten the title of slide 1.", {"set_slide_text"},
     lambda a: a["slide"] == 1 and 0 < len(a.get("title", "")) < len("Kestrel weather station")),
    (P, "Rename slide 2 to 'Parts list'.", {"set_slide_text"}, lambda a: a["slide"] == 2 and a.get("title") == "Parts list"),
    (P, "Remove 'Rain gauge' from the list on slide 2.", {"set_slide_text"},
     lambda a: a["slide"] == 2 and "rain gauge" not in low(a.get("body", "x rain gauge")) and "bme280" in low(a.get("body", ""))),
]


def context(kind: str, doc) -> dict:
    return build_context(kind, lambda tool, args: T.read(doc, tool, args))


def main() -> int:
    office = lo.Office()
    docs = {W: lo.writer_doc(office), C: lo.calc_doc(office), P: lo.impress_doc(office)}
    lo.select_paragraph(docs[W], 5)
    ctxs = {k: context(k, d) for k, d in docs.items()}
    first, final, retried, times = 0, 0, 0, []

    def attempt(kind, request, tools, check, retry=None):
        call, dt = ask(kind, ctxs[kind], request, retry)
        times.append(dt)
        tool, args = call["tool"], call["args"]
        error = None
        if tool != "answer":
            try:
                (T.preview if tool in T.EDIT else T.read)(docs[kind], tool, args)
            except T.ToolError as e:
                error = str(e)
        ok = tool in tools and not error
        if ok and check:
            try:
                ok = bool(check(args))
            except (KeyError, IndexError, TypeError):
                ok = False
        return call, ok, error

    try:
        for i, (kind, request, tools, check) in enumerate(CASES, 1):
            call, ok, error = attempt(kind, request, tools, check)
            first += ok
            note = ""
            if error:  # the tool refused the call: hand the error back once, as the daemon will
                print(f"      first try: {json.dumps(call, ensure_ascii=False)[:160]} → {error}", flush=True)
                retried += 1
                call, ok, error = attempt(kind, request, tools, check, retry=(call, error))
                note = "(after retry) "
            final += ok
            line = (f"{'OK ' if ok else 'BAD'} {i:2} {kind:7} {call['tool']:17} "
                    f"{note}{json.dumps(call['args'], ensure_ascii=False)[:90]}" + (f"  FAILS: {error}" if error else ""))
            print(line if VERBOSE or not ok else f"OK  {i:2} {kind:7} {call['tool']} {note}", flush=True)
    finally:
        office.close()
    n = len(CASES)
    print(f"\nfirst try {first}/{n} = {100 * first / n:.0f} %; with one retry on tool errors "
          f"({retried} retried) {final}/{n} = {100 * final / n:.0f} %  (target ≥ 90 %)\n"
          f"median {sorted(times)[len(times) // 2]:.1f} s per request, max {max(times):.1f} s")
    return 0 if final / n >= 0.9 else 1


if __name__ == "__main__":
    sys.exit(main())
