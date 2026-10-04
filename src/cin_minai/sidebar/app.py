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
"""


def margined(box) -> None:
    """A dialog's content with room around it (2026-10-04: the text touched the dialog's left edge)."""
    for side in ("start", "end", "top"):
        getattr(box, f"set_margin_{side}")(12)


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
        # a picture to read (D64, D78): this button, or drop the file anywhere on the sidebar
        inputs.pack_start(self.icon_button("image-x-generic-symbolic", "Show me a picture: a photo, a screenshot, "
                                           "a scanned letter (or drop it here)", self.on_pick_image), False, False, 0)
        inputs.pack_start(self.entry, True, True, 0)
        inputs.pack_end(self.stop, False, False, 0)
        inputs.pack_end(self.go, False, False, 0)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        for w, expand in ((header, False), (privacy, False), (self.project_box, False), (self.journal_box, False),
                          (Gtk.Separator(), False),
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
                          row_spacing=6, min_children_per_line=1, max_children_per_line=3)
        for label, cb in (("Start a writing project", lambda b: self.new_project()),
                          ("Open the journal", lambda b: self.open_journal()),
                          ("Open AICUI (coding)", lambda b: self.open_aicui())):
            b = Gtk.Button(label=label)
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
        self.proxy.get_connection().signal_subscribe(LIBREOFFICE[0], LIBREOFFICE[2], "Asked", LIBREOFFICE[1], None,
                                                     Gio.DBusSignalFlags.NONE, self.on_libreoffice)
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
        project = status.get("project", "")
        self.project_label.set_text(words.project_bar(project))
        self.project_box.set_visible(bool(project))
        journal = bool(status.get("journal"))
        self.journal_box.set_visible(journal)
        self.entry.set_placeholder_text("Tell me about your story…" if project else
                                        "Tell me about your day…" if journal else "Ask…")
        busy = self.rid is not None
        self.stop.set_visible(busy)
        self.go.set_visible(not busy)
        if self.reply is not None and not self.reply_started:
            self.reply.set_text(words.waiting(state, status.get("build", "")))

    # --- pictures (D64, D78) ------------------------------------------------------------------------------
    def on_pick_image(self, button) -> None:
        dialog = Gtk.FileChooserDialog(title="Show the assistant a picture", parent=self.win,
                                       action=Gtk.FileChooserAction.OPEN)
        dialog.add_buttons("Cancel", Gtk.ResponseType.CANCEL, "Show it", Gtk.ResponseType.ACCEPT)
        pics = Gtk.FileFilter()
        pics.set_name("Pictures")
        for ext in words.PICTURE_TYPES:
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
            if path and path.lower().endswith(words.PICTURE_TYPES):
                self.ask_image(path)
                return
        self.progress_line("I can read pictures (photos, screenshots, scans). Videos come next.")

    def ask_image(self, path: str) -> None:
        """The picture in the chat, then the question typed in the box (or "what's in this picture?")."""
        if not self.proxy or self.rid is not None:
            return
        request = self.entry.get_text().strip()
        self.entry.set_text("")
        self.bubble("user", request or words.PICTURE_DEFAULT)
        try:
            thumb = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, 240, 240, True)
            pic = Gtk.Image.new_from_pixbuf(thumb)
            pic.set_halign(Gtk.Align.END)
            self.chat.pack_start(pic, False, False, 0)
            pic.show()
        except GLib.Error:
            pass
        self.terminal_turn = False
        self.start_job("AskImage", (path, request), words.LOOKING, "(ss)")

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
        if self.rid is None or (self.rid != -1 and args[0] != self.rid):
            return  # another client's question (e.g. Firefox, a test)
        if signal == "Token" and self.reply is not None:
            if not self.reply_started:
                self.reply_started = True
                self.reply.set_text("")
                self.reply.get_style_context().remove_class("waiting")
            self.reply.set_text(self.reply.get_text() + args[1])
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
        elif signal == "Action" and args[1] == "journal" and args[3] == "done":
            self.progress_line(words.journal_written(json.loads(args[4] or "{}")))
        elif signal == "Action" and args[1] == "download":
            p = json.loads(args[4] or "{}")
            self.progress_line(words.download_progress(p) if args[3] == "running" else words.download_done(p))
        elif signal == "Action" and args[1] == "draft":
            p = json.loads(args[4] or "{}")
            self.progress_line(words.draft_progress(p) if args[3] == "running" else words.draft_done(p))
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
        sharing = self.daemon_json("TerminalSharing", "state") or {}
        if sharing.get("available"):  # D77: the switch, for after the one-time offer
            menu.append(Gtk.SeparatorMenuItem())
            check = Gtk.CheckMenuItem(label="Let the assistant see my terminals")
            check.set_active(bool(sharing.get("on")))
            check.set_tooltip_text("New terminals show ◆ and the assistant can read their commands and output. "
                                   "Type ai off in one to make it private. Nothing leaves this computer.")

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
                self.start_job("ModelDownload", task, "Getting the model… (you can keep using the computer)")
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
        self.reply = self.bubble("assistant", "Writing today's entry…")
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
    def search_card(self, offer: dict) -> None:
        """The query that would be sent, editable; nothing is sent until Search (SPEC §7.5)."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.get_style_context().add_class("proposal")
        head = Gtk.Label(label="Search the web for:", xalign=0)
        head.get_style_context().add_class("what")
        box.pack_start(head, False, False, 0)
        query = Gtk.Entry(text=offer.get("query", ""))
        box.pack_start(query, False, False, 0)
        note = Gtk.Label(label=words.search_note(offer), xalign=0, wrap=True, max_width_chars=30)
        note.get_style_context().add_class("note")
        box.pack_start(note, False, False, 0)
        buttons = Gtk.Box(spacing=6)
        go = Gtk.Button(label="Search")
        go.get_style_context().add_class("suggested-action")
        no = Gtk.Button(label="No thanks")

        def search(button) -> None:
            go.set_sensitive(False)
            no.set_sensitive(False)
            query.set_sensitive(False)
            self.start_job("Search", (offer.get("id", ""), query.get_text().strip()), "Looking it up…", "(ss)")

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
            link = Gtk.LinkButton(uri=s.get("url", ""), label=words.source_line(s))
            link.set_halign(Gtk.Align.START)
            link.get_child().set_line_wrap(True)
            link.get_child().set_max_width_chars(30)
            box.pack_start(link, False, False, 0)
        self.chat.pack_start(box, False, False, 0)
        box.show_all()

    def start_job(self, method: str, arg, waiting: str, fmt: str = "(s)") -> None:
        """WriteUp / WriteDraft / Search: like a question, but nothing typed: the reply streams into a new bubble."""
        if not self.proxy or self.rid is not None:
            return
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

    def progress_line(self, text: str) -> None:
        """One line that follows the draft (scene n of N), then says where it was saved."""
        if getattr(self, "progress", None) is None or self.progress.get_parent() is None:
            self.progress = Gtk.Label(xalign=0, wrap=True, max_width_chars=30)
            self.progress.get_style_context().add_class("action")
            self.chat.pack_start(self.progress, False, False, 0)
            self.progress.show()
        self.progress.set_text(text)

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
            if self.reply_started and words.worth_a_document(self.reply.get_text()):
                self.writer_button(self.reply.get_text())
        self.cards = []
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
