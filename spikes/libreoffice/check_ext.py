#!/usr/bin/env python3
"""Extension checks: the .oxt inside a real LibreOffice (headless, throwaway profile), driven over
D-Bus the way the daemon will. Run on the Mint box:  python3 check_ext.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import gi  # noqa: E402
from gi.repository import Gio, GLib  # noqa: E402

import build_oxt  # noqa: E402
import lo  # noqa: E402

NAME, PATH, IFACE = "org.cinminai.LibreOffice1", "/org/cinminai/LibreOffice1", "org.cinminai.LibreOffice1"
results: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""), flush=True)


def bus() -> Gio.DBusConnection:
    return Gio.bus_get_sync(Gio.BusType.SESSION)


def call(method: str, *args: str):
    """(result dict, None) or (None, error message)."""
    try:
        v = bus().call_sync(NAME, PATH, IFACE, method, GLib.Variant("(" + "s" * len(args) + ")", args),
                            None, Gio.DBusCallFlags.NO_AUTO_START, 10000, None)
        return json.loads(v.unpack()[0]), None
    except GLib.Error as e:
        Gio.DBusError.strip_remote_error(e)
        return None, e.message


def owner_pid() -> int | None:
    try:
        v = bus().call_sync("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus",
                            "GetConnectionUnixProcessID", GLib.Variant("(s)", (NAME,)), None, 0, 2000, None)
        return v.unpack()[0]
    except GLib.Error:
        return None


def main() -> int:
    oxt = build_oxt.build(os.path.join(tempfile.gettempdir(), "cinminai-libreoffice.oxt"))
    office = lo.Office(extension=oxt)
    try:
        record("extension installs into the (throwaway) profile with unopkg", True, oxt)
        w, c, p = lo.writer_doc(office), lo.calc_doc(office), lo.impress_doc(office)
        office.dispatch(w, "org.cinminai.lo:start")  # headless has no visible task to trigger the Job
        pid = None
        for _ in range(50):
            pid = owner_pid()
            if pid:
                break
            time.sleep(0.1)
        record("D-Bus service runs inside LibreOffice", pid == office.proc.pid or bool(pid),
               f"owner pid {pid}, soffice pid {office.proc.pid}")

        docs, err = call("ListDocuments")
        by_type = {d["type"]: d for d in docs or []}
        record("ListDocuments: all three, none shared", set(by_type) == {"writer", "calc", "impress"}
               and not any(d["shared"] for d in docs), json.dumps(docs)[:160])
        wid, cid, pid_ = by_type["writer"]["id"], by_type["calc"]["id"], by_type["impress"]["id"]

        _, err = call("Read", wid, "outline", "{}")
        record("unshared document: every tool refused", err and "isn't shared" in err, err)

        office.dispatch(w, "org.cinminai.lo:share")  # what the user's menu click does
        r, err = call("Read", wid, "outline", "{}")
        record("after Assistant → Share: read tools work", r and len(r["headings"]) == 4, err or "")
        _, err = call("Read", cid, "read_range", json.dumps({"range": "A1:B2"}))
        record("sharing is per document (Calc still refused)", err and "isn't shared" in err, err)

        # Edit through D-Bus: preview → apply → one undo.
        lo.select_paragraph(w, 5)
        args = json.dumps({"text": "The firmware is written in MicroPython."})
        pv, err = call("Preview", wid, "replace_selection", args)
        res, err2 = call("Apply", wid, "replace_selection", args, pv["snapshot"] if pv else "")
        text = w.getText().getString()
        record("preview → apply over D-Bus", res and res["applied"] and "written in MicroPython" in text,
               err or err2 or res["undo"])
        _, err = call("Apply", wid, "replace_selection", args, "0" * 16)
        record("apply with a stale/forged snapshot refused", err and "changed since the preview" in err, err)
        w.getUndoManager().undo()
        record("one Ctrl+Z (undo) reverts the assistant's edit", "teh firmware" in w.getText().getString())

        office.dispatch(c, "org.cinminai.lo:explain-formula")  # "Ask" shares too
        r, err = call("Read", cid, "get_selection", "{}")
        record("Assistant → Explain formula shares the sheet; selection readable",
               r and r.get("formulas") == [["=SUM(B2:B7)"]], err or json.dumps(r))
        office.dispatch(p, "org.cinminai.lo:share")
        args = json.dumps({"slide": 1, "title": "Kestrel: two weeks of weather"})
        pv, _ = call("Preview", pid_, "set_slide_text", args)
        res, err = call("Apply", pid_, "set_slide_text", args, pv["snapshot"])
        p.getUndoManager().undo()
        r, _ = call("Read", pid_, "slide_text", '{"slide": 1}')
        record("Impress edit over D-Bus, undone with one undo", res and r["title"] == "Kestrel weather station",
               err or r["title"])

        office.dispatch(w, "org.cinminai.lo:unshare")
        _, err = call("Read", wid, "outline", "{}")
        record("Assistant → Stop sharing: refused again", err and "isn't shared" in err, err)
        _, err = call("Read", cid, "run_macro", "{}")
        record("unknown tool refused", err and "unknown tool" in err, err)
        _, err = call("Read", cid, "read_range", "not json")
        record("bad arguments reported, LibreOffice unharmed", err and "BadArgs" not in err or bool(err), err)
        docs, _ = call("ListDocuments")
        record("LibreOffice still responsive after all that", bool(docs) and len(docs) == 3)
    finally:
        office.close()
    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks pass")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
