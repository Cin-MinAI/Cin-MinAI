#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Small test-SSD client for every org.cinminai.Admin1 verb."""

import argparse
import os

from gi.repository import Gio, GLib

NAME = "org.cinminai.Admin1"
PATH = "/org/cinminai/Admin1"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--interactive", action="store_true", help="allow the one-request polkit dialog")
    sub = parser.add_subparsers(dest="verb", required=True)
    for name in ("restart", "load", "unload", "install", "remove"):
        command = sub.add_parser(name)
        command.add_argument("value")
    enabled = sub.add_parser("enabled")
    enabled.add_argument("unit")
    enabled.add_argument("state", choices=("true", "false"))
    write = sub.add_parser("write")
    write.add_argument("path")
    write.add_argument("content")
    write.add_argument("--mode", type=lambda value: int(value, 8), default=0o644)
    run = sub.add_parser("run")
    run.add_argument("argv", nargs=argparse.REMAINDER)
    args = parser.parse_args()

    calls = {
        "restart": ("RestartService", GLib.Variant("(s)", (getattr(args, "value", ""),))),
        "load": ("LoadModule", GLib.Variant("(s)", (getattr(args, "value", ""),))),
        "unload": ("UnloadModule", GLib.Variant("(s)", (getattr(args, "value", ""),))),
        "install": ("InstallPackage", GLib.Variant("(s)", (getattr(args, "value", ""),))),
        "remove": ("RemovePackage", GLib.Variant("(s)", (getattr(args, "value", ""),))),
        "enabled": ("SetServiceEnabled", GLib.Variant("(sb)", (getattr(args, "unit", ""), getattr(args, "state", "false") == "true"))),
        "write": ("WriteFile", GLib.Variant("(sayu)", (getattr(args, "path", ""), getattr(args, "content", "").encode(), getattr(args, "mode", 0o644)))),
        "run": ("RunArgv", GLib.Variant("(as)", (getattr(args, "argv", []),))),
    }
    method, parameters = calls[args.verb]
    flags = Gio.DBusCallFlags.ALLOW_INTERACTIVE_AUTHORIZATION if args.interactive else Gio.DBusCallFlags.NONE
    bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
    result = bus.call_sync(NAME, PATH, NAME, method, parameters, None, flags, 20 * 60 * 1000, None)
    if result is not None:
        print(result.unpack())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
