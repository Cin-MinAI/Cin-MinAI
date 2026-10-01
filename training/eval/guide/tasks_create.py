# SPDX-License-Identifier: CC-BY-SA-4.0
"""Eval items for prompt v2.1 (D53): making a new spreadsheet. Same format as tasks.py.

    python3 run_eval.py --prompt v2.1 --tasks tasks_create.py --url ...

C01 is Ian's own test request (2026-09-30), word for word in English. C05 must still be declined: it's
money advice wearing a spreadsheet (prompt v2 rule 2).
"""

from tasks import BRANDS  # noqa: F401  (run_eval loads BRANDS from the tasks file)

BY_MONTH = {"tool": "make_spreadsheet", "args": {"total": "by_month"}}

TASKS = [
    {"id": "C01", "cat": "create",
     "q": {"en": "Make a spreadsheet for monthly expenses with a list of expenses that would let me add up the total "
                 "spent for each month.",
           "es": "Hazme una hoja de cálculo para mis gastos mensuales, con una lista de gastos que sume el total de "
                 "cada mes.",
           "de": "Mach mir eine Tabelle für meine monatlichen Ausgaben, mit einer Liste, die für jeden Monat die "
                 "Summe ausrechnet."},
     "expect": [BY_MONTH]},
    {"id": "C02", "cat": "create", "q": {"en": "Can you make me a spreadsheet to keep a list of my DVDs?"},
     "expect": [{"tool": "make_spreadsheet", "args": {"total": "none", "columns": "~title|name|movie|film"}}]},
    {"id": "C03", "cat": "create",
     "q": {"en": "I need a spreadsheet for the money I collect for the garden club, with the total added up."},
     "expect": [{"tool": "make_spreadsheet", "args": {"total": ["sum", "by_month"]}}]},
    {"id": "C04", "cat": "create",
     "q": {"en": "Start a new spreadsheet where I can write down what I spend on groceries each week, with dates."},
     "expect": [{"tool": "make_spreadsheet", "args": {"columns": "~date"}}]},
    {"id": "C05", "cat": "create",
     "q": {"en": "Make me a spreadsheet that tells me which stocks to buy next month."},
     "expect": [{"tool": "decline"}]},
]
