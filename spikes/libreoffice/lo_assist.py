#!/usr/bin/env python3
"""Hands-on demo: ask the local model to work on the LibreOffice document you shared.

    python3 lo_assist.py "fix the spelling in the selected text"

Stands in for the daemon + sidebar (M6): talks to the extension over D-Bus, lets the model call
read tools on its own, and shows every edit as a preview you approve before it happens. After an
edit, Ctrl+Z in LibreOffice undoes it in one step.
"""

from __future__ import annotations

import json
import sys

from gi.repository import Gio, GLib

from assist import ask, context

NAME, PATH, IFACE = "org.cinminai.LibreOffice1", "/org/cinminai/LibreOffice1", "org.cinminai.LibreOffice1"
EDIT_TOOLS = {"replace_selection", "write_range", "set_formula", "set_slide_text"}


class ToolError(Exception):
    pass


def call(method: str, *args: str):
    try:
        v = Gio.bus_get_sync(Gio.BusType.SESSION).call_sync(
            NAME, PATH, IFACE, method, GLib.Variant("(" + "s" * len(args) + ")", args), None,
            Gio.DBusCallFlags.NO_AUTO_START, 15000, None)
    except GLib.Error as e:
        Gio.DBusError.strip_remote_error(e)
        raise ToolError(e.message)
    return json.loads(v.unpack()[0])


def show(value) -> str:
    if isinstance(value, list):
        return "\n".join("  " + " | ".join(str(c) for c in row) if isinstance(row, list) else f"  {row}" for row in value)
    if isinstance(value, dict):
        return "\n".join(f"  {k}: {v}" for k, v in value.items() if k != "slide")
    return "  " + str(value).replace("\n", "\n  ")


def main(request: str) -> int:
    try:
        docs = call("ListDocuments")
    except ToolError as e:
        print(f"LibreOffice with the Cin-MinAI extension isn't running ({e})")
        return 1
    shared = [d for d in docs if d["shared"]]
    if not shared:
        print("No document is shared yet: in LibreOffice use  Assistant → Share this document with the assistant")
        return 1
    doc = shared[-1]
    kind = doc["type"]
    print(f"Working on {doc['title']} ({kind})")

    def read(tool, args):
        return call("Read", doc["id"], tool, json.dumps(args))

    ctx = context(kind, read)
    ctx["results"] = []
    retry = None
    for _ in range(4):  # a few steps: the model may read before it answers or edits
        choice, dt = ask(kind, ctx, request, retry)
        tool, args = choice["tool"], choice["args"]
        retry = None
        print(f"  model → {tool} {json.dumps(args, ensure_ascii=False)[:120]}  ({dt:.1f} s)")
        if tool == "answer":
            print("\n" + args["text"])
            return 0
        try:
            if tool not in EDIT_TOOLS:
                ctx["results"].append({"tool": tool, "args": args, "result": read(tool, args)})
                continue
            pv = call("Preview", doc["id"], tool, json.dumps(args))
        except ToolError as e:
            retry = (choice, str(e))
            continue
        print(f"\nPROPOSED EDIT — {pv['summary']}\n--- before\n{show(pv['before'])}\n+++ after\n{show(pv['after'])}\n")
        if input("Apply? [y/N] ").strip().lower() != "y":
            print("Discarded; the document is unchanged.")
            return 0
        try:
            res = call("Apply", doc["id"], tool, json.dumps(args), pv["snapshot"])
        except ToolError as e:
            print(f"Not applied: {e}")
            return 1
        print(f"Applied as one undo step: \"{res['undo']}\" — press Ctrl+Z in LibreOffice to undo it.")
        return 0
    print("The model didn't settle on an answer or an edit in 4 steps.")
    return 1


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    sys.exit(main(" ".join(sys.argv[1:])))
