#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""The journal over D-Bus with the real model (PLAN D55): the interviewer's questions, a normal entry, a private
one (PIN). Needs a running daemon with this code. Uses Documents/Journal of the machine: run it on a test system;
it removes what it made (the entries, and journal.json if it made it).

    python3 tests/integration/check_journal_dbus.py
"""

from __future__ import annotations

import json
import os
import sys

from gi.repository import Gio, GLib

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
from check_writer_dbus import call, run  # noqa: E402

JOURNAL = os.path.join(os.path.expanduser("~"), "Documents", "Journal")
DAY = ["Today I finally fixed the old computer for my neighbour, it took all afternoon.",
       "Honestly I felt proud, but also a bit tired and annoyed that the update broke things first.",
       "It reminded me of when my dad taught me to fix radios when I was a kid."]


def main() -> int:
    ok = True
    had_index = os.path.isfile(os.path.join(JOURNAL, "journal.json"))
    before = set(os.listdir(JOURNAL)) if os.path.isdir(JOURNAL) else set()
    info = json.loads(call("JournalOpen")[0])
    print("JournalOpen:", info)
    for text in DAY:
        s = run("Ask", text)
        q = s["tokens"].strip()
        print(f"> {text}\n  {q}")
        ok &= "?" in q and not s["error"]
    s = run_bool("JournalWrite", False)
    e = next((json.loads(r) for t, st, r in s["actions"] if t == "journal" and st == "done"), None)
    print("entry:", s["tokens"].strip(), "|", e)
    ok &= bool(e and not e["private"])
    if e:
        import subprocess
        txt = subprocess.run(["unzip", "-p", os.path.join(JOURNAL, e["file"]), "content.xml"], capture_output=True,
                             text=True).stdout
        import re
        import html
        print("TEXT:", html.unescape(re.sub(r"<[^>]+>", " ", txt))[:1200])
    # a private one
    if not info["has_pin"]:
        call("JournalSetPin", "(ss)", "2468", "")
    run("Ask", "Something I don't want anyone to read: I've been worried about money this month.")
    s = run_bool("JournalWrite", True)
    p = next((json.loads(r) for t, st, r in s["actions"] if t == "journal" and st == "done"), None)
    print("private entry:", s["tokens"].strip(), "|", p)
    ok &= bool(p and p["private"] and p["title"] == "")
    if p:
        with open(os.path.join(JOURNAL, p["file"]), "rb") as f:
            ok &= b"money" not in f.read()
        try:
            call("JournalRead", "(ss)", p["file"], "0000")
            print("wrong PIN: opened (FAIL)")
            ok = False
        except GLib.Error as err:
            print("wrong PIN refused:", "wrong PIN" in err.message)
        r = json.loads(call("JournalRead", "(ss)", p["file"], "2468")[0])
        print("with the PIN:", r["title"], "|", r["text"][:300])
        ok &= "money" in r["text"].lower()
    call("JournalClose")
    for f in set(os.listdir(JOURNAL)) - before:  # clean up what this check made
        os.remove(os.path.join(JOURNAL, f))
    if not had_index and os.path.isfile(os.path.join(JOURNAL, "journal.json")):
        os.remove(os.path.join(JOURNAL, "journal.json"))
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


def run_bool(method, value):
    """run() for a method taking a boolean."""
    import check_writer_dbus as c
    loop, seen, rid = GLib.MainLoop(), {"tokens": "", "actions": [], "error": None}, {}

    def on_signal(conn, sender, path, iface, signal, params, *_):
        a = params.unpack()
        if a[0] != rid.get("id"):
            return
        if signal == "Token":
            seen["tokens"] += a[1]
        elif signal == "Action":
            seen["actions"].append((a[1], a[3], a[4]))
        elif signal == "Error":
            seen["error"] = a[1]
        elif signal == "Done":
            loop.quit()

    sub = c.bus.signal_subscribe(c.NAME, c.IFACE, None, c.PATH, None, Gio.DBusSignalFlags.NONE, on_signal)
    (rid["id"],) = call(method, "(b)", value)
    GLib.timeout_add_seconds(600, loop.quit)
    loop.run()
    c.bus.signal_unsubscribe(sub)
    return seen


if __name__ == "__main__":
    sys.exit(main())
