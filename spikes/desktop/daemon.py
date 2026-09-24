#!/usr/bin/env python3
"""Stub assistant daemon (M0 desktop-surface spike).

Owns org.cinminai.Assistant1 on the session bus, like the real cinminai-daemon will (SPEC §4),
and fakes the model: Ask() streams a canned reply as Token signals at ~40 tokens/s.
D-Bus activated via org.cinminai.Assistant1.service. Uses only PyGObject (Gio), which Mint ships.
"""

from __future__ import annotations

import sys

from gi.repository import Gio, GLib

NAME = "org.cinminai.Assistant1"
PATH = "/org/cinminai/Assistant1"
IFACE = "org.cinminai.Assistant1"

XML = f"""
<node>
  <interface name="{IFACE}">
    <method name="Ask">
      <arg type="s" name="text" direction="in"/>
      <arg type="u" name="id" direction="out"/>
    </method>
    <!-- spike only: force a state so the applet's icons can be checked -->
    <method name="SetState">
      <arg type="s" name="state" direction="in"/>
    </method>
    <signal name="Token"><arg type="u" name="id"/><arg type="s" name="text"/></signal>
    <signal name="Done"><arg type="u" name="id"/></signal>
    <property name="State" type="s" access="read"/>
    <property name="Model" type="s" access="read"/>
    <property name="Awareness" type="a{{sb}}" access="readwrite"/>
    <property name="LastAsk" type="s" access="read"/>
  </interface>
</node>
"""

STATES = {"idle", "thinking", "approval", "off", "error"}
REPLY = ("This is the stub daemon answering {q!r}. The real daemon will stream tokens from the "
         "local model here, the same way: one D-Bus signal per chunk, so the sidebar, the applet "
         "and the Firefox sidebar can all follow the same conversation.")


class Daemon:
    def __init__(self, loop: GLib.MainLoop) -> None:
        self.loop = loop
        self.conn: Gio.DBusConnection | None = None
        self.state = "idle"
        self.model = "stub-model  8K  LOCAL"
        self.awareness = {"terminals": True, "browser": False, "web": False}
        self.last_ask = ""
        self.next_id = 0

    # --- bus plumbing ---------------------------------------------------------------------
    def acquired(self, conn: Gio.DBusConnection, name: str) -> None:
        self.conn = conn
        info = Gio.DBusNodeInfo.new_for_xml(XML).interfaces[0]
        conn.register_object(PATH, info, self.call, self.get, self.set)

    def lost(self, conn, name) -> None:
        print(f"lost {name} (another daemon running?)", file=sys.stderr)
        self.loop.quit()

    def variant(self, prop: str) -> GLib.Variant:
        return {
            "State": lambda: GLib.Variant("s", self.state),
            "Model": lambda: GLib.Variant("s", self.model),
            "Awareness": lambda: GLib.Variant("a{sb}", self.awareness),
            "LastAsk": lambda: GLib.Variant("s", self.last_ask),
        }[prop]()

    def changed(self, *props: str) -> None:
        self.conn.emit_signal(
            None, PATH, "org.freedesktop.DBus.Properties", "PropertiesChanged",
            GLib.Variant("(sa{sv}as)", (IFACE, {p: self.variant(p) for p in props}, [])))

    def get(self, conn, sender, path, iface, prop) -> GLib.Variant:
        return self.variant(prop)

    def set(self, conn, sender, path, iface, prop, value) -> bool:
        if prop == "Awareness":
            self.awareness.update(value.unpack())
            self.changed("Awareness")
            return True
        return False

    def call(self, conn, sender, path, iface, method, params, inv) -> None:
        if method == "Ask":
            (text,) = params.unpack()
            self.next_id += 1
            inv.return_value(GLib.Variant("(u)", (self.next_id,)))
            self.last_ask = text
            self.stream(self.next_id, REPLY.format(q=text))
        elif method == "SetState":
            (state,) = params.unpack()
            if state not in STATES:
                inv.return_dbus_error(f"{IFACE}.Error.BadState", f"unknown state {state!r}")
                return
            self.set_state(state)
            inv.return_value(None)

    # --- fake model -----------------------------------------------------------------------
    def set_state(self, state: str) -> None:
        if state != self.state:
            self.state = state
            self.changed("State")

    def stream(self, rid: int, text: str) -> None:
        self.set_state("thinking")
        self.changed("LastAsk")
        words = iter(text.split(" "))

        def tick() -> bool:
            word = next(words, None)
            if word is None:
                self.conn.emit_signal(None, PATH, IFACE, "Done", GLib.Variant("(u)", (rid,)))
                self.set_state("idle")
                return False
            self.conn.emit_signal(None, PATH, IFACE, "Token", GLib.Variant("(us)", (rid, word + " ")))
            return True

        GLib.timeout_add(25, tick)


def main() -> None:
    loop = GLib.MainLoop()
    d = Daemon(loop)
    Gio.bus_own_name(Gio.BusType.SESSION, NAME, Gio.BusNameOwnerFlags.NONE, d.acquired, None, d.lost)
    loop.run()


if __name__ == "__main__":
    main()
