# SPDX-License-Identifier: GPL-3.0-or-later
"""Ask the running assistant one question over the session bus and print what happened, as JSON:

    python3 -m cin_minai.daemon.client "How do I install a program?" [--timeout 300]

{"reply": ..., "actions": [[tool, args, state], ...], "error": ..., "model": ..., "seconds": ...}.
Starts the daemon through D-Bus activation if it isn't running, like the sidebar does. Used by the boot
test (distro/test-packages/cinminai-boottest) and for looking at the daemon by hand.
"""

from __future__ import annotations

import argparse
import json
import time

from gi.repository import Gio, GLib

NAME = IFACE = "org.cinminai.Assistant1"
PATH = "/org/cinminai/Assistant1"


def ask(question: str, timeout: int = 300) -> dict:
    bus = Gio.bus_get_sync(Gio.BusType.SESSION)
    loop = GLib.MainLoop()
    out = {"reply": "", "actions": [], "error": None, "timed_out": False}
    rid = {"id": None}

    def on_signal(conn, sender, path, iface, name, params, *_):
        v = params.unpack()
        if rid["id"] is not None and v[0] != rid["id"]:
            return
        if name == "Token":
            out["reply"] += v[1]
        elif name == "Action":
            out["actions"].append([v[1], json.loads(v[2]), v[3]])
        elif name == "Error":
            out["error"] = v[1]
        elif name == "Done":
            loop.quit()

    bus.signal_subscribe(NAME, IFACE, None, PATH, None, Gio.DBusSignalFlags.NONE, on_signal)
    t0 = time.monotonic()
    (rid["id"],) = bus.call_sync(NAME, PATH, IFACE, "Ask", GLib.Variant("(s)", (question,)),
                                 GLib.VariantType("(u)"), Gio.DBusCallFlags.NONE, 60000, None).unpack()

    def give_up():
        out["timed_out"] = True
        loop.quit()
        return False

    GLib.timeout_add_seconds(timeout, give_up)
    loop.run()
    out["seconds"] = round(time.monotonic() - t0, 1)
    get = lambda p: bus.call_sync(NAME, PATH, "org.freedesktop.DBus.Properties", "Get",
                                  GLib.Variant("(ss)", (IFACE, p)), None, Gio.DBusCallFlags.NONE, 5000, None).unpack()[0]
    out["model"], out["state"] = get("Model"), get("State")
    out["stats"] = json.loads(get("LastStats") or "{}")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(prog="cinminai-ask")
    ap.add_argument("question")
    ap.add_argument("--timeout", type=int, default=300)
    o = ap.parse_args()
    print(json.dumps(ask(o.question, o.timeout), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
