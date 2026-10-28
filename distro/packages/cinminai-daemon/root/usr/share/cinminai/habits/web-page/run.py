#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""web-page: a page's title, headings and paragraphs, its tables as rows of cells, and its links, as JSON."""

import json
import sys
import urllib.parse
import urllib.request
from html.parser import HTMLParser

SKIP = {"script", "style", "noscript", "template", "svg", "nav", "footer"}
BLOCKS = {"p", "li", "blockquote", "dd", "dt", "figcaption", "pre"}
HEADINGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
MAX = 8_000_000


class Page(HTMLParser):
    def __init__(self, base: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base, self.skip, self.title, self.in_title = base, 0, "", False
        self.blocks, self.tables, self.links = [], [], []
        self.text, self.kind = [], None
        self.table, self.row, self.cell, self.caption = None, None, None, None
        self.href, self.link_text = None, []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in SKIP:
            self.skip += 1
        elif tag == "title":
            self.in_title = True
        elif tag == "table":
            self.table = {"caption": "", "rows": []}
        elif tag == "caption" and self.table is not None:
            self.caption = []
        elif tag == "tr" and self.table is not None:
            self.row = []
        elif tag in ("td", "th") and self.row is not None:
            self.cell = []
        elif tag in HEADINGS or tag in BLOCKS:
            self.flush()
            self.kind = "heading" if tag in HEADINGS else "text"
        elif tag == "a" and a.get("href"):
            self.href, self.link_text = urllib.parse.urljoin(self.base, a["href"]), []
        elif tag == "br":
            self.add("\n")

    def handle_endtag(self, tag):
        if tag in SKIP:
            self.skip = max(0, self.skip - 1)
        elif tag == "title":
            self.in_title = False
        elif tag == "caption" and self.caption is not None:
            self.table["caption"] = " ".join("".join(self.caption).split())
            self.caption = None
        elif tag in ("td", "th") and self.cell is not None:
            self.row.append(" ".join("".join(self.cell).split()))
            self.cell = None
        elif tag == "tr" and self.row is not None:
            if any(self.row):
                self.table["rows"].append(self.row)
            self.row = None
        elif tag == "table" and self.table is not None:
            if self.table["rows"]:
                self.tables.append(self.table)
            self.table = None
        elif tag in HEADINGS or tag in BLOCKS:
            self.flush()
        elif tag == "a" and self.href:
            text = " ".join("".join(self.link_text).split())
            if self.href.startswith(("http://", "https://")):
                self.links.append({"text": text, "url": self.href})
            self.href = None

    def add(self, data):
        if self.cell is not None:
            self.cell.append(data)
        elif self.caption is not None:
            self.caption.append(data)
        elif self.kind:
            self.text.append(data)
        if self.href:
            self.link_text.append(data)

    def handle_data(self, data):
        if self.skip:
            return
        if self.in_title:
            self.title += data
            return
        self.add(data)

    def flush(self):
        text = " ".join("".join(self.text).split())
        if text and self.kind:
            self.blocks.append({"kind": self.kind, "text": text})
        self.text, self.kind = [], None


def fetch(url: str) -> tuple[str, str]:
    if not url.startswith("https://"):
        raise SystemExit(f"only https addresses: {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Cin-MinAI habit"})
    with urllib.request.urlopen(req, timeout=60) as r:
        raw = r.read(MAX)
        charset = r.headers.get_content_charset() or "utf-8"
    return raw.decode(charset, "replace"), url


def main() -> int:
    with open(sys.argv[1], encoding="utf-8") as f:
        inputs = json.load(f)
    if inputs.get("path"):
        with open(inputs["path"], encoding="utf-8", errors="replace") as f:
            html, source = f.read(), inputs["path"]
        base = inputs.get("url", "")
    else:
        html, source = fetch(inputs.get("url", ""))
        base = source
    page = Page(base)
    page.feed(html)
    page.flush()
    out = {"source": source, "title": " ".join(page.title.split()), "blocks": page.blocks, "tables": page.tables,
           "links": page.links[:500]}
    with open(sys.argv[2], "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"{len(page.blocks)} blocks, {len(page.tables)} tables, {len(page.links)} links")
    return 0


if __name__ == "__main__":
    sys.exit(main())
