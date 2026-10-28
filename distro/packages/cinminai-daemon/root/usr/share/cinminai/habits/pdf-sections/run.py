#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""pdf-sections: a PDF's pages (pdftotext, one page at a time, layout kept) and the headings with their page."""

import json
import re
import subprocess
import sys

HEADING = re.compile(r"^\s{0,8}(?:(?:[IVX]{1,6}|\d{1,2}(?:\.\d{1,2}){0,3}|[A-Z])[.)]\s+\S.{1,70}|[A-Z][A-Z0-9 ,&'/:-]{3,60})\s*$")


def pages_of(path: str) -> int:
    out = subprocess.run(["pdfinfo", path], capture_output=True, text=True, timeout=60).stdout
    m = re.search(r"^Pages:\s+(\d+)", out, re.M)
    return int(m.group(1)) if m else 0


def page_text(path: str, n: int) -> str:
    p = subprocess.run(["pdftotext", "-f", str(n), "-l", str(n), "-layout", "-enc", "UTF-8", path, "-"],
                       capture_output=True, timeout=120)
    return p.stdout.decode("utf-8", "replace")


def main() -> int:
    with open(sys.argv[1], encoding="utf-8") as f:
        path = json.load(f).get("path", "")
    count = pages_of(path)
    if not count:
        print(f"no pages: {path} isn't a PDF pdfinfo can read")
        return 1
    pages, sections = [], []
    for n in range(1, count + 1):
        text = page_text(path, n)
        pages.append({"page": n, "text": text})
        for line in text.splitlines():
            if HEADING.match(line) and len(line.strip()) >= 4 and not line.strip().isdigit():
                sections.append({"title": " ".join(line.split()), "page": n})
    with open(sys.argv[2], "w", encoding="utf-8") as f:
        json.dump({"source": path, "pages": pages, "sections": sections}, f, ensure_ascii=False, indent=1)
    print(f"{count} pages, {len(sections)} headings")
    return 0


if __name__ == "__main__":
    sys.exit(main())
