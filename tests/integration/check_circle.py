#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""The circle while gathering (PLAN D56), with the real model: replay a writing project's conversation (on a
copy; the original is untouched) through the circle's own question and show what each message filled. Uses the
daemon's config; stop the user's daemon first (they share the server's socket).

    python3 tests/integration/check_circle.py ~/Documents/Writing/<project>      (from the repo root)
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import threading
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))

from cin_minai.daemon import config  # noqa: E402
from cin_minai.daemon.projects import STEP, STEPS, Project  # noqa: E402
from cin_minai.daemon.writer import Writer  # noqa: E402
from cin_minai.inference.llamacpp import LlamaCppBackend  # noqa: E402


def main() -> int:
    src = sys.argv[1]
    dst = os.path.join(tempfile.mkdtemp(prefix="cinminai-circle-"), os.path.basename(src.rstrip("/")))
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("*.odt", "*.docx", ".~lock*"))
    p = Project.open(dst)
    messages = p.data["messages"]
    p.data["messages"], p.data["circle"] = [], {k: [] for k in STEPS}
    backend = LlamaCppBackend(config.load()["inference"], lambda m: None)
    w = Writer(backend.chat)
    try:
        t0, n = time.monotonic(), 0
        for m in messages:
            p.data["messages"].append(m)
            if m["role"] != "user" or m["content"].startswith("{"):
                continue
            before = {k: len(v) for k, v in p.circle.items()}
            w.take_circle(p, m["content"], threading.Event())
            n += 1
            new = [f"{STEP[k]['name']}: {p.circle[k][-1]}" for k in STEPS if len(p.circle[k]) > before[k]]
            print(f"> {m['content'][:110]}\n    {' | '.join(new) or '(no step)'}")
        print(f"\n{n} messages in {time.monotonic() - t0:.0f} s; the circle:")
        for k in STEPS:
            print(f"  {STEP[k]['name']}: {' / '.join(p.circle[k]) or '—'}")
        print(f"open step (what the partner would ask about): {p.open_step()}")
    finally:
        backend.unload()
    return 0


if __name__ == "__main__":
    sys.exit(main())
