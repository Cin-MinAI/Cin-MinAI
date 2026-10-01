#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""The writer with the real model (PLAN D54): gather ideas over a few messages, outline, write the chapter,
count its pages in LibreOffice. Uses the daemon's config (its model and llama-server); stop the user's daemon
first (they share the server's socket). Writes into a throwaway folder, never the user's Documents.

    python3 tests/integration/check_writer.py [OUT_DIR]        (from the repo root)
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))

from cin_minai.daemon import config  # noqa: E402
from cin_minai.daemon.projects import Project  # noqa: E402
from cin_minai.daemon.writer import Writer  # noqa: E402
from cin_minai.inference.llamacpp import LlamaCppBackend  # noqa: E402

IDEAS = [
    "I want to write a small book. Chapter one: a retired lighthouse keeper, Elias, lives in a little coastal town.",
    "He finds a message in a bottle on the beach. The important thing: the message was written by Elias himself, "
    "forty years ago, when he was a young man.",
    "His neighbour Rosa is cheerful and nosy, and she bakes too much. There's a storm coming in from the sea.",
    "It should be a gentle mystery with a bit of humour. At the end of the chapter he decides to find out why "
    "his younger self threw the bottle into the sea.",
]


def quality(path: str) -> dict:
    """Repeated paragraphs (the same, or 85 % the same words, as an earlier one), scene openings that repeat
    the previous scene's ending, and CJK characters in the text."""
    import html
    from cin_minai.daemon.writer import CJK, _same
    xml = subprocess.run(["unzip", "-p", path, "content.xml"], capture_output=True, text=True).stdout
    paras = [html.unescape(re.sub(r"<[^>]+>", "", p)) for p in re.findall(r"<text:p[^>]*>(.*?)</text:p>", xml)]
    body = [p for p in paras[1:] if p.strip() != "*   *   *"]
    repeats = sum(1 for i, p in enumerate(body) if any(_same(p, q) for q in body[:i]))
    echoes = sum(1 for i, p in enumerate(paras) if i > 1 and paras[i - 1].strip() == "*   *   *" and _same(p, paras[i - 2]))
    return {"paragraphs": len(body), "words": sum(len(p.split()) for p in body), "repeated_paragraphs": repeats,
            "scene_openings_repeating_the_last_ending": echoes, "cjk_chars": sum(len(m) for m in CJK.findall(" ".join(body)))}


def main() -> int:
    out = sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp(prefix="cinminai-writer-")
    cfg = config.load()
    backend = LlamaCppBackend(cfg["inference"], lambda m: None)
    w = Writer(backend.chat)
    cancel = threading.Event()
    try:
        if os.environ.get("WRITER_PROJECT"):  # an existing project's notes, on a copy (the original is untouched)
            import shutil
            src = os.environ["WRITER_PROJECT"]
            dst = os.path.join(out, os.path.basename(src.rstrip("/")))
            shutil.copytree(src, dst, ignore=shutil.ignore_patterns("*.odt", ".~lock*"))
            p = Project.open(dst)
            print(f"project {p.title!r}, {sum(len(v) for v in p.notes.values())} notes (a copy)\n")
        else:
            p = Project.new("The Bottle", root=out)
            t0 = time.monotonic()
            for text in IDEAS:
                reply = w.reply(p, text, lambda t: None, cancel)
                print(f"> {text}\n  {reply}\n")
            print(f"gathering: {time.monotonic() - t0:.0f} s\nNOTES:\n{p.notes_text()}\n")
        # the story's shape (D56): WRITER_SHAPE=chapters:4 writes WRITER_CHAPTERS (default 1) chapters of 4
        shape = os.environ.get("WRITER_SHAPE", "chapter")
        if shape.startswith("chapters"):
            p.set_shape("chapters", int(shape.partition(":")[2] or 4), 1)
        else:
            p.set_shape("chapter")
        for _ in range(int(os.environ.get("WRITER_CHAPTERS", "1"))):
            t0 = time.monotonic()
            review = w.review(p, cancel)  # D57: before every chapter
            print(f"REVIEW ({time.monotonic() - t0:.0f} s), chapters read {review['chapters_read']}, "
                  f"next steps {review['next_steps']}")
            from cin_minai.sidebar import words
            print("\n".join("  " + line for line in words.review_lines(review)))
            t0 = time.monotonic()
            outline = w.outline(p, os.environ.get("WRITER_ANSWERS", ""), cancel, review=review)
            print(f"OUTLINE ({time.monotonic() - t0:.0f} s): chapter {outline['chapter']} of {outline['of']}, "
                  f"{outline['chapter_title']!r}, steps {outline['steps']}")
            for i, s in enumerate(outline["scenes"], 1):
                print(f"  {i}. [{s.get('step_name')}] {s['title']}: {s['what_happens']}")
            t0 = time.monotonic()
            res = w.draft(p, outline, lambda n, total, what: print(f"  writing scene {n}/{total}: {what}", flush=True),
                          cancel)
            dt = time.monotonic() - t0
            print(f"\nDRAFT: {json.dumps(res, ensure_ascii=False)}  ({dt:.0f} s, "
                  f"{res['words'] / max(dt, 1) * 60:.0f} words/min)\nQUALITY: {json.dumps(quality(res['file']))}")
            if outline["chapter"]:
                print(f"CHAPTER SUMMARY: {p.data['drafts'][-1]['summary']}\n")
        pdf = subprocess.run(["soffice", "--headless", f"-env:UserInstallation=file://{out}/lo-profile",
                              "--convert-to", "pdf", "--outdir", out, res["file"]], capture_output=True, text=True, timeout=180)
        pdfs = [f for f in os.listdir(out) if f.endswith(".pdf")]
        if pdfs:
            info = subprocess.run(["pdfinfo", os.path.join(out, pdfs[0])], capture_output=True, text=True).stdout
            print("PAGES:", (re.search(r"Pages:\s+(\d+)", info) or [None, "?"])[1])
        else:
            print("PDF conversion failed:", pdf.stderr[-300:])
        txt = subprocess.run(["unzip", "-p", res["file"], "content.xml"], capture_output=True, text=True).stdout
        prose = re.sub(r"<[^>]+>", "\n", txt)
        print("QUALITY:", json.dumps(quality(res["file"])))
        if os.environ.get("WRITER_COMPARE"):
            print("COMPARE (the earlier draft):", json.dumps(quality(os.environ["WRITER_COMPARE"])))
        print("\nFACT CHECK: 'younger self'/'himself'/'his own' in the draft:",
              bool(re.search(r"younger self|himself|his own hand|his own handwriting|young(er)? Elias", prose, re.I)))
        print(f"\nOUT: {out}")
    finally:
        backend.unload()
    return 0


if __name__ == "__main__":
    sys.exit(main())
