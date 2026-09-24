#!/usr/bin/env python3
"""Docked assistant sidebar (M0 desktop-surface spike, SPEC §5.1 stage 1).

A GTK 3 window on the right edge of the primary monitor that reserves its space with
_NET_WM_STRUT_PARTIAL, so maximized windows stop at its edge. Single instance (GApplication):

    sidebar.py [--toggle | --show | --hide | --quit]      (default --toggle; the hotkey runs this)

Talks to the stub daemon (daemon.py) over the session bus; the daemon is D-Bus activated.
"""

from __future__ import annotations

import ctypes
import subprocess
import sys
import warnings

import gi

warnings.filterwarnings("ignore", category=DeprecationWarning)  # set_wmclass, Screen.get_width: X11-only APIs we need

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkX11", "3.0")
from gi.repository import Gdk, GdkX11, Gio, GLib, Gtk  # noqa: E402

APP_ID = "org.cinminai.Sidebar"
DAEMON = ("org.cinminai.Assistant1", "/org/cinminai/Assistant1", "org.cinminai.Assistant1")
WIDTH = 380  # logical px

CSS = b"""
#sidebar { background: @theme_bg_color; border-left: 1px solid @borders; }
#status { font-family: monospace; font-size: 90%; padding: 6px 8px; }
#context { font-size: 85%; padding: 0 8px 6px 8px; opacity: 0.8; }
#chat { padding: 8px; }
"""


class X11:
    """Just enough libX11 to set window properties PyGObject can't (format-32 CARDINAL arrays)."""

    def __init__(self) -> None:
        self.lib = ctypes.cdll.LoadLibrary("libX11.so.6")
        self.lib.XOpenDisplay.restype = ctypes.c_void_p
        self.lib.XOpenDisplay.argtypes = [ctypes.c_char_p]
        self.lib.XInternAtom.restype = ctypes.c_ulong
        self.lib.XInternAtom.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
        self.lib.XChangeProperty.argtypes = [
            ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_int,
            ctypes.c_int, ctypes.c_void_p, ctypes.c_int]
        self.lib.XFlush.argtypes = [ctypes.c_void_p]
        self.dpy = self.lib.XOpenDisplay(None)

    def set_cardinals(self, xid: int, prop: str, values: list[int]) -> None:
        atom = self.lib.XInternAtom(self.dpy, prop.encode(), 0)
        data = (ctypes.c_long * len(values))(*values)
        XA_CARDINAL, PROP_MODE_REPLACE = 6, 0
        self.lib.XChangeProperty(self.dpy, xid, atom, XA_CARDINAL, 32, PROP_MODE_REPLACE,
                                 ctypes.cast(data, ctypes.c_void_p), len(values))
        self.lib.XFlush(self.dpy)


def monitor_index(display: Gdk.Display, mon: Gdk.Monitor) -> int:
    return next(i for i in range(display.get_n_monitors()) if display.get_monitor(i) == mon)


def cinnamon_panels(monitor: int) -> tuple[int, int]:
    """Heights (logical px) of Cinnamon panels at the top and bottom of a monitor."""
    source = Gio.SettingsSchemaSource.get_default()
    if not source.lookup("org.cinnamon", True):
        return 0, 0
    s = Gio.Settings.new("org.cinnamon")
    heights = dict(e.split(":")[:2] for e in s.get_strv("panels-height"))
    top = bottom = 0
    for entry in s.get_strv("panels-enabled"):  # "id:monitor:position"
        pid, mon, pos = entry.split(":")
        if int(mon) == monitor and pos in ("top", "bottom"):
            h = int(heights.get(pid, 40))
            top, bottom = (max(top, h), bottom) if pos == "top" else (top, max(bottom, h))
    return top, bottom


def focused_window() -> str:
    """Class and title of the window that had focus before us (the context to attach)."""
    try:
        wid = subprocess.run(["xprop", "-root", "_NET_ACTIVE_WINDOW"], capture_output=True,
                             text=True, timeout=1).stdout.split()[-1]
        out = subprocess.run(["xprop", "-id", wid, "WM_CLASS", "_NET_WM_NAME"],
                             capture_output=True, text=True, timeout=1).stdout
    except (OSError, IndexError, subprocess.TimeoutExpired):
        return "?"
    props = dict(line.split(" = ", 1) for line in out.splitlines() if " = " in line)
    cls = props.get("WM_CLASS(STRING)", "").split(", ")[-1].strip('"')
    title = props.get("_NET_WM_NAME(UTF8_STRING)", "").strip('"')
    return f"{cls} — {title}" if cls else "?"


class Sidebar(Gtk.Application):
    def __init__(self) -> None:
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.win: Gtk.ApplicationWindow | None = None
        self.x11 = X11()
        self.proxy: Gio.DBusProxy | None = None
        self.context = "?"

    # --- window ---------------------------------------------------------------------------
    def build(self) -> None:
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        win = Gtk.ApplicationWindow(application=self, title="Cin-MinAI Assistant")
        win.set_name("sidebar")
        win.set_wmclass("cinminai-sidebar", "Cin-MinAI Sidebar")
        # DOCK: Muffin keeps normal windows out of struts (including their own) and applies
        # focus-stealing prevention to them; docks are exempt from both. But Muffin doesn't
        # focus a dock when it's clicked, so we ask for focus ourselves (on_click).
        win.set_type_hint(Gdk.WindowTypeHint.DOCK)
        win.set_decorated(False)
        win.set_skip_taskbar_hint(True)
        win.set_skip_pager_hint(True)
        win.stick()  # all workspaces
        win.connect("realize", lambda w: self.place())
        win.connect("delete-event", lambda *a: win.hide() or True)
        win.connect("key-press-event", self.on_key)
        # Capture phase: see every click before the widget under it (Ask field, button) does.
        self.click = Gtk.GestureMultiPress.new(win)
        self.click.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        self.click.connect("pressed", self.on_click)

        self.status = Gtk.Label(xalign=0, name="status")
        self.ctx_label = Gtk.Label(xalign=0, name="context", ellipsize=3)
        self.chat = Gtk.TextView(name="chat", editable=False, cursor_visible=False,
                                 wrap_mode=Gtk.WrapMode.WORD_CHAR)
        scroll = Gtk.ScrolledWindow(vexpand=True)
        scroll.add(self.chat)
        self.entry = Gtk.Entry(placeholder_text="Ask…")
        self.entry.connect("activate", self.on_ask)

        close = Gtk.Button.new_from_icon_name("window-close-symbolic", Gtk.IconSize.MENU)
        close.set_relief(Gtk.ReliefStyle.NONE)
        close.set_valign(Gtk.Align.START)
        close.set_tooltip_text("Hide (Esc, or Super+A)")
        close.connect("clicked", lambda b: self.hide())
        header = Gtk.Box()
        header.pack_start(self.status, True, True, 0)
        header.pack_end(close, False, False, 0)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.pack_start(header, False, False, 0)
        box.pack_start(self.ctx_label, False, False, 0)
        box.pack_start(Gtk.Separator(), False, False, 0)
        box.pack_start(scroll, True, True, 0)
        box.pack_start(self.entry, False, False, 6)
        win.add(box)
        box.show_all()
        self.win = win

        # A resolution change arrives as a burst: size, monitors, then (from Cinnamon, a moment
        # later) the scale factor and work area. Re-dock once things settle.
        self.replace_id = 0
        screen = Gdk.Screen.get_default()
        screen.connect("monitors-changed", lambda *a: self.watch_monitors())
        screen.connect("size-changed", lambda *a: self.queue_place())
        win.connect("notify::scale-factor", lambda *a: self.queue_place())
        self.watch_monitors()
        self.connect_daemon()

    def watch_monitors(self) -> None:
        display = Gdk.Display.get_default()
        for i in range(display.get_n_monitors()):
            mon = display.get_monitor(i)
            if not getattr(mon, "_cinminai_watched", False):
                for prop in ("geometry", "workarea", "scale-factor"):
                    mon.connect(f"notify::{prop}", lambda *a: self.queue_place())
                mon._cinminai_watched = True
        self.queue_place()

    def queue_place(self) -> None:
        if self.replace_id:
            GLib.source_remove(self.replace_id)

        def run() -> bool:
            self.replace_id = 0
            self.place()
            return False

        self.replace_id = GLib.timeout_add(150, run)

    def place(self) -> None:
        """Right edge of the primary monitor, full work-area height, space reserved."""
        win = self.win
        display = Gdk.Display.get_default()
        mon = display.get_primary_monitor() or display.get_monitor(0)
        geo, wa, scale = mon.get_geometry(), mon.get_workarea(), mon.get_scale_factor()
        x, y, h = geo.x + geo.width - WIDTH, wa.y, wa.height
        # Cinnamon panels set to (intelli)hide reserve no space; stay clear of them anyway, or
        # the panel hides for good behind the sidebar.
        panel_top, panel_bottom = cinnamon_panels(monitor_index(display, mon))
        if wa.y == geo.y:
            y, h = y + panel_top, h - panel_top
        if wa.y + wa.height == geo.y + geo.height:
            h -= panel_bottom
        win.move(x, y)
        win.resize(WIDTH, h)
        if not win.get_realized():
            return
        # Struts are in device pixels, measured from the edge of the whole X screen.
        screen_w = Gdk.Screen.get_default().get_width() * scale
        right = screen_w - (geo.x + geo.width - WIDTH) * scale
        xid = GdkX11.X11Window.get_xid(win.get_window())
        top, bottom = y * scale, (y + h) * scale - 1
        self.x11.set_cardinals(xid, "_NET_WM_STRUT_PARTIAL",
                               [0, right, 0, 0, 0, 0, top, bottom, 0, 0, 0, 0])
        self.x11.set_cardinals(xid, "_NET_WM_STRUT", [0, right, 0, 0])

    def show(self) -> None:
        ctx = focused_window()
        if not ctx.startswith("Cin-MinAI Sidebar"):  # keep the last real context
            self.context = ctx
        self.ctx_label.set_text(f"Context: {self.context}")
        self.win.show()
        self.place()
        # Hotkey launches arrive without a user timestamp; focus-stealing prevention would
        # refuse a plain present(). The X server time counts as "now".
        self.take_focus()
        self.entry.grab_focus()

    def take_focus(self, timestamp: int | None = None) -> None:
        gdk_win = self.win.get_window()
        ts = timestamp or GdkX11.x11_get_server_time(gdk_win)
        self.win.present_with_time(ts)
        gdk_win.focus(ts)

    def on_click(self, gesture, n_press, x, y) -> None:
        # Doesn't claim the event, so the click still reaches the widget.
        if not self.win.is_active():
            event = gesture.get_last_event(gesture.get_current_sequence())
            self.take_focus(event.get_time() if event else None)

    def hide(self) -> None:
        self.win.hide()  # unmapped windows' struts are dropped by the window manager

    def toggle(self) -> None:
        if self.win.get_visible() and self.win.is_active():
            self.hide()
        else:
            self.show()

    def on_key(self, win, event) -> bool:
        if event.keyval == Gdk.KEY_Escape:
            self.hide()
            return True
        return False

    # --- daemon ---------------------------------------------------------------------------
    def connect_daemon(self) -> None:
        # Without DO_NOT_AUTO_START, creating the proxy D-Bus-activates the daemon.
        Gio.DBusProxy.new_for_bus(Gio.BusType.SESSION, Gio.DBusProxyFlags.NONE, None, *DAEMON,
                                  None, self.on_proxy)

    def on_proxy(self, source, result) -> None:
        try:
            self.proxy = Gio.DBusProxy.new_for_bus_finish(result)
        except GLib.Error as e:
            self.status.set_text(f"daemon unavailable: {e.message}")
            return
        self.proxy.connect("g-properties-changed", lambda *a: self.update_status())
        self.proxy.connect("notify::g-name-owner", lambda *a: self.update_status())
        self.proxy.connect("g-signal", self.on_signal)
        self.update_status()

    def update_status(self) -> None:
        p = self.proxy
        if not p.get_name_owner():
            self.status.set_text("● OFFLINE — daemon not running")
            return
        state = p.get_cached_property("State")
        model = p.get_cached_property("Model")
        aware = p.get_cached_property("Awareness")
        sees = ", ".join(k for k, v in (aware.unpack() if aware else {}).items() if v) or "nothing"
        self.status.set_text(f"● {state.unpack() if state else '?'}   {model.unpack() if model else '?'}"
                             f"   ADMIN: LOCKED\nSees: {sees}")

    def append(self, text: str) -> None:
        buf = self.chat.get_buffer()
        buf.insert(buf.get_end_iter(), text)
        self.chat.scroll_to_mark(buf.get_insert(), 0, False, 0, 0)

    def on_ask(self, entry: Gtk.Entry) -> None:
        text = entry.get_text().strip()
        if not text or not self.proxy:
            return
        entry.set_text("")
        self.append(f"\nYou: {text}\nAssistant: ")
        self.proxy.call("Ask", GLib.Variant("(s)", (text,)), Gio.DBusCallFlags.NONE, -1, None, None)

    def on_signal(self, proxy, sender, signal, params) -> None:
        if signal == "Token":
            self.append(params.unpack()[1])
        elif signal == "Done":
            self.append("\n")

    # --- GApplication ---------------------------------------------------------------------
    def do_command_line(self, cmdline: Gio.ApplicationCommandLine) -> int:
        if self.win is None:
            self.hold()
            self.build()
        args = cmdline.get_arguments()[1:] or ["--toggle"]
        action = {"--toggle": self.toggle, "--show": self.show, "--hide": self.hide,
                  "--quit": self.quit}.get(args[0])
        if action is None:
            cmdline.printerr(f"unknown option {args[0]}\n")
            return 2
        action()
        return 0


if __name__ == "__main__":
    sys.exit(Sidebar().run(sys.argv))
