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
import os
import sys

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gtk  # noqa: E402

from . import words  # noqa: E402
from .dock import Dock  # noqa: E402

APP_ID = "org.cinminai.Sidebar"
DAEMON = ("org.cinminai.Assistant1", "/org/cinminai/Assistant1", "org.cinminai.Assistant1")
LIBREOFFICE = ("org.cinminai.LibreOffice1", "/org/cinminai/LibreOffice1", "org.cinminai.LibreOffice1")
WIDTH = 380  # logical px
AUTO_CHECKS = 4  # Download…: files checked by themselves (each reads up to ~96 MB of its header)

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
#project, #journal { padding: 2px 6px 2px 10px; }
.bubble { padding: 8px 10px; border-radius: 10px; }
.bubble.user { background: alpha(@theme_selected_bg_color, 0.25); }
.bubble.assistant { background: alpha(@theme_fg_color, 0.06); }
.bubble.error { background: alpha(#e01b24, 0.15); }
.waiting { opacity: 0.65; font-style: italic; }
.action { font-size: 88%; opacity: 0.75; }
.command { padding: 6px 8px; border-radius: 8px; border: 1px solid alpha(@theme_fg_color, 0.2); }
.command .code { font-family: monospace; }
.command .note { font-size: 88%; opacity: 0.8; }
.proposal { padding: 8px; border-radius: 8px; border: 1px solid alpha(@theme_selected_bg_color, 0.6); }
.proposal .what { font-weight: bold; }
.proposal .before { opacity: 0.6; }
.proposal .cell { font-family: monospace; font-size: 88%; padding: 1px 4px; border: 1px solid alpha(@theme_fg_color, 0.12); }
#input { padding: 6px 8px 8px 8px; }
.start { color: #ffffff; text-shadow: none; border: none; border-radius: 16px; padding: 7px 16px;
         background-image: linear-gradient(to bottom, alpha(#ffffff, 0.20), alpha(#ffffff, 0.0) 60%);
         box-shadow: inset 0 1px alpha(#ffffff, 0.25), 0 1px 3px alpha(#000000, 0.35); }
.start label { color: #ffffff; }
.start:hover { background-image: linear-gradient(to bottom, alpha(#ffffff, 0.30), alpha(#ffffff, 0.08)); }
.start:active { background-image: linear-gradient(to bottom, alpha(#000000, 0.15), alpha(#000000, 0.0));
                box-shadow: inset 0 1px 2px alpha(#000000, 0.35); }
.start.writing { background-color: #1c71d8; }
.start.journal { background-color: #813d9c; }
.start.aicui { background-color: #26a269; }
.start.standing { background-color: #c64600; }
.start.updates { background-color: #0f7b8a; }
.start.requests { background-color: #5e5c64; }
.start.models { background-color: #a51d6f; }
.start.library { background-color: #865e3c; }
"""


def margined(box) -> None:
    """A dialog's content with room around it (2026-10-04: the text touched the dialog's left edge)."""
    for side in ("start", "end", "top"):
        getattr(box, f"set_margin_{side}")(12)



class Answer(Gtk.Label):
    """An answer bubble: shows the model's Markdown formatted, and gives back the text as written (get_text), which
    the command cards, "Put in Writer" and the caveats read."""

    def __init__(self, text: str = "") -> None:
        super().__init__(xalign=0, wrap=True, selectable=True, max_width_chars=30)
        self.raw = ""
        self.set_text(text)

    def set_text(self, text: str) -> None:
        self.raw = text or ""
        try:
            self.set_markup(words.markdown(self.raw))
        except Exception:  # markup it can't show: the words as written
            Gtk.Label.set_text(self, self.raw)

    def get_text(self) -> str:
        return self.raw

class Sidebar(Gtk.Application):
    def __init__(self) -> None:
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.win: Gtk.ApplicationWindow | None = None
        self.proxy: Gio.DBusProxy | None = None
        self.rid: int | None = None       # the answer we're showing
        self.reply: Gtk.Label | None = None
        self.reply_started = False
        self.pending_ask: str | None = None
        self.cards: list[dict] = []        # commands from the tools' results, shown under the answer (D53)
        self.diag_step: dict | None = None  # a fault's tree, walked on a card under the answer (D51, D7)
        self.terminal_turn = False         # this answer read the shared terminal: cards get "To terminal" (M3)

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
        new = self.icon_button("document-new-symbolic", "New…", self.on_new_menu)
        close = self.icon_button("window-close-symbolic", "Hide (Esc or Super+A)", lambda b: self.hide())
        header = Gtk.Box(name="header", spacing=4)
        header.pack_start(texts, True, True, 0)
        header.pack_end(close, False, False, 0)
        header.pack_end(new, False, False, 0)
        privacy = Gtk.Label(xalign=0, name="privacy", wrap=True, max_width_chars=30,
                            label="Runs on this computer. What you type stays here.")

        # the writing project bar (D54): shown while a project is open
        self.project_label = Gtk.Label(xalign=0, wrap=True, max_width_chars=22)
        self.project_label.get_style_context().add_class("what")
        notes = Gtk.Button(label="Notes")
        notes.connect("clicked", lambda b: self.show_notes())
        writeup = Gtk.Button(label="Write it up")
        writeup.get_style_context().add_class("suggested-action")
        writeup.connect("clicked", lambda b: self.start_job("WriteUp", "", "Reading the story so far…"))
        close_project = self.icon_button("window-close-symbolic", "Close the writing project", lambda b: self.close_project())
        self.project_box = Gtk.Box(spacing=4, name="project")
        self.project_box.pack_start(self.project_label, True, True, 0)
        for w in (close_project, writeup, notes):
            self.project_box.pack_end(w, False, False, 0)

        # the journal bar (D55): shown while the journal is open
        journal_label = Gtk.Label(label="Journal", xalign=0)
        journal_label.get_style_context().add_class("what")
        self.private = Gtk.CheckButton(label="Private")
        self.private.set_tooltip_text("Locked with your 4-digit PIN; the assistant can't read it while it's locked")
        write_entry = Gtk.Button(label="Write today's entry")
        write_entry.get_style_context().add_class("suggested-action")
        write_entry.connect("clicked", lambda b: self.write_entry())
        entries = Gtk.Button(label="Entries")
        entries.connect("clicked", lambda b: self.show_entries())
        close_journal = self.icon_button("window-close-symbolic", "Close the journal", lambda b: self.close_journal())
        self.journal_box = Gtk.Box(spacing=4, name="journal")
        self.journal_box.pack_start(journal_label, False, False, 0)
        self.journal_box.pack_start(self.private, False, False, 0)
        for w in (close_journal, entries, write_entry):
            self.journal_box.pack_end(w, False, False, 0)

        # an installed update (D59): the assistant restarts into it on a 2-minute pause, or now if the person says so
        # (2026-10-07: Ian kept asking right after installing and got the old version, with nothing saying why)
        update_label = Gtk.Label(label=words.UPDATE_READY, xalign=0, wrap=True, max_width_chars=24)
        update_label.get_style_context().add_class("note")
        update_now = Gtk.Button(label=words.UPDATE_NOW)
        update_now.connect("clicked", lambda b: self.update_now(b))
        self.update_box = Gtk.Box(spacing=4, name="update")
        self.update_box.pack_start(update_label, True, True, 0)
        self.update_box.pack_end(update_now, False, False, 0)

        # the conversation
        self.chat = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, name="chat")
        # the conversation on white, dark or light theme alike; the box to type in stays the window's grey (Ian,
        # 2026-10-24: "the chat history white background and the box stays grey"); buttons in it keep the theme's look
        self.scroll = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER, name="chatscroll")
        self.scroll.add(self.chat)
        self.at_bottom = True  # follow the newest text only while the person is down there (Ian, 2026-10-24)
        self.scroll.get_vadjustment().connect("changed", self.follow)
        self.scroll.get_vadjustment().connect("value-changed", self.scrolled)
        self.hello()

        # input
        self.entry = Gtk.Entry(placeholder_text="Ask…", hexpand=True)
        self.entry.connect("activate", self.on_ask)
        self.go = self.icon_button("go-next-symbolic", "Ask", lambda b: self.on_ask(self.entry))
        self.stop = self.icon_button("media-playback-stop-symbolic", "Stop the answer", self.on_stop)
        inputs = Gtk.Box(spacing=4, name="input")
        # a picture to read (D64, D78): this button, or drop the file anywhere on the sidebar
        inputs.pack_start(self.icon_button("image-x-generic-symbolic", "Show me a picture: a photo, a screenshot, "
                                           "a scanned letter (or drop it here)", self.on_pick_image), False, False, 0)
        inputs.pack_start(self.entry, True, True, 0)
        inputs.pack_end(self.stop, False, False, 0)
        inputs.pack_end(self.go, False, False, 0)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        for w, expand in ((header, False), (privacy, False), (self.project_box, False), (self.journal_box, False),
                          (self.update_box, False), (Gtk.Separator(), False),
                          (self.scroll, True), (Gtk.Separator(), False), (inputs, False)):
            box.pack_start(w, expand, expand, 0)
        win.add(box)
        win.drag_dest_set(Gtk.DestDefaults.ALL, [], Gdk.DragAction.COPY)
        win.drag_dest_add_uri_targets()
        win.connect("drag-data-received", self.on_drop)
        box.show_all()
        self.stop.hide()
        self.project_box.hide()
        self.journal_box.hide()
        self.update_box.hide()
        self.said_updated = False
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
        # the writing modes, visible where a newcomer looks (2026-10-01: behind the header's New icon, not found).
        # A FlowBox, so the buttons wrap: in a plain row their total width became the chat's minimum width, and on
        # a 1024-pixel screen the whole conversation was cut off at the sidebar's edge (boot test, 2026-10-03).
        row = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, homogeneous=False, column_spacing=6,
                          row_spacing=6, min_children_per_line=1, max_children_per_line=2)
        # each in its own colour, on the start screen only (Ian, 2026-10-24: "for the initial UI it gets colored for
        # aesthetic"); the buttons inside the views keep the theme's grey, one look for every choice
        for kind, label, cb in (("writing", "Start a writing project", lambda b: self.new_project()),
                                ("journal", "Open the journal", lambda b: self.open_journal()),
                                ("aicui", "Open AICUI (coding)", lambda b: self.open_aicui()),
                                ("standing", words.t("standing"), lambda b: self.standing_list()),  # D88
                                ("updates", words.t("updates_window"), lambda b: self.open_updates()),  # D29
                                ("requests", words.t("requests"), lambda b: self.requests_view()),  # SPEC §22.4
                                ("models", words.t("models"), lambda b: self.models_view()),  # §22.3
                                ("library", words.t("library"), lambda b: self.library_view())):  # D68
            b = Gtk.Button(label=label)
            for c in ("start", kind):
                b.get_style_context().add_class(c)
            b.connect("clicked", cb)
            row.add(b)
        self.chat.pack_start(row, False, False, 0)
        row.show_all()

    def writer_button(self, text: str) -> None:
        """"Put in Writer" under an answer: a new Writer document with it (2026-10-01: "it won't write in Writer")."""
        b = Gtk.Button(label="Put in Writer")
        b.set_relief(Gtk.ReliefStyle.NONE)
        b.set_tooltip_text("Make a new Writer document with this answer and open it")
        b.get_style_context().add_class("action")

        def make(button) -> None:
            first = text.strip().splitlines()[0] if text.strip() else ""
            title = words.document_title(first)
            out = self.daemon_json("MakeDocument", title, text)
            if out:
                button.set_label(f"Saved {out['shown']}")
                button.set_sensitive(False)

        b.connect("clicked", make)
        row = Gtk.Box()
        row.pack_start(b, False, False, 0)
        self.chat.pack_start(row, False, False, 0)
        row.show_all()

    def bubble(self, kind: str, text: str) -> Gtk.Label:
        if kind == "user":
            label = Gtk.Label(label=text, xalign=0, wrap=True, selectable=True, max_width_chars=30)
        else:
            label = Answer(text)
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
        """Keep the newest text in view — unless the person scrolled up: the Models view's file checks kept adding
        lines and pulled them away from the Download button they were about to click (Ian, 2026-10-24)."""
        if self.at_bottom:
            adj.set_value(adj.get_upper() - adj.get_page_size())

    def scrolled(self, adj: Gtk.Adjustment) -> None:
        self.at_bottom = adj.get_value() >= adj.get_upper() - adj.get_page_size() - 24

    def to_bottom(self) -> None:
        """Something the person started (a question, a job): follow its answer again."""
        self.at_bottom = True
        self.follow(self.scroll.get_vadjustment())

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
        self.proxy.get_connection().signal_subscribe(LIBREOFFICE[0], LIBREOFFICE[2], "Asked", LIBREOFFICE[1], None,
                                                     Gio.DBusSignalFlags.NONE, self.on_libreoffice)
        self.update_header()
        GLib.idle_add(self.show_waiting)
        if not self.pending_ask:
            GLib.idle_add(self.rundown_offer)
        if self.pending_ask:
            text, self.pending_ask = self.pending_ask, None
            self.ask(text)

    def rundown_offer(self) -> bool:
        """D40: after a pause, "Want a quick rundown of where we left off?" Yes reads the notes back, No goes straight
        in (after a few no's in a row, asked once whether to stop offering), Start fresh is a new conversation."""
        try:  # quiet when it fails: an offer, not something the person asked for
            v = self.proxy.call_sync("RundownOffer", None, Gio.DBusCallFlags.NONE, 10000, None)
            offer = json.loads(v.unpack()[0]).get("offer")
        except (GLib.Error, ValueError, AttributeError):
            offer = False
        if not offer:
            return False
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.get_style_context().add_class("proposal")
        box.pack_start(Gtk.Label(label=words.t("r_offer"), xalign=0, wrap=True, max_width_chars=30), False, False, 0)
        row = Gtk.Box(spacing=6)

        def yes(b) -> None:
            box.destroy()
            self.start_job("Rundown", (), words.t("r_reading"), "()")

        def no(b) -> None:
            box.destroy()
            self.daemon_async("RundownSay", ("no",), "(s)", lambda v: v.get("ask_stop") and self.stop_asking())

        for label, cb in ((words.t("r_yes"), yes), (words.t("r_no"), no),
                          (words.t("r_fresh"), lambda b: (box.destroy(), self.on_new(None)))):
            b = Gtk.Button(label=label)
            b.connect("clicked", cb)
            row.pack_start(b, False, False, 0)
        box.pack_start(row, False, False, 0)
        self.chat.pack_start(box, False, False, 0)
        box.show_all()
        return False

    def stop_asking(self) -> None:
        """Asked once, after the third no in a row (Rule 9, D39)."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.get_style_context().add_class("proposal")
        box.pack_start(Gtk.Label(label=words.t("r_stop_q"), xalign=0, wrap=True, max_width_chars=30), False, False, 0)
        row = Gtk.Box(spacing=6)
        for label, choice in ((words.t("r_stop"), "stop"), (words.t("r_keep"), "keep")):
            b = Gtk.Button(label=label)
            b.connect("clicked", lambda b, c=choice: (box.destroy(),
                                                      self.daemon_async("RundownSay", (c,), "(s)", lambda v: None)))
            row.pack_start(b, False, False, 0)
        box.pack_start(row, False, False, 0)
        self.chat.pack_start(box, False, False, 0)
        box.show_all()

    def notebook_card(self, lines: list) -> None:
        """D40: the earlier conversation folded into notes, never silently: what was kept, each line removable."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        box.get_style_context().add_class("proposal")
        box.pack_start(self.note_label(words.t("n_kept")), False, False, 0)
        for i, line in enumerate(lines):
            row = Gtk.Box(spacing=6)
            text = Gtk.Label(label="• " + line, xalign=0, wrap=True, max_width_chars=28)
            row.pack_start(text, True, True, 0)
            x = Gtk.Button.new_from_icon_name("window-close-symbolic", Gtk.IconSize.MENU)
            x.set_relief(Gtk.ReliefStyle.NONE)
            x.set_tooltip_text(words.t("n_remove"))

            def remove(b, i=i) -> None:
                self.daemon_async("NotebookRemove", (i,), "(u)",
                                  lambda v: (box.destroy(), self.notebook_card(v.get("lines", []))))
            x.connect("clicked", remove)
            row.pack_end(x, False, False, 0)
            box.pack_start(row, False, False, 0)
        self.chat.pack_start(box, False, False, 0)
        box.show_all()

    def show_waiting(self) -> bool:
        """Cards proposed while the sidebar was closed (the CUDA engine's offer, update 6) are shown when it opens."""
        for card in (self.daemon_json("ActionList") or {}).get("waiting", []):
            self.action_card(card)
        return False

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
        project = status.get("project", "")
        self.project_label.set_text(words.project_bar(project))
        self.project_box.set_visible(bool(project))
        journal = bool(status.get("journal"))
        self.journal_box.set_visible(journal)
        self.update_box.set_visible(bool(status.get("update_ready")))
        if status.get("just_updated") and not self.said_updated:
            self.said_updated = True
            self.bubble("note", words.UPDATED)
        self.entry.set_placeholder_text("Tell me about your story…" if project else
                                        "Tell me about your day…" if journal else "Ask…")
        busy = self.rid is not None
        self.stop.set_visible(busy)
        self.go.set_visible(not busy)
        if self.reply is not None and not self.reply_started:  # a job keeps its own words ("Getting the model…")
            self.reply.set_text(getattr(self, "job_waiting", None) or
                                words.waiting(state, status.get("build", ""), status.get("detail", "")))

    def update_now(self, button) -> None:
        button.set_sensitive(False)

        def done(proxy, res) -> None:
            button.set_sensitive(True)
            try:
                proxy.call_finish(res)
            except GLib.Error as e:
                self.bubble("note", words.action_error(e.message))

        self.proxy.call("UpdateNow", None, Gio.DBusCallFlags.NONE, -1, None, done)

    # --- pictures (D64, D78) ------------------------------------------------------------------------------
    def on_pick_image(self, button) -> None:
        dialog = Gtk.FileChooserDialog(title="Show the assistant a picture or a video", parent=self.win,
                                       action=Gtk.FileChooserAction.OPEN)
        dialog.add_buttons("Cancel", Gtk.ResponseType.CANCEL, "Show it", Gtk.ResponseType.ACCEPT)
        pics = Gtk.FileFilter()
        pics.set_name("Pictures and videos")
        for ext in words.PICTURE_TYPES + words.VIDEO_TYPES:
            pics.add_pattern("*" + ext)
            pics.add_pattern("*" + ext.upper())
        dialog.add_filter(pics)
        dialog.set_current_folder(GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_PICTURES) or GLib.get_home_dir())
        if dialog.run() == Gtk.ResponseType.ACCEPT:
            path = dialog.get_filename()
            dialog.destroy()
            self.ask_image(path)
        else:
            dialog.destroy()

    def on_drop(self, widget, context, x, y, data, info, time_) -> None:
        for uri in data.get_uris() or []:
            path = GLib.filename_from_uri(uri)[0] if uri.startswith("file://") else None
            if path and path.lower().endswith(words.PICTURE_TYPES + words.VIDEO_TYPES):
                self.ask_image(path)
                return
        self.progress_line(words.NOT_A_PICTURE)

    def ask_image(self, path: str) -> None:
        """The picture in the chat, then the question typed in the box (or "what's in this picture?")."""
        if not self.proxy or self.rid is not None:
            return
        request = self.entry.get_text().strip()
        self.entry.set_text("")
        moving = path.lower().endswith(words.VIDEO_TYPES)
        self.bubble("user", request or (words.VIDEO_DEFAULT if moving else words.PICTURE_DEFAULT))
        try:
            if moving:  # the file's name; a thumbnail would need the video decoded here
                pic = Gtk.Label(label="🎞 " + os.path.basename(path), xalign=1, wrap=True, max_width_chars=30)
            else:
                pic = Gtk.Image.new_from_pixbuf(GdkPixbuf.Pixbuf.new_from_file_at_scale(path, 240, 240, True))
            pic.set_halign(Gtk.Align.END)
            self.chat.pack_start(pic, False, False, 0)
            pic.show()
        except GLib.Error:
            pass
        self.terminal_turn = False
        self.start_job("AskImage", (path, request), words.WATCHING if moving else words.LOOKING, "(ss)")

    def vision_setup_card(self, offer: dict) -> None:
        """The reading model's projector isn't here yet: a download, so asked first (D30)."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.get_style_context().add_class("proposal")
        head = Gtk.Label(label=words.vision_setup(offer), xalign=0, wrap=True, max_width_chars=30)
        head.get_style_context().add_class("what")
        box.pack_start(head, False, False, 0)
        buttons = Gtk.Box(spacing=6)
        go = Gtk.Button(label="Download ({} MB)".format(offer.get("size_mb", "?")))
        go.get_style_context().add_class("suggested-action")
        no = Gtk.Button(label="Not now")

        def fetch(b) -> None:
            go.set_sensitive(False)
            no.set_sensitive(False)
            self.start_job("VisionSetup", offer.get("id", ""), "Getting it ready…")

        go.connect("clicked", fetch)
        no.connect("clicked", lambda b: box.destroy())
        buttons.pack_start(go, False, False, 0)
        buttons.pack_start(no, False, False, 0)
        box.pack_start(buttons, False, False, 0)
        self.chat.pack_start(box, False, False, 0)
        box.show_all()

    def on_ask(self, entry: Gtk.Entry) -> None:
        text = entry.get_text().strip()
        if text and self.rid is None:
            entry.set_text("")
            self.ask(text)

    def ask(self, text: str) -> None:
        if not self.proxy:
            self.pending_ask = text
            return
        self.to_bottom()
        self.job_waiting = None
        self.bubble("user", text)
        self.terminal_turn = False
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

    def on_new(self, button, project: bool = False) -> None:
        """A fresh conversation; project=True: one inside the writing project just opened (D54)."""
        if self.rid is not None:
            self.on_stop(button)
        if self.proxy:
            self.proxy.call("Reset", None, Gio.DBusCallFlags.NONE, -1, None, None)
            status = self.prop("Status", {}) or {}
            if not project and status.get("project"):
                self.proxy.call("ProjectClose", None, Gio.DBusCallFlags.NONE, -1, None, None)
            if not project and status.get("journal"):
                self.proxy.call("JournalClose", None, Gio.DBusCallFlags.NONE, -1, None, None)
        for child in self.chat.get_children():
            child.destroy()
        self.reply, self.rid = None, None
        if project:
            self.bubble("assistant", words.PROJECT_HELLO)
        else:
            self.hello()
        self.update_header()
        self.entry.grab_focus()

    def on_signal(self, proxy, sender, signal, params) -> None:
        args = params.unpack()
        if signal == "ActionCard":           # M4: drawn from the daemon's record, whatever question it came from
            self.action_card(json.loads(args[0]))
            return
        if signal == "Standing":             # D88: a standing task's run found something new
            self.standing_report(json.loads(args[0]))
            return
        if self.rid is None or (self.rid != -1 and args[0] != self.rid):
            return  # another client's question (e.g. Firefox, a test)
        if signal == "Token" and self.reply is not None:
            if not self.reply_started:
                self.reply_started = True
                self.reply.set_text("")
                self.reply.get_style_context().remove_class("waiting")
            self.reply.set_text(self.reply.get_text() + args[1])
        elif signal == "Replace" and self.reply is not None:
            self.reply_started = True
            self.reply.get_style_context().remove_class("waiting")
            self.reply.set_text(args[1])
        elif signal == "Action" and args[1] == "notebook":  # D40: the notes after a compaction, said and correctable
            self.notebook_card(json.loads(args[4] or "{}").get("lines", []))
        elif signal == "Action" and args[1] == "outline" and args[3] == "proposal":
            self.outline_card(json.loads(args[4] or "{}"))
        elif signal == "Action" and args[1] == "review" and args[3] == "proposal":
            self.review_card(json.loads(args[4] or "{}"))
        elif signal == "Action" and args[1] == "sandbox" and args[3] == "running":
            self.progress_line(words.trying(json.loads(args[2] or "{}")))
        elif signal == "Action" and args[1] == "sandbox" and args[3] == "done":
            self.try_result(json.loads(args[4] or "{}"))
        elif signal == "Action" and args[1] == "vision_setup" and args[3] == "proposal":
            if self.reply is not None:
                self.reply.get_style_context().remove_class("waiting")
                self.reply.set_text(words.VISION_NEEDS)
                self.reply_started = True
            self.vision_setup_card(json.loads(args[4] or "{}"))
        elif signal == "Action" and args[1] == "vision" and args[3] == "running":
            self.progress_line(words.vision_reading(json.loads(args[2] or "{}")))
        elif signal == "Action" and args[1] == "video" and args[3] == "running":
            self.progress_line(words.video_step(json.loads(args[2] or "{}"), json.loads(args[4] or "{}")))
        elif signal == "Action" and args[1] == "video" and args[3] == "done":
            self.progress_line(words.video_caveat(json.loads(args[4] or "{}"), self.reply.get_text() if self.reply else ""))
        elif signal == "Action" and args[1] == "vision" and args[3] == "done":
            self.progress_line(words.vision_caveat(json.loads(args[4] or "{}"), self.reply.get_text() if self.reply else ""))
        elif signal == "Action" and args[1] == "terminal_offer" and args[3] == "proposal":
            self.terminal_offer_card()
        elif signal == "Action" and args[1] == "bigger_model" and args[3] == "proposal":
            self.bigger_card(json.loads(args[4] or "{}"))
        elif signal == "Action" and args[1] == "bigger_model" and args[3] == "running":
            self.progress_line(words.bigger_running(json.loads(args[2] or "{}")))
        elif signal == "Action" and args[1] == "bigger_model" and args[3] == "done":
            self.progress_line(words.bigger_done(json.loads(args[4] or "{}")))
        elif signal == "Action" and args[1] == "web_search" and args[3] == "proposal":
            self.search_card(json.loads(args[4] or "{}"))
        elif signal == "Action" and args[1] == "web_search" and args[3] == "running":
            self.progress_line(f"Searching the web for: {json.loads(args[2] or '{}').get('query', '')}")
        elif signal == "Action" and args[1] == "web_search" and args[3] == "done":
            self.sources_card(json.loads(args[4] or "{}"))
        elif signal == "Action" and args[1] == "wikipedia" and args[3] == "running":  # D68
            self.progress_line(words.wikipedia_running(json.loads(args[2] or "{}")))
        elif signal == "Action" and args[1] == "wikipedia" and args[3] == "done":
            found = json.loads(args[4] or "{}")
            self.progress_line(words.wikipedia_done(found))
            self.sources_card(found)
        elif signal == "Action" and args[1] == "journal" and args[3] == "done":
            self.progress_line(words.journal_written(json.loads(args[4] or "{}")))
        elif signal == "Action" and args[1] == "download":
            p = json.loads(args[4] or "{}")
            running = args[3] == "running"
            self.progress_line(words.download_progress(p) if running else words.download_done(p),
                               p["have"] / p["total"] if running and p.get("total") and not p.get("testing") else None)
        elif signal == "Action" and args[1] == "draft":
            p = json.loads(args[4] or "{}")
            self.progress_line(words.draft_progress(p) if args[3] == "running" else words.draft_done(p))
        elif signal == "Action" and args[1] == "queue" and args[3] == "waiting":  # turn tokens: its turn comes
            self.progress_line(words.t("queued", ahead=max(1, json.loads(args[4] or "{}").get("ahead", 1))))
        elif signal == "Action" and args[1] == "think" and args[3] == "proposal":
            self.think_card(json.loads(args[4] or "{}"))
        elif signal == "Action" and args[1] == "think" and args[3] == "running":
            self.progress_line(words.think_progress(json.loads(args[2] or "{}"), json.loads(args[4] or "{}")))
        elif signal == "Action" and args[1] == "think" and args[3] == "done":
            self.progress_line(words.think_done(json.loads(args[4] or "{}")))
        elif signal == "Action" and args[1] == "diagnosis" and args[3] == "proposal":
            self.diag_step = json.loads(args[4] or "{}")  # shown under the answer, after its command
        elif signal == "Action" and args[1] == "watch" and args[3] == "proposal":
            self.watch_card(json.loads(args[4] or "{}"))
        elif signal == "Action" and args[1] == "key_needed" and args[3] == "proposal":
            self.key_card(json.loads(args[4] or "{}"))
        elif signal == "Action" and args[3] == "proposal":
            self.proposal_card(json.loads(args[4] or "{}"))
        elif signal == "Action" and args[3] == "done":
            if args[1] == "terminal":
                self.terminal_turn = True
            self.action_line(*words.action(args[1], json.loads(args[2] or "{}"), args[4]))
            self.cards += words.commands_in_result(args[4])
        elif signal == "Error":
            self.finish_reply(error=args[1])
        elif signal == "Done":
            self.finish_reply()

    def open_aicui(self) -> None:
        """AICUI, the coding workspace (D61): it asks for a folder and tucks this sidebar away (Super+A brings it
        back)."""
        try:
            info = Gio.DesktopAppInfo.new("cinminai-aicui.desktop")
            if info is None:
                raise GLib.Error("AICUI isn't installed")
            info.launch([], None)
        except GLib.Error as e:
            self.bubble("error", f"Couldn't open AICUI: {e.message}")

    def open_updates(self) -> None:
        """The Updates window (D29): what's waiting, in plain words, and every step of installing it."""
        try:
            info = Gio.DesktopAppInfo.new("cinminai-updates.desktop")
            if info is None:
                raise GLib.Error("the Updates window isn't installed")
            info.launch([], None)
        except GLib.Error as e:
            self.bubble("error", f"Couldn't open Updates: {e.message}")

    # --- writing projects (D54) ---------------------------------------------------------------------------
    def on_new_menu(self, button) -> None:
        menu = Gtk.Menu()
        item = Gtk.MenuItem(label="New conversation")
        item.connect("activate", lambda i: self.on_new(None))
        menu.append(item)
        item = Gtk.MenuItem(label="New writing project…")
        item.connect("activate", lambda i: self.new_project())
        menu.append(item)
        item = Gtk.MenuItem(label="Journal")
        item.connect("activate", lambda i: self.open_journal())
        menu.append(item)
        item = Gtk.MenuItem(label="Coding (AICUI)…")
        item.connect("activate", lambda i: self.open_aicui())
        menu.append(item)
        item = Gtk.MenuItem(label=words.t("standing"))
        item.connect("activate", lambda i: self.standing_list())
        menu.append(item)
        item = Gtk.MenuItem(label=words.t("updates_window"))
        item.connect("activate", lambda i: self.open_updates())
        menu.append(item)
        item = Gtk.MenuItem(label=words.t("requests"))
        item.connect("activate", lambda i: self.requests_view())
        menu.append(item)
        item = Gtk.MenuItem(label=words.t("models"))
        item.connect("activate", lambda i: self.models_view())
        menu.append(item)
        item = Gtk.MenuItem(label=words.t("library"))
        item.connect("activate", lambda i: self.library_view())
        menu.append(item)
        sharing = self.daemon_json("TerminalSharing", "state") or {}
        if sharing.get("available"):  # D77: the switch, for after the one-time offer
            menu.append(Gtk.SeparatorMenuItem())
            check = Gtk.CheckMenuItem(label=words.t("t_share"))
            check.set_active(bool(sharing.get("on")))
            check.set_tooltip_text(words.t("t_share_tip"))

            def toggled(item) -> None:
                state = self.daemon_json("TerminalSharing", "on" if item.get_active() else "off") or {}
                self.progress_line(words.terminal_sharing_said("on" if item.get_active() else "off", state))
            check.connect("toggled", toggled)
            menu.append(check)
        projects = self.daemon_json("ProjectList") or []
        if projects:
            sub = Gtk.Menu()
            for p in projects:
                it = Gtk.MenuItem(label=p["title"])
                it.connect("activate", lambda i, folder=p["folder"]: self.open_project(folder))
                sub.append(it)
            opener = Gtk.MenuItem(label="Open a writing project")
            opener.set_submenu(sub)
            menu.append(opener)
        menu.show_all()
        menu.popup_at_widget(button, Gdk.Gravity.SOUTH_EAST, Gdk.Gravity.NORTH_EAST, None)

    def daemon_json(self, method: str, *args: str):
        if not self.proxy:
            return None
        try:
            v = self.proxy.call_sync(method, GLib.Variant("(" + "s" * len(args) + ")", args) if args else None,
                                     Gio.DBusCallFlags.NONE, 10000, None)
        except GLib.Error as e:
            Gio.DBusError.strip_remote_error(e)
            self.bubble("error", e.message)
            return None
        return json.loads(v.unpack()[0]) if v and v.unpack() else None

    def new_project(self) -> None:
        dialog = Gtk.Dialog(title="New writing project", transient_for=self.win, modal=True)
        dialog.add_buttons("Cancel", Gtk.ResponseType.CANCEL, "Start", Gtk.ResponseType.OK)
        dialog.set_default_response(Gtk.ResponseType.OK)
        entry = Gtk.Entry(placeholder_text="A working title, e.g. The Bottle", activates_default=True)
        box = dialog.get_content_area()
        box.set_spacing(6)
        margined(box)
        box.pack_start(Gtk.Label(label="What should we call it? You can change it later.", xalign=0), False, False, 6)
        box.pack_start(entry, False, False, 6)
        shape = Gtk.ComboBoxText()  # D56: the whole story circle in one chapter, or over chapters
        for label in words.SHAPES:
            shape.append_text(label)
        shape.set_active(0)
        box.pack_start(Gtk.Label(label="How long? (You can change this in Notes.)", xalign=0), False, False, 2)
        box.pack_start(shape, False, False, 6)
        dialog.show_all()
        ok = dialog.run() == Gtk.ResponseType.OK
        title, settings = entry.get_text().strip(), words.shape_settings(shape.get_active())
        dialog.destroy()
        if ok and self.daemon_json("ProjectNew", title or "Untitled") is not None:
            if settings["shape"] != "chapter":
                self.daemon_json("ProjectSet", json.dumps(settings))
            self.on_new(None, project=True)
            self.offer_model("writing")

    def open_project(self, folder: str) -> None:
        info = self.daemon_json("ProjectOpen", folder)
        if info is not None:
            self.on_new(None, project=True)
            n = sum(len(v) for v in info.get("notes", {}).values())
            self.bubble("assistant", f"Back to \"{info['title']}\": {n} notes so far. Tell me more, or click Write it up.")
            self.offer_model("writing")

    def offer_model(self, task: str) -> None:
        """D60: if the matcher has a stronger model for this task here, offer it (asked without blocking)."""
        if not self.proxy:
            return

        def got(proxy, result) -> None:
            try:
                info = json.loads(proxy.call_finish(result).unpack()[0])
            except (GLib.Error, ValueError):
                return
            if info.get("offer"):
                self.offer_card(task, info["offer"])
        self.proxy.call("ModelOffer", GLib.Variant("(s)", (task,)), Gio.DBusCallFlags.NONE, 30000, None, got)

    def offer_card(self, task: str, offer: dict) -> None:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.get_style_context().add_class("proposal")
        head = Gtk.Label(label=words.offer_title(offer), xalign=0, wrap=True, max_width_chars=30)
        head.get_style_context().add_class("what")
        box.pack_start(head, False, False, 0)
        for line in words.offer_lines(offer):
            box.pack_start(Gtk.Label(label=line, xalign=0, wrap=True, max_width_chars=30), False, False, 0)
        buttons = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, homogeneous=False, column_spacing=6,
                              row_spacing=6, min_children_per_line=1, max_children_per_line=3)  # wraps when narrow
        get = Gtk.Button(label="Use it" if offer.get("downloaded") else "Bring back" if offer.get("parked_on")
                         else "Download")
        get.get_style_context().add_class("suggested-action")
        later, never = Gtk.Button(label="Not now"), Gtk.Button(label="Don't ask again")

        def go(button) -> None:
            for b in (get, later, never):
                b.set_sensitive(False)
            if offer.get("downloaded"):
                self.daemon_json("ModelUse", task, offer["file"])
                self.progress_line(words.model_line({"model": offer.get("model")}))
            else:
                self.start_job("ModelDownload", task, words.MODEL_GETTING)
        get.connect("clicked", go)
        get.set_sensitive(bool(offer.get("space_ok", True)))
        later.connect("clicked", lambda b: box.destroy())
        never.connect("clicked", lambda b: (self.proxy.call("ModelDecline", GLib.Variant("(s)", (offer["file"],)),
                                                            Gio.DBusCallFlags.NONE, -1, None, None), box.destroy()))
        for b in (get, later, never):
            buttons.add(b)
        box.pack_start(buttons, False, False, 0)
        self.chat.pack_start(box, False, False, 0)
        box.show_all()

    def close_project(self) -> None:
        if self.proxy:
            self.proxy.call("ProjectClose", None, Gio.DBusCallFlags.NONE, -1, None, None)
        self.on_new(None)

    def show_notes(self) -> None:
        info = self.daemon_json("ProjectInfo")
        if info is None:
            return
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        box.get_style_context().add_class("proposal")
        head = Gtk.Label(label=f"Notes for \"{info['title']}\"", xalign=0)
        head.get_style_context().add_class("what")
        box.pack_start(head, False, False, 0)
        for line in words.notes_lines(info.get("notes", {})) + words.circle_lines(info):
            box.pack_start(Gtk.Label(label=line, xalign=0, wrap=True, max_width_chars=30, selectable=True), False, False, 0)
        # the story's shape (D56): the whole circle in one chapter, or a piece of it per chapter
        shape = Gtk.ComboBoxText()
        for label in words.SHAPES:
            shape.append_text(label)
        shape.set_active(words.shape_index(info))
        chapter = Gtk.ComboBoxText()
        for n in range(1, int(info.get("chapters", 4)) + 1):
            chapter.append_text(f"Next: chapter {n}")
        chapter.set_active(int(info.get("next_chapter") or 1) - 1)
        chapter.set_no_show_all(info.get("shape") != "chapters")
        line = Gtk.Label(label=words.next_chapter_line(info), xalign=0, wrap=True, max_width_chars=30)

        def changed(widget) -> None:
            settings = words.shape_settings(shape.get_active())
            if widget is chapter and chapter.get_active() >= 0:
                settings["next_chapter"] = chapter.get_active() + 1
            new = self.daemon_json("ProjectSet", json.dumps(settings))
            if new:
                line.set_text(words.next_chapter_line(new))
                if widget is shape:  # the chapter list follows the number of chapters
                    chapter.handler_block(chapter_id)
                    chapter.remove_all()
                    for n in range(1, int(new.get("chapters", 4)) + 1):
                        chapter.append_text(f"Next: chapter {n}")
                    chapter.set_active(int(new.get("next_chapter") or 1) - 1)
                    chapter.handler_unblock(chapter_id)
                    chapter.set_visible(new.get("shape") == "chapters")
        shape.connect("changed", changed)
        chapter_id = chapter.connect("changed", changed)
        for w in (shape, chapter, line):
            box.pack_start(w, False, False, 2)
        models = self.daemon_json("ModelOffer", "writing") or {}
        box.pack_start(Gtk.Label(label=words.model_line(models.get("in_use")), xalign=0, wrap=True, max_width_chars=30),
                       False, False, 2)
        if models.get("in_use"):
            back = Gtk.Button(label="Write with the built-in guide")
            back.connect("clicked", lambda b: (self.daemon_json("ModelUse", "writing", ""), b.set_sensitive(False)))
            box.pack_start(back, False, False, 2)
        if info.get("drafts"):  # D58: offered once something is written, never done on its own
            ms = Gtk.Button(label="Make a manuscript")
            ms.set_tooltip_text(words.MANUSCRIPT_TIP)
            ms.connect("clicked", lambda b: self.make_manuscript())
            box.pack_start(ms, False, False, 4)
        self.chat.pack_start(box, False, False, 0)
        box.show_all()

    def make_manuscript(self) -> None:
        """The story in standard manuscript format, .odt and .docx (D58): the author's name, contact optional."""
        dialog = Gtk.Dialog(title="Make a manuscript", transient_for=self.win, modal=True)
        dialog.add_buttons("Cancel", Gtk.ResponseType.CANCEL, "Make it", Gtk.ResponseType.OK)
        dialog.set_default_response(Gtk.ResponseType.OK)
        box = dialog.get_content_area()
        box.set_spacing(6)
        margined(box)
        box.pack_start(Gtk.Label(label=words.MANUSCRIPT_INTRO, xalign=0, wrap=True, max_width_chars=44), False, False, 6)
        name = Gtk.Entry(text=GLib.get_real_name() if GLib.get_real_name() not in ("", "Unknown") else "",
                         placeholder_text="Your name, as it should appear", activates_default=True)
        contact = Gtk.Entry(placeholder_text="Email or address (optional)", activates_default=True)
        for label, entry in (("Author", name), ("Contact", contact)):
            box.pack_start(Gtk.Label(label=label, xalign=0), False, False, 0)
            box.pack_start(entry, False, False, 2)
        dialog.show_all()
        ok = dialog.run() == Gtk.ResponseType.OK
        author, how = name.get_text().strip(), contact.get_text().strip()
        dialog.destroy()
        if not ok:
            return
        res = self.daemon_json("MakeManuscript", json.dumps({"author": author, "contact": how}))
        if res:
            self.bubble("assistant", words.manuscript_done(res))

    # --- the journal (D55) -------------------------------------------------------------------------------
    def open_journal(self) -> None:
        info = self.daemon_json("JournalOpen")
        if info is not None:
            self.on_new(None, project=True)  # the conversation starts fresh; the mode stays open
            for child in self.chat.get_children():
                child.destroy()
            self.bubble("assistant", words.JOURNAL_HELLO)

    def close_journal(self) -> None:
        if self.proxy:
            self.proxy.call("JournalClose", None, Gio.DBusCallFlags.NONE, -1, None, None)
        self.on_new(None)

    def pin_dialog(self, title: str, confirm: bool = False) -> str | None:
        """A 4-digit PIN, typed hidden (twice when setting one). None if cancelled."""
        dialog = Gtk.Dialog(title=title, transient_for=self.win, modal=True)
        dialog.add_buttons("Cancel", Gtk.ResponseType.CANCEL, "OK", Gtk.ResponseType.OK)
        dialog.set_default_response(Gtk.ResponseType.OK)
        box = dialog.get_content_area()
        box.set_spacing(6)
        margined(box)
        fields = []
        for label in (["PIN (4 digits)", "The same PIN again"] if confirm else ["PIN"]):
            box.pack_start(Gtk.Label(label=label, xalign=0), False, False, 2)
            e = Gtk.Entry(visibility=False, max_length=4, input_purpose=Gtk.InputPurpose.PIN, activates_default=True)
            box.pack_start(e, False, False, 2)
            fields.append(e)
        if confirm:
            box.pack_start(Gtk.Label(label="It locks private entries against people looking. Don't lose it: without "
                                           "it, a private entry can't be opened.", xalign=0, wrap=True,
                                     max_width_chars=40), False, False, 6)
        dialog.show_all()
        ok = dialog.run() == Gtk.ResponseType.OK
        values = [e.get_text() for e in fields]
        dialog.destroy()
        if not ok:
            return None
        if confirm and values[0] != values[1]:
            self.bubble("error", "The two PINs weren't the same; nothing was changed.")
            return None
        return values[0]

    def write_entry(self) -> None:
        private = self.private.get_active()
        if private:
            info = self.daemon_json("JournalEntries") or {}
            if not info.get("has_pin"):
                pin = self.pin_dialog("Choose a PIN for private entries", confirm=True)
                if pin is None:
                    return
                try:
                    self.proxy.call_sync("JournalSetPin", GLib.Variant("(ss)", (pin, "")), Gio.DBusCallFlags.NONE, 10000, None)
                except GLib.Error as e:
                    Gio.DBusError.strip_remote_error(e)
                    self.bubble("error", e.message)
                    return
        if not self.proxy or self.rid is not None:
            return
        self.job_waiting = "Writing today's entry…"
        self.reply = self.bubble("assistant", self.job_waiting)
        self.reply.get_style_context().add_class("waiting")
        self.reply_started = False
        self.rid = -1

        def started(proxy, result) -> None:
            try:
                (self.rid,) = proxy.call_finish(result).unpack()
            except GLib.Error as e:
                Gio.DBusError.strip_remote_error(e)
                self.finish_reply(error=e.message)
            self.update_header()

        self.proxy.call("JournalWrite", GLib.Variant("(b)", (private,)), Gio.DBusCallFlags.NONE, 600000, None, started)
        self.update_header()

    def show_entries(self) -> None:
        info = self.daemon_json("JournalEntries")
        if info is None:
            return
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        box.get_style_context().add_class("proposal")
        head = Gtk.Label(label="Journal entries", xalign=0)
        head.get_style_context().add_class("what")
        box.pack_start(head, False, False, 0)
        if not info["entries"]:
            box.pack_start(Gtk.Label(label="No entries yet.", xalign=0), False, False, 0)
        for e in reversed(info["entries"][-30:]):
            b = Gtk.Button(label=words.entry_label(e))
            b.set_relief(Gtk.ReliefStyle.NONE)
            b.get_child().set_xalign(0)
            b.connect("clicked", lambda btn, e=e: self.open_entry(e))
            box.pack_start(b, False, False, 0)
        self.chat.pack_start(box, False, False, 0)
        box.show_all()

    def open_entry(self, e: dict) -> None:
        import os
        if not e.get("private"):
            path = os.path.join(os.path.expanduser("~"), "Documents", "Journal", e["file"])
            Gio.AppInfo.launch_default_for_uri(Gio.File.new_for_path(path).get_uri(), None)
            return
        pin = self.pin_dialog("Open a private entry")
        if pin is None:
            return
        try:
            v = self.proxy.call_sync("JournalRead", GLib.Variant("(ss)", (e["file"], pin)), Gio.DBusCallFlags.NONE, 30000, None)
        except GLib.Error as err:
            Gio.DBusError.strip_remote_error(err)
            self.bubble("error", err.message)
            return
        r = json.loads(v.unpack()[0])
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        card.get_style_context().add_class("proposal")
        head = Gtk.Label(label=f"🔒 {r['title']} — {r['when'].replace('T', ' ')}", xalign=0, wrap=True, max_width_chars=30)
        head.get_style_context().add_class("what")
        card.pack_start(head, False, False, 0)
        card.pack_start(Gtk.Label(label=r["text"], xalign=0, wrap=True, max_width_chars=30, selectable=True), False, False, 0)
        hide = Gtk.Button(label="Hide")
        hide.connect("clicked", lambda b: card.destroy())  # gone from the screen and from memory here
        card.pack_start(hide, False, False, 0)
        self.chat.pack_start(card, False, False, 0)
        card.show_all()

    # --- web search (D55) ---------------------------------------------------------------------------------
    def action_card(self, card: dict) -> None:
        """An action the assistant proposes or took (M4, PLAN D85, SPEC §8.3): from the daemon's record of it, never
        from model text. Waiting: Allow / No. Done: an Undo where it has one."""
        event = card.get("event")
        if event == "waiting":
            shown = self.__dict__.setdefault("waiting_shown", set())
            if card.get("id") in shown:
                return  # already on screen (a signal and ActionList can both bring it)
            shown.add(card.get("id"))
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            box.get_style_context().add_class("proposal")
            for text, cls in words.action_lines(card):
                label = Gtk.Label(label=text, xalign=0, wrap=True, max_width_chars=30)
                label.get_style_context().add_class(cls)
                box.pack_start(label, False, False, 0)
            buttons = Gtk.Box(spacing=6)
            allow = Gtk.Button(label=words.t("allow"))
            allow.get_style_context().add_class("suggested-action")
            no = Gtk.Button(label=words.t("no"))

            def answer(button, yes: bool) -> None:
                allow.set_sensitive(False)
                no.set_sensitive(False)

                def done(proxy, res) -> None:
                    try:
                        proxy.call_finish(res)
                    except GLib.Error as e:
                        self.bubble("note", words.action_error(e.message))
                    box.destroy()

                # no time limit: after Allow an admin action waits for the password, then apt (-1 would be 25 s)
                self.proxy.call("ActionAnswer", GLib.Variant("(sb)", (card["id"], yes)), Gio.DBusCallFlags.NONE,
                                0x7fffffff, None, done)

            allow.connect("clicked", answer, True)
            no.connect("clicked", answer, False)
            buttons.pack_start(allow, False, False, 0)
            buttons.pack_start(no, False, False, 0)
            box.pack_start(buttons, False, False, 0)
            self.chat.pack_start(box, False, False, 0)
            box.show_all()
            return
        if event == "done" and card.get("undo"):
            row = Gtk.Box(spacing=6)
            label = Gtk.Label(label=words.action_done(card), xalign=0, wrap=True, max_width_chars=24)
            label.get_style_context().add_class("note")
            undo = Gtk.Button(label="Undo")

            def take_back(button) -> None:
                undo.set_sensitive(False)

                def done(proxy, res) -> None:
                    try:
                        (ok,) = proxy.call_finish(res).unpack()
                        label.set_text(words.action_undone(ok))
                    except GLib.Error as e:
                        label.set_text(words.action_error(e.message))
                        undo.set_sensitive(True)

                self.proxy.call("ActionUndo", GLib.Variant("(s)", (card["id"],)), Gio.DBusCallFlags.NONE, -1, None,
                                done)

            undo.connect("clicked", take_back)
            row.pack_start(label, True, True, 0)
            row.pack_start(undo, False, False, 0)
            self.chat.pack_start(row, False, False, 0)
            row.show_all()
        elif event == "done" and card.get("lane") == "admin":   # others say so in their own way
            self.bubble("note", words.action_done(card))
        elif event == "denied" and card.get("at") == "password":
            self.bubble("note", words.action_declined(card))
        elif event == "failed":
            self.bubble("note", words.action_failed(card))

    # --- standing tasks (D88) and keys (D92) ----------------------------------------------------------------
    def watch_card(self, offer: dict) -> None:
        """What would be watched, how often, and where the words go; nothing is set up or sent before Set up."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.get_style_context().add_class("proposal")
        head = Gtk.Label(label=words.watch_head(offer), xalign=0, wrap=True, max_width_chars=30)
        head.get_style_context().add_class("what")
        box.pack_start(head, False, False, 0)
        topic = Gtk.Entry(text=offer.get("topic", ""), placeholder_text=words.t("watch_empty"))
        box.pack_start(topic, False, False, 0)
        note = Gtk.Label(label=words.watch_note(offer), xalign=0, wrap=True, max_width_chars=30)
        note.get_style_context().add_class("note")
        box.pack_start(note, False, False, 0)
        buttons = Gtk.Box(spacing=6)
        go = Gtk.Button(label=words.t("set_up"))
        go.get_style_context().add_class("suggested-action")
        no = Gtk.Button(label=words.t("no_thanks"))

        def setup(button) -> None:
            for w in (go, no, topic):
                w.set_sensitive(False)
            self.start_job("StandingAdd", (offer.get("id", ""), topic.get_text().strip()), words.t("setting_up"),
                           "(ss)")

        go.connect("clicked", setup)
        no.connect("clicked", lambda b: box.destroy())  # nothing was set up or sent
        buttons.pack_start(go, False, False, 0)
        buttons.pack_start(no, False, False, 0)
        box.pack_start(buttons, False, False, 0)
        self.chat.pack_start(box, False, False, 0)
        box.show_all()

    def models_view(self, opened: bool = True) -> None:
        """Which model does each job, and the models on this computer (SPEC §22.3): give a job another model that
        runs here, or our pick again. Help and the system stay with the guide (D94)."""
        if not self.proxy:
            return
        if opened:  # opened by the person, not refreshed: show it (a refresh leaves them where they were)
            self.to_bottom()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.get_style_context().add_class("proposal")
        title = Gtk.Label(label=words.t("models"), xalign=0)
        title.get_style_context().add_class("what")
        box.pack_start(title, False, False, 0)
        helper = Gtk.Button(label=words.t("s_help"))  # D93: what do you want to do? a setup suggested, you decide
        helper.set_halign(Gtk.Align.START)
        helper.connect("clicked", lambda b: (b.destroy(), self.setup_helper(box)))
        box.pack_start(helper, False, False, 0)
        reading = Gtk.Label(label=words.t("m_reading"), xalign=0)
        box.pack_start(reading, False, False, 0)
        self.chat.pack_start(box, False, False, 0)
        box.show_all()

        def again() -> bool:
            box.destroy()
            self.models_view(False)
            return False

        def assigned(p, r) -> None:
            try:
                p.call_finish(r)
            except GLib.Error as e:
                Gio.DBusError.strip_remote_error(e)
                msg = e.message
                GLib.idle_add(lambda: self.bubble("error", msg) and False)
            GLib.idle_add(again)

        def fill(v) -> bool:
            reading.destroy()
            for job in v["jobs"]:
                name, now = words.job_lines(job)
                head = Gtk.Label(label=name, xalign=0)
                head.get_style_context().add_class("what")
                box.pack_start(head, False, False, 0)
                small = Gtk.Label(label=now, xalign=0, wrap=True, max_width_chars=30)
                small.get_style_context().add_class("note")
                box.pack_start(small, False, False, 0)
                if job["job"] == "system":
                    self.assistant_choice(box, again)
                if job["locked"] or not job["active"] or not job["choices"]:
                    continue
                pick = Gtk.ComboBoxText()
                pick.append("", words.t("m_use_ours"))
                for c in job["choices"]:
                    pick.append(c["file"] if c["fits"] else "-" + c["file"], words.choice_label(c))
                pick.set_active_id(job["current"]["file"] if job["chosen"] else "")
                for cell in pick.get_cells():  # a long model name is cut with … instead of widening the dock
                    cell.set_property("ellipsize", 3)  # Pango END

                def changed(combo, j=job["job"], was=pick.get_active_id()) -> None:
                    file = combo.get_active_id()
                    if file is None or file == was:
                        return
                    if file.startswith("-"):  # doesn't run here: keep what it was
                        combo.set_active_id(was)
                        return
                    combo.set_sensitive(False)
                    self.proxy.call("ModelAssign", GLib.Variant("(ss)", (j, file)), Gio.DBusCallFlags.NONE,
                                    120000, None, assigned)
                pick.connect("changed", changed)
                box.pack_start(pick, False, False, 0)
            here = Gtk.Label(label=words.t("m_here"), xalign=0)
            here.get_style_context().add_class("what")
            box.pack_start(here, False, False, 0)
            for m in v["models"]:
                where = (words.t("m_system") if m["where"] == "system" else
                         words.t("m_parked", drive=m.get("drive") or "?") if m["where"] == "parked" else "")
                used = ", ".join(words.t("job_" + j) for j in m.get("used_by", []))
                line = f"{m['model']} · {m['size'] / 2**30:.1f} GB" + (f" · {where}" if where else "") + \
                    (f" · {words.t('h_used', jobs=used)}" if used else "")
                row = Gtk.Box(spacing=6)
                name = Gtk.Label(label=line, xalign=0, wrap=True, max_width_chars=26)
                name.set_line_wrap_mode(2)  # Pango WORD_CHAR: a model's name has no spaces to break at
                row.pack_start(name, True, True, 0)
                if m["where"] == "store" and m["present"] and not used:
                    rm = Gtk.Button(label=words.t("h_remove"))

                    def remove(b, f=m["file"]) -> None:
                        if b.get_label() == words.t("h_remove"):
                            b.set_label(words.t("m_sure"))  # the second click removes it (Ian, 2026-10-24; D85)
                            return
                        b.set_sensitive(False)
                        self.daemon_async("ModelRemove", (f,), "(s)", lambda v: again())
                    rm.connect("clicked", remove)
                    row.pack_end(rm, False, False, 0)
                box.pack_start(row, False, False, 0)
            free = Gtk.Label(label=words.t("m_free", gb=f"{v['free_bytes'] / 2**30:.0f}"), xalign=0)
            free.get_style_context().add_class("note")
            box.pack_start(free, False, False, 0)
            self.more_models(box, v["free_bytes"])
            close = Gtk.Button(label=words.t("close"))
            close.set_halign(Gtk.Align.START)
            close.connect("clicked", lambda b: box.destroy())
            box.pack_start(close, False, False, 0)
            box.show_all()
            return False

        def got(p, r) -> None:
            try:
                v = json.loads(p.call_finish(r).unpack()[0])
            except GLib.Error as e:
                Gio.DBusError.strip_remote_error(e)
                msg = e.message
                GLib.idle_add(lambda: (box.destroy(), self.bubble("error", msg)) and False)
                return
            GLib.idle_add(fill, v)

        self.proxy.call("ModelsView", None, Gio.DBusCallFlags.NONE, 120000, None, got)

    def setup_helper(self, box: Gtk.Box) -> None:
        """D93: the person says what they want to do; our pick for each job on this computer is suggested (here or how
        much to download, how it runs); nothing changes until Use this setup."""
        area = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.pack_start(area, False, False, 0)
        box.reorder_child(area, 1)
        area.pack_start(self.note_label(words.t("s_ask")), False, False, 0)
        ticks = {}
        for job in ("writing", "coding", "vision", "review"):
            ticks[job] = Gtk.CheckButton(label=words.t("job_" + job))
            area.pack_start(ticks[job], False, False, 0)
        go = Gtk.Button(label=words.t("s_suggest"))
        go.set_halign(Gtk.Align.START)
        area.pack_start(go, False, False, 0)
        out = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        area.pack_start(out, False, False, 0)

        def shown(v) -> None:
            for c in out.get_children():
                c.destroy()
            for s in v["setup"]:
                if not s["file"]:
                    what = words.t("s_none")
                else:
                    what = s["model"] + " · " + (words.t("s_here") if s["here"] else
                                                 words.t("s_get", gb=f"{s['download'] / 2**30:.1f}"))
                out.pack_start(self.note_label(f"{words.t('job_' + s['job'])}: {what}"), False, False, 0)
            usable = [s["job"] for s in v["setup"] if s["file"] and not s.get("offline")]
            if v["download"]:
                out.pack_start(self.note_label(words.t("s_total", gb=f"{v['download'] / 2**30:.1f}")), False, False, 0)
            if len(usable) > 1:
                out.pack_start(self.note_label(words.t("s_one_card")), False, False, 0)
            if not v["space_ok"]:
                out.pack_start(self.note_label(words.t("s_room", gb=f"{v['download'] / 2**30:.1f}")), False, False, 0)
            elif usable:
                use = Gtk.Button(label=words.t("s_use"))
                use.get_style_context().add_class("suggested-action")
                use.set_halign(Gtk.Align.START)
                use.connect("clicked", lambda b: (area.destroy(), self.start_job(
                    "ModelSetupApply", json.dumps(usable), words.t("s_working"))))
                out.pack_start(use, False, False, 0)
            out.show_all()

        def suggest(b) -> None:
            wants = [j for j, t in ticks.items() if t.get_active()]
            if wants:
                self.daemon_async("ModelSetup", (json.dumps(wants),), "(s)", shown)
        go.connect("clicked", suggest)
        area.show_all()

    def assistant_choice(self, box: Gtk.Box, again) -> None:
        """D35: the assistant on the person's own cloud model, under Help and the system: the models of each provider
        with a key here; what goes to the provider is said before it's used; the tools, Allow cards and password stay
        on this computer."""
        spot = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.pack_start(spot, False, False, 0)
        names = {"anthropic": "Anthropic", "openai": "OpenAI"}

        def change(what: dict) -> None:
            spot.set_sensitive(False)
            self.daemon_async("AssistantCloud", (json.dumps(what),), "(s)", lambda v: again())

        def show(v) -> None:
            cur, offers = v.get("current"), v.get("offers") or []
            if cur:
                spot.pack_start(self.note_label(words.t("a_cloud_now", label=cur["label"], spent=cur["spent_usd"],
                                                        budget=cur["budget_usd"])), False, False, 0)
                row = Gtk.Box(spacing=6)
                back = Gtk.Button(label=words.t("a_cloud_back"))
                back.connect("clicked", lambda b: change({"model": ""}))
                more = Gtk.Button(label=words.t("a_cloud_more"))
                more.connect("clicked", lambda b: change({"budget_usd": cur["budget_usd"] + 2}))
                row.pack_start(back, False, False, 0)
                row.pack_start(more, False, False, 0)
                spot.pack_start(row, False, False, 0)
            elif not offers:
                spot.pack_start(self.note_label(words.t("a_cloud_none")), False, False, 0)
            others = [o for o in offers if not cur or o["model"] != cur["model"]]
            if others:
                pick = Gtk.ComboBoxText()
                pick.append("", words.t("a_cloud_pick"))
                for o in others:
                    pick.append(o["model"], o["label"])
                pick.set_active_id("")
                for cell in pick.get_cells():
                    cell.set_property("ellipsize", 3)  # Pango END
                warn = self.note_label("")
                use = Gtk.Button(label=words.t("a_cloud_use"))
                use.set_halign(Gtk.Align.START)

                def picked(combo) -> None:
                    m = combo.get_active_id()
                    o = next((x for x in others if x["model"] == m), None)
                    if o is None:
                        warn.hide()
                        use.hide()
                        return
                    budget = (cur or {}).get("budget_usd") or 2.0
                    warn.set_text(words.t("a_cloud_warn", provider=names.get(o["provider"], o["provider"]),
                                          budget=budget))
                    warn.show()
                    use.show()
                pick.connect("changed", picked)
                use.connect("clicked", lambda b: change({"model": pick.get_active_id()}))
                spot.pack_start(pick, False, False, 0)
                spot.pack_start(warn, False, False, 0)
                spot.pack_start(use, False, False, 0)
                spot.show_all()
                warn.hide()
                use.hide()
                return
            spot.show_all()

        self.daemon_async("AssistantCloud", (json.dumps({}),), "(s)", show)

    def library_view(self, opened: bool = True) -> None:
        """The Library (D68): the Wikipedia shelves on this computer, each removable if the person downloaded it, and
        Kiwix's list for a language, with Ian's pair suggested, never chosen. Downloads run in the daemon on their own
        (hours for the big files); this card shows how far each is while it's open."""
        if not self.proxy:
            return
        if opened:
            self.to_bottom()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.get_style_context().add_class("proposal")
        title = Gtk.Label(label=words.t("library"), xalign=0)
        title.get_style_context().add_class("what")
        box.pack_start(title, False, False, 0)
        box.pack_start(self.note_label(words.t("lib_note")), False, False, 0)
        here = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        box.pack_start(here, False, False, 0)
        more = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        box.pack_start(more, False, False, 0)
        listing = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        close = Gtk.Button(label=words.t("close"))
        close.set_halign(Gtk.Align.START)
        close.connect("clicked", lambda b: box.destroy())
        state = {"view": None, "files": None, "open": True, "polling": False}
        box.connect("destroy", lambda w: state.update(open=False))
        gb = lambda b: f"{b / 2**30:.1f}"  # noqa: E731

        def clear(area: Gtk.Box) -> None:
            for c in area.get_children():
                c.destroy()

        def show_here(v: dict) -> None:
            clear(here)
            head = Gtk.Label(label=words.t("lib_here"), xalign=0)
            head.get_style_context().add_class("what")
            here.pack_start(head, False, False, 0)
            if not v["shelves"]:
                here.pack_start(self.note_label(words.t("lib_none")), False, False, 0)
            for s in v["shelves"]:
                name = f"{words.t('ed_' + s['edition']) if s.get('edition') else s['title']} " \
                       f"({words.LANG_NAMES.get(s['lang'], s['lang'])}), {words.t('kind_' + s['kind'])}"
                line = f"{name} · {gb(s['size'])} GB · {s['date']}" + \
                    ("" if s["removable"] else f" · {words.t('lib_shipped')}")
                row = Gtk.Box(spacing=6)
                row.pack_start(Gtk.Label(label=line, xalign=0, wrap=True, max_width_chars=26), True, True, 0)
                if s["removable"]:
                    rm = Gtk.Button(label=words.t("h_remove"))

                    def remove(b, path=s["path"]) -> None:
                        if b.get_label() == words.t("h_remove"):
                            b.set_label(words.t("lib_sure"))  # the second click removes it
                            return
                        b.set_sensitive(False)
                        self.daemon_async("LibraryRemove", (path,), "(s)", lambda r: refresh())
                    rm.connect("clicked", remove)
                    row.pack_end(rm, False, False, 0)
                here.pack_start(row, False, False, 0)
            for file, j in v["getting"].items():
                key = {"running": "lib_checking" if j["total"] and j["have"] >= j["total"] else "lib_getting",
                       "stopped": "lib_stopped", "done": "lib_done", "failed": "lib_failed"}[j["state"]]
                text = f"{file}: " + words.t(key, have=gb(j["have"]), total=gb(j["total"]), error=j.get("error", ""))
                row = Gtk.Box(spacing=6)
                row.pack_start(self.note_label(text), True, True, 0)
                if j["state"] == "running":
                    stop = Gtk.Button(label=words.t("stop"))
                    stop.connect("clicked", lambda b, f=file: (b.set_sensitive(False), self.daemon_async(
                        "LibraryStop", (f,), "(s)", lambda r: None)))
                    row.pack_end(stop, False, False, 0)
                here.pack_start(row, False, False, 0)
                if j["state"] in ("running", "stopped") and j["total"]:  # the numbers, and a bar (Ian, 2026-10-24)
                    here.pack_start(Gtk.ProgressBar(fraction=min(j["have"] / j["total"], 1.0)), False, False, 0)
            here.pack_start(self.note_label(words.t("lib_free", gb=f"{v['free_bytes'] / 2**30:.0f}")), False, False, 0)
            here.show_all()

        def show_files(c: dict) -> None:
            clear(listing)
            v = state["view"] or {}
            getting = {f for f, j in v.get("getting", {}).items() if j["state"] == "running"}
            listing.pack_start(self.note_label(words.t("lib_suggest")), False, False, 0)
            edition = None
            for f in c["files"]:
                if f["edition"] != edition:
                    edition = f["edition"]
                    head = Gtk.Label(label=words.t("ed_" + edition), xalign=0)
                    head.get_style_context().add_class("what")
                    listing.pack_start(head, False, False, 0)
                line = words.t("lib_line", kind=words.t("kind_" + f["kind"]), gb=gb(f["size"]),
                               articles=f"{f['articles']:,}", date=f["date"]) + \
                    (f" · {words.t('lib_suggested')}" if f["suggested"] else "")
                row = Gtk.Box(spacing=6)
                row.pack_start(Gtk.Label(label=line, xalign=0, wrap=True, max_width_chars=24), True, True, 0)
                if f["here"]:
                    row.pack_end(self.note_label(words.t("lib_have")), False, False, 0)
                elif f["file"] in getting:
                    pass  # its progress shows above
                elif f["size"] - v.get("partial", {}).get(f["file"], 0) + (2 << 30) > v.get("free_bytes", 0):
                    row.pack_end(self.note_label(words.t("lib_room")), False, False, 0)
                else:
                    get = Gtk.Button(label=words.t("lib_carry" if f["file"] in v.get("partial", {}) else "lib_get"))

                    def fetch(b, file=f["file"]) -> None:
                        b.set_sensitive(False)
                        self.daemon_async("LibraryGet", (file,), "(s)", lambda r: refresh())
                    get.connect("clicked", fetch)
                    row.pack_end(get, False, False, 0)
                listing.pack_start(row, False, False, 0)
            listing.show_all()

        def show_more(v: dict) -> None:
            clear(more)
            if v["offline"]:  # D28: the list is hidden, not greyed out
                more.pack_start(self.note_label(words.t("lib_offline")), False, False, 0)
                more.show_all()
                return
            head = Gtk.Label(label=words.t("lib_more"), xalign=0)
            head.get_style_context().add_class("what")
            more.pack_start(head, False, False, 0)
            more.pack_start(self.note_label(words.t("lib_look_note")), False, False, 0)
            row = Gtk.Box(spacing=6)
            lang = Gtk.ComboBoxText()
            for code, name in words.LANG_NAMES.items():
                lang.append(code, name)
            lang.set_active_id(v["lang"] if v["lang"] in words.LANG_NAMES else "en")
            look = Gtk.Button(label=words.t("lib_look"))

            def looked(c: dict) -> None:
                look.set_sensitive(True)
                state["files"] = c
                show_files(c)

            def ask(b) -> None:
                look.set_sensitive(False)
                clear(listing)
                listing.pack_start(self.note_label(words.t("lib_reading")), False, False, 0)
                listing.show_all()
                self.daemon_async("LibraryCatalog", (lang.get_active_id() or "",), "(s)", looked)
            look.connect("clicked", ask)
            row.pack_start(lang, False, False, 0)
            row.pack_start(look, False, False, 0)
            more.pack_start(row, False, False, 0)
            more.pack_start(listing, False, False, 0)
            more.show_all()

        def viewed(v: dict) -> None:
            first = state["view"] is None
            state["view"] = v
            show_here(v)
            if first:
                show_more(v)
                box.pack_start(close, False, False, 0)
                close.show()
            elif state["files"]:
                show_files(state["files"])  # what's here and what's downloading changed
            if any(j["state"] == "running" for j in v["getting"].values()) and not state["polling"]:
                state["polling"] = True  # one timer at a time, while a download runs and the card is open

                def poll() -> bool:
                    state["polling"] = False
                    refresh()
                    return False
                GLib.timeout_add_seconds(2, poll)

        def refresh() -> None:
            if state["open"]:
                self.daemon_async("LibraryView", (), "", viewed)

        self.chat.pack_start(box, False, False, 0)
        box.show_all()
        refresh()

    def note_label(self, text: str) -> Gtk.Label:
        label = Gtk.Label(label=text, xalign=0, wrap=True, max_width_chars=30)
        label.set_line_wrap_mode(2)  # Pango WORD_CHAR: a file name has no spaces to break at
        label.get_style_context().add_class("note")
        return label

    def daemon_async(self, method: str, args: tuple, fmt: str, done) -> None:
        """A daemon call that may take a while (the network, reading model files): done(value) on the main loop;
        an error goes to a bubble and done is not called."""
        def got(p, r) -> None:
            try:
                v = p.call_finish(r).unpack()
            except GLib.Error as e:
                Gio.DBusError.strip_remote_error(e)
                msg = e.message
                GLib.idle_add(lambda: self.bubble("error", msg) and False)
                return
            out = v[0] if v else None
            GLib.idle_add(lambda: done(json.loads(out) if isinstance(out, str) else out) and False)
        self.proxy.call(method, GLib.Variant(fmt, args) if args else None, Gio.DBusCallFlags.NONE, 180000, None, got)

    def job_picker(self, fit: dict) -> Gtk.ComboBoxText:
        """The jobs a model could do here (none yet is first): it gets the job after its speed test."""
        pick = Gtk.ComboBoxText()
        pick.append("", words.t("h_no_job"))
        for job, f in fit.items():
            if f["fits"]:
                pick.append(job, words.t("job_" + job))
        pick.set_active_id("")
        return pick

    def more_models(self, box: Gtk.Box, free: int) -> None:
        """The Models view's lower part: search Hugging Face (what's sent is said first, D86), look at a repository's
        files, check one runs here before fetching it, fetch it and give it a job; or bring one in from a drive.
        In offline mode (D28) only the drives: the search is hidden, not greyed out."""
        from cin_minai.daemon import offline
        head = Gtk.Label(label=words.t("h_more"), xalign=0)
        head.get_style_context().add_class("what")
        box.pack_start(head, False, False, 0)
        note = Gtk.Label(label=words.t("h_note"), xalign=0, wrap=True, max_width_chars=30)
        note.get_style_context().add_class("note")
        row = Gtk.Box(spacing=6)
        entry = Gtk.Entry(placeholder_text=words.t("h_hint"))
        go = Gtk.Button(label=words.t("h_search"))
        row.pack_start(entry, True, True, 0)
        row.pack_end(go, False, False, 0)
        found = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        if not offline.on():
            box.pack_start(note, False, False, 0)
            box.pack_start(row, False, False, 0)
            box.pack_start(found, False, False, 0)
        drives = Gtk.Button(label=words.t("h_drives"))
        drives.set_halign(Gtk.Align.START)
        box.pack_start(drives, False, False, 0)
        on_drives = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        box.pack_start(on_drives, False, False, 0)

        def clear(area: Gtk.Box) -> None:
            for c in area.get_children():
                c.destroy()

        def small(text: str) -> Gtk.Label:
            label = Gtk.Label(label=text, xalign=0, wrap=True, max_width_chars=30)
            label.set_line_wrap_mode(2)  # Pango WORD_CHAR: file and repo names have no spaces to break at
            label.get_style_context().add_class("note")
            return label

        def checked(area: Gtk.Box, v: dict, then=None) -> None:
            if then:
                then()  # the next file's check (Download…: one after another)
            clear(area)
            for line in words.fit_lines(v["jobs"]):
                area.pack_start(small(line), False, False, 0)
            if not any(f["fits"] for f in v["jobs"].values()):
                area.pack_start(small(words.t("h_runs_nothing")), False, False, 0)
            elif not v["here"] and v["size"] + (2 << 30) > v["free_bytes"]:
                area.pack_start(small(words.t("h_room", gb=f"{v['size'] / 2**30:.1f}")), False, False, 0)
            else:
                pick = self.job_picker(v["jobs"])
                get = Gtk.Button(label=words.t("h_get", gb=f"{v['size'] / 2**30:.1f}"))
                get.connect("clicked", lambda b: (b.set_sensitive(False), self.start_job(
                    "HubDownload", (v["file"], pick.get_active_id() or ""),
                    words.MODEL_GETTING, "(ss)")))
                area.pack_start(pick, False, False, 0)
                area.pack_start(get, False, False, 0)
            area.show_all()

        def repo_files(area: Gtk.Box, v: dict, auto: bool = False) -> None:
            """auto (Download…, Ian 2026-10-10: "We need a download button for the hugging face search"): the
            offered files are checked by themselves, smallest first, up to AUTO_CHECKS, so each one that runs here
            shows its Download button without another click."""
            clear(area)
            checks = []
            area.pack_start(small(words.licence_line(v["licence"])), False, False, 0)
            opened = not v["gated"] or v.get("token")  # D93: a gated repository opens with the person's token
            if v["gated"] and v.get("token"):
                area.pack_start(small(words.t("h_gated_ok")), False, False, 0)
                page = Gtk.LinkButton(uri=v.get("page", ""), label=words.t("h_page"))
                page.set_halign(Gtk.Align.START)
                area.pack_start(page, False, False, 0)
            elif v["gated"]:
                area.pack_start(small(words.t("h_gated")), False, False, 0)
                if v.get("key_card"):
                    self.key_card(v["key_card"])
            for f in v["files"]:
                line = Gtk.Box(spacing=6)
                why = {"a part is missing": "h_part_missing", "picture reader": "h_mmproj", "no checksum": "h_nosum",
                       "helper file": "h_helper"}.get(f["why_not"])
                parts = words.t("h_in_parts", n=len(f["parts"])) if f.get("parts") else ""
                text = " · ".join(x for x in (f"{f['file']}", f"{f['size'] / 2**30:.1f} GB", parts,
                                              words.t(why) if why else "") if x)
                name = Gtk.Label(label=text, xalign=0, wrap=True, max_width_chars=24)
                name.set_line_wrap_mode(2)  # Pango WORD_CHAR: a long file name breaks instead of widening the dock
                line.pack_start(name, True, True, 0)
                result = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
                result.set_margin_start(12)
                if f["offered"] and opened:
                    check = Gtk.Button(label=words.t("h_check"))

                    def run_check(b, path=f["path"], result=result, then=None) -> None:
                        b.set_sensitive(False)
                        clear(result)
                        result.pack_start(small(words.t("h_checking")), False, False, 0)
                        result.show_all()
                        self.daemon_async("HubCheck", (v["repo"], path), "(ss)", lambda c: checked(result, c, then))
                    check.connect("clicked", run_check)
                    line.pack_end(check, False, False, 0)
                    checks.append((f["size"], check, run_check))
                area.pack_start(line, False, False, 0)
                area.pack_start(result, False, False, 0)
            area.show_all()
            if auto:
                queue = [c for c in sorted(checks, key=lambda c: c[0])[:AUTO_CHECKS]]

                def next_check() -> None:
                    if queue:
                        _, button, run_check = queue.pop(0)
                        run_check(button, then=next_check)
                next_check()

        def results(rs: list) -> None:
            clear(found)
            go.set_sensitive(True)
            if not rs:
                found.pack_start(small(words.t("h_none")), False, False, 0)
            for r in rs:
                b = Gtk.Button(label=r["repo"])
                b.set_halign(Gtk.Align.START)
                b.set_relief(Gtk.ReliefStyle.NONE)
                b.get_child().set_line_wrap(True)  # a long repo name breaks instead of widening the dock (2026-10-24:
                b.get_child().set_line_wrap_mode(2)  # Qwen3.8's names stretched it across half the screen)
                b.get_child().set_max_width_chars(28)
                b.get_child().set_xalign(0)
                found.pack_start(b, False, False, 0)
                found.pack_start(small(f"{words.licence_line(r['licence'])} · {words.t('h_dl', n=r['downloads'])}"),
                                 False, False, 0)
                area = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
                area.set_margin_start(12)
                found.pack_start(area, False, False, 0)
                b.connect("clicked", lambda b, repo=r["repo"], area=area: self.daemon_async(
                    "HubFiles", (repo,), "(s)", lambda v: repo_files(area, v)))
                get = Gtk.Button(label=words.t("h_open"))  # the repository's files, each checked, each downloadable
                get.set_halign(Gtk.Align.START)
                get.connect("clicked", lambda b, repo=r["repo"], area=area: (b.set_sensitive(False), self.daemon_async(
                    "HubFiles", (repo,), "(s)", lambda v: repo_files(area, v, auto=True))))
                found.pack_start(get, False, False, 0)
            found.show_all()

        def search(*_a) -> None:
            q = entry.get_text().strip()
            if q:
                go.set_sensitive(False)
                self.daemon_async("HubSearch", (q,), "(s)", results)
        go.connect("clicked", search)
        entry.connect("activate", search)

        def drive_list(ds: list) -> None:
            clear(on_drives)
            drives.set_sensitive(True)
            if not ds:
                on_drives.pack_start(small(words.t("h_no_drives")), False, False, 0)
            for d in ds:
                on_drives.pack_start(Gtk.Label(label=f"{d['model']} · {d['size'] / 2**30:.1f} GB", xalign=0,
                                               wrap=True, max_width_chars=30), False, False, 0)
                on_drives.pack_start(small(d["path"]), False, False, 0)
                for line in words.fit_lines(d["jobs"]):
                    on_drives.pack_start(small(line), False, False, 0)
                if d.get("here"):
                    on_drives.pack_start(small(words.t("h_have")), False, False, 0)
                elif any(f["fits"] for f in d["jobs"].values()):
                    pick = self.job_picker(d["jobs"])
                    bring = Gtk.Button(label=words.t("h_bring", gb=f"{d['size'] / 2**30:.1f}"))
                    bring.connect("clicked", lambda b, path=d["path"], pick=pick: (b.set_sensitive(False),
                                  self.start_job("ModelBringIn", (path, pick.get_active_id() or ""),
                                                 words.MODEL_COPYING, "(ss)")))
                    on_drives.pack_start(pick, False, False, 0)
                    on_drives.pack_start(bring, False, False, 0)
            on_drives.show_all()
        drives.connect("clicked", lambda b: (b.set_sensitive(False),
                                             self.daemon_async("ModelsOnDrives", (), "()", drive_list)))

    def requests_view(self, opened: bool = True) -> None:
        """Recent requests, each with its tree of tasks: state, what kind, which model did it; Stop on anything not
        finished (turn tokens, SPEC §22.4)."""
        trees = self.daemon_json("TurnList")
        if trees is None:
            return
        if opened:
            self.to_bottom()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.get_style_context().add_class("proposal")
        head = Gtk.Box(spacing=6)
        title = Gtk.Label(label=words.t("requests"), xalign=0)
        title.get_style_context().add_class("what")
        head.pack_start(title, True, True, 0)
        refresh = Gtk.Button(label=words.t("refresh"))
        refresh.connect("clicked", lambda b: (box.destroy(), self.requests_view(False)))
        head.pack_end(refresh, False, False, 0)
        box.pack_start(head, False, False, 0)
        if not trees:
            box.pack_start(Gtk.Label(label=words.t("no_requests"), xalign=0), False, False, 0)

        def node(task: dict, depth: int) -> None:
            line, detail = words.request_lines(task)
            row = Gtk.Box(spacing=6)
            row.set_margin_start(12 * depth)
            text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            text.pack_start(Gtk.Label(label=("└ " if depth else "") + line, xalign=0, wrap=True,
                                      max_width_chars=26), False, False, 0)
            if detail:
                small = Gtk.Label(label=detail, xalign=0, wrap=True, max_width_chars=26)
                small.get_style_context().add_class("note")
                text.pack_start(small, False, False, 0)
            row.pack_start(text, True, True, 0)
            if task.get("status") in ("pending", "in_progress", "awaiting_review"):
                stop = Gtk.Button(label=words.t("stop"))

                def stop_it(b, tid=task["id"]) -> None:
                    b.set_sensitive(False)
                    self.proxy.call("TurnCancel", GLib.Variant("(u)", (tid,)), Gio.DBusCallFlags.NONE, 10000, None,
                                    lambda p, r: GLib.idle_add(lambda: (box.destroy(), self.requests_view(False)) and False))
                stop.connect("clicked", stop_it)
                row.pack_end(stop, False, False, 0)
            box.pack_start(row, False, False, 0)
            for child in task.get("children", []):
                node(child, depth + 1)

        for tree in trees:
            node(tree, 0)
        close = Gtk.Button(label=words.t("close"))
        close.set_halign(Gtk.Align.START)
        close.connect("clicked", lambda b: box.destroy())
        box.pack_start(close, False, False, 0)
        self.chat.pack_start(box, False, False, 0)
        box.show_all()

    def standing_report(self, r: dict) -> None:
        if r.get("report"):
            self.bubble("assistant", words.standing_head(r) + "\n\n" + r["report"])
            if r.get("sources"):
                self.sources_card({"sources": r["sources"]})
        for card in r.get("key_cards", []):
            self.key_card(card)

    def standing_list(self) -> None:
        """Every standing task: what, when, the last run; pause, resume or delete each (D88)."""
        tasks = self.daemon_json("StandingList")
        if tasks is None:
            return
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.get_style_context().add_class("proposal")
        head = Gtk.Label(label=words.t("standing"), xalign=0)
        head.get_style_context().add_class("what")
        box.pack_start(head, False, False, 0)
        if not tasks:
            box.pack_start(Gtk.Label(label=words.t("standing_none"), xalign=0, wrap=True, max_width_chars=30),
                           False, False, 0)
        for t in tasks:
            row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            if t.get("kind") == "updates":  # D88: changed where they're set, in the Updates window (D89)
                row.pack_start(Gtk.Label(label=words.daily_line(t), xalign=0, wrap=True, max_width_chars=30),
                               False, False, 0)
                open_it = Gtk.Button(label=words.t("updates_window"))
                open_it.set_halign(Gtk.Align.START)
                open_it.connect("clicked", lambda b: self.open_updates())
                row.pack_start(open_it, False, False, 0)
                box.pack_start(row, False, False, 0)
                continue
            row.pack_start(Gtk.Label(label=words.standing_line(t), xalign=0, wrap=True, max_width_chars=30),
                           False, False, 0)
            buttons = Gtk.Box(spacing=6)
            pause = Gtk.Button(label=words.t("resume") if t.get("paused") else words.t("pause"))
            delete = Gtk.Button(label=words.t("delete"))
            last = Gtk.Button(label=words.t("last_report"))
            last.set_sensitive(bool(t.get("last_report")))

            def change(button, tid=t["id"], what="", row=row) -> None:
                what = what or ("resume" if button.get_label() == words.t("resume") else "pause")
                if self.daemon_json("StandingChange", tid, what) is None:
                    return
                if what == "delete":
                    row.destroy()
                else:
                    button.set_label(words.t("resume") if what == "pause" else words.t("pause"))

            pause.connect("clicked", change)
            delete.connect("clicked", lambda b, tid=t["id"], row=row: change(b, tid, "delete", row))
            last.connect("clicked", lambda b, t=t: self.bubble("assistant", t.get("last_report", "")))
            for b in (pause, delete, last):
                buttons.pack_start(b, False, False, 0)
            row.pack_start(buttons, False, False, 0)
            box.pack_start(row, False, False, 0)
        close = Gtk.Button(label=words.t("close"))
        close.set_halign(Gtk.Align.START)
        close.connect("clicked", lambda b: box.destroy())
        box.pack_start(close, False, False, 0)
        self.chat.pack_start(box, False, False, 0)
        box.show_all()

    def key_card(self, card: dict) -> None:
        """A source needs a key: how to get one (the person registers themselves), and a masked box that sends it
        straight to the daemon, which keeps it in the login keyring. It never goes into the conversation."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.get_style_context().add_class("proposal")
        head = Gtk.Label(label=words.key_head(card), xalign=0, wrap=True, max_width_chars=30)
        head.get_style_context().add_class("what")
        box.pack_start(head, False, False, 0)
        steps = "\n".join(f"{i + 1}. {step}" for i, step in enumerate(card.get("steps", [])))
        box.pack_start(Gtk.Label(label=steps, xalign=0, wrap=True, max_width_chars=30), False, False, 0)
        url = card.get("signup_url", "")
        if url.startswith("https://"):
            link = Gtk.LinkButton(uri=url, label=words.t("open_signup"))
            link.set_halign(Gtk.Align.START)
            box.pack_start(link, False, False, 0)
        entry = Gtk.Entry(visibility=False, placeholder_text=words.t("paste_key"))
        entry.set_input_purpose(Gtk.InputPurpose.PASSWORD)
        box.pack_start(entry, False, False, 0)
        note = Gtk.Label(label=words.t("key_note"), xalign=0, wrap=True, max_width_chars=30)
        note.get_style_context().add_class("note")
        box.pack_start(note, False, False, 0)
        buttons = Gtk.Box(spacing=6)
        save = Gtk.Button(label=words.t("save_key"))
        save.get_style_context().add_class("suggested-action")
        later = Gtk.Button(label=words.t("later"))

        def keep(button) -> None:
            key = entry.get_text()
            entry.set_text("")  # out of the widget at once, whatever happens next
            if not key.strip() or not self.proxy:
                return
            save.set_sensitive(False)

            def done(proxy, res) -> None:
                save.set_sensitive(True)
                try:
                    out = json.loads(proxy.call_finish(res).unpack()[0])
                except GLib.Error as e:
                    Gio.DBusError.strip_remote_error(e)
                    out = {"ok": False, "error": e.message}
                if out.get("ok"):
                    box.destroy()
                    self.progress_line(words.key_saved(out.get("name", card.get("name", ""))))
                else:
                    note.set_text(words.t("not_saved", error=out.get("error", "")))

            self.proxy.call("KeySet", GLib.Variant("(ss)", (card.get("source", ""), key)), Gio.DBusCallFlags.NONE,
                            30000, None, done)

        save.connect("clicked", keep)
        entry.connect("activate", keep)
        later.connect("clicked", lambda b: box.destroy())
        buttons.pack_start(save, False, False, 0)
        buttons.pack_start(later, False, False, 0)
        box.pack_start(buttons, False, False, 0)
        self.chat.pack_start(box, False, False, 0)
        box.show_all()

    def search_card(self, offer: dict) -> None:
        """The query that would be sent, editable; nothing is sent until Search (SPEC §7.5)."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.get_style_context().add_class("proposal")
        head = Gtk.Label(label=words.t("search_head"), xalign=0)
        head.get_style_context().add_class("what")
        box.pack_start(head, False, False, 0)
        query = Gtk.Entry(text=offer.get("query", ""))
        box.pack_start(query, False, False, 0)
        note = Gtk.Label(label=words.search_note(offer), xalign=0, wrap=True, max_width_chars=30)
        note.get_style_context().add_class("note")
        box.pack_start(note, False, False, 0)
        buttons = Gtk.Box(spacing=6)
        go = Gtk.Button(label=words.t("search"))
        go.get_style_context().add_class("suggested-action")
        no = Gtk.Button(label=words.t("no_thanks"))

        def search(button) -> None:
            go.set_sensitive(False)
            no.set_sensitive(False)
            query.set_sensitive(False)
            self.start_job("Search", (offer.get("id", ""), query.get_text().strip()), words.t("looking"), "(ss)")

        def dismiss(button) -> None:
            box.destroy()  # nothing was sent

        go.connect("clicked", search)
        no.connect("clicked", dismiss)
        buttons.pack_start(go, False, False, 0)
        buttons.pack_start(no, False, False, 0)
        box.pack_start(buttons, False, False, 0)
        self.chat.pack_start(box, False, False, 0)
        box.show_all()

    def try_result(self, r: dict) -> None:
        """What the command did on the copy (M3 slice 4): the verdict in the answer bubble, the details below."""
        if self.reply is not None:
            self.reply.get_style_context().remove_class("waiting")
            self.reply.set_text(words.try_verdict(r))
            self.reply_started = True
        details = words.try_details(r)
        if details:
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            box.get_style_context().add_class("command")
            for text, mono in details:
                label = Gtk.Label(label=text, xalign=0, wrap=True, selectable=mono, max_width_chars=30)
                label.get_style_context().add_class("code" if mono else "note")
                box.pack_start(label, False, False, 0)
            self.chat.pack_start(box, False, False, 0)
            box.show_all()

    def terminal_offer_card(self) -> None:
        """D77: asked once, when it would help. Nothing is shared before Yes; terminals already open stay as they are."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.get_style_context().add_class("proposal")
        head = Gtk.Label(label=words.TERMINAL_OFFER, xalign=0, wrap=True, max_width_chars=30)
        head.get_style_context().add_class("what")
        box.pack_start(head, False, False, 0)
        note = Gtk.Label(label=words.TERMINAL_OFFER_NOTE, xalign=0, wrap=True, max_width_chars=30)
        note.get_style_context().add_class("note")
        box.pack_start(note, False, False, 0)
        buttons = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, max_children_per_line=3, column_spacing=6,
                              row_spacing=6, homogeneous=False)
        said = Gtk.Label(xalign=0, wrap=True, max_width_chars=30)
        said.get_style_context().add_class("note")

        def answer(choice: str) -> None:
            state = self.daemon_json("TerminalSharing", choice) or {}
            buttons.destroy()
            said.set_text(words.terminal_sharing_said(choice, state))
            said.show()

        for label, choice, suggested in (("Yes, share new terminals", "on", True), ("Not now", "later", False),
                                         ("Don't ask again", "never", False)):
            b = Gtk.Button(label=label)
            if suggested:
                b.get_style_context().add_class("suggested-action")
            b.connect("clicked", lambda w, c=choice: answer(c))
            buttons.add(b)
        box.pack_start(buttons, False, False, 0)
        box.pack_start(said, False, False, 0)
        self.chat.pack_start(box, False, False, 0)
        box.show_all()
        said.hide()

    def diagnosis_card(self, step: dict) -> None:
        """A fault's tree, walked (D51, D7): this fix, what fixed looks like, and Check again — the checks run again
        and the rule decides (gone, the next fix, or the end of the tree), never the model."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.get_style_context().add_class("proposal")
        head = Gtk.Label(label=words.diag_head(step), xalign=0, wrap=True, max_width_chars=30)
        head.get_style_context().add_class("what")
        box.pack_start(head, False, False, 0)
        for s in step.get("steps", []):
            box.pack_start(Gtk.Label(label="• " + s, xalign=0, wrap=True, max_width_chars=30), False, False, 0)
        notes = ([words.diag("fixed_is", verify=step["verify"])] if step.get("verify") else []) +             ([words.diag("restart")] if step.get("restart") else [])
        for text in notes:
            note = Gtk.Label(label=text, xalign=0, wrap=True, max_width_chars=30)
            note.get_style_context().add_class("note")
            box.pack_start(note, False, False, 0)
        buttons = Gtk.Box(spacing=6)
        check, later = Gtk.Button(label=words.diag("check")), Gtk.Button(label=words.diag("later"))
        check.get_style_context().add_class("suggested-action")

        def checked(proxy, result) -> None:
            try:
                out = json.loads(proxy.call_finish(result).unpack()[0])
            except (GLib.Error, ValueError) as e:
                out = {"outcome": "error", "said": str(e)}
            buttons.destroy()
            said = Gtk.Label(label=out.get("said", ""), xalign=0, wrap=True, max_width_chars=30)  # its own line,
            said.get_style_context().add_class("action")                                    # in the walk's order
            self.chat.pack_start(said, False, False, 0)
            said.show()
            nxt = out.get("next")
            if nxt:
                if nxt.get("command"):
                    self.command_card({"command": nxt["command"], "explain": nxt.get("command_explained", ""),
                                       "undo": nxt.get("undo", "")})
                self.diagnosis_card(nxt)
            elif out.get("think"):  # the end of the tree: Think it through, offered (D7)
                self.think_card(out["think"])

        def on_check(b) -> None:
            check.set_sensitive(False)
            later.set_sensitive(False)
            check.set_label(words.diag("checking"))
            self.proxy.call("DiagCheck", GLib.Variant("(s)", (json.dumps(
                {"code": step["code"], "n": step.get("fix_n", 0), "title": step.get("title", "")}),)),
                Gio.DBusCallFlags.NONE, 60000, None, checked)

        check.connect("clicked", on_check)
        later.connect("clicked", lambda b: buttons.destroy())
        buttons.pack_start(check, False, False, 0)
        buttons.pack_start(later, False, False, 0)
        box.pack_start(buttons, False, False, 0)
        self.chat.pack_start(box, False, False, 0)
        box.show_all()

    def think_card(self, offer: dict) -> None:
        """Past the end of the diagnostic trees (D7): the person may have the model reason over what the checks
        recorded — the coding model if they have one, thinking; else the guide. Nothing loads before the click."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.get_style_context().add_class("proposal")
        head = Gtk.Label(label=words.think("offer"), xalign=0, wrap=True, max_width_chars=30)
        head.get_style_context().add_class("what")
        box.pack_start(head, False, False, 0)
        model = offer.get("model") or ""
        note = Gtk.Label(label=words.think("note_model", model=model) if model else words.think("note_guide"),
                         xalign=0, wrap=True, max_width_chars=30)
        note.get_style_context().add_class("note")
        box.pack_start(note, False, False, 0)
        buttons = Gtk.Box(spacing=6)
        go, no = Gtk.Button(label=words.think("go")), Gtk.Button(label=words.think("no"))
        go.get_style_context().add_class("suggested-action")

        def ask(button) -> None:
            go.set_sensitive(False)
            no.set_sensitive(False)
            self.start_job("DiagThink", offer.get("id", ""),
                           words.think("loading", model=model) if model else words.think("running", s=0))

        go.connect("clicked", ask)
        no.connect("clicked", lambda b: box.destroy())
        buttons.pack_start(go, False, False, 0)
        buttons.pack_start(no, False, False, 0)
        box.pack_start(buttons, False, False, 0)
        self.chat.pack_start(box, False, False, 0)
        box.show_all()

    def bigger_card(self, offer: dict) -> None:
        """A terminal error the built-in help doesn't cover: the person may ask the bigger model they already have
        (Ian, 2026-10-04: only when no card fits, and only if they say so). Nothing loads before the click."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.get_style_context().add_class("proposal")
        head = Gtk.Label(label=words.bigger_offer(offer), xalign=0, wrap=True, max_width_chars=30)
        head.get_style_context().add_class("what")
        box.pack_start(head, False, False, 0)
        note = Gtk.Label(label=words.bigger_note(offer), xalign=0, wrap=True, max_width_chars=30)
        note.get_style_context().add_class("note")
        box.pack_start(note, False, False, 0)
        buttons = Gtk.Box(spacing=6)
        go = Gtk.Button(label="Ask it")
        go.get_style_context().add_class("suggested-action")
        no = Gtk.Button(label="No thanks")

        def ask(button) -> None:
            go.set_sensitive(False)
            no.set_sensitive(False)
            self.start_job("AskBigger", offer.get("id", ""), "Loading the bigger model…")

        go.connect("clicked", ask)
        no.connect("clicked", lambda b: box.destroy())
        buttons.pack_start(go, False, False, 0)
        buttons.pack_start(no, False, False, 0)
        box.pack_start(buttons, False, False, 0)
        self.chat.pack_start(box, False, False, 0)
        box.show_all()

    def sources_card(self, found: dict) -> None:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        box.get_style_context().add_class("command")
        head = Gtk.Label(label="Sources", xalign=0)
        head.get_style_context().add_class("note")
        box.pack_start(head, False, False, 0)
        for s in found.get("sources", []):
            # an article from a shelf on this computer brings its own photo and, for a place, its map (D68): what it
            # is and where, beside the answer; the daemon saved them from the file, nothing was fetched
            for p in s.get("pictures", []):
                try:
                    pic = Gtk.Image.new_from_pixbuf(GdkPixbuf.Pixbuf.new_from_file_at_scale(p["path"], 240, 240, True))
                except (GLib.Error, KeyError, TypeError):
                    continue
                pic.set_halign(Gtk.Align.START)
                pic.set_tooltip_text(words.picture_tip(p.get("kind", ""), s.get("title", "")))
                box.pack_start(pic, False, False, 0)
            link = Gtk.LinkButton(uri=s.get("url", ""), label=words.source_line(s))
            link.set_halign(Gtk.Align.START)
            link.get_child().set_line_wrap(True)
            link.get_child().set_line_wrap_mode(2)  # Pango WORD_CHAR: a long address breaks instead of widening the dock
            link.get_child().set_max_width_chars(30)
            box.pack_start(link, False, False, 0)
        self.chat.pack_start(box, False, False, 0)
        if found.get("videos") and self.reply is not None:
            # a chain's list of videos (D91) is the menu to choose from: above the summary, not under it like citations
            self.chat.reorder_child(box, self.chat.get_children().index(self.reply.get_parent().get_parent()))
        box.show_all()

    def start_job(self, method: str, arg, waiting: str, fmt: str = "(s)") -> None:
        """WriteUp / WriteDraft / Search: like a question, but nothing typed: the reply streams into a new bubble."""
        if not self.proxy or self.rid is not None:
            return
        self.to_bottom()
        self.job_waiting = waiting  # 2026-10-24: a status change put "Reading your question…" over a download
        self.reply = self.bubble("assistant", waiting)
        self.reply.get_style_context().add_class("waiting")
        self.reply_started = False
        self.rid = -1

        def started(proxy, result) -> None:
            try:
                (self.rid,) = proxy.call_finish(result).unpack()
            except GLib.Error as e:
                Gio.DBusError.strip_remote_error(e)
                self.finish_reply(error=e.message)
            self.update_header()

        args = arg if isinstance(arg, tuple) else (arg,)
        self.proxy.call(method, GLib.Variant(fmt, args), Gio.DBusCallFlags.NONE, 3600000, None, started)
        self.update_header()

    def review_card(self, review: dict) -> None:
        """Before every chapter (D57): where the story is on the circle, what's missing, questions; the writer's
        answers go with Plan the chapter and become notes."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.get_style_context().add_class("proposal")
        head = Gtk.Label(label=words.review_title(review), xalign=0, wrap=True, max_width_chars=30)
        head.get_style_context().add_class("what")
        box.pack_start(head, False, False, 0)
        # the circle as tick boxes: ticked = already written; the writer's ticks decide where the chapter starts
        box.pack_start(Gtk.Label(label="The story circle — tick what's already written:", xalign=0, wrap=True,
                                 max_width_chars=30), False, False, 0)
        ticks = {}
        cover = Gtk.Label(xalign=0, wrap=True, max_width_chars=30)

        def follow(*_) -> None:
            cover.set_text(words.cover_line(review, words.would_cover(review, {k for k, b in ticks.items() if b.get_active()})))
        for key, line, written in words.review_steps(review):
            b = Gtk.CheckButton(active=written)
            b.add(Gtk.Label(label=line, xalign=0, wrap=True, max_width_chars=28))
            b.connect("toggled", follow)
            ticks[key] = b
            box.pack_start(b, False, False, 0)
        for line in words.review_lines(review, steps=False):
            box.pack_start(Gtk.Label(label=line, xalign=0, wrap=True, max_width_chars=30, selectable=True), False, False, 0)
        follow()
        box.pack_start(cover, False, False, 2)
        answers = Gtk.Entry(placeholder_text="Your answers, or anything to add (optional)")
        box.pack_start(answers, False, False, 2)
        plan = Gtk.Button(label="Plan the chapter")
        plan.get_style_context().add_class("suggested-action")

        def go(button) -> None:
            plan.set_sensitive(False)
            answers.set_sensitive(False)
            for b in ticks.values():
                b.set_sensitive(False)
            self.start_job("PlanChapter", json.dumps({"answers": answers.get_text().strip(),
                                                      "written": [k for k, b in ticks.items() if b.get_active()]}),
                           "Planning the chapter…")
        plan.connect("clicked", go)
        answers.connect("activate", go)
        box.pack_start(plan, False, False, 0)
        self.chat.pack_start(box, False, False, 0)
        box.show_all()

    def outline_card(self, outline: dict) -> None:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.get_style_context().add_class("proposal")
        head = Gtk.Label(label=outline.get("chapter_title", "The plan"), xalign=0, wrap=True, max_width_chars=30)
        head.get_style_context().add_class("what")
        box.pack_start(head, False, False, 0)
        for line in words.outline_lines(outline):
            box.pack_start(Gtk.Label(label=line, xalign=0, wrap=True, max_width_chars=30, selectable=True), False, False, 0)
        change = Gtk.Entry(placeholder_text="What should change? (optional)")
        box.pack_start(change, False, False, 2)
        buttons = Gtk.Box(spacing=6)
        write = Gtk.Button(label="Write it")
        write.get_style_context().add_class("suggested-action")
        again = Gtk.Button(label="Plan again")

        def go(button, method: str) -> None:
            write.set_sensitive(False)
            again.set_sensitive(False)
            if method == "WriteDraft":
                self.start_job("WriteDraft", outline.get("id", ""), "Writing the draft… (you can keep using the computer)")
            else:
                self.start_job("PlanChapter", change.get_text().strip(), "Planning again…")

        write.connect("clicked", go, "WriteDraft")
        again.connect("clicked", go, "PlanChapter")
        buttons.pack_start(write, False, False, 0)
        buttons.pack_start(again, False, False, 0)
        box.pack_start(buttons, False, False, 0)
        self.chat.pack_start(box, False, False, 0)
        box.show_all()

    def progress_line(self, text: str, fraction: float | None = None) -> None:
        """One line that follows the draft (scene n of N), then says where it was saved; with a fraction (a
        download), a bar under it as well as the numbers (Ian, 2026-10-24)."""
        if getattr(self, "progress", None) is None or self.progress.get_parent() is None:
            self.progress = Gtk.Label(xalign=0, wrap=True, max_width_chars=30)
            self.progress.get_style_context().add_class("action")
            self.chat.pack_start(self.progress, False, False, 0)
            self.progress.show()
            self.progress_bar = Gtk.ProgressBar()
            self.chat.pack_start(self.progress_bar, False, False, 0)
        self.progress.set_text(text)
        if fraction is None:
            self.progress_bar.hide()
        else:
            self.progress_bar.set_fraction(min(max(fraction, 0.0), 1.0))
            self.progress_bar.show()

    def proposal_card(self, pv: dict) -> None:
        """A document edit the assistant prepared: before -> after, Apply / Discard (SPEC §7.8). Nothing
        changes until Apply; LibreOffice refuses it if the document changed since the preview."""
        parts = words.preview_parts(pv)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.get_style_context().add_class("proposal")
        what = Gtk.Label(label=parts["title"], xalign=0, wrap=True, max_width_chars=30)
        what.get_style_context().add_class("what")
        box.pack_start(what, False, False, 0)
        for label, value, cls in (("Now", parts["before"], "before"), ("After", parts["after"], "after")):
            if not value:
                continue
            head = Gtk.Label(label=label, xalign=0)
            head.get_style_context().add_class(cls)
            box.pack_start(head, False, False, 0)
            if parts["kind"] == "grid":
                g = Gtk.Grid(column_spacing=0, row_spacing=0)
                for r, row in enumerate(value):
                    for c, v in enumerate(row):
                        cell = Gtk.Label(label=v, xalign=0)
                        cell.get_style_context().add_class("cell")
                        cell.get_style_context().add_class(cls)
                        g.attach(cell, c, r, 1, 1)
                box.pack_start(g, False, False, 0)
            else:
                text = Gtk.Label(label=value, xalign=0, wrap=True, selectable=True, max_width_chars=30)
                text.set_line_wrap_mode(2)
                text.get_style_context().add_class(cls)
                box.pack_start(text, False, False, 0)
        buttons = Gtk.Box(spacing=6)
        apply = Gtk.Button(label="Apply")
        apply.get_style_context().add_class("suggested-action")
        discard = Gtk.Button(label="Discard")
        result = Gtk.Label(xalign=0, wrap=True, max_width_chars=30)

        def decide(button, yes: bool) -> None:
            apply.set_sensitive(False)
            discard.set_sensitive(False)

            def done(proxy, res) -> None:
                try:
                    (out,) = proxy.call_finish(res).unpack()
                    result.set_text(words.decided(json.loads(out), None))
                except GLib.Error as e:
                    Gio.DBusError.strip_remote_error(e)
                    result.set_text(words.decided(None, e.message))
                result.show()

            self.proxy.call("Decide", GLib.Variant("(sb)", (pv.get("id", ""), yes)), Gio.DBusCallFlags.NONE,
                            30000, None, done)

        apply.connect("clicked", decide, True)
        discard.connect("clicked", decide, False)
        buttons.pack_start(apply, False, False, 0)
        buttons.pack_start(discard, False, False, 0)
        box.pack_start(buttons, False, False, 0)
        box.pack_start(result, False, False, 0)
        self.chat.pack_start(box, False, False, 0)
        box.show_all()
        result.hide()

    def on_libreoffice(self, conn, sender, path, iface, signal, params) -> None:
        """LibreOffice's Assistant menu: open the sidebar, and ask (or wait for the question)."""
        _doc, action, _context = params.unpack()
        self.show()
        question = words.ASKED.get(action)
        if question and self.rid is None:
            self.ask(question)

    def command_card(self, card: dict) -> None:
        """A command the person can copy and run themselves, with what it does and how to undo it (D53)."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.get_style_context().add_class("command")
        top = Gtk.Box(spacing=6)
        code = Gtk.Label(label=card["command"], xalign=0, wrap=True, selectable=True, max_width_chars=28)
        code.set_line_wrap_mode(2)
        code.get_style_context().add_class("code")
        copy = Gtk.Button(label="Copy")
        copy.set_tooltip_text("Copy the command; paste it in the Terminal with Ctrl+Shift+V")

        def on_copy(b) -> None:
            Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_text(card["command"], -1)
            b.set_label("Copied")
            GLib.timeout_add_seconds(2, lambda: b.set_label("Copy") or False)

        copy.connect("clicked", on_copy)
        top.pack_start(code, True, True, 0)
        top.pack_end(copy, False, False, 0)
        box.pack_start(top, False, False, 0)
        explain = Gtk.Button(label="Explain")  # SPEC §6.4: what it does, and whether it changes anything
        explain.set_tooltip_text("Ask what this command does, in plain words, and whether it changes anything")
        explain.connect("clicked", lambda b, c=card["command"]: self.ask(words.explain_question(c, words.ui_lang())))
        explain_row = Gtk.Box(spacing=6)
        explain_row.pack_start(explain, False, False, 0)
        box.pack_start(explain_row, False, False, 0)
        if self.terminal_turn:  # the answer was about the shared terminal: offer to put it at the prompt (SPEC §6.4)
            send = Gtk.Button(label="To terminal")
            send.set_tooltip_text("Put this command at your terminal's prompt. It doesn't run until you press Enter there.")
            said = Gtk.Label(xalign=0, wrap=True, max_width_chars=30)
            said.get_style_context().add_class("note")

            def on_send(b) -> None:
                def done(proxy, result) -> None:
                    try:
                        reply = json.loads(proxy.call_finish(result).unpack()[0])
                    except (GLib.Error, ValueError) as e:
                        reply = {"ok": False, "error": str(e)}
                    said.set_text(words.sent_to_terminal(reply))
                    said.show()
                self.proxy.call("TerminalSend", GLib.Variant("(s)", (card["command"],)), Gio.DBusCallFlags.NONE,
                                5000, None, done)

            send.connect("clicked", on_send)
            row = Gtk.Box(spacing=6)
            row.pack_start(send, False, False, 0)
            if words.can_try(card["command"]):  # M3 slice 4: on a copy of the folder, in the sandbox
                trial = Gtk.Button(label="Try it first")
                trial.set_tooltip_text("Run it on a copy of your folder, in a sandbox: your files and your system "
                                       "aren't touched. Then you decide.")
                trial.connect("clicked", lambda b, c=card["command"]: (b.set_sensitive(False), self.start_job(
                    "TerminalTry", c, words.TRYING)))
                row.pack_start(trial, False, False, 0)
            box.pack_start(row, False, False, 0)
            box.pack_start(said, False, False, 0)
        for text in words.card_notes(card, self.terminal_turn):
            note = Gtk.Label(label=text, xalign=0, wrap=True, max_width_chars=30)
            note.get_style_context().add_class("note")
            box.pack_start(note, False, False, 0)
        self.chat.pack_start(box, False, False, 0)
        box.show_all()
        for child in box.get_children():  # the "sent" note stays hidden until there's something to say
            if isinstance(child, Gtk.Label) and not child.get_text():
                child.hide()

    def finish_reply(self, error: str | None = None) -> None:
        if self.reply is not None and not error:
            for card in words.merge_cards(self.cards, words.commands_in_text(self.reply.get_text())):
                self.command_card(card)
            if self.diag_step:
                self.diagnosis_card(self.diag_step)
            if self.reply_started and words.worth_a_document(self.reply.get_text()):
                self.writer_button(self.reply.get_text())
        self.cards, self.diag_step = [], None
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
                  "--quit": self.quit, "--standing": lambda: (self.show(), self.standing_list()),
                  "--requests": lambda: (self.show(), self.requests_view()),
                  "--models": lambda: (self.show(), self.models_view()),
                  "--library": lambda: (self.show(), self.library_view())}.get(args[0])
        if action is None:
            cmdline.printerr(f"unknown option {args[0]}\n")
            return 2
        action()
        return 0


LOG_MAX = 256 * 1024


def keep_log() -> None:
    """Errors go to ~/.cache/cinminai/sidebar.log: the panel starts the sidebar with its output on /dev/null, and a
    multi-chapter fault on 2026-10-01 left nothing behind. PyGObject reports callback errors via sys.excepthook."""
    import time
    import traceback
    folder = os.path.join(os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache"), "cinminai")
    try:
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, "sidebar.log")
        if os.path.exists(path) and os.path.getsize(path) > LOG_MAX:
            os.replace(path, path + ".1")
        sys.stderr = open(path, "a", buffering=1, encoding="utf-8", errors="replace")
    except OSError:
        return

    def hook(kind, value, tb) -> None:
        sys.stderr.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} sidebar error:\n"
                         + "".join(traceback.format_exception(kind, value, tb)))
    sys.excepthook = hook
    sys.stderr.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} sidebar started: {' '.join(sys.argv[1:])}\n")


def main() -> None:
    keep_log()
    sys.exit(Sidebar().run(sys.argv))
