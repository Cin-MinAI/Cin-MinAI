# SPDX-License-Identifier: GPL-3.0-or-later
"""The assistant sidebar (SPEC §5.1, §5.4, §5.5): docked on the right, one instance per session.

    cinminai-sidebar [--toggle | --flip | --show | --hide | --quit | --ask TEXT]

--toggle (the default; Super+A): open and focus, or close if it's open and focused. --flip (the panel icon):
open if closed, close if open.

Talks to org.cinminai.Assistant1 (the daemon is D-Bus activated when the sidebar opens). Answers stream
in as they're written; every tool the guide uses shows as a line in plain words; the header says what
runs where, and why it's reduced if it is. Nothing here reaches the network.
"""

from __future__ import annotations

import json
import sys

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, Gio, GLib, Gtk  # noqa: E402

from . import words  # noqa: E402
from .dock import Dock  # noqa: E402

APP_ID = "org.cinminai.Sidebar"
DAEMON = ("org.cinminai.Assistant1", "/org/cinminai/Assistant1", "org.cinminai.Assistant1")
WIDTH = 380  # logical px

CSS = b"""
#sidebar { background: @theme_bg_color; border-left: 1px solid @borders; }
#header { padding: 8px 6px 6px 10px; }
#state { font-weight: bold; }
#model { font-size: 90%; opacity: 0.8; }
#privacy { font-size: 85%; opacity: 0.7; padding: 0 10px 6px 10px; }
.dot { font-size: 120%; }
.dot.ok { color: #2ec27e; }
.dot.busy { color: #e5a50a; }
.dot.off { color: alpha(@theme_fg_color, 0.5); }
.dot.bad { color: #e01b24; }
#chat { padding: 8px 10px; }
.bubble { padding: 8px 10px; border-radius: 10px; }
.bubble.user { background: alpha(@theme_selected_bg_color, 0.25); }
.bubble.assistant { background: alpha(@theme_fg_color, 0.06); }
.bubble.error { background: alpha(#e01b24, 0.15); }
.waiting { opacity: 0.65; font-style: italic; }
.action { font-size: 88%; opacity: 0.75; }
#input { padding: 6px 8px 8px 8px; }
"""


class Sidebar(Gtk.Application):
    def __init__(self) -> None:
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.win: Gtk.ApplicationWindow | None = None
        self.proxy: Gio.DBusProxy | None = None
        self.rid: int | None = None       # the answer we're showing
        self.reply: Gtk.Label | None = None
        self.reply_started = False
        self.pending_ask: str | None = None

    # --- window ------------------------------------------------------------------------------------
    def build(self) -> None:
        css = Gtk.CssProvider()
        css.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        win = Gtk.ApplicationWindow(application=self, title="Cin-MinAI Assistant")
        win.set_name("sidebar")
        win.set_wmclass("cinminai-sidebar", "Cin-MinAI Sidebar")
        win.connect("delete-event", lambda *a: win.hide() or True)
        win.connect("key-press-event", self.on_key)
        self.win = win
        self.dock = Dock(win, WIDTH)

        # header: state, model, new conversation, close
        self.dot = Gtk.Label(label="●")
        self.dot.get_style_context().add_class("dot")
        self.state_label = Gtk.Label(xalign=0, name="state")
        self.model_label = Gtk.Label(xalign=0, name="model", wrap=True, max_width_chars=30)
        texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        top = Gtk.Box(spacing=6)
        top.pack_start(self.dot, False, False, 0)
        top.pack_start(self.state_label, False, False, 0)
        texts.pack_start(top, False, False, 0)
        texts.pack_start(self.model_label, False, False, 0)
        new = self.icon_button("document-new-symbolic", "New conversation", self.on_new)
        close = self.icon_button("window-close-symbolic", "Hide (Esc or Super+A)", lambda b: self.hide())
        header = Gtk.Box(name="header", spacing=4)
        header.pack_start(texts, True, True, 0)
        header.pack_end(close, False, False, 0)
        header.pack_end(new, False, False, 0)
        privacy = Gtk.Label(xalign=0, name="privacy", wrap=True, max_width_chars=30,
                            label="Runs on this computer. What you type stays here.")

        # the conversation
        self.chat = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, name="chat")
        self.scroll = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        self.scroll.add(self.chat)
        self.scroll.get_vadjustment().connect("changed", self.follow)
        self.hello()

        # input
        self.entry = Gtk.Entry(placeholder_text="Ask…", hexpand=True)
        self.entry.connect("activate", self.on_ask)
        self.go = self.icon_button("go-next-symbolic", "Ask", lambda b: self.on_ask(self.entry))
        self.stop = self.icon_button("media-playback-stop-symbolic", "Stop the answer", self.on_stop)
        inputs = Gtk.Box(spacing=4, name="input")
        inputs.pack_start(self.entry, True, True, 0)
        inputs.pack_end(self.stop, False, False, 0)
        inputs.pack_end(self.go, False, False, 0)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        for w, expand in ((header, False), (privacy, False), (Gtk.Separator(), False),
                          (self.scroll, True), (Gtk.Separator(), False), (inputs, False)):
            box.pack_start(w, expand, expand, 0)
        win.add(box)
        box.show_all()
        self.stop.hide()
        self.set_header("offline", {})
        self.connect_daemon()

    @staticmethod
    def icon_button(icon: str, tip: str, cb) -> Gtk.Button:
        b = Gtk.Button.new_from_icon_name(icon, Gtk.IconSize.BUTTON)
        b.set_relief(Gtk.ReliefStyle.NONE)
        b.set_tooltip_text(tip)
        b.connect("clicked", cb)
        return b

    def hello(self) -> None:
        self.bubble("assistant", "Hello! I can help you use this computer: finding things, how-to steps, "
                                 "and checking how it's doing. What would you like to do?")

    def bubble(self, kind: str, text: str) -> Gtk.Label:
        label = Gtk.Label(label=text, xalign=0, wrap=True, selectable=True, max_width_chars=30)
        label.set_line_wrap_mode(2)  # Pango WORD_CHAR
        frame = Gtk.Box()
        frame.get_style_context().add_class("bubble")
        frame.get_style_context().add_class(kind)
        frame.pack_start(label, True, True, 0)
        row = Gtk.Box()
        if kind == "user":
            row.pack_end(frame, False, False, 0)
            frame.set_margin_start(40)
        else:
            row.pack_start(frame, True, True, 0)
        self.chat.pack_start(row, False, False, 0)
        row.show_all()
        return label

    def action_line(self, icon: str, text: str) -> None:
        row = Gtk.Box(spacing=6)
        row.get_style_context().add_class("action")
        row.pack_start(Gtk.Image.new_from_icon_name(icon, Gtk.IconSize.MENU), False, False, 0)
        row.pack_start(Gtk.Label(label=text, xalign=0, wrap=True, max_width_chars=30), True, True, 0)
        # above the answer it belongs to
        if self.reply is not None:
            parent = self.reply.get_parent().get_parent()
            self.chat.pack_start(row, False, False, 0)
            self.chat.reorder_child(row, self.chat.get_children().index(parent))
        else:
            self.chat.pack_start(row, False, False, 0)
        row.show_all()

    def follow(self, adj: Gtk.Adjustment) -> None:
        adj.set_value(adj.get_upper() - adj.get_page_size())  # keep the newest text in view

    def show(self) -> None:
        self.win.show()
        self.dock.place()
        # hotkey launches come without a user timestamp: the X server time counts as "now"
        self.dock.take_focus()
        self.entry.grab_focus()

    def hide(self) -> None:
        self.win.hide()  # the window manager drops an unmapped window's struts

    def toggle(self) -> None:
        if self.win.get_visible() and self.win.is_active():
            self.hide()
        else:
            self.show()

    def flip(self) -> None:
        """The panel icon: open if closed, close if open (a panel click takes focus from nothing)."""
        if self.win.get_visible():
            self.hide()
        else:
            self.show()

    def on_key(self, win, event) -> bool:
        if event.keyval == Gdk.KEY_Escape:
            self.hide()
            return True
        return False

    # --- daemon --------------------------------------------------------------------------------------
    def connect_daemon(self) -> None:
        # without DO_NOT_AUTO_START, the proxy D-Bus-activates the daemon
        Gio.DBusProxy.new_for_bus(Gio.BusType.SESSION, Gio.DBusProxyFlags.NONE, None, *DAEMON, None, self.on_proxy)

    def on_proxy(self, source, result) -> None:
        try:
            self.proxy = Gio.DBusProxy.new_for_bus_finish(result)
        except GLib.Error as e:
            self.set_header("offline", {"detail": e.message})
            return
        self.proxy.connect("g-properties-changed", lambda *a: self.update_header())
        self.proxy.connect("notify::g-name-owner", lambda *a: self.update_header())
        self.proxy.connect("g-signal", self.on_signal)
        self.update_header()
        if self.pending_ask:
            text, self.pending_ask = self.pending_ask, None
            self.ask(text)

    def prop(self, name: str, default=None):
        v = self.proxy.get_cached_property(name) if self.proxy else None
        return v.unpack() if v is not None else default

    def state(self) -> str:
        if not self.proxy or not self.proxy.get_name_owner():
            return "offline"
        return self.prop("State", "offline")

    def update_header(self) -> None:
        self.set_header(self.state(), self.prop("Status", {}) or {})

    def set_header(self, state: str, status: dict) -> None:
        dot, first, second = words.status_line(state, status)
        ctx = self.dot.get_style_context()
        for c in ("ok", "busy", "off", "bad"):
            ctx.remove_class(c)
        ctx.add_class(dot)
        self.state_label.set_text(first)
        self.model_label.set_text(second)
        busy = self.rid is not None
        self.stop.set_visible(busy)
        self.go.set_visible(not busy)
        if self.reply is not None and not self.reply_started:
            self.reply.set_text(words.waiting(state, status.get("build", "")))

    def on_ask(self, entry: Gtk.Entry) -> None:
        text = entry.get_text().strip()
        if text and self.rid is None:
            entry.set_text("")
            self.ask(text)

    def ask(self, text: str) -> None:
        if not self.proxy:
            self.pending_ask = text
            return
        self.bubble("user", text)
        self.reply = self.bubble("assistant", words.waiting(self.state(), (self.prop("Status", {}) or {}).get("build", "")))
        self.reply.get_style_context().add_class("waiting")
        self.reply_started = False
        self.rid = -1  # asked, id not back yet

        def asked(proxy, result) -> None:
            try:
                (self.rid,) = proxy.call_finish(result).unpack()
            except GLib.Error as e:
                Gio.DBusError.strip_remote_error(e)
                self.finish_reply(error="The assistant is busy with another answer. Please wait a moment."
                                  if "Busy" in (e.message or "") else f"The assistant couldn't be reached. ({e.message})")
                self.entry.set_text(text)
            self.update_header()

        self.proxy.call("Ask", GLib.Variant("(s)", (text,)), Gio.DBusCallFlags.NONE, 600000, None, asked)
        self.update_header()

    def on_stop(self, button) -> None:
        if self.proxy:
            self.proxy.call("Cancel", None, Gio.DBusCallFlags.NONE, -1, None, None)

    def on_new(self, button) -> None:
        if self.rid is not None:
            self.on_stop(button)
        if self.proxy:
            self.proxy.call("Reset", None, Gio.DBusCallFlags.NONE, -1, None, None)
        for child in self.chat.get_children():
            child.destroy()
        self.reply, self.rid = None, None
        self.hello()
        self.update_header()
        self.entry.grab_focus()

    def on_signal(self, proxy, sender, signal, params) -> None:
        args = params.unpack()
        if self.rid is None or (self.rid != -1 and args[0] != self.rid):
            return  # another client's question (e.g. Firefox, a test)
        if signal == "Token" and self.reply is not None:
            if not self.reply_started:
                self.reply_started = True
                self.reply.set_text("")
                self.reply.get_style_context().remove_class("waiting")
            self.reply.set_text(self.reply.get_text() + args[1])
        elif signal == "Action" and args[3] == "done":
            self.action_line(*words.action(args[1], json.loads(args[2] or "{}"), args[4]))
        elif signal == "Error":
            self.finish_reply(error=args[1])
        elif signal == "Done":
            self.finish_reply()

    def finish_reply(self, error: str | None = None) -> None:
        if self.reply is not None:
            if error:
                self.reply.set_text(error)
                ctx = self.reply.get_parent().get_style_context()
                ctx.remove_class("assistant")
                ctx.add_class("error")
                self.reply.get_style_context().remove_class("waiting")
            elif not self.reply_started:
                self.reply.set_text("(stopped)")
        self.reply, self.rid = None, None
        self.update_header()

    # --- GApplication --------------------------------------------------------------------------------
    def do_command_line(self, cmdline: Gio.ApplicationCommandLine) -> int:
        if self.win is None:
            self.hold()
            self.build()
        args = cmdline.get_arguments()[1:] or ["--toggle"]
        if args[0] == "--ask" and len(args) > 1:
            self.show()
            self.ask(" ".join(args[1:]))
            return 0
        action = {"--toggle": self.toggle, "--flip": self.flip, "--show": self.show, "--hide": self.hide,
                  "--quit": self.quit}.get(args[0])
        if action is None:
            cmdline.printerr(f"unknown option {args[0]}\n")
            return 2
        action()
        return 0


def main() -> None:
    sys.exit(Sidebar().run(sys.argv))
