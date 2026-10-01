#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""The writing flow over D-Bus, the way the sidebar drives it (PLAN D54): ProjectNew, Ask (gathering), WriteUp
(the outline), WriteDraft (progress, then the file), ProjectClose. Needs a running daemon with this code.

    python3 tests/integration/check_writer_dbus.py
"""

from __future__ import annotations

import json
import shutil
import sys

from gi.repository import Gio, GLib

NAME, PATH, IFACE = "org.cinminai.Assistant1", "/org/cinminai/Assistant1", "org.cinminai.Assistant1"
bus = Gio.bus_get_sync(Gio.BusType.SESSION)


def call(method, fmt=None, *args, timeout=60000):
    v = bus.call_sync(NAME, PATH, IFACE, method, GLib.Variant(fmt, args) if fmt else None, None,
                      Gio.DBusCallFlags.NONE, timeout, None)
    return v.unpack() if v else None


def run(method, arg):
    """Start a job and collect its signals until Done."""
    loop, seen = GLib.MainLoop(), {"tokens": "", "actions": [], "error": None}
    rid = {}

    def on_signal(conn, sender, path, iface, signal, params, *_):
        a = params.unpack()
        if a[0] != rid.get("id"):
            return
        if signal == "Token":
            seen["tokens"] += a[1]
        elif signal == "Action":
            seen["actions"].append((a[1], a[3], a[4]))
            if a[1] == "draft" and a[3] == "running":
                print("   ", json.loads(a[4]), flush=True)
        elif signal == "Error":
            seen["error"] = a[1]
        elif signal == "Done":
            loop.quit()

    sub = bus.signal_subscribe(NAME, IFACE, None, PATH, None, Gio.DBusSignalFlags.NONE, on_signal)
    (rid["id"],) = call(method, "(s)", arg)
    GLib.timeout_add_seconds(1800, loop.quit)
    loop.run()
    bus.signal_unsubscribe(sub)
    return seen


def main() -> int:
    ok = True
    info = json.loads(call("ProjectNew", "(s)", "Dbus Check Lighthouse")[0])
    print("ProjectNew:", info["title"], info["folder"])
    for text in ("A retired lighthouse keeper, Elias, finds a message in a bottle he wrote himself forty years ago.",
                 "His neighbour Rosa is nosy and bakes too much. A storm is coming.",
                 "At the end of the chapter he decides to find out why he threw it into the sea."):
        s = run("Ask", text)
        print(f"> {text}\n  {s['tokens'].strip()}")
        ok &= bool(s["tokens"].strip()) and not s["error"]
    notes = json.loads(call("ProjectInfo")[0])["notes"]
    print("notes:", sum(len(v) for v in notes.values()), "→", notes["facts"][:3])
    s = run("WriteUp", "")
    outline = next((json.loads(r) for t, st, r in s["actions"] if t == "outline" and st == "proposal"), None)
    print("WriteUp:", s["tokens"].strip()[:120], "| scenes:", len(outline["scenes"]) if outline else None)
    ok &= bool(outline)
    s = run("WriteDraft", outline["id"])
    done = next((json.loads(r) for t, st, r in s["actions"] if t == "draft" and st == "done"), None)
    print("WriteDraft:", s["tokens"].strip(), "|", json.dumps(done)[:200] if done else s["error"])
    ok &= bool(done and done.get("file"))
    call("ProjectClose")
    shutil.rmtree(info["folder"], ignore_errors=True)  # the check's project only
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
