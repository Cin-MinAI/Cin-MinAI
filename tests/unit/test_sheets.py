# SPDX-License-Identifier: GPL-3.0-or-later
"""New spreadsheets (src/cin_minai/daemon/sheets.py, SPEC §7.9, D53): the model says what the sheet is for,
our code writes every formula, and no file is ever overwritten. The totals are checked in a real
LibreOffice by tests/integration/check_libreoffice.py.

    python3 -m unittest tests.unit.test_sheets -v        (from the repo root)
"""

import datetime as dt
import os
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))

from cin_minai.daemon import sheets  # noqa: E402

T = "{urn:oasis:names:tc:opendocument:xmlns:table:1.0}"


class Plan(unittest.TestCase):
    def test_finds_date_and_amount(self):
        p = sheets.plan(["Date", "Item", "Amount"], "by_month")
        self.assertEqual((p["date"], p["money"], p["total"]), (0, 2, "by_month"))

    def test_by_month_without_a_date_adds_one(self):
        p = sheets.plan(["Item", "Cost"], "by_month")
        self.assertEqual(p["columns"], ["Date", "Item", "Cost"])
        self.assertEqual((p["date"], p["money"]), (0, 2))

    def test_other_languages(self):
        p = sheets.plan(["Fecha", "Concepto", "Importe"], "by_month")
        self.assertEqual((p["date"], p["money"]), (0, 2))
        p = sheets.plan(["Datum", "Was", "Betrag"], "sum")
        self.assertEqual(p["money"], 2)

    def test_a_list_without_totals(self):
        p = sheets.plan(["Title", "Year", "Watched"], "none")
        self.assertEqual(p["total"], "none")
        self.assertEqual(sheets.plan([], "none")["columns"], ["Item", "Amount"])

    def test_sum_falls_back_to_the_last_column(self):
        self.assertEqual(sheets.plan(["Name", "Donation"], "sum")["money"], 1)


class MonthlyRequests(unittest.TestCase):
    """The guide picked "sum" for the Spanish and German versions of Ian's request (A/B 2026-09-30)."""

    def test_six_languages(self):
        for text in ("a list that adds up the total spent for each month",
                     "una lista de gastos que sume el total de cada mes",
                     "eine Liste, die für jeden Monat die Summe ausrechnet",
                     "le total de chaque mois", "o total de cada mês", "毎月の合計"):
            self.assertEqual(sheets.wants_by_month(text, "sum"), "by_month", text)

    def test_otherwise_unchanged(self):
        self.assertEqual(sheets.wants_by_month("money for the garden club, with a total", "sum"), "sum")
        self.assertEqual(sheets.wants_by_month("each month", "none"), "none")  # a plain list stays a list
        self.assertEqual(sheets.wants_by_month("una mesa de madera", "sum"), "sum")  # "mesa" isn't "mes"


class Files(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def make(self, **kw):
        args = dict(title="Monthly expenses", columns=["Date", "Item", "Amount"], total="by_month",
                    today=dt.date(2026, 9, 30))
        args.update(kw)
        return sheets.make(self.dir, **args)

    def content(self, path):
        with zipfile.ZipFile(path) as z:
            first = z.infolist()[0]
            self.assertEqual((first.filename, first.compress_type), ("mimetype", zipfile.ZIP_STORED))
            return ET.fromstring(z.read("content.xml"))

    def test_never_overwrites(self):
        a, b = self.make()["file"], self.make()["file"]
        self.assertEqual(os.path.basename(a), "Monthly expenses.ods")
        self.assertEqual(os.path.basename(b), "Monthly expenses (2).ods")

    def test_title_cant_escape_the_folder(self):
        f = self.make(title="../../etc/passwd")["file"]
        self.assertEqual(os.path.dirname(f), self.dir)

    def test_by_month_has_twelve_month_formulas_and_a_year_total(self):
        root = self.content(self.make()["file"])
        tables = root.iter(T + "table")
        names = [t.get(T + "name") for t in root.iter(T + "table")]
        self.assertEqual(names, ["Entries", "Totals by month"])
        totals = [t for t in root.iter(T + "table") if t.get(T + "name") == "Totals by month"][0]
        formulas = [c.get(T + "formula") for c in totals.iter(T + "table-cell") if c.get(T + "formula")]
        self.assertEqual(len(formulas), 13)
        self.assertTrue(all("SUMIFS([Entries.$C$2:.$C$1000]" in f for f in formulas[:12]))
        self.assertEqual(formulas[-1], "of:=SUM([.B2:.B13])")
        dates = [c.get("{urn:oasis:names:tc:opendocument:xmlns:office:1.0}date-value") for c in totals.iter(T + "table-cell")]
        self.assertIn("2026-01-01", dates)
        self.assertIn("2026-12-01", dates)

    def test_sum_sits_beside_the_list(self):
        root = self.content(self.make(title="Garden club", columns=["Name", "Amount"], total="sum",
                                      rows=[["Ann", "20"], ["Bob", "$15.50"]])["file"])
        cells = [c for c in root.iter(T + "table-cell")]
        self.assertIn("of:=SUM([.B2:.B1000])", [c.get(T + "formula") for c in cells])
        values = [c.get("{urn:oasis:names:tc:opendocument:xmlns:office:1.0}value") for c in cells]
        self.assertIn("15.5", values)  # "$15.50" became a number

    def test_example_dates_become_dates(self):
        root = self.content(self.make(rows=[["2026-09-02", "Rent", "900"]])["file"])
        dv = [c.get("{urn:oasis:names:tc:opendocument:xmlns:office:1.0}date-value") for c in root.iter(T + "table-cell")]
        self.assertIn("2026-09-02", dv)

    def test_text_is_escaped(self):
        root = self.content(self.make(columns=["A & B <C>", "Amount"], total="sum")["file"])
        self.assertIn("A & B <C>", ["".join(c.itertext()) for c in root.iter(T + "table-cell")])


if __name__ == "__main__":
    unittest.main()
