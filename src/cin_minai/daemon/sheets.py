# SPDX-License-Identifier: GPL-3.0-or-later
"""New spreadsheets (SPEC §7.9, D53): the guide says what the sheet is for; this code writes the file.

The model gives a title, the column names, example rows (optional) and the kind of total; every formula
is ours, so it's right: a total of the amount column, or a total for each month from the date column
(SUMIFS on a second sheet). The file is a new OpenDocument spreadsheet (.ods) in the user's Documents
folder — never an existing file (§7.8) — written with the standard library only (no LibreOffice process,
nothing of the user's touched). Opening it is the caller's job.
"""

from __future__ import annotations

import datetime as dt
import os
import re
import zipfile
from xml.sax.saxutils import escape

ROWS = 1000          # formulas cover rows 2..ROWS: room to keep adding
MAX_COLS = 12
DATE_WORDS = re.compile(r"\b(date|day|when|fecha|d[ií]a|data|dia|jour|datum|tag)\b|日付|日", re.I)
MONEY_WORDS = re.compile(r"\b(amount|cost|price|spent|paid|total|sum|value|importe|precio|gasto|valor|"
                         r"montant|prix|co[uû]t|betrag|preis|kosten|summe)\b|[$€£¥]|金額|料金", re.I)
TOTALS = ("none", "sum", "by_month")
# the user asked for totals per month, in any of the six languages (D25): the guide picked "sum" for the
# Spanish and German versions of the same request (A/B 2026-09-30, eval items C01-es, C01-de)
MONTHLY = re.compile(r"\b(month|monthly|months|mes|meses|mensual\w*|monat\w*|mois|mensuel\w*|m[eê]s|mensa\w*)\b|月", re.I)


def wants_by_month(request: str, total: str) -> str:
    return "by_month" if total == "sum" and MONTHLY.search(request or "") else total


def _col(i: int) -> str:
    s, i = "", i + 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def plan(columns: list[str], total: str) -> dict:
    """Which column holds dates and which amounts (from their names); by_month needs a date column, so
    one is added first when the names have none."""
    cols = [str(c).strip()[:40] for c in columns if str(c).strip()][:MAX_COLS] or ["Item", "Amount"]
    total = total if total in TOTALS else "none"
    date = next((i for i, c in enumerate(cols) if DATE_WORDS.search(c)), None)
    if total == "by_month" and date is None:
        cols, date = ["Date"] + cols, 0
    money = next((i for i in range(len(cols) - 1, -1, -1) if MONEY_WORDS.search(cols[i]) and i != date), None)
    if total != "none" and money is None:
        money = len(cols) - 1 if len(cols) - 1 != date else None
    if money is None:
        total = "none"
    return {"columns": cols, "date": date, "money": money, "total": total}


def _cell(v, style: str = "") -> str:
    s = f' table:style-name="{style}"' if style else ""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return f'<table:table-cell{s} office:value-type="float" office:value="{v}"><text:p>{v}</text:p></table:table-cell>'
    if isinstance(v, dt.date):
        return (f'<table:table-cell{s} office:value-type="date" office:date-value="{v.isoformat()}">'
                f'<text:p>{v.isoformat()}</text:p></table:table-cell>')
    return f'<table:table-cell{s} office:value-type="string"><text:p>{escape(str(v))}</text:p></table:table-cell>'


def _formula(f: str, style: str = "") -> str:
    s = f' table:style-name="{style}"' if style else ""
    return f'<table:table-cell{s} table:formula="{escape(f, {chr(34): "&quot;"})}" office:value-type="float"/>'


def _value(text: str, kind: str):
    """An example cell as the right type: '37.50' -> 37.5 in an amount column, '2026-09-30' -> a date."""
    t = str(text).strip()
    if kind == "money":
        try:
            return float(t.replace("$", "").replace("€", "").replace("£", "").replace(",", ""))
        except ValueError:
            return t
    if kind == "date":
        try:
            return dt.date.fromisoformat(t)
        except ValueError:
            return t
    return t


def content(title: str, p: dict, rows: list[list[str]], year: int) -> str:
    cols, date, money = p["columns"], p["date"], p["money"]
    style = lambda i: "date" if i == date else "money" if i == money else ""
    head = "".join(_cell(c, "head") for c in cols)
    body = []
    for r in rows[:50]:
        cells = [_value(r[i] if i < len(r) else "", "date" if i == date else "money" if i == money else "") for i in range(len(cols))]
        body.append("<table:table-row>" + "".join(_cell(v, style(i)) if v != "" else '<table:table-cell/>' for i, v in enumerate(cells)) + "</table:table-row>")
    colspec = "".join(f'<table:table-column table:style-name="wide" table:default-cell-style-name="{style(i) or "Default"}"/>'
                      for i in range(len(cols)))
    sheet1 = "Entries"
    extra_cols, extra_rows = "", ""
    if p["total"] == "sum":
        m = _col(money)
        extra_cols = '<table:table-column table:style-name="wide"/><table:table-column table:style-name="wide"/>'
        # the total sits beside the list, so new rows never push it around
        head += '<table:table-cell/>' + _cell("Total", "head")
        total_cell = _formula(f"of:=SUM([.{m}2:.{m}{ROWS}])", "money")
        if body:
            body[0] = body[0].replace("</table:table-row>", '<table:table-cell/>' + total_cell + "</table:table-row>")
        else:
            body.append("<table:table-row>" + "<table:table-cell/>" * (len(cols) + 1) + total_cell + "</table:table-row>")
    sheets = [f'<table:table table:name="{sheet1}">{colspec}{extra_cols}'
              f'<table:table-row>{head}</table:table-row>{"".join(body)}</table:table>']
    if p["total"] == "by_month":
        d, m = _col(date), _col(money)
        rows_xml = ["<table:table-row>" + _cell("Month", "head") + _cell("Total", "head") + "</table:table-row>"]
        for month in range(1, 13):
            r = month + 1
            f = (f"of:=SUMIFS([{sheet1}.${m}$2:.${m}${ROWS}];[{sheet1}.${d}$2:.${d}${ROWS}];\">=\"&[.A{r}];"
                 f"[{sheet1}.${d}$2:.${d}${ROWS}];\"<\"&DATE(YEAR([.A{r}]);MONTH([.A{r}])+1;1))")
            rows_xml.append("<table:table-row>" + _cell(dt.date(year, month, 1), "month") + _formula(f, "money") + "</table:table-row>")
        rows_xml.append("<table:table-row>" + _cell(f"Year {year}", "head") + _formula("of:=SUM([.B2:.B13])", "money") + "</table:table-row>")
        sheets.append('<table:table table:name="Totals by month"><table:table-column table:style-name="wide"/>'
                      '<table:table-column table:style-name="wide"/>' + "".join(rows_xml) + "</table:table>")
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
        'xmlns:style="urn:oasis:names:tc:opendocument:xmlns:style:1.0" '
        'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" '
        'xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0" '
        'xmlns:fo="urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0" '
        'xmlns:number="urn:oasis:names:tc:opendocument:xmlns:datastyle:1.0" '
        'xmlns:of="urn:oasis:names:tc:opendocument:xmlns:of:1.2" office:version="1.3">'
        '<office:automatic-styles>'
        '<number:date-style style:name="Ndate" number:automatic-order="true"><number:day/><number:text>/</number:text>'
        '<number:month/><number:text>/</number:text><number:year number:style="long"/></number:date-style>'
        '<number:date-style style:name="Nmonth"><number:month number:style="long" number:textual="true"/>'
        '<number:text> </number:text><number:year number:style="long"/></number:date-style>'
        '<number:number-style style:name="Nmoney"><number:number number:decimal-places="2" '
        'number:min-decimal-places="2" number:min-integer-digits="1" number:grouping="true"/></number:number-style>'
        '<style:style style:name="wide" style:family="table-column"><style:table-column-properties style:column-width="1.4in"/></style:style>'
        '<style:style style:name="head" style:family="table-cell"><style:text-properties fo:font-weight="bold"/></style:style>'
        '<style:style style:name="date" style:family="table-cell" style:data-style-name="Ndate"/>'
        '<style:style style:name="month" style:family="table-cell" style:data-style-name="Nmonth"/>'
        '<style:style style:name="money" style:family="table-cell" style:data-style-name="Nmoney"/>'
        '</office:automatic-styles>'
        f'<office:body><office:spreadsheet>{"".join(sheets)}</office:spreadsheet></office:body></office:document-content>')


MANIFEST = ('<?xml version="1.0" encoding="UTF-8"?>'
            '<manifest:manifest xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0" manifest:version="1.3">'
            '<manifest:file-entry manifest:full-path="/" manifest:media-type="application/vnd.oasis.opendocument.spreadsheet"/>'
            '<manifest:file-entry manifest:full-path="content.xml" manifest:media-type="text/xml"/>'
            '</manifest:manifest>')


def safe_name(title: str) -> str:
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "", str(title)).strip(" .")[:60].strip(" .")
    return name or "Spreadsheet"


def new_path(folder: str, title: str) -> str:
    """A path that doesn't exist yet: "Monthly expenses.ods", then "Monthly expenses (2).ods"…"""
    base = os.path.join(folder, safe_name(title))
    path, n = base + ".ods", 2
    while os.path.exists(path):
        path, n = f"{base} ({n}).ods", n + 1
    return path


def make(folder: str, title: str, columns: list[str], rows: list[list[str]] | None = None, total: str = "none",
         today: dt.date | None = None) -> dict:
    p = plan(columns, total)
    os.makedirs(folder, exist_ok=True)
    path = new_path(folder, title)
    year = (today or dt.date.today()).year
    with open(path, "xb") as f:  # x: never an existing file, even in a race
        with zipfile.ZipFile(f, "w") as z:
            z.writestr(zipfile.ZipInfo("mimetype"), "application/vnd.oasis.opendocument.spreadsheet")  # stored, first
            z.writestr("META-INF/manifest.xml", MANIFEST, zipfile.ZIP_DEFLATED)
            z.writestr("content.xml", content(title, p, rows or [], year), zipfile.ZIP_DEFLATED)
    return {"file": path, "columns": p["columns"], "total": p["total"],
            "sheets": ["Entries"] + (["Totals by month"] if p["total"] == "by_month" else [])}
