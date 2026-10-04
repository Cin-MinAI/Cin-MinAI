# SPDX-License-Identifier: GPL-3.0-or-later
"""The helper between the Firefox extension and the assistant (D14, D78).

Firefox starts it when the extension starts (native messaging: 4-byte native-endian length + UTF-8 JSON on stdin/
stdout) and it lives as long as Firefox. It answers on the session bus as org.cinminai.Firefox, so the daemon can
ask "what video is open?":

  CurrentVideo() -> s   JSON from the extension: {url, id, title, author, length, storyboard, transcript: [[t, text]]}
                        or {error: "no_video" | "read" | "no_extension"}

Exits when Firefox closes stdin.
"""

from __future__ import annotations

import itertools
import json
import struct
import sys
import threading

NAME, PATH = "org.cinminai.Firefox", "/org/cinminai/Firefox"
XML = f"""<node><interface name="{NAME}">
  <method name="CurrentVideo"><arg type="s" name="json" direction="out"/></method>
</interface></node>"""
TIMEOUT_S = 25  # opening the transcript panel can take a few seconds
MAX_MESSAGE = 8 << 20


def frame(msg: dict) -> bytes:
    data = json.dumps(msg).encode()
    return struct.pack("=I", len(data)) + data


def read_message(stream):
    raw = stream.read(4)
    if len(raw) < 4:
        return None
    (n,) = struct.unpack("=I", raw)
    if n > MAX_MESSAGE:
        return {"type": "invalid"}
    try:
        return json.loads(stream.read(n))
    except ValueError:
        return {"type": "invalid"}


class Host:
    def __init__(self, out=None) -> None:
        self.out = out or sys.stdout.buffer
        self.lock = threading.Lock()
        self.ids = itertools.count(1)
        self.waiting: dict[int, object] = {}  # request id -> Gio.DBusMethodInvocation

    def send(self, msg: dict) -> None:
        with self.lock:
            self.out.write(frame(msg))
            self.out.flush()

    def ask(self, inv) -> None:
        from gi.repository import GLib
        req = next(self.ids)
        self.waiting[req] = inv
        self.send({"type": "current_video", "req": req})
        GLib.timeout_add_seconds(TIMEOUT_S, self.expire, req)

    def expire(self, req: int) -> bool:
        inv = self.waiting.pop(req, None)
        if inv is not None:
            self.reply(inv, {"error": "read", "detail": "Firefox didn't answer in time"})
        return False

    def handle(self, msg: dict) -> bool:
        if msg.get("type") == "video":
            inv = self.waiting.pop(msg.pop("req", None), None)
            msg.pop("type", None)
            if inv is not None:
                self.reply(inv, msg)
        return False

    @staticmethod
    def reply(inv, data: dict) -> None:
        from gi.repository import GLib
        inv.return_value(GLib.Variant("(s)", (json.dumps(data, ensure_ascii=False),)))


def main() -> int:
    from gi.repository import Gio, GLib
    loop = GLib.MainLoop()
    host = Host()
    node = Gio.DBusNodeInfo.new_for_xml(XML)

    def call(conn, sender, path, iface, method, params, inv) -> None:
        if method == "CurrentVideo":
            host.ask(inv)

    def acquired(conn, name) -> None:
        conn.register_object(PATH, node.interfaces[0], call, None, None)

    # another Firefox (a second profile) already has the name: this one just doesn't answer
    Gio.bus_own_name(Gio.BusType.SESSION, NAME, Gio.BusNameOwnerFlags.DO_NOT_QUEUE, None, acquired, None)

    def reader() -> None:
        while (msg := read_message(sys.stdin.buffer)) is not None:
            GLib.idle_add(host.handle, msg)
        GLib.idle_add(loop.quit)  # Firefox closed

    threading.Thread(target=reader, daemon=True).start()
    loop.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
