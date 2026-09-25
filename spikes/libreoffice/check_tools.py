#!/usr/bin/env python3
"""Toolkit checks against a real (headless, throwaway-profile) LibreOffice. Run on the Mint box:

    python3 check_tools.py
"""

from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "extension", "pythonpath"))
sys.path.insert(0, HERE)

import cinminai_tools as T  # noqa: E402
import lo  # noqa: E402

results: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""), flush=True)


def fails(fn, *a) -> str:
    try:
        fn(*a)
    except T.ToolError as e:
        return str(e)
    return ""


def main() -> int:
    office = lo.Office()
    try:
        writer(office)
        calc(office)
        impress(office)
    finally:
        office.close()
    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks pass")
    return 1 if failed else 0


def writer(office) -> None:
    print("== Writer")
    doc = lo.writer_doc(office)
    info = T.read(doc, "doc_info", {})
    record("doc_info", info["type"] == "writer" and info["paragraphs"] == 8, json.dumps(info))
    heads = T.read(doc, "outline", {})["headings"]
    record("outline: headings with levels", [(h["level"], h["text"]) for h in heads] ==
           [(1, "Project Kestrel"), (2, "Hardware"), (2, "Software"), (1, "Results")], json.dumps(heads)[:120])
    lo.select_paragraph(doc, 5)
    sel = T.read(doc, "get_selection", {})["text"]
    record("get_selection", sel.startswith("teh firmware"), sel[:60])

    original = doc.getText().getString()
    fixed = "The firmware is written in MicroPython and posts readings every five minutes."
    pv = T.preview(doc, "replace_selection", {"text": fixed})
    record("preview shows before/after, changes nothing",
           pv["before"] == sel and pv["after"] == fixed and doc.getText().getString() == original, pv["summary"])
    res = T.apply(doc, "replace_selection", {"text": fixed}, pv["snapshot"])
    now = doc.getText().getString()
    record("apply replaces exactly the selection", fixed in now and "teh firmware" not in now
           and now.count("\n") == original.count("\n"), res["undo"])
    undo = doc.getUndoManager()
    record("one undo step, named for the assistant", undo.getCurrentUndoActionTitle() == res["undo"],
           undo.getCurrentUndoActionTitle())
    undo.undo()
    record("a single undo restores the original", doc.getText().getString() == original)

    lo.select_paragraph(doc, 5)
    pv = T.preview(doc, "replace_selection", {"text": "x"})
    doc.getText().getEnd().setString(" (edited by the user)")
    record("apply refuses after the document changed", "changed since the preview" in
           fails(T.apply, doc, "replace_selection", {"text": "x"}, pv["snapshot"]))
    record("tools refuse the wrong document type", "isn't available" in fails(T.read, doc, "read_range", {"range": "A1"}))
    record("unknown tools refused", "unknown tool" in fails(T.read, doc, "run_macro", {}))
    doc.close(True)


def calc(office) -> None:
    print("== Calc")
    doc = lo.calc_doc(office)
    info = T.read(doc, "doc_info", {})
    record("doc_info: sheets, active sheet, selection", info["sheets"] == ["Weather"] and
           info["selection"] == "Weather.B8:B8", json.dumps(info))
    r = T.read(doc, "read_range", {"range": "A1:C3"})
    record("read_range: values", r["values"][1] == ["Jan", 78.0, 6.5], json.dumps(r["values"]))
    r = T.read(doc, "get_selection", {})
    record("get_selection gives the formula", r.get("formulas") == [["=SUM(B2:B7)"]] and r["values"] == [[339.0]],
           json.dumps(r))
    record("used_range", T.read(doc, "used_range", {})["range"] == "A1:C8")
    record("sheet-qualified and lower-case refs", T.read(doc, "read_range", {"range": "Weather.b2"})["values"] == [[78.0]])
    record("bad ranges refused clearly", "not a cell range" in fails(T.read, doc, "read_range", {"range": "B2:??"})
           and "no sheet named" in fails(T.read, doc, "read_range", {"range": "Nope.A1"}))

    sheet = doc.getSheets().getByName("Weather")
    args = {"range": "D1:D8", "values": [["Rain in"]] + [[f"=B{r}/25.4"] for r in range(2, 8)] + [["=SUM(D2:D7)"]]}
    before = [list(x) for x in sheet.getCellRangeByName("D1:D8").getFormulaArray()]
    pv = T.preview(doc, "write_range", args)
    record("preview write_range", pv["before"] == before and pv["after"][1] == ["=B2/25.4"], pv["summary"])
    res = T.apply(doc, "write_range", args, pv["snapshot"])
    d2 = sheet.getCellRangeByName("D2").getValue()
    d8 = sheet.getCellRangeByName("D8").getValue()
    record("formulas written and computed", abs(d2 - 78 / 25.4) < 1e-9 and abs(d8 - 339 / 25.4) < 1e-9,
           f"D2={d2:.3f} D8={d8:.3f}")
    um = doc.getUndoManager()
    record("one undo step, named for the assistant", um.getCurrentUndoActionTitle() == res["undo"])
    um.undo()
    record("a single undo clears all 8 cells", [list(x) for x in sheet.getCellRangeByName("D1:D8").getFormulaArray()] == before)
    um.redo()
    record("redo re-applies it", sheet.getCellRangeByName("D2").getFormula() == "=B2/25.4")
    pv = T.preview(doc, "set_formula", {"cell": "B9", "formula": "AVERAGE(B2:B7)"})
    res = T.apply(doc, "set_formula", {"cell": "B9", "formula": "AVERAGE(B2:B7)"}, pv["snapshot"])
    b9 = sheet.getCellRangeByName("B9")
    record("set_formula (adds the missing '=')", b9.getFormula() == "=AVERAGE(B2:B7)" and abs(b9.getValue() - 56.5) < 1e-9,
           f"{pv['summary']}; B9={b9.getValue()}")
    um.undo()
    record("set_formula undone with one undo", b9.getFormula() == "")
    record("set_formula refuses ranges", "one cell" in fails(T.preview, doc, "set_formula", {"cell": "B9:B10", "formula": "=1"}))
    record("shape mismatch refused", "row(s)" in fails(T.preview, doc, "write_range", {"range": "A1:B2", "values": [["x"]]}))
    record("huge range refused", "too large" in fails(T.read, doc, "read_range", {"range": "A1:Z1000"}))
    pv = T.preview(doc, "write_range", {"range": "E1", "values": [["x"]]})
    sheet.getCellRangeByName("E1").setString("user typed this")
    record("apply refuses after the target changed", "changed" in
           fails(T.apply, doc, "write_range", {"range": "E1", "values": [["x"]]}, pv["snapshot"]))
    doc.close(True)


def impress(office) -> None:
    print("== Impress")
    doc = lo.impress_doc(office)
    record("doc_info", T.read(doc, "doc_info", {})["slides"] == 2)
    s2 = T.read(doc, "slide_text", {"slide": 2})
    record("slide_text", s2["title"] == "Hardware" and "BME280" in s2["body"], json.dumps(s2))
    args = {"slide": 2, "body": "Raspberry Pi Pico W\nBME280 (I2C)\nTipping-bucket rain gauge"}
    pv = T.preview(doc, "set_slide_text", args)
    res = T.apply(doc, "set_slide_text", args, pv["snapshot"])
    after = T.read(doc, "slide_text", {"slide": 2})
    record("set_slide_text changes the body, keeps the title",
           after["title"] == "Hardware" and "Tipping-bucket" in after["body"], res["undo"])
    um = doc.getUndoManager()
    record("undo step named for the assistant", um.getCurrentUndoActionTitle() == res["undo"],
           str(um.getCurrentUndoActionTitle()))
    um.undo()
    record("a single undo restores the slide", T.read(doc, "slide_text", {"slide": 2}) == s2)
    um.redo()
    record("redo re-applies it", "Tipping-bucket" in T.read(doc, "slide_text", {"slide": 2})["body"])
    record("missing slide refused", "no slide 9" in fails(T.read, doc, "slide_text", {"slide": 9}))
    doc.close(True)


if __name__ == "__main__":
    sys.exit(main())
