#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""pdf-sections' check: every page there once and in order, the page count the PDF's own, and text on its pages (a
scanned PDF has none: said, so the pictures are looked at instead)."""

import json
import re
import subprocess
import sys


def main() -> int:
    with open(sys.argv[1], encoding="utf-8") as f:
        data = json.load(f)
    found, bad = [], False
    pages = data.get("pages") or []
    info = subprocess.run(["pdfinfo", data.get("source", "")], capture_output=True, text=True, timeout=60).stdout
    m = re.search(r"^Pages:\s+(\d+)", info, re.M)
    want = int(m.group(1)) if m else -1
    if [p.get("page") for p in pages] != list(range(1, len(pages) + 1)):
        found.append("the pages aren't 1..N in order")
        bad = True
    if want >= 0 and len(pages) != want:
        found.append(f"{len(pages)} pages kept, the PDF has {want}")
        bad = True
    empty = [p["page"] for p in pages if not str(p.get("text", "")).strip()]
    if pages and len(empty) == len(pages):
        found.append("no page has text: a scanned PDF (look at its pages instead)")
        bad = True
    elif empty:
        found.append(f"{len(empty)} pages without text (pictures or blank): {empty[:10]}")
    found.append(f"{len(pages)} pages, {len(data.get('sections') or [])} headings")
    print(json.dumps(found))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
