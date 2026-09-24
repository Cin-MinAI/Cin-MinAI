#!/usr/bin/env python3
"""Desktop-surface spike checks (M0). Run on the Mint box in the Cinnamon session after install.sh:

    DISPLAY=:0 python3 check.py [--xrandr MODE] [--shots DIR]

Drives the real X server: reads the work area / active window / geometry, types with XTest
(hotkey and text), and saves screenshots for a human to look at. --xrandr MODE also switches the
monitor to MODE and back to check that the sidebar follows (the screen will flicker).

WARNING: --xrandr bypasses Cinnamon's display manager; when the mode comes back Cinnamon picks a
scale again and *saves* it to ~/.config/cinnamon-monitors.xml (it changed 3x to 2x on the Mint box).
Use it only on a test machine, or restore the scale in System Settings → Display afterwards.
A proper test would go through org.cinnamon.Muffin.DisplayConfig.
"""

from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import time

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gtk  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SIDEBAR = os.path.expanduser("~/.local/bin/cinminai-sidebar")
DAEMON = ("org.cinminai.Assistant1", "/org/cinminai/Assistant1", "org.cinminai.Assistant1")
WIDTH = 380
SHOTS = sys.argv[sys.argv.index("--shots") + 1] if "--shots" in sys.argv else "/tmp/cinminai-shots"
XRANDR = sys.argv[sys.argv.index("--xrandr") + 1] if "--xrandr" in sys.argv else None
os.makedirs(SHOTS, exist_ok=True)

results: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""), flush=True)


# --- X helpers --------------------------------------------------------------------------------

def sh(*cmd: str) -> str:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=10).stdout


def workarea() -> list[int]:
    return [int(v) for v in sh("xprop", "-root", "_NET_WORKAREA").split("=")[1].split(",")[:4]]


def active_window() -> int:
    return int(sh("xprop", "-root", "_NET_ACTIVE_WINDOW").split()[-1], 16)


def find_window(wm_class: str) -> dict | None:
    """Mapped window by WM_CLASS; geometry from xwininfo (wmctrl misreports dock windows)."""
    for line in sh("wmctrl", "-lx").splitlines():
        f = line.split(None, 4)
        if len(f) >= 3 and wm_class in f[2]:
            info = dict(l.strip().split(": ", 1) for l in sh("xwininfo", "-id", f[0]).splitlines()
                        if ": " in l)
            return {"id": int(f[0], 16), "desktop": int(f[1]),
                    "x": int(info["Absolute upper-left X"]), "y": int(info["Absolute upper-left Y"]),
                    "w": int(info["Width"]), "h": int(info["Height"])}
    return None


def spawn(*cmd: str) -> None:
    subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True)


def applet_state() -> str:
    """Icon name + tooltip of the running applet, read through Cinnamon's Eval."""
    js = ("imports.ui.appletManager.getRunningInstancesForUuid('cinminai@cinminai')"
          ".map(a => a._applet_icon.icon_name + ' | ' + a._applet_tooltip._tooltip.get_text()).join(';')")
    ok, out = bus().call_sync("org.Cinnamon", "/org/Cinnamon", "org.Cinnamon", "Eval",
                              GLib.Variant("(s)", (js,)), None, Gio.DBusCallFlags.NONE, 3000, None).unpack()
    return out.strip('"') if ok else f"eval failed: {out}"


def panel_height(scale: int) -> int:
    s = Gio.Settings.new("org.cinnamon")
    bottom = [e.split(":")[0] for e in s.get_strv("panels-enabled") if e.endswith(":0:bottom")]
    heights = dict(e.split(":")[:2] for e in s.get_strv("panels-height"))
    return int(heights.get(bottom[0], 0)) * scale if bottom else 0


def wait_for(pred, timeout: float = 5.0, step: float = 0.1):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        v = pred()
        if v:
            return v
        time.sleep(step)
    return pred()


def screen_px() -> tuple[int, int, int]:
    ctx = GLib.MainContext.default()
    while ctx.pending():  # take in display changes (xrandr) since the last look
        ctx.iteration(False)
    mon = Gdk.Display.get_default().get_monitor(0)
    g, s = mon.get_geometry(), mon.get_scale_factor()
    return g.width * s, g.height * s, s


class XTest:
    def __init__(self) -> None:
        self.x = ctypes.cdll.LoadLibrary("libX11.so.6")
        self.t = ctypes.cdll.LoadLibrary("libXtst.so.6")
        self.x.XOpenDisplay.restype = ctypes.c_void_p
        self.x.XOpenDisplay.argtypes = [ctypes.c_char_p]
        self.x.XStringToKeysym.restype = ctypes.c_ulong
        self.x.XStringToKeysym.argtypes = [ctypes.c_char_p]
        self.x.XKeysymToKeycode.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        self.x.XFlush.argtypes = [ctypes.c_void_p]
        self.t.XTestFakeKeyEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_int, ctypes.c_ulong]
        self.t.XTestFakeMotionEvent.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_ulong]
        self.t.XTestFakeButtonEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_int, ctypes.c_ulong]
        self.dpy = self.x.XOpenDisplay(None)

    def click(self, x: int, y: int) -> None:
        """Left click at root coordinates (device px), like a real mouse."""
        self.t.XTestFakeMotionEvent(self.dpy, -1, x, y, 0)
        self.x.XFlush(self.dpy)
        time.sleep(0.1)
        self.t.XTestFakeButtonEvent(self.dpy, 1, 1, 0)
        self.t.XTestFakeButtonEvent(self.dpy, 1, 0, 0)
        self.x.XFlush(self.dpy)
        time.sleep(0.3)

    def code(self, name: str) -> int:
        return self.x.XKeysymToKeycode(self.dpy, self.x.XStringToKeysym(name.encode()))

    def key(self, *names: str) -> None:
        """Press names in order (modifiers first), release in reverse."""
        codes = [self.code(n) for n in names]
        for c in codes:
            self.t.XTestFakeKeyEvent(self.dpy, c, 1, 0)
        for c in reversed(codes):
            self.t.XTestFakeKeyEvent(self.dpy, c, 0, 0)
        self.x.XFlush(self.dpy)
        time.sleep(0.03)

    def type(self, text: str) -> None:
        names = {" ": "space", "\n": "Return", ".": "period", "-": "minus"}
        for ch in text:
            self.key(names.get(ch, ch))


def screenshot(name: str, region: tuple[int, int, int, int] | None = None, width: int = 1600) -> str:
    """Root window (or a region, device px) scaled to `width`, saved as PNG."""
    root = Gdk.get_default_root_window()
    sw, shh, s = screen_px()
    x, y, w, h = region or (0, 0, sw, shh)
    # Gdk works in logical px on scaled displays.
    pb = Gdk.pixbuf_get_from_window(root, x // s, y // s, w // s, h // s)
    if pb.get_width() > width:
        pb = pb.scale_simple(width, pb.get_height() * width // pb.get_width(), GdkPixbuf.InterpType.BILINEAR)
    path = os.path.join(SHOTS, f"{name}.png")
    pb.savev(path, "png", [], [])
    return path


def bus() -> Gio.DBusConnection:
    return Gio.bus_get_sync(Gio.BusType.SESSION)


def daemon_prop(name: str, autostart: bool = True):
    flags = Gio.DBusCallFlags.NONE if autostart else Gio.DBusCallFlags.NO_AUTO_START
    try:
        v = bus().call_sync(DAEMON[0], DAEMON[1], "org.freedesktop.DBus.Properties", "Get",
                            GLib.Variant("(ss)", (DAEMON[2], name)), None, flags, 3000, None)
    except GLib.Error:
        return None
    return v.unpack()[0]


def daemon_call(method: str, *args: str) -> None:
    bus().call_sync(DAEMON[0], DAEMON[1], DAEMON[2], method,
                    GLib.Variant("(" + "s" * len(args) + ")", args), None, Gio.DBusCallFlags.NONE, 3000, None)


def daemon_running() -> bool:
    return bool(sh("pgrep", "-f", "desktop/daemon.py").strip())


class TestWindow:
    """An ordinary maximized app window, to see where maximized windows stop."""

    def __init__(self) -> None:
        self.proc = subprocess.Popen([sys.executable, "-c", (
            "import gi; gi.require_version('Gtk','3.0'); from gi.repository import Gtk;"
            "w=Gtk.Window(title='cinminai-testwin'); w.set_wmclass('cinminai-testwin','Testwin');"
            "w.add(Gtk.Label(label='test window')); w.connect('destroy', Gtk.main_quit);"
            "w.maximize(); w.show_all(); Gtk.main()")])
        self.win = wait_for(lambda: find_window("cinminai-testwin"))

    def close(self) -> None:
        self.proc.terminate()
        self.proc.wait()


# --- checks -----------------------------------------------------------------------------------

def main() -> int:
    sw, shh, scale = screen_px()
    strip = WIDTH * scale
    xt = XTest()

    subprocess.run([SIDEBAR, "--quit"], capture_output=True)
    subprocess.run(["pkill", "-f", "desktop/daemon.py"])
    time.sleep(0.5)
    base_wa = workarea()

    # Applet with the daemon down (it must not auto-start the daemon).
    time.sleep(0.5)
    st = applet_state()
    record("applet loaded, shows daemon offline", st.startswith("network-offline-symbolic")
           and not daemon_running(), st)

    # D-Bus activation.
    state = daemon_prop("State")
    record("daemon D-Bus activated on first call", state == "idle" and daemon_running(), f"State={state}")
    st = wait_for(lambda: applet_state().startswith("user-available") and applet_state(), 3)
    record("applet follows: idle", bool(st), applet_state())

    # Sidebar docks and reserves space.
    tw = TestWindow()
    spawn(SIDEBAR, "--show")
    wait_for(lambda: find_window("cinminai-sidebar"))
    time.sleep(0.8)
    sb = find_window("cinminai-sidebar")
    wa = workarea()
    panel = panel_height(scale)
    record("sidebar at the right edge, clear of the panel",
           bool(sb) and sb["x"] + sb["w"] == sw and abs(sb["w"] - strip) <= scale
           and sb["y"] + sb["h"] == shh - panel, f"{sb}, panel {panel}px")
    record("work area shrinks by the sidebar width", wa[2] == base_wa[2] - strip, f"{base_wa} -> {wa}")
    maxed = find_window("cinminai-testwin")
    record("maximized windows stop at the sidebar",
           bool(maxed) and maxed["x"] + maxed["w"] <= sw - strip, f"testwin {maxed}")
    record("sidebar on all workspaces (sticky)", bool(sb) and sb["desktop"] == -1, f"desktop={sb and sb['desktop']}")
    record("sidebar opened focused", bool(sb) and active_window() == sb["id"],
           f"active=0x{active_window():x} sidebar=0x{sb['id'] if sb else 0:x}")

    xt.type("hello sidebar\n")
    ask = wait_for(lambda: daemon_prop("LastAsk") == "hello sidebar", 3)
    record("typing goes to the sidebar input, reaches the daemon", bool(ask), f"LastAsk={daemon_prop('LastAsk')!r}")
    st = wait_for(lambda: applet_state().startswith("emblem-synchronizing") and applet_state(), 2, 0.05)
    record("applet follows: thinking while streaming", bool(st), applet_state())
    time.sleep(2.5)
    screenshot("sidebar-streamed", (sw - strip - 200, 0, strip + 200, shh), 900)
    screenshot("desktop")

    # Workspaces.
    sh("wmctrl", "-s", "1")
    time.sleep(0.8)
    on_ws2 = find_window("cinminai-sidebar")
    wa2 = workarea()
    sh("wmctrl", "-s", "0")
    time.sleep(0.5)
    record("survives a workspace switch", bool(on_ws2) and wa2[2] == base_wa[2] - strip, f"workarea on ws2 {wa2}")
    record("(info) still focused after switching back", True,
           str(bool(on_ws2) and active_window() == on_ws2["id"]))

    # Escape hides and gives the space back.
    spawn(SIDEBAR, "--show")
    wait_for(lambda: on_ws2 and active_window() == on_ws2["id"], 3)
    xt.key("Escape")
    gone = wait_for(lambda: find_window("cinminai-sidebar") is None, 2)
    record("Escape hides it and frees the space", bool(gone) and workarea()[2] == base_wa[2], f"{workarea()}")

    # Hotkey from another window.
    sh("wmctrl", "-i", "-a", hex(tw.win["id"]))
    time.sleep(0.5)
    xt.key("Super_L", "a")
    sb = wait_for(lambda: find_window("cinminai-sidebar"), 3)
    time.sleep(0.5)
    record("hotkey opens it focused", bool(sb) and active_window() == sb["id"],
           f"active=0x{active_window():x}")
    ctx = screenshot("sidebar-hotkey", (sw - strip, 0, strip, 400), 600)
    record("context line names the previously focused window (see screenshot)", True, ctx)
    xt.type("via hotkey\n")
    ask = wait_for(lambda: daemon_prop("LastAsk") == "via hotkey", 3)
    record("hotkey → type → daemon", bool(ask), f"LastAsk={daemon_prop('LastAsk')!r}")
    time.sleep(2.5)

    # The way a person does it: focus goes elsewhere, they click back into the Ask field.
    sh("wmctrl", "-i", "-a", hex(tw.win["id"]))
    time.sleep(0.5)
    xt.click(sb["x"] + sb["w"] // 2, sb["y"] + sb["h"] - 25 * scale)
    record("clicking the Ask field focuses the sidebar", active_window() == sb["id"],
           f"active=0x{active_window():x}")
    xt.type("after click\n")
    ask = wait_for(lambda: daemon_prop("LastAsk") == "after click", 3)
    record("second prompt after clicking back in", bool(ask), f"LastAsk={daemon_prop('LastAsk')!r}")
    time.sleep(2.5)
    xt.key("Super_L", "a")
    record("hotkey hides it after a click", bool(wait_for(lambda: find_window("cinminai-sidebar") is None, 2)))

    xt.key("Super_L", "a")
    sb = wait_for(lambda: find_window("cinminai-sidebar"), 3)
    time.sleep(0.5)
    ctx = screenshot("sidebar-reopened", (sw - strip, 0, strip, 400), 600)
    xt.click(sb["x"] + sb["w"] - 12 * scale, sb["y"] + 12 * scale)
    record("close button hides it", bool(wait_for(lambda: find_window("cinminai-sidebar") is None, 2)), ctx)

    # Applet states.
    icons = {"approval": "dialog-warning", "error": "dialog-error", "off": "user-offline",
             "idle": "user-available"}
    for s, icon in icons.items():
        daemon_call("SetState", s)
        got = wait_for(lambda: applet_state().startswith(icon), 2, 0.05)
        record(f"applet follows: {s}", bool(got), applet_state())
    subprocess.run(["pkill", "-f", "desktop/daemon.py"])
    got = wait_for(lambda: applet_state().startswith("network-offline"), 3)
    record("applet notices the daemon dying", bool(got), applet_state())

    # Monitor change.
    if XRANDR:
        out = sh("xrandr")
        output = next(l.split()[0] for l in out.splitlines() if " connected" in l)
        current = next(l.split()[0] for l in out.splitlines() if "*" in l)
        spawn(SIDEBAR, "--show")
        wait_for(lambda: find_window("cinminai-sidebar"))
        sh("xrandr", "--output", output, "--mode", XRANDR)
        time.sleep(3)
        nsw, nsh, nscale = screen_px()
        sb = find_window("cinminai-sidebar")
        wa = workarea()
        ok = (bool(sb) and sb["x"] + sb["w"] == nsw and sb["w"] == WIDTH * nscale
              and wa[2] == nsw - WIDTH * nscale)
        screenshot("after-xrandr")
        sh("xrandr", "--output", output, "--mode", current)
        time.sleep(3)
        bsw, bsh, bscale = screen_px()
        sb2 = find_window("cinminai-sidebar")
        wa2 = workarea()
        back = (bool(sb2) and sb2["x"] + sb2["w"] == bsw and sb2["w"] == WIDTH * bscale
                and wa2[2] == bsw - WIDTH * bscale)
        record(f"follows a resolution change to {XRANDR} (scale {nscale})", ok,
               f"{nsw}x{nsh}: {sb}, workarea {wa}")
        record(f"follows the change back (scale {bscale})", back, f"{bsw}x{bsh}: {sb2}, workarea {wa2}")
        subprocess.run([SIDEBAR, "--hide"])

    tw.close()
    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks pass; screenshots in {SHOTS}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
