#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""table-rows: a CSV or TSV file as rows keyed by its header (the delimiter found from the file itself)."""

import csv
import json
import sys


def main() -> int:
    with open(sys.argv[1], encoding="utf-8") as f:
        path = json.load(f).get("path", "")
    with open(path, encoding="utf-8-sig", errors="replace", newline="") as f:
        sample = f.read(65536)
        f.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",\t;|")
        except csv.Error:
            dialect = csv.excel_tab if path.lower().endswith(".tsv") else csv.excel
        reader = csv.reader(f, dialect)
        header = next(reader, [])
        columns = [h.strip() for h in header]
        rows, ragged = [], 0
        for raw in reader:
            if not any(cell.strip() for cell in raw):
                continue
            if len(raw) != len(columns):
                ragged += 1
            rows.append({c: (raw[i].strip() if i < len(raw) else "") for i, c in enumerate(columns)})
    with open(sys.argv[2], "w", encoding="utf-8") as f:
        json.dump({"source": path, "columns": columns, "rows": rows, "count": len(rows), "ragged": ragged}, f,
                  ensure_ascii=False, indent=1)
    print(f"{len(rows)} rows, {len(columns)} columns")
    return 0


if __name__ == "__main__":
    sys.exit(main())
