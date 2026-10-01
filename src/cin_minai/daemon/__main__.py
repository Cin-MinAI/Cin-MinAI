# SPDX-License-Identifier: GPL-3.0-or-later
"""cinminai-daemon: python3 -m cin_minai.daemon [--ask TEXT]

Normally started by systemd --user (D-Bus activated, cinminai-daemon.service). --ask answers one message
on the terminal without the bus (for tests and for looking at what the guide does).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading

from cin_minai.inference.llamacpp import LlamaCppBackend

from . import config
from .guide import Guide
from .helpcards import HelpIndex
from .office import Office, dbus_call
from .tools import Tools


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def build(cfg: dict, lang: str | None = None) -> tuple[LlamaCppBackend, Guide]:
    data_dir = cfg["guide"]["data_dir"]
    with open(os.path.join(data_dir, "guide.json"), encoding="utf-8") as f:
        guide_data = json.load(f)
    with open(os.path.join(data_dir, "help.json"), encoding="utf-8") as f:
        help_data = json.load(f)
    backend = LlamaCppBackend(cfg["inference"], log)
    tools = Tools(help_data["labels"], help_data["desktop"], lang)
    try:
        office = Office(dbus_call())  # LibreOffice documents the user shared (D20)
    except ImportError:  # no PyGObject: --ask on a bare system
        office = None
    return backend, Guide(backend, guide_data, HelpIndex(help_data), tools, cfg["guide"], office)


def main() -> None:
    ap = argparse.ArgumentParser(prog="cinminai-daemon")
    ap.add_argument("--ask", action="append", help="answer this message on the terminal (repeat for a conversation)")
    ap.add_argument("--lang", help="the desktop language for names on screen (default: from the locale)")
    o = ap.parse_args()
    cfg = config.load()
    backend, guide = build(cfg, o.lang)
    if o.ask:
        cancel = threading.Event()
        try:
            for text in o.ask:
                print(f"> {text}", flush=True)
                out = guide.turn(text, lambda t: print(t, end="", flush=True),
                                 lambda tool, args, state, result: print(
                                     f"\n  [{tool} {json.dumps(args, ensure_ascii=False)} {state}]"
                                     + (f"\n  {result[:400]}" if result else ""), flush=True),
                                 cancel)
                print(f"\n  stats: {json.dumps({'tool': out['tool'], 'timings': out['timings']})}\n", flush=True)
            print(json.dumps(backend.status().__dict__), flush=True)
        finally:
            backend.unload()
        return
    from .service import run  # needs PyGObject; --ask doesn't
    run(backend, guide, config.preload(cfg))


if __name__ == "__main__":
    main()
