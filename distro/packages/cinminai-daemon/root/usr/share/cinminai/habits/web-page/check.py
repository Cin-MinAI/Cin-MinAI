#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""web-page's check: something was read (text or a table), and each table's rows are the same width (a table whose rows
differ is said, not failed: merged cells are real)."""

import json
import sys


def main() -> int:
    with open(sys.argv[1], encoding="utf-8") as f:
        data = json.load(f)
    found = []
    blocks, tables = data.get("blocks") or [], data.get("tables") or []
    words = sum(len(b.get("text", "").split()) for b in blocks)
    if not blocks and not tables:
        print(json.dumps(["nothing read: no text and no tables (a page drawn by scripts? keep it as a file and look)"]))
        return 1
    for i, t in enumerate(tables, 1):
        widths = {len(r) for r in t.get("rows", [])}
        if len(widths) > 1:
            found.append(f"table {i} has rows of {sorted(widths)} cells (merged cells, or a layout table)")
    found.append(f"{len(blocks)} blocks ({words} words), {len(tables)} tables, {len(data.get('links') or [])} links")
    print(json.dumps(found))
    return 0


if __name__ == "__main__":
    sys.exit(main())
