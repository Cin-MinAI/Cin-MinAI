# SPDX-License-Identifier: GPL-3.0-or-later
"""org.cinminai.Assistant1 on the session bus (SPEC §4, D15).

Compatible with the M0 spike's clients (applet, sidebar: Ask/Cancel/Reset, Token/Done/Error, State,
Model, Awareness); new: the Action signal (every tool the guide uses is shown, SPEC §5.5), the Status
property (model, where it runs, context, and why it's reduced, SPEC §4.2 "say so"), Load and Unload.
The model runs on worker threads; the bus never waits on it (GLib.idle_add hands results back).
"""

from __future__ import annotations

import json
import sys
import threading
import time

from gi.repository import Gio, GLib

from cin_minai.inference.backend import BackendError, Cancelled, InferenceBackend

from .guide import Guide
from .office import LO, OfficeError

NAME = "org.cinminai.Assistant1"
PATH = "/org/cinminai/Assistant1"
IFACE = "org.cinminai.Assistant1"

XML = f"""
<node>
  <interface name="{IFACE}">
    <method name="Ask"><arg type="s" name="text" direction="in"/><arg type="u" name="id" direction="out"/></method>
    <method name="Cancel"/>
    <method name="Reset"/>
    <method name="Load"/>
    <method name="Unload"/>
    <!-- a proposed document edit (Action state "proposal", its result has the id): apply it, or discard it -->
    <method name="Decide"><arg type="s" name="proposal" direction="in"/><arg type="b" name="apply" direction="in"/>
      <arg type="s" name="json" direction="out"/></method>
    <!-- stop using the shared LibreOffice document (sharing itself is switched in LibreOffice's menu) -->
    <method name="ForgetDocument"/>
    <signal name="Token"><arg type="u" name="id"/><arg type="s" name="text"/></signal>
    <!-- a tool the guide used: state running | done; result is the tool's output (JSON or help text) -->
    <signal name="Action"><arg type="u" name="id"/><arg type="s" name="tool"/><arg type="s" name="args"/>
      <arg type="s" name="state"/><arg type="s" name="result"/></signal>
    <signal name="Done"><arg type="u" name="id"/></signal>
    <signal name="Error"><arg type="u" name="id"/><arg type="s" name="message"/></signal>
    <!-- idle | loading | thinking | off | error -->
    <property name="State" type="s" access="read"/>
    <!-- one line for the applet and the sidebar header -->
    <property name="Model" type="s" access="read"/>
    <!-- model, build (cuda|vulkan|cpu), context, reduced (why, in words; "" = full), detail, backend_state,
         document (the shared LibreOffice document the assistant sees; "" = none) -->
    <property name="Status" type="a{{sv}}" access="read"/>
    <property name="Awareness" type="a{{sb}}" access="readwrite"/>
    <property name="LastStats" type="s" access="read"/>
  </interface>
</node>
"""
WHERE = {"cuda": "graphics card", "vulkan": "graphics card", "cpu": "processor"}


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


class Service:
    def __init__(self, loop: GLib.MainLoop, backend: InferenceBackend, guide: Guide, preload: bool) -> None:
        self.loop, self.backend, self.guide = loop, backend, guide
        self.conn: Gio.DBusConnection | None = None
        self.state = "off"
        self.awareness = {"terminals": False, "browser": False, "web": False}  # nothing is watched in the Alpha
        self.last_stats = "{}"
        self.next_id = 0
        self.busy = False       # answering (one question at a time)
        self.loading = False    # a load started by Load or the preload; questions wait for it
        self.cancel = threading.Event()
        self.preload = preload
        self.document = ""  # title of the shared LibreOffice document, for the sidebar header (§7.6)

    # --- bus plumbing ------------------------------------------------------------------------------
    def acquired(self, conn: Gio.DBusConnection, name: str) -> None:
        self.conn = conn
        conn.register_object(PATH, Gio.DBusNodeInfo.new_for_xml(XML).interfaces[0], self.call, self.get, self.set)
        log(f"owning {NAME}")
        # LibreOffice says when a document is shared or not (its menu); the header follows
        conn.signal_subscribe(LO[0], LO[2], "Shared", LO[1], None, Gio.DBusSignalFlags.NONE,
                              lambda *a: self.refresh_document(), None)
        conn.signal_subscribe("org.freedesktop.DBus", "org.freedesktop.DBus", "NameOwnerChanged",
                              "/org/freedesktop/DBus", LO[0], Gio.DBusSignalFlags.NONE,
                              lambda *a: self.refresh_document(), None)
        self.refresh_document()
        if self.preload:
            self.start_load()

    def lost(self, conn, name) -> None:
        log(f"lost {name} (is another daemon running?)")
        self.loop.quit()

    def model_line(self) -> str:
        st = self.backend.status()
        if st.state in ("ready", "loading") and st.build:
            line = f"{st.model} · {st.context // 1024}K · {WHERE.get(st.build, st.build)}"
            return line + (f" — {st.reduced}" if st.reduced else "")
        if st.state == "error":
            return f"{st.model} — not available"
        return st.model

    def variant(self, prop: str) -> GLib.Variant:
        st = self.backend.status()
        return {
            "State": lambda: GLib.Variant("s", self.state),
            "Model": lambda: GLib.Variant("s", self.model_line()),
            "Status": lambda: GLib.Variant("a{sv}", {
                "model": GLib.Variant("s", st.model), "build": GLib.Variant("s", st.build),
                "context": GLib.Variant("u", st.context), "reduced": GLib.Variant("s", st.reduced),
                "detail": GLib.Variant("s", st.detail), "backend_state": GLib.Variant("s", st.state),
                "document": GLib.Variant("s", self.document)}),
            "Awareness": lambda: GLib.Variant("a{sb}", self.awareness),
            "LastStats": lambda: GLib.Variant("s", self.last_stats),
        }[prop]()

    def changed(self, *props: str) -> None:
        if self.conn:
            self.conn.emit_signal(None, PATH, "org.freedesktop.DBus.Properties", "PropertiesChanged",
                                  GLib.Variant("(sa{sv}as)", (IFACE, {p: self.variant(p) for p in props}, [])))

    def emit(self, signal: str, fmt: str, *args) -> bool:
        if self.conn:
            self.conn.emit_signal(None, PATH, IFACE, signal, GLib.Variant(fmt, args))
        return False

    def get(self, conn, sender, path, iface, prop):
        return self.variant(prop)

    def set(self, conn, sender, path, iface, prop, value) -> bool:
        if prop == "Awareness":
            self.awareness.update(value.unpack())
            self.changed("Awareness")
            return True
        return False

    def set_state(self, state: str) -> bool:
        if state != self.state:
            self.state = state
            self.changed("State", "Model", "Status")
        return False

    def call(self, conn, sender, path, iface, method, params, inv) -> None:
        if method == "Ask":
            (text,) = params.unpack()
            if self.busy:
                inv.return_dbus_error(f"{IFACE}.Error.Busy", "still answering; Cancel first")
                return
            if not text.strip():
                inv.return_dbus_error(f"{IFACE}.Error.Empty", "nothing to answer")
                return
            self.next_id += 1
            inv.return_value(GLib.Variant("(u)", (self.next_id,)))
            self.ask(self.next_id, text)
        elif method == "Cancel":
            self.cancel.set()
            interrupt = getattr(self.backend, "interrupt", None)
            if interrupt:
                interrupt()
            inv.return_value(None)
        elif method == "Reset":
            self.guide.reset()
            inv.return_value(None)
        elif method == "Load":
            self.start_load()
            inv.return_value(None)
        elif method == "Decide":
            pid, apply = params.unpack()
            office = self.guide.office

            def work():
                try:
                    out, err = json.dumps(office.decide(pid, apply), ensure_ascii=False), None
                except OfficeError as e:
                    out, err = None, str(e)
                GLib.idle_add(lambda: (inv.return_dbus_error(f"{IFACE}.Error.Office", err) if err
                                       else inv.return_value(GLib.Variant("(s)", (out,)))) and False)

            if office is None:
                inv.return_dbus_error(f"{IFACE}.Error.Office", "LibreOffice support isn't available")
            else:
                threading.Thread(target=work, daemon=True).start()
        elif method == "ForgetDocument":
            office = self.guide.office
            doc = office.current() if office else None
            if doc:
                office.forget(doc["id"])
            self.refresh_document()
            inv.return_value(None)
        elif method == "Unload":
            if self.busy or self.loading:
                inv.return_dbus_error(f"{IFACE}.Error.Busy", "still answering; Cancel first")
                return
            self.backend.unload()
            self.set_state("off")
            inv.return_value(None)

    def refresh_document(self) -> None:
        office = self.guide.office

        def work():
            doc = office.current() if office else None
            GLib.idle_add(self.set_document, doc["title"] if doc else "")

        threading.Thread(target=work, daemon=True).start()

    def set_document(self, title: str) -> bool:
        if title != self.document:
            self.document = title
            self.changed("Status")
        return False

    # --- work ----------------------------------------------------------------------------------------
    def start_load(self) -> None:
        if self.loading or self.busy or self.backend.status().state == "ready":
            return
        self.loading = True
        self.set_state("loading")

        def work():
            try:
                self.backend.load()
                state = "idle"
            except BackendError as e:
                log(f"load: {e}")
                state = "error"
            GLib.idle_add(self.loaded, state)

        threading.Thread(target=work, daemon=True).start()

    def loaded(self, state: str) -> bool:
        self.loading = False
        if not self.busy:  # a question waiting on this load sets the state itself
            self.set_state(state)
        return False

    def ask(self, rid: int, text: str) -> None:
        self.busy = True
        self.cancel.clear()
        self.set_state("loading" if self.backend.status().state != "ready" else "thinking")

        def on_text(piece: str) -> None:
            GLib.idle_add(self.emit, "Token", "(us)", rid, piece)
            if self.state != "thinking":
                GLib.idle_add(self.set_state, "thinking")

        def on_action(tool: str, args: dict, state: str, result: str) -> None:
            GLib.idle_add(self.emit, "Action", "(ussss)", rid, tool,
                          json.dumps(args, ensure_ascii=False), state, result)

        def work():
            t0 = time.monotonic()
            error, stats = None, {}
            try:
                out = self.guide.turn(text, on_text, on_action, self.cancel)
                stats = {"tool": out["tool"], "args": out["args"], "reply_chars": len(out["reply"]),
                         "timings": out["timings"]}
            except Cancelled:
                stats = {"cancelled": True}
            except BackendError as e:
                error = str(e)
            except Exception as e:  # never leave the sidebar waiting
                log(f"turn failed: {type(e).__name__}: {e}")
                error = "Something went wrong while answering. Please try again."
            stats["seconds"] = round(time.monotonic() - t0, 2)
            GLib.idle_add(self.finish, rid, error, stats)

        threading.Thread(target=work, daemon=True).start()

    def finish(self, rid: int, error: str | None, stats: dict) -> bool:
        self.busy = False
        self.last_stats = json.dumps(stats, ensure_ascii=False)
        if error:
            self.emit("Error", "(us)", rid, error)
        self.set_state("error" if error and self.backend.status().state == "error" else
                       "idle" if self.backend.status().state == "ready" else "off")
        self.changed("LastStats", "Model", "Status")
        self.emit("Done", "(u)", rid)
        return False


def run(backend: InferenceBackend, guide: Guide, preload: bool) -> None:
    loop = GLib.MainLoop()
    svc = Service(loop, backend, guide, preload)
    Gio.bus_own_name(Gio.BusType.SESSION, NAME, Gio.BusNameOwnerFlags.NONE, svc.acquired, None, svc.lost)
    try:
        loop.run()
    finally:
        backend.unload()
