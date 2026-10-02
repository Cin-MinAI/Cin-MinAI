# SPDX-License-Identifier: GPL-3.0-or-later
"""A finished story as a manuscript (PLAN D58): the chapters as they are now — the writer's own edits in Writer
included — gathered into one new document in standard manuscript format, as .odt and .docx (agents and
publishers mostly ask for Word). Written by our code alone, no model; the drafts are never touched.

The format: 12 pt Times New Roman, double-spaced, 2.54 cm (1 inch) margins, US Letter where people use it and A4
elsewhere; a title page (the author's name and contact, the word count, the title and "by" line halfway down, no
header); on every other page a header "Surname / SHORT TITLE / page"; each chapter on a new page, a third of
the way down; "#" between scenes; "THE END".
"""

from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
import zipfile
from xml.sax.saxutils import escape

from . import odt
from .projects import Project

TEXT = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}"
LETTER_REGIONS = {"US", "CA", "MX", "PH", "CL", "CO", "VE", "GT", "CR", "PA", "PR", "DO", "SV", "NI", "HN", "BO"}


# --- gathering ----------------------------------------------------------------------------------------------
def read_scenes(path: str) -> tuple[str, list[list[str]]]:
    """(title, scenes) of a draft as the file is now: the first paragraph is its title, a paragraph of only
    asterisks (ours) or "#" is a scene break; our "Chapter n — " in the title is left out."""
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read("content.xml"))
    paras = odt.top_paragraphs(root)  # each paragraph once; footnote bodies out (2026-10-02)
    paras = [p for p in paras if p]
    if not paras:
        return "", []
    title, scenes = re.sub(r"^Chapter \d+ — ", "", paras[0]), [[]]
    for p in paras[1:]:
        if re.fullmatch(r"[*#\s]+", p):
            if scenes[-1]:
                scenes.append([])
        else:
            scenes[-1].append(p)
    return title, [s for s in scenes if s]


def gather(project: Project) -> list[dict]:
    """The chapters to print: for a story over chapters, the newest draft of each chapter, in order; for a story
    in one chapter, its newest draft. Drafts whose file is gone are skipped."""
    drafts = [d for d in project.data["drafts"] if os.path.isfile(os.path.join(project.folder, d["file"]))]
    numbered = [d for d in drafts if d.get("chapter")]
    if numbered:
        newest = {d["chapter"]: d for d in numbered}
        chosen = [newest[k] for k in sorted(newest)]
    else:
        chosen = drafts[-1:]
    out = []
    for d in chosen:
        title, scenes = read_scenes(os.path.join(project.folder, d["file"]))
        if scenes:
            out.append({"chapter": d.get("chapter"), "title": title or d["title"], "scenes": scenes, "file": d["file"]})
    return out


def word_count(chapters: list[dict]) -> int:
    return sum(len(p.split()) for c in chapters for s in c["scenes"] for p in s)


def rounded(words: int) -> str:
    """The title page's count, rounded as agents expect: to the hundred for short work, the thousand for long."""
    n = round(words, -2) if words < 10000 else round(words, -3)
    return f"about {max(n, 100):,} words"


def letter_paper() -> bool:
    loc = os.environ.get("LC_PAPER") or os.environ.get("LC_ALL") or os.environ.get("LANG") or ""
    m = re.match(r"[a-z]{2,3}_([A-Z]{2})", loc)
    return bool(m and m.group(1) in LETTER_REGIONS)


def header_text(author: str, title: str) -> str:
    surname = (author.split() or ["Author"])[-1]
    short = " ".join(title.split()[:4]).upper()
    return f"{surname} / {short} / "


def heading(c: dict, numbered: bool) -> tuple[str, str]:
    return (f"Chapter {c['chapter']}", c["title"]) if numbered else ("", "")


# --- OpenDocument -------------------------------------------------------------------------------------------
def odt_styles(letter: bool, header: str) -> str:
    w, h = ("21.59cm", "27.94cm") if letter else ("21cm", "29.7cm")
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<office:document-styles {odt.NS}>
<office:font-face-decls><style:font-face style:name="Times New Roman" svg:font-family="'Times New Roman'" style:font-family-generic="roman"/></office:font-face-decls>
<office:styles>
<style:default-style style:family="paragraph"><style:text-properties style:font-name="Times New Roman" fo:font-size="12pt"/></style:default-style>
<style:style style:name="Standard" style:family="paragraph"/>
<style:style style:name="Body" style:family="paragraph"><style:paragraph-properties fo:line-height="200%" fo:text-indent="1.27cm" fo:margin-top="0cm" fo:margin-bottom="0cm"/></style:style>
<style:style style:name="First" style:family="paragraph" style:parent-style-name="Body"><style:paragraph-properties fo:text-indent="0cm"/></style:style>
<style:style style:name="Contact" style:family="paragraph"><style:paragraph-properties fo:line-height="100%"/></style:style>
<style:style style:name="Count" style:family="paragraph"><style:paragraph-properties fo:text-align="end" fo:line-height="100%"/></style:style>
<style:style style:name="Title" style:family="paragraph"><style:paragraph-properties fo:text-align="center" fo:margin-top="7cm" fo:line-height="200%"/></style:style>
<style:style style:name="Byline" style:family="paragraph"><style:paragraph-properties fo:text-align="center" fo:line-height="200%"/></style:style>
<style:style style:name="ChapterFirst" style:family="paragraph" style:master-page-name="Manuscript"><style:paragraph-properties fo:text-align="center" fo:margin-top="7cm" fo:line-height="200%"/></style:style>
<style:style style:name="Chapter" style:family="paragraph"><style:paragraph-properties fo:break-before="page" fo:text-align="center" fo:margin-top="7cm" fo:line-height="200%"/></style:style>
<style:style style:name="ChapterTitle" style:family="paragraph"><style:paragraph-properties fo:text-align="center" fo:line-height="200%" fo:margin-bottom="0.85cm"/></style:style>
<style:style style:name="Break" style:family="paragraph"><style:paragraph-properties fo:text-align="center" fo:line-height="200%"/></style:style>
<style:style style:name="End" style:family="paragraph"><style:paragraph-properties fo:text-align="center" fo:line-height="200%" fo:margin-top="0.85cm"/></style:style>
<style:style style:name="Header" style:family="paragraph"><style:paragraph-properties fo:text-align="end"/></style:style>
</office:styles>
<office:automatic-styles>
<style:page-layout style:name="Page"><style:page-layout-properties fo:page-width="{w}" fo:page-height="{h}" fo:margin-top="1.27cm" fo:margin-bottom="2.54cm" fo:margin-left="2.54cm" fo:margin-right="2.54cm"/>
<style:header-style><style:header-footer-properties fo:min-height="0.6cm" fo:margin-bottom="0.67cm"/></style:header-style></style:page-layout>
</office:automatic-styles>
<office:master-styles>
<style:master-page style:name="Standard" style:page-layout-name="Page"/>
<style:master-page style:name="Manuscript" style:page-layout-name="Page">
<style:header><text:p text:style-name="Header">{escape(header)}<text:page-number text:select-page="current"/></text:p></style:header>
</style:master-page>
</office:master-styles>
</office:document-styles>'''


def odt_content(title: str, author: str, contact: str, words: int, chapters: list[dict]) -> str:
    p = lambda style, text: f'<text:p text:style-name="{style}">{escape(text)}</text:p>'  # noqa: E731
    body = [p("Contact", author)] + [p("Contact", line) for line in contact.splitlines() if line.strip()]
    body += [p("Count", rounded(words)), p("Title", title.upper()), p("Byline", f"by {author}")]
    numbered = len(chapters) > 1 or bool(chapters and chapters[0]["chapter"])
    for i, c in enumerate(chapters):
        first, second = heading(c, numbered)
        style = "ChapterFirst" if i == 0 else "Chapter"
        if numbered:
            body += [p(style, first), p("ChapterTitle", second)]
        else:  # a story in one chapter: the text starts on the first manuscript page
            body.append(f'<text:p text:style-name="{style}"/>')
        for j, scene in enumerate(c["scenes"]):
            if j:
                body.append(p("Break", "#"))
            body += [p("First" if k == 0 else "Body", para) for k, para in enumerate(scene)]
    body.append(p("End", "THE END"))
    return (f'<?xml version="1.0" encoding="UTF-8"?><office:document-content {odt.NS}>'
            f'<office:body><office:text>{"".join(body)}</office:text></office:body></office:document-content>')


def write_odt(path: str, title: str, author: str, contact: str, chapters: list[dict], letter: bool) -> None:
    words = word_count(chapters)
    with open(path, "xb") as f:  # x: never an existing file
        with zipfile.ZipFile(f, "w") as z:
            z.writestr(zipfile.ZipInfo("mimetype"), "application/vnd.oasis.opendocument.text")
            z.writestr("META-INF/manifest.xml", odt.MANIFEST, zipfile.ZIP_DEFLATED)
            z.writestr("styles.xml", odt_styles(letter, header_text(author, title)), zipfile.ZIP_DEFLATED)
            z.writestr("content.xml", odt_content(title, author, contact, words, chapters), zipfile.ZIP_DEFLATED)


# --- Word (.docx) -------------------------------------------------------------------------------------------
W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" ' \
    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
CONTENT_TYPES = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                 '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                 '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                 '<Default Extension="xml" ContentType="application/xml"/>'
                 '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
                 '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
                 '<Override PartName="/word/header1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml"/>'
                 '</Types>')
RELS = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
        '</Relationships>')
DOC_RELS = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/header" Target="header1.xml"/>'
            '</Relationships>')
DOCX_STYLES = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:styles {W}>'
               '<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" '
               'w:cs="Times New Roman" w:eastAsia="Times New Roman"/><w:sz w:val="24"/><w:szCs w:val="24"/></w:rPr>'
               '</w:rPrDefault><w:pPrDefault><w:pPr><w:spacing w:before="0" w:after="0" w:line="480" w:lineRule="auto"/>'
               '</w:pPr></w:pPrDefault></w:docDefaults>'
               '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>'
               '</w:styles>')


def docx_p(text: str, center=False, right=False, indent=False, before=0, page_break=False, single=False) -> str:
    ppr = ""
    if page_break:
        ppr += "<w:pageBreakBefore/>"
    if before or single:
        ppr += f'<w:spacing w:before="{before}" w:after="0"' + (' w:line="240" w:lineRule="auto"' if single else "") + "/>"
    if indent:
        ppr += '<w:ind w:firstLine="720"/>'
    if center or right:
        ppr += f'<w:jc w:val="{"center" if center else "right"}"/>'
    run = f'<w:r><w:t xml:space="preserve">{escape(text)}</w:t></w:r>' if text else ""
    return f"<w:p>{'<w:pPr>' + ppr + '</w:pPr>' if ppr else ''}{run}</w:p>"


def docx_document(title: str, author: str, contact: str, words: int, chapters: list[dict], letter: bool) -> str:
    body = [docx_p(author, single=True)] + [docx_p(line, single=True) for line in contact.splitlines() if line.strip()]
    body += [docx_p(rounded(words), right=True, single=True), docx_p(title.upper(), center=True, before=3960),
             docx_p(f"by {author}", center=True)]
    numbered = len(chapters) > 1 or bool(chapters and chapters[0]["chapter"])
    for c in chapters:
        first, second = heading(c, numbered)
        if numbered:
            body += [docx_p(first, center=True, before=3960, page_break=True), docx_p(second, center=True), docx_p("")]
        else:
            body.append(docx_p("", page_break=True, before=3960))
        for j, scene in enumerate(c["scenes"]):
            if j:
                body.append(docx_p("#", center=True))
            body += [docx_p(para, indent=k > 0) for k, para in enumerate(scene)]
    body.append(docx_p("THE END", center=True, before=480))
    w, h = (12240, 15840) if letter else (11906, 16838)
    sect = (f'<w:sectPr><w:headerReference w:type="default" r:id="rId2"/><w:pgSz w:w="{w}" w:h="{h}"/>'
            '<w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" w:header="720" w:footer="720" w:gutter="0"/>'
            '<w:titlePg/></w:sectPr>')  # titlePg: the title page has its own (empty) header
    return (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document {W}><w:body>{"".join(body)}'
            f'{sect}</w:body></w:document>')


def docx_header(text: str) -> str:
    return (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:hdr {W}><w:p><w:pPr><w:spacing w:line="240" '
            f'w:lineRule="auto"/><w:jc w:val="right"/></w:pPr><w:r><w:t xml:space="preserve">{escape(text)}</w:t></w:r>'
            '<w:fldSimple w:instr=" PAGE "><w:r><w:t>1</w:t></w:r></w:fldSimple></w:p></w:hdr>')


def write_docx(path: str, title: str, author: str, contact: str, chapters: list[dict], letter: bool) -> None:
    words = word_count(chapters)
    with open(path, "xb") as f:
        with zipfile.ZipFile(f, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("[Content_Types].xml", CONTENT_TYPES)
            z.writestr("_rels/.rels", RELS)
            z.writestr("word/_rels/document.xml.rels", DOC_RELS)
            z.writestr("word/styles.xml", DOCX_STYLES)
            z.writestr("word/header1.xml", docx_header(header_text(author, title)))
            z.writestr("word/document.xml", docx_document(title, author, contact, words, chapters, letter))


# --- the whole -----------------------------------------------------------------------------------------------
def free_base(folder: str, name: str) -> str:
    """A base name free as both .odt and .docx: never overwrites."""
    base, n = os.path.join(folder, odt.safe_name(name)), 2
    stem = base
    while os.path.exists(base + ".odt") or os.path.exists(base + ".docx"):
        base, n = f"{stem} ({n})", n + 1
    return base


def make(project: Project, author: str, contact: str = "", letter: bool | None = None) -> dict:
    chapters = gather(project)
    if not chapters:
        raise ValueError("there's nothing written yet to put in a manuscript")
    author = re.sub(r"\s+", " ", author).strip() or "Author"
    letter = letter_paper() if letter is None else letter
    base = free_base(project.folder, f"{project.title} — manuscript")
    write_odt(base + ".odt", project.title, author, contact, chapters, letter)
    write_docx(base + ".docx", project.title, author, contact, chapters, letter)
    return {"odt": base + ".odt", "docx": base + ".docx", "chapters": len(chapters), "words": word_count(chapters),
            "paper": "Letter" if letter else "A4", "files": [c["file"] for c in chapters]}
