# SPDX-License-Identifier: GPL-3.0-or-later
"""New Writer documents (D54): a rough draft as an OpenDocument text (.odt), written with the standard
library — no LibreOffice process, nothing of the user's touched, never an existing file.

The page is a small book's: A5, a serif at 12 pt on a fixed 0.62 cm line pitch, so a page holds about
28 lines (Ian: "15-20 pages max with a 25-30 line per page book"). The header says "Rough draft".
"""

from __future__ import annotations

import os
import re
import zipfile
from xml.sax.saxutils import escape

LINES_PER_PAGE = 28
WORDS_PER_LINE = 10  # A5, 12 pt serif, 11.2 cm of text width: about 10 words a line

NS = ('xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
      'xmlns:style="urn:oasis:names:tc:opendocument:xmlns:style:1.0" '
      'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" '
      'xmlns:fo="urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0" '
      'xmlns:svg="urn:oasis:names:tc:opendocument:xmlns:svg-compatible:1.0" office:version="1.3"')

STYLES = f'''<?xml version="1.0" encoding="UTF-8"?>
<office:document-styles {NS}>
<office:font-face-decls><style:font-face style:name="Serif" svg:font-family="'Liberation Serif'" style:font-family-generic="roman"/></office:font-face-decls>
<office:styles>
<style:default-style style:family="paragraph"><style:text-properties style:font-name="Serif" fo:font-size="12pt"/></style:default-style>
<style:style style:name="Standard" style:family="paragraph"/>
<style:style style:name="Body" style:family="paragraph"><style:paragraph-properties fo:line-height="0.62cm" fo:text-indent="0.6cm" fo:text-align="justify" fo:margin-top="0cm" fo:margin-bottom="0cm"/></style:style>
<style:style style:name="First" style:family="paragraph" style:parent-style-name="Body"><style:paragraph-properties fo:text-indent="0cm"/></style:style>
<style:style style:name="Title" style:family="paragraph"><style:paragraph-properties fo:text-align="center" fo:margin-top="1.24cm" fo:margin-bottom="1.24cm"/><style:text-properties fo:font-size="18pt" fo:font-weight="bold"/></style:style>
<style:style style:name="Break" style:family="paragraph"><style:paragraph-properties fo:text-align="center" fo:line-height="1.24cm"/></style:style>
<style:style style:name="Em" style:family="text"><style:text-properties fo:font-style="italic"/></style:style>
<style:style style:name="Header" style:family="paragraph"><style:paragraph-properties fo:text-align="center"/><style:text-properties fo:font-size="9pt" fo:font-style="italic" fo:color="#666666"/></style:style>
</office:styles>
<office:automatic-styles>
<style:page-layout style:name="A5"><style:page-layout-properties fo:page-width="14.8cm" fo:page-height="21cm" fo:margin-top="1.4cm" fo:margin-bottom="1.6cm" fo:margin-left="1.8cm" fo:margin-right="1.8cm"/>
<style:header-style><style:header-footer-properties fo:min-height="0.5cm" fo:margin-bottom="0.3cm"/></style:header-style></style:page-layout>
</office:automatic-styles>
<office:master-styles><style:master-page style:name="Standard" style:page-layout-name="A5">
<style:header><text:p text:style-name="Header">{{header}}</text:p></style:header>
</style:master-page></office:master-styles>
</office:document-styles>'''

MANIFEST = ('<?xml version="1.0" encoding="UTF-8"?>'
            '<manifest:manifest xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0" manifest:version="1.3">'
            '<manifest:file-entry manifest:full-path="/" manifest:media-type="application/vnd.oasis.opendocument.text"/>'
            '<manifest:file-entry manifest:full-path="content.xml" manifest:media-type="text/xml"/>'
            '<manifest:file-entry manifest:full-path="styles.xml" manifest:media-type="text/xml"/>'
            '</manifest:manifest>')


def paragraphs(text: str) -> list[str]:
    """The model's prose as paragraphs: blank lines or single line breaks, headings and stray markup dropped."""
    out = []
    for p in re.split(r"\n\s*\n|\n", text.strip()):
        p = re.sub(r"^\s*(#+\s*)?(Scene \d+[:.]?)?\s*", "", p.replace("**", "")).strip()
        if p and not re.fullmatch(r"[*\-_ ]{3,}", p):
            out.append(p)
    return out


TEXT_NS = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}"


def _text(el) -> str:
    """A paragraph's own text: spaces, tabs and line breaks as spaces; footnote and endnote bodies left out."""
    parts = [el.text or ""]
    for c in el:
        if c.tag in (TEXT_NS + "s", TEXT_NS + "tab", TEXT_NS + "line-break"):
            parts.append(" ")
        elif c.tag != TEXT_NS + "note":
            parts.append(_text(c))
        parts.append(c.tail or "")
    return "".join(parts)


def top_paragraphs(root) -> list[str]:
    """Every paragraph and heading once, in order: paragraphs nested inside another (a footnote, a text frame the
    writer added in Writer) aren't counted again — root.iter() did, found by Qwen3.8-27B reviewing manuscript.py
    (2026-10-02)."""
    out = []

    def walk(el) -> None:
        for c in el:
            if c.tag in (TEXT_NS + "p", TEXT_NS + "h"):
                out.append(re.sub(r"\s+", " ", _text(c)).strip())
            else:
                walk(c)
    walk(root)
    return out


def read(path: str) -> list[str]:
    """The paragraphs of an .odt as it is now — ours, or after the writer edited and saved it in Writer (D57).
    Our header line and scene breaks are left out."""
    import xml.etree.ElementTree as ET
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read("content.xml"))
    return [s for s in top_paragraphs(root) if s and s.replace("*", "").strip()]


def estimate_lines(texts: list[str]) -> int:
    return sum(max(1, -(-len(p.split()) // WORDS_PER_LINE)) for t in texts for p in paragraphs(t))


EMPHASIS = re.compile(r"(?<![\w*])\*(?!\s)([^*\n]+?)(?<!\s)\*(?![\w*])")


def inline(p: str) -> str:
    """Escaped text; the model's *emphasis* (Markdown) becomes italics instead of literal asterisks."""
    return EMPHASIS.sub(lambda m: f'<text:span text:style-name="Em">{m.group(1)}</text:span>', escape(p))


def content(title: str, scenes: list[str]) -> str:
    body = [f'<text:p text:style-name="Title">{escape(title)}</text:p>']
    for i, scene in enumerate(scenes):
        if i:
            body.append('<text:p text:style-name="Break">*   *   *</text:p>')
        for j, p in enumerate(paragraphs(scene)):
            body.append(f'<text:p text:style-name="{"First" if j == 0 else "Body"}">{inline(p)}</text:p>')
    return (f'<?xml version="1.0" encoding="UTF-8"?><office:document-content {NS}>'
            f'<office:body><office:text>{"".join(body)}</office:text></office:body></office:document-content>')


def safe_name(title: str) -> str:
    # trimmed after the cut too: "…reconnecting .odt" (2026-10-01)
    return re.sub(r'[\\/:*?"<>|\x00-\x1f]', "", str(title)).strip(" .")[:60].strip(" .") or "Draft"


def new_path(folder: str, name: str) -> str:
    base = os.path.join(folder, safe_name(name))
    path, n = base + ".odt", 2
    while os.path.exists(path):
        path, n = f"{base} ({n}).odt", n + 1
    return path


def write(folder: str, name: str, title: str, scenes: list[str], header: str = "Rough draft") -> str:
    os.makedirs(folder, exist_ok=True)
    path = new_path(folder, name)
    with open(path, "xb") as f:  # x: never an existing file
        with zipfile.ZipFile(f, "w") as z:
            z.writestr(zipfile.ZipInfo("mimetype"), "application/vnd.oasis.opendocument.text")  # stored, first
            z.writestr("META-INF/manifest.xml", MANIFEST, zipfile.ZIP_DEFLATED)
            z.writestr("styles.xml", STYLES.replace("{header}", escape(header)), zipfile.ZIP_DEFLATED)
            z.writestr("content.xml", content(title, scenes), zipfile.ZIP_DEFLATED)
    return path
