# SPDX-License-Identifier: GPL-3.0-or-later
"""Docking on the right edge with reserved space (SPEC §5.1 stage 1), from the M0 desktop-surface spike
(docs/spikes.md "Desktop surface", GO 2026-09-24, 27/27 checks + hands-on). What it learned, kept here:

1. The window is a DOCK: Muffin keeps normal windows out of every strut, their own included, and applies
   focus-stealing prevention to them; docks are exempt from both. Muffin doesn't focus a dock on click,
   so focus is requested by hand (with the click's time, or the X server time for the hotkey).
2. Cinnamon panels set to (intelli)hide reserve no space: stay clear of them, or the panel hides for good.
3. Resolution changes arrive in a burst (mode, then scale a moment later): re-dock, debounced.
"""

from __future__ import annotations

import ctypes
import warnings

import gi

warnings.filterwarnings("ignore", category=DeprecationWarning)  # Screen.get_width: X11-only, needed here
gi.require_version("Gdk", "3.0")
gi.require_version("GdkX11", "3.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GdkX11, Gio, GLib, Gtk  # noqa: E402


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


def cinnamon_panels(monitor: int) -> tuple[int, int]:
    """Heights (logical px) of Cinnamon panels at the top and bottom of a monitor."""
    source = Gio.SettingsSchemaSource.get_default()
    if not source or not source.lookup("org.cinnamon", True):
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


class Dock:
    def __init__(self, win: Gtk.Window, width: int) -> None:
        self.win, self.width, self.x11 = win, width, X11()
        self.pending = 0
        win.set_type_hint(Gdk.WindowTypeHint.DOCK)
        win.set_decorated(False)
        win.set_skip_taskbar_hint(True)
        win.set_skip_pager_hint(True)
        win.stick()  # all workspaces
        win.connect("realize", lambda w: self.place())
        # capture phase: see every click before the widget under it does; doesn't claim it
        self.click = Gtk.GestureMultiPress.new(win)
        self.click.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        self.click.connect("pressed", self.on_click)
        screen = Gdk.Screen.get_default()
        screen.connect("monitors-changed", lambda *a: self.watch_monitors())
        screen.connect("size-changed", lambda *a: self.queue_place())
        win.connect("notify::scale-factor", lambda *a: self.queue_place())
        self.watch_monitors()

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
        if self.pending:
            GLib.source_remove(self.pending)

        def run() -> bool:
            self.pending = 0
            self.place()
            return False

        self.pending = GLib.timeout_add(150, run)

    def place(self) -> None:
        """Right edge of the primary monitor, full work-area height, space reserved."""
        win, w = self.win, self.width
        display = Gdk.Display.get_default()
        mon = display.get_primary_monitor() or display.get_monitor(0)
        index = next(i for i in range(display.get_n_monitors()) if display.get_monitor(i) == mon)
        geo, wa, scale = mon.get_geometry(), mon.get_workarea(), mon.get_scale_factor()
        x, y, h = geo.x + geo.width - w, wa.y, wa.height
        panel_top, panel_bottom = cinnamon_panels(index)
        if wa.y == geo.y:
            y, h = y + panel_top, h - panel_top
        if wa.y + wa.height == geo.y + geo.height:
            h -= panel_bottom
        win.move(x, y)
        win.resize(w, h)
        if not win.get_realized():
            return
        # struts are in device pixels, measured from the edge of the whole X screen
        screen_w = Gdk.Screen.get_default().get_width() * scale
        right = screen_w - (geo.x + geo.width - w) * scale
        xid = GdkX11.X11Window.get_xid(win.get_window())
        top, bottom = y * scale, (y + h) * scale - 1
        self.x11.set_cardinals(xid, "_NET_WM_STRUT_PARTIAL", [0, right, 0, 0, 0, 0, top, bottom, 0, 0, 0, 0])
        self.x11.set_cardinals(xid, "_NET_WM_STRUT", [0, right, 0, 0])

    def take_focus(self, timestamp: int | None = None) -> None:
        gdk_win = self.win.get_window()
        ts = timestamp or GdkX11.x11_get_server_time(gdk_win)
        self.win.present_with_time(ts)
        gdk_win.focus(ts)

    def on_click(self, gesture, n_press, x, y) -> None:
        if not self.win.is_active():
            event = gesture.get_last_event(gesture.get_current_sequence())
            self.take_focus(event.get_time() if event else None)
