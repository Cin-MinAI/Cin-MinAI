#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""table-rows' check: a header with no empty or repeated names, the count the rows', and every row with the same
number of cells as the header (a ragged row fails: a value would land under the wrong column)."""

import json
import sys


def main() -> int:
    with open(sys.argv[1], encoding="utf-8") as f:
        data = json.load(f)
    found, bad = [], False
    columns, rows = data.get("columns") or [], data.get("rows") or []
    if not columns or any(not c for c in columns):
        found.append("the header has an empty column name")
        bad = True
    if len(set(columns)) != len(columns):
        found.append("the header repeats a column name")
        bad = True
    if data.get("count") != len(rows):
        found.append(f"count says {data.get('count')}, {len(rows)} rows kept")
        bad = True
    if data.get("ragged"):
        found.append(f"{data['ragged']} rows don't have one cell per column")
        bad = True
    found.append(f"{len(rows)} rows, {len(columns)} columns")
    print(json.dumps(found))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
