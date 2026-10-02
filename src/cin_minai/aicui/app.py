# SPDX-License-Identifier: GPL-3.0-or-later
"""AICUI, the AI coding workspace (PLAN D61, SPEC §21) — slice 1: Ian's layout with a real terminal.

    python3 -m cin_minai.aicui [FOLDER-OR-FILE]

Left: chat history. Middle: the working tree (a button at its bottom swaps in the changelog) over the session goals.
Right, the largest: the AI terminal — a real terminal (VTE) in the project folder. Bottom: the typing box and model
selection. The agent (cinminai-code), the changelog's shadow git store and the cloud providers come in later slices.
"""

from __future__ import annotations

import os
import sys

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("Vte", "2.91")
from gi.repository import Gdk, Gio, GLib, Gtk, Pango, Vte  # noqa: E402

from .project import Goals, project_root, tree  # noqa: E402

TITLE = "AICUI"
CSS = b"""
.pane-title { font-weight: bold; padding: 4px 6px; }
.bubble-user { background: alpha(@theme_selected_bg_color, 0.25); border-radius: 6px; padding: 6px; }
.bubble-ai { background: alpha(@theme_fg_color, 0.06); border-radius: 6px; padding: 6px; }
"""


def titled(title: str, child: Gtk.Widget, extra: Gtk.Widget | None = None) -> Gtk.Box:
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    head = Gtk.Label(label=title, xalign=0)
    head.get_style_context().add_class("pane-title")
    box.pack_start(head, False, False, 0)
    box.pack_start(child, True, True, 0)
    if extra is not None:
        box.pack_end(extra, False, False, 2)
    return box


def scrolled(child: Gtk.Widget) -> Gtk.ScrolledWindow:
    sw = Gtk.ScrolledWindow(hexpand=True, vexpand=True)
    sw.add(child)
    return sw


class Workspace(Gtk.ApplicationWindow):
    def __init__(self, app: Gtk.Application, root: str) -> None:
        super().__init__(application=app, title=f"{TITLE} — {os.path.basename(root) or root}")
        self.root, self.goals = root, Goals(root)
        self.set_default_size(1700, 960)

        # left: chat history (thinking will stream in and collapse into bubbles, slice 4)
        self.chat = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self.bubble("ai", f"Working in {root}. The terminal on the right is a real one; the coding agent arrives in the "
                          "next slice. Add the session's goals in the middle, or tell me about the project here.")
        left = titled("Chat history", scrolled(self.chat))

        # middle: the working tree, with the changelog behind a button at its bottom
        self.store = Gtk.TreeStore(str, str, str)  # name, git status, relative path
        view = Gtk.TreeView(model=self.store, headers_visible=False)
        name = Gtk.CellRendererText(ellipsize=Pango.EllipsizeMode.END)
        col = Gtk.TreeViewColumn("", name, text=0)
        col.set_expand(True)
        view.append_column(col)
        view.append_column(Gtk.TreeViewColumn("", Gtk.CellRendererText(), text=1))
        view.connect("row-activated", self.open_file)
        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        self.stack.add_named(scrolled(view), "files")
        self.changes = Gtk.Label(label="No AI changes yet. Every file the AI changes will be listed here, with what "
                                       "changed and an undo.", wrap=True, xalign=0, yalign=0, margin=8)
        self.stack.add_named(scrolled(self.changes), "changes")
        self.swap = Gtk.Button(label="Changelog")
        self.swap.connect("clicked", self.toggle_changelog)
        refresh = Gtk.Button.new_from_icon_name("view-refresh-symbolic", Gtk.IconSize.BUTTON)
        refresh.set_tooltip_text("Read the folder again")
        refresh.connect("clicked", lambda b: self.load_tree())
        bar = Gtk.Box(spacing=4)
        bar.pack_start(self.swap, True, True, 0)
        bar.pack_end(refresh, False, False, 0)
        self.tree_title = Gtk.Label(label="Working tree", xalign=0)
        self.tree_title.get_style_context().add_class("pane-title")
        tree_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        tree_box.pack_start(self.tree_title, False, False, 0)
        tree_box.pack_start(self.stack, True, True, 0)
        tree_box.pack_end(bar, False, False, 2)

        # middle, below: session goals (written by the user and the AI; the AI's to-do list once work starts)
        self.goal_list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self.goal_entry = Gtk.Entry(placeholder_text="Add a goal…")
        self.goal_entry.connect("activate", self.add_goal)
        goals_box = titled("Session goals", scrolled(self.goal_list), self.goal_entry)

        middle = Gtk.Paned(orientation=Gtk.Orientation.VERTICAL)
        middle.pack1(tree_box, True, False)
        middle.pack2(goals_box, True, False)

        # right: the AI terminal, a real one in the project folder
        self.term = Vte.Terminal()
        self.term.set_scrollback_lines(10000)
        self.term.spawn_async(Vte.PtyFlags.DEFAULT, root, [os.environ.get("SHELL", "/bin/bash")],
                              [f"CINMINAI_PROJECT={root}"], GLib.SpawnFlags.DEFAULT, None, None, -1, None, None, None)
        self.term.connect("child-exited", lambda *a: self.bubble("ai", "The terminal's shell ended. Open the folder "
                                                                       "again to get a new one."))
        right = titled("AI terminal", self.term)

        inner = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        inner.pack1(left, True, False)
        inner.pack2(middle, False, False)
        outer = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        outer.pack1(inner, False, False)
        outer.pack2(right, True, False)
        inner.set_position(330)
        outer.set_position(600)  # the AI terminal gets the rest: the largest pane, as sketched

        # bottom: the typing box and model selection
        self.entry = Gtk.Entry(placeholder_text="Tell the AI what to do…", hexpand=True)
        self.entry.connect("activate", self.send)
        self.model = Gtk.ComboBoxText()
        self.model.append("local", "Local: the best model for this computer")
        self.model.append("claude", "Claude (connect in slice 5)")
        self.model.set_active_id("local")
        bottom = Gtk.Box(spacing=6, margin=6)
        bottom.pack_start(self.entry, True, True, 0)
        bottom.pack_end(self.model, False, False, 0)

        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        page.pack_start(outer, True, True, 0)
        page.pack_end(bottom, False, False, 0)
        self.add(page)
        self.load_tree()
        self.load_goals()

    # --- chat --------------------------------------------------------------------------------------------
    def bubble(self, who: str, text: str) -> None:
        label = Gtk.Label(label=text, wrap=True, xalign=0, selectable=True, max_width_chars=48)
        label.get_style_context().add_class("bubble-user" if who == "user" else "bubble-ai")
        row = Gtk.ListBoxRow(activatable=False)
        row.add(label)
        self.chat.add(row)
        row.show_all()

    def send(self, entry: Gtk.Entry) -> None:
        text = entry.get_text().strip()
        if text:
            self.bubble("user", text)
            entry.set_text("")
            self.bubble("ai", "(The coding agent arrives in the next slice: it will run in the terminal on the right, "
                              "ask there before it changes anything, and log every change.)")

    # --- the working tree and the changelog ------------------------------------------------------------------
    def load_tree(self) -> None:
        self.store.clear()
        parents = {"": None}
        for rel, is_dir, status in tree(self.root):
            parent = parents.get(os.path.dirname(rel))
            it = self.store.append(parent, [os.path.basename(rel) + ("/" if is_dir else ""), status, rel])
            if is_dir:
                parents[rel] = it

    def open_file(self, view, path, column) -> None:
        rel = self.store[path][2]
        full = os.path.join(self.root, rel)
        if os.path.isfile(full):  # the user's own editor (on Mint: Xed), as a file manager would
            Gio.AppInfo.launch_default_for_uri(Gio.File.new_for_path(full).get_uri(), None)

    def toggle_changelog(self, button: Gtk.Button) -> None:
        showing = self.stack.get_visible_child_name() == "changes"
        self.stack.set_visible_child_name("files" if showing else "changes")
        self.tree_title.set_text("Working tree" if showing else "Changelog")
        button.set_label("Changelog" if showing else "Back to the files")

    # --- goals -------------------------------------------------------------------------------------------
    def load_goals(self) -> None:
        for child in self.goal_list.get_children():
            child.destroy()
        for g in self.goals.load():
            box = Gtk.Box(spacing=4)
            tick = Gtk.CheckButton(active=g["done"])
            tick.add(Gtk.Label(label=g["text"] + ("  (AI)" if g.get("by") == "ai" else ""), wrap=True, xalign=0))
            tick.connect("toggled", lambda b, gid=g["id"]: self.goals.set_done(gid, b.get_active()))
            drop = Gtk.Button.new_from_icon_name("window-close-symbolic", Gtk.IconSize.MENU)
            drop.set_relief(Gtk.ReliefStyle.NONE)
            drop.connect("clicked", lambda b, gid=g["id"]: (self.goals.remove(gid), self.load_goals()))
            box.pack_start(tick, True, True, 0)
            box.pack_end(drop, False, False, 0)
            self.goal_list.add(box)
        self.goal_list.show_all()

    def add_goal(self, entry: Gtk.Entry) -> None:
        if entry.get_text().strip():
            self.goals.add(entry.get_text())
            entry.set_text("")
            self.load_goals()


class App(Gtk.Application):
    def __init__(self) -> None:
        super().__init__(application_id="org.cinminai.AICUI", flags=Gio.ApplicationFlags.HANDLES_OPEN
                         | Gio.ApplicationFlags.NON_UNIQUE)

    def do_startup(self) -> None:
        Gtk.Application.do_startup(self)
        css = Gtk.CssProvider()
        css.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), css,
                                                 Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def do_open(self, files, n, hint) -> None:
        for f in files:
            Workspace(self, project_root(f.get_path())).show_all()

    def do_activate(self) -> None:
        dialog = Gtk.FileChooserNative(title="Open a project folder", action=Gtk.FileChooserAction.SELECT_FOLDER)
        if dialog.run() == Gtk.ResponseType.ACCEPT:
            Workspace(self, project_root(dialog.get_filename())).show_all()
        dialog.destroy()


def main() -> int:
    return App().run(sys.argv)
