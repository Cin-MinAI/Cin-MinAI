"""Document toolkit for the Cin-MinAI LibreOffice extension (M0 spike, SPEC §7.7–7.8).

Pure UNO: every function takes a document model and a dict of arguments and returns JSON-able
data, so it runs the same inside LibreOffice (the extension) and from a test harness over a UNO
bridge. Edit tools come in two steps:

    preview(doc, tool, args) -> {"before", "after", "snapshot", "summary"}
    apply(doc, tool, args, snapshot) -> {"applied": True, "undo": "<undo action title>"}

apply() refuses when the target changed since the preview (snapshot mismatch) and runs the whole
edit inside one undo context, so a single Ctrl+Z reverts it.
"""

from __future__ import annotations

import hashlib
import json
import re

MAX_CELLS = 2000
MAX_TEXT = 20000


class ToolError(Exception):
    pass


# --- document kinds --------------------------------------------------------------------------

def kind(doc) -> str:
    if doc.supportsService("com.sun.star.text.TextDocument"):
        return "writer"
    if doc.supportsService("com.sun.star.sheet.SpreadsheetDocument"):
        return "calc"
    if doc.supportsService("com.sun.star.presentation.PresentationDocument"):
        return "impress"
    return "other"


def title(doc) -> str:
    try:
        return doc.getTitle()
    except Exception:
        return doc.getURL().rsplit("/", 1)[-1] or "Untitled"


def doc_info(doc, args: dict) -> dict:
    k = kind(doc)
    info = {"type": k, "title": title(doc), "modified": bool(doc.isModified())}
    if k == "writer":
        info["paragraphs"] = sum(1 for _ in paragraphs(doc))
        info["characters"] = len(doc.getText().getString())
    elif k == "calc":
        sheets = doc.getSheets()
        info["sheets"] = list(sheets.getElementNames())
        info["active_sheet"] = doc.getCurrentController().getActiveSheet().getName()
        info["selection"] = selection_address(doc)
    elif k == "impress":
        info["slides"] = doc.getDrawPages().getCount()
    return info


# --- Writer ------------------------------------------------------------------------------------

def paragraphs(doc):
    enum = doc.getText().createEnumeration()
    while enum.hasMoreElements():
        p = enum.nextElement()
        if p.supportsService("com.sun.star.text.Paragraph"):
            yield p


def text_selection(doc):
    sel = doc.getCurrentController().getSelection()
    if sel is None or not hasattr(sel, "getCount") or sel.getCount() == 0:
        raise ToolError("nothing is selected")
    rng = sel.getByIndex(0)
    if not hasattr(rng, "getString"):
        raise ToolError("the selection is not text")
    return rng


def get_selection(doc, args: dict) -> dict:
    k = kind(doc)
    if k == "writer":
        return {"text": text_selection(doc).getString()[:MAX_TEXT]}
    if k == "calc":
        addr = selection_address(doc)
        return {"range": addr, **read_range(doc, {"range": addr})}
    raise ToolError(f"get_selection isn't available for {k}")


def outline(doc, args: dict) -> dict:
    heads = []
    for i, p in enumerate(paragraphs(doc)):
        level = p.getPropertyValue("OutlineLevel")
        if level > 0:
            heads.append({"level": level, "text": p.getString()[:200], "paragraph": i})
    return {"headings": heads}


def get_paragraphs(doc, args: dict) -> dict:
    start, count = int(args.get("start", 0)), min(int(args.get("count", 20)), 200)
    out = [p.getString() for i, p in enumerate(paragraphs(doc)) if start <= i < start + count]
    return {"start": start, "paragraphs": out}


def _selection_state(doc) -> str:
    """Selected text plus the whole text: any change anywhere invalidates a preview."""
    return f"{text_selection(doc).getString()}\x00{doc.getText().getString()}"


def preview_replace_selection(doc, args: dict) -> dict:
    new = str(args["text"])
    before = text_selection(doc).getString()
    return {"before": before, "after": new, "snapshot": snap(_selection_state(doc)),
            "summary": f"Replace the selected text ({len(before)} → {len(new)} characters)"}


def apply_replace_selection(doc, args: dict) -> None:
    text_selection(doc).setString(str(args["text"]))


# --- Calc --------------------------------------------------------------------------------------

RANGE_RE = re.compile(r"^(?:(?P<sheet>[^.!]+)[.!])?\$?(?P<c1>[A-Z]{1,3})\$?(?P<r1>\d{1,7})"
                      r"(?::\$?(?P<c2>[A-Z]{1,3})\$?(?P<r2>\d{1,7}))?$", re.IGNORECASE)


def selection_address(doc) -> str:
    sel = doc.getCurrentController().getSelection()
    if hasattr(sel, "getRangeAddress"):
        a = sel.getRangeAddress()
        sheet = doc.getSheets().getByIndex(a.Sheet).getName()
        return f"{sheet}.{col_name(a.StartColumn)}{a.StartRow + 1}:{col_name(a.EndColumn)}{a.EndRow + 1}"
    return ""


def col_name(i: int) -> str:
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def cell_range(doc, ref: str):
    m = RANGE_RE.match(ref.strip())
    if not m:
        raise ToolError(f"not a cell range: {ref!r} (use e.g. A1:C10 or Sheet1.A1:C10)")
    sheets = doc.getSheets()
    name = m["sheet"]
    if name:
        if not sheets.hasByName(name):
            raise ToolError(f"no sheet named {name!r}; sheets: {list(sheets.getElementNames())}")
        sheet = sheets.getByName(name)
    else:
        sheet = doc.getCurrentController().getActiveSheet()
    c1, r1 = m["c1"].upper(), m["r1"]
    c2, r2 = (m["c2"] or c1).upper(), (m["r2"] or r1)
    rng = sheet.getCellRangeByName(f"{c1}{r1}:{c2}{r2}")
    a = rng.getRangeAddress()
    if (a.EndColumn - a.StartColumn + 1) * (a.EndRow - a.StartRow + 1) > MAX_CELLS:
        raise ToolError(f"range too large (max {MAX_CELLS} cells)")
    return rng


def read_range(doc, args: dict) -> dict:
    rng = cell_range(doc, args["range"])
    values = [list(row) for row in rng.getDataArray()]
    formulas = [list(row) for row in rng.getFormulaArray()]
    has_formula = any(str(f).startswith("=") for row in formulas for f in row)
    return {"values": values, **({"formulas": formulas} if has_formula else {})}


def used_range(doc, args: dict) -> dict:
    sheet = doc.getCurrentController().getActiveSheet()
    cur = sheet.createCursor()
    cur.gotoEndOfUsedArea(False)
    a = cur.getRangeAddress()
    return {"sheet": sheet.getName(), "range": f"A1:{col_name(a.EndColumn)}{a.EndRow + 1}"}


def _normalize(values, rng) -> list[list[str]]:
    a = rng.getRangeAddress()
    rows, cols = a.EndRow - a.StartRow + 1, a.EndColumn - a.StartColumn + 1
    if not isinstance(values, list) or not all(isinstance(r, list) for r in values):
        raise ToolError("values must be a list of rows (lists)")
    if len(values) != rows or any(len(r) != cols for r in values):
        raise ToolError(f"values must be {rows} row(s) × {cols} column(s) for this range")
    return [["" if v is None else (repr(v) if isinstance(v, float) else str(v)) for v in r] for r in values]


def _cells(args: dict):
    return args["cells"] if "cells" in args else args["values"]  # "cells": the name the model sees


def preview_write_range(doc, args: dict) -> dict:
    rng = cell_range(doc, args["range"])
    after = _normalize(_cells(args), rng)
    before = [list(r) for r in rng.getFormulaArray()]
    return {"before": before, "after": after, "snapshot": snap(json.dumps(before)),
            "summary": f"Write {len(after)}×{len(after[0])} cells at {args['range']}"}


def apply_write_range(doc, args: dict) -> None:
    # Cell by cell: setFormulaArray() isn't recorded for undo, setFormula() is ("Input").
    rng = cell_range(doc, args["range"])
    for r, row in enumerate(_normalize(_cells(args), rng)):
        for c, v in enumerate(row):
            rng.getCellByPosition(c, r).setFormula(v)


def _formula_args(args: dict) -> dict:
    cell, formula = str(args["cell"]).strip(), str(args["formula"]).strip()
    if ":" in cell:
        raise ToolError("set_formula takes one cell (e.g. B9); use write_range for ranges")
    if not formula.startswith("="):
        formula = "=" + formula
    return {"range": cell, "cells": [[formula]]}


def preview_set_formula(doc, args: dict) -> dict:
    pv = preview_write_range(doc, _formula_args(args))
    pv["summary"] = f"Set {args['cell']} to {_formula_args(args)['cells'][0][0]}"
    return pv


def apply_set_formula(doc, args: dict) -> None:
    apply_write_range(doc, _formula_args(args))


# --- Impress -----------------------------------------------------------------------------------

def slide(doc, n) -> object:
    pages = doc.getDrawPages()
    n = int(n)
    if not 1 <= n <= pages.getCount():
        raise ToolError(f"no slide {n} (the presentation has {pages.getCount()})")
    return pages.getByIndex(n - 1)


def _shapes(page):
    title_shape = body = None
    for i in range(page.getCount()):
        s = page.getByIndex(i)
        t = s.getShapeType()
        if t == "com.sun.star.presentation.TitleTextShape" and title_shape is None:
            title_shape = s
        elif t in ("com.sun.star.presentation.OutlinerShape", "com.sun.star.presentation.SubtitleShape") and body is None:
            body = s
    return title_shape, body


def slide_text(doc, args: dict) -> dict:
    page = slide(doc, args["slide"])
    t, b = _shapes(page)
    return {"slide": int(args["slide"]), "title": t.getString() if t else "", "body": b.getString() if b else ""}


def preview_set_slide_text(doc, args: dict) -> dict:
    before = slide_text(doc, args)
    after = {"slide": before["slide"], "title": args.get("title", before["title"]),
             "body": args.get("body", before["body"])}
    t, b = _shapes(slide(doc, args["slide"]))
    if "title" in args and t is None or "body" in args and b is None:
        raise ToolError("this slide has no title/body placeholder to write into")
    return {"before": before, "after": after, "snapshot": snap(json.dumps(before)),
            "summary": f"Change the text of slide {before['slide']}"}


def apply_set_slide_text(doc, args: dict) -> None:
    # Impress doesn't record API text changes for undo at all, so register our own undo action.
    t, b = _shapes(slide(doc, args["slide"]))
    before = (t.getString() if t else None, b.getString() if b else None)

    def put(title_text, body_text) -> None:
        if t is not None and title_text is not None:
            t.setString(title_text)
        if b is not None and body_text is not None:
            b.setString(body_text)

    after = (str(args["title"]) if "title" in args else before[0],
             str(args["body"]) if "body" in args else before[1])
    put(*after)
    doc.getUndoManager().addUndoAction(
        UndoAction(f"Assistant: edit slide {args['slide']}", lambda: put(*before), lambda: put(*after)))


try:  # only inside LibreOffice / with a UNO bridge
    import unohelper
    from com.sun.star.document import XUndoAction

    class UndoAction(unohelper.Base, XUndoAction):
        def __init__(self, title: str, undo, redo) -> None:
            self.Title = title
            self._undo, self._redo = undo, redo

        def undo(self) -> None:
            self._undo()

        def redo(self) -> None:
            self._redo()
except ImportError:  # imported without UNO (e.g. schema generation)
    UndoAction = None


# --- registry ----------------------------------------------------------------------------------

READ = {
    "doc_info": (doc_info, {"writer", "calc", "impress"}),
    "get_selection": (get_selection, {"writer", "calc"}),
    "outline": (outline, {"writer"}),
    "get_paragraphs": (get_paragraphs, {"writer"}),
    "read_range": (read_range, {"calc"}),
    "used_range": (used_range, {"calc"}),
    "slide_text": (slide_text, {"impress"}),
}
EDIT = {
    "replace_selection": (preview_replace_selection, apply_replace_selection, {"writer"},
                          lambda a: "replace selection"),
    "write_range": (preview_write_range, apply_write_range, {"calc"}, lambda a: f"write {a.get('range')}"),
    "set_formula": (preview_set_formula, apply_set_formula, {"calc"}, lambda a: f"formula in {a.get('cell')}"),
    "set_slide_text": (preview_set_slide_text, apply_set_slide_text, {"impress"},
                       lambda a: f"edit slide {a.get('slide')}"),
}


def snap(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()[:16]


def _check(doc, tool: str, table: dict):
    if tool not in table:
        raise ToolError(f"unknown tool {tool!r}")
    k = kind(doc)
    if k not in table[tool][-2 if table is EDIT else -1]:
        raise ToolError(f"{tool} isn't available for a {k} document")


def read(doc, tool: str, args: dict) -> dict:
    _check(doc, tool, READ)
    return READ[tool][0](doc, args)


def preview(doc, tool: str, args: dict) -> dict:
    _check(doc, tool, EDIT)
    return EDIT[tool][0](doc, args)


def apply(doc, tool: str, args: dict, snapshot: str) -> dict:
    _check(doc, tool, EDIT)
    prev, act, _, describe = EDIT[tool]
    if prev(doc, args)["snapshot"] != snapshot:
        raise ToolError("the document changed since the preview; make a new preview")
    name = f"Assistant: {describe(args)}"
    undo = doc.getUndoManager()
    undo.enterUndoContext(name)
    try:
        act(doc, args)
    finally:
        undo.leaveUndoContext()
    return {"applied": True, "undo": name}
