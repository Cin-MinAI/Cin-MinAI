# SPDX-License-Identifier: GPL-3.0-or-later
"""AICUI, the AI coding workspace (PLAN D61, SPEC §21) — slice 1: Ian's layout with a real terminal.

    python3 -m cin_minai.aicui [FOLDER-OR-FILE]

Left: chat history. Middle: the working tree (a button at its bottom swaps in the changelog) over the session goals.
Right, the largest: the AI terminal — a real terminal (VTE) in the project folder. Bottom: the typing box and model
selection. The agent (cinminai-code), the changelog's shadow git store and the cloud providers come in later slices.
"""

from __future__ import annotations

import json
import os
import threading
import sys
import time

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("Vte", "2.91")
from gi.repository import Gdk, Gio, GLib, Gtk, Pango, Vte  # noqa: E402

from .changelog import Changelog  # noqa: E402
from .project import (Goals, build_env, can_be_project, declare_env, entry_point, env_header, env_state,  # noqa: E402
                      known_projects, make_project, orphan_envs, project_root, token_of, tree, venv_python)

TITLE = "AICUI"
CSS = b"""
.pane-title { font-weight: bold; padding: 4px 6px; }
.bubble-user { background: alpha(@theme_selected_bg_color, 0.25); border-radius: 6px; padding: 6px; }
.bubble-ai { background: alpha(@theme_fg_color, 0.06); border-radius: 6px; padding: 6px; }
.waiting { background: rgba(255, 170, 0, 0.30); border-radius: 6px; padding: 2px 6px; font-weight: bold; }
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
        self.root, self.goals, self.log = root, Goals(root), Changelog(root)
        self.set_default_size(1700, 960)

        # left: chat history (thinking will stream in and collapse into bubbles, slice 4)
        self.chat = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self.bubble("ai", f"Working in {root}. The coding agent runs in the terminal on the right and asks there before "
                          "it changes anything. Tell it about the project here or there; goals go in the middle.")
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
        self.changes = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)  # newest first, each with its diff + undo
        self.stack.add_named(scrolled(self.changes), "changes")
        self.swap = Gtk.Button(label="Changelog")
        self.swap.connect("clicked", self.toggle_changelog)
        refresh = Gtk.Button.new_from_icon_name("view-refresh-symbolic", Gtk.IconSize.BUTTON)
        refresh.set_tooltip_text("Read the folder again")
        refresh.connect("clicked", lambda b: self.load_tree())
        run = Gtk.Button(label="Run")
        run.set_tooltip_text("Start the project as you would: run.sh, else main.py (with its own Python), "
                             "else index.html in the browser")
        run.connect("clicked", lambda b: self.run_project())
        bar = Gtk.Box(spacing=4)
        bar.pack_start(run, False, False, 0)
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
        env = [f"CINMINAI_PROJECT={root}"] + ([f"PYTHONPATH={os.environ['PYTHONPATH']}"]
                                              if os.environ.get("PYTHONPATH") else [])
        # the agent starts in the terminal; leaving it (Ctrl+D) leaves a normal shell in the project folder
        shell = os.environ.get("SHELL", "/bin/bash")
        self.term.spawn_async(Vte.PtyFlags.DEFAULT, root, [shell, "-c", f"{self.agent_command()}; exec {shell}"],
                              env, GLib.SpawnFlags.DEFAULT, None, None, -1, None, None, None)
        self.term.connect("child-exited", lambda *a: self.bubble("ai", "The terminal's shell ended. Open the folder "
                                                                       "again to get a new one."))
        self.events_at = os.path.getsize(self.events_path()) if os.path.exists(self.events_path()) else 0
        GLib.timeout_add(400, self.follow_events)
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
        # permissions are the user's (SPEC §21): ask (default), auto for this session, none (behind a warning); admin
        self.perms = Gtk.ComboBoxText()
        for key, label in (("ask", "Ask before changes"), ("auto", "Auto (this session)"),
                           ("none", "No permissions (not advised)")):
            self.perms.append(key, label)
        self.perms.set_active_id("ask")
        self.perms_id = self.perms.connect("changed", self.restart_agent)
        self.admin = Gtk.CheckButton(label="Admin")
        self.admin.set_tooltip_text("Let the AI ask for administrator commands")
        self.admin_id = self.admin.connect("toggled", self.restart_agent)
        # while the AI works: what it's doing, for how long, and Stop (Ctrl+C in its terminal)
        self.spinner = Gtk.Spinner()
        self.busy_label = Gtk.Label(xalign=0, ellipsize=Pango.EllipsizeMode.END, width_chars=46, max_width_chars=60)
        stop = Gtk.Button(label="Stop")
        stop.set_tooltip_text("Stop the AI now (Ctrl+C in its terminal). What it has done stays, with undo.")
        stop.connect("clicked", lambda b: self.term.feed_child(b"\x03"))
        self.busy_box = Gtk.Box(spacing=6, no_show_all=True)
        for w in (self.spinner, self.busy_label, stop):
            w.show()
            self.busy_box.pack_start(w, False, False, 0)
        # when the AI waits for a yes/no: plainly visible, answerable here (2026-10-03: a step waited three minutes on
        # a question in the terminal Ian hadn't seen — "I was just the hold up in a system of my design")
        self.ask_box = Gtk.Box(spacing=4, no_show_all=True)
        for label, key, tip in (("Allow", b"y\n", "Yes, this once"),
                                ("Always", b"a\n", "Yes, and don't ask again this session (Auto)"),
                                ("No", b"n\n", "Don't do this")):
            b = Gtk.Button(label=label)
            b.set_tooltip_text(tip)
            b.connect("clicked", lambda btn, k=key: self.term.feed_child(k))
            b.show()
            self.ask_box.pack_start(b, False, False, 0)
        self.busy_box.pack_start(self.ask_box, False, False, 0)
        self.busy, self.busy_since, self.notified = None, 0.0, 0.0
        GLib.timeout_add_seconds(1, self.show_busy)
        bottom = Gtk.Box(spacing=6, margin=6)
        bottom.pack_start(self.busy_box, False, False, 0)
        bottom.pack_start(self.entry, True, True, 0)
        bottom.pack_end(self.model, False, False, 0)
        bottom.pack_end(self.admin, False, False, 0)
        bottom.pack_end(self.perms, False, False, 0)

        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        page.pack_start(outer, True, True, 0)
        page.pack_end(bottom, False, False, 0)
        self.add(page)
        self.load_tree()
        self.load_goals()
        self.load_changes()
        self.building = False
        GLib.idle_add(self.offer_project)

    # --- the agent in the terminal -----------------------------------------------------------------------
    def agent_command(self) -> str:
        mode = self.perms.get_active_id() if hasattr(self, "perms") else "ask"
        flags = {"auto": " --auto", "none": " --no-permissions"}.get(mode, "")
        if hasattr(self, "admin") and self.admin.get_active():
            flags += " --admin"
        # -P: the project folder is the agent's working directory, and plain -m would put it first on the import path —
        # a project that contains a cin_minai/ folder (Ian's diag-test, 2026-10-04) replaced the agent's own code
        return f"{sys.executable} -P -m cin_minai.aicui.agent{flags} {GLib.shell_quote(self.root)}"

    def restart_agent(self, widget) -> None:
        """A new permission choice: written where the agent reads it before every question, so it holds at once, even
        mid-task (it used to type Ctrl+D and a new command into the terminal, which a busy agent never saw)."""
        if widget is self.perms and self.perms.get_active_id() == "none":
            d = Gtk.MessageDialog(transient_for=self, modal=True, message_type=Gtk.MessageType.WARNING,
                                  buttons=Gtk.ButtonsType.OK_CANCEL, text="Work without any permissions?")
            d.format_secondary_text("The AI will change files and run commands without asking, outside the sandbox. "
                                    "This is strongly advised against until you have tested how stable this model is "
                                    "on this kind of work. Don't risk anything you aren't willing to lose.")
            ok = d.run() == Gtk.ResponseType.OK
            d.destroy()
            if not ok:
                with self.perms.handler_block(self.perms_id):
                    self.perms.set_active_id("ask")
                return
        path = os.path.join(self.root, ".cinminai", "session.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path + ".tmp", "w", encoding="utf-8") as f:
            json.dump({"mode": self.perms.get_active_id(), "admin": self.admin.get_active()}, f)
        os.replace(path + ".tmp", path)

    def events_path(self) -> str:
        return os.path.join(self.root, ".cinminai", "events.jsonl")

    def follow_events(self) -> bool:
        """The agent's event lines → the chat history, the changelog, the goals (and the tree after a change)."""
        try:
            with open(self.events_path(), encoding="utf-8") as f:
                f.seek(self.events_at)
                lines = f.readlines()
                self.events_at = f.tell()
        except OSError:
            return True
        for line in lines:
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if e["kind"] == "user":
                self.bubble("user", e.get("text", ""))
            elif e["kind"] == "thinking":
                self.thought(e.get("text", ""))
            elif e["kind"] == "answer":
                self.bubble("ai", e.get("text", ""))
            elif e["kind"] == "note":  # a step that went wrong (cut off, not valid), told to the model as it was
                self.thought(e.get("text", ""), "Note")
            elif e["kind"] == "handover":  # every 60 steps: where the work stands; the AI goes on
                self.bubble("ai", e.get("text", ""))
            elif e["kind"] == "handoff":  # the organizer (the guide) and the coder passing work (SPEC 22.5)
                who = {"coder": "Organizer → coder", "fetch": "Organizer → fetch", "person": "Organizer → you",
                       "organizer": "Coder → organizer"}
                self.thought(e.get("text", ""), who.get(e.get("to", ""), "Organizer"))
            elif e["kind"] == "env_request":  # the AI declared a package the work needs: the person decides
                self.offer_build()
            elif e["kind"] == "check":  # a problem found in a file the AI just changed
                self.thought(f"{e.get('file', '')}: {e.get('problem', '')}", "Check")
            elif e["kind"] == "busy":
                if self.busy is None or e.get("step") != self.busy.get("step"):
                    self.busy_since = e.get("t", time.time())
                self.busy = e
                self.show_busy()
            elif e["kind"] == "idle":
                self.busy = None
                self.show_busy()
            elif e["kind"] == "session":  # the agent's own change ("always" in the terminal): the choices follow
                with self.perms.handler_block(self.perms_id):
                    self.perms.set_active_id(e.get("mode", "ask"))
                with self.admin.handler_block(self.admin_id):
                    self.admin.set_active(bool(e.get("admin")))
            elif e["kind"] == "change":
                self.load_changes()
                self.load_tree()
            elif e["kind"] == "goals":
                self.load_goals()
        return True

    def show_busy(self) -> bool:
        """The indicator: step, what the AI is doing, tokens so far, and how long this step has taken."""
        e = self.busy
        if e is None or (e.get("doing") != "waiting for your answer in the terminal"
                         and time.time() - self.busy_since > 3600):  # an agent that died without saying idle
            self.spinner.stop()
            self.busy_box.hide()
            return True
        secs = int(time.time() - self.busy_since)
        waiting = e.get("doing") == "waiting for your answer in the terminal"
        style = self.busy_box.get_style_context()
        if waiting:
            self.busy_label.set_text(f"Waiting for you: allow {e.get('asking') or 'this'}? · {secs // 60}:{secs % 60:02}")
            style.add_class("waiting")
            self.ask_box.show()
            self.spinner.stop()
            if self.notified != self.busy_since and not self.is_active():  # once per question, if not in front
                self.notified = self.busy_since
                n = Gio.Notification.new("AICUI is waiting for you")
                n.set_body(f"Allow {e.get('asking') or 'the next step'}?")
                self.get_application().send_notification("aicui-waiting", n)
        else:
            parts = [f"Step {e['step']}" if e.get("step") else "", e.get("doing", "working"),
                     f"{e['tokens']} tokens" if e.get("tokens") else "", f"{secs // 60}:{secs % 60:02}"]
            self.busy_label.set_text(" · ".join(p for p in parts if p))
            style.remove_class("waiting")
            self.ask_box.hide()
            self.spinner.start()
        self.busy_box.show()
        return True

    # --- chat --------------------------------------------------------------------------------------------
    def thought(self, text: str, title: str = "Thought") -> None:
        """The model's thinking: a bubble that stays collapsed, to open when you want to see how it got there."""
        exp = Gtk.Expander(label=title)
        exp.add(Gtk.Label(label=text, wrap=True, xalign=0, selectable=True, max_width_chars=48))
        exp.get_style_context().add_class("bubble-ai")
        row = Gtk.ListBoxRow(activatable=False)
        row.add(exp)
        self.chat.add(row)
        row.show_all()
    def bubble(self, who: str, text: str) -> None:
        label = Gtk.Label(label=text, wrap=True, xalign=0, selectable=True, max_width_chars=48)
        label.get_style_context().add_class("bubble-user" if who == "user" else "bubble-ai")
        row = Gtk.ListBoxRow(activatable=False)
        row.add(label)
        self.chat.add(row)
        row.show_all()

    # --- running the project the way the user would ----------------------------------------------------------
    def run_project(self) -> None:
        """Run, outside the agent's sandbox, on the real screen: the agent's own checks run headless with its
        project venv, and a newcomer's double-click doesn't (2026-10-03: "No module named pygame", then a game that
        opened and closed at once — and nothing on screen said why)."""
        entry = entry_point(self.root)
        if not entry:
            self.bubble("ai", "Nothing to run yet: no run.sh, main.py or index.html in this project.")
            return
        full = os.path.join(self.root, entry)
        if entry.endswith(".html"):
            Gio.AppInfo.launch_default_for_uri(Gio.File.new_for_path(full).get_uri(), None)
            self.bubble("ai", f"Opened {entry} in your browser.")
            return
        argv = ["bash", full] if entry.endswith(".sh") else [venv_python(self.root), full]
        launcher = Gio.SubprocessLauncher.new(Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_MERGE)
        launcher.set_cwd(self.root)
        venv = os.path.dirname(os.path.dirname(venv_python(self.root))) if venv_python(self.root) != "python3" else ""
        if venv:  # the project's environment on, as in the AI's own commands: run.sh's `python3` is the project's
            launcher.setenv("VIRTUAL_ENV", venv, True)  # (2026-10-08: run.sh said `python3 main.py` — the system's,
            launcher.setenv("PATH", os.path.join(venv, "bin") + os.pathsep + os.environ.get("PATH", ""), True)  # no pygame)
        try:
            proc = launcher.spawnv(argv)
        except GLib.Error as e:
            self.bubble("ai", f"Couldn't start {entry}: {e.message}")
            return
        self.bubble("ai", f"Running {entry}…")
        proc.communicate_utf8_async(None, None, self.ran, entry)

    def ran(self, proc: Gio.Subprocess, result, entry: str) -> None:
        try:
            _, out, _ = proc.communicate_utf8_finish(result)
        except GLib.Error as e:
            out = e.message
        out = (out or "").strip()
        if proc.get_if_exited() and proc.get_exit_status() == 0:
            self.bubble("ai", f"{entry} finished normally.")
            return
        code = proc.get_exit_status() if proc.get_if_exited() else f"signal {proc.get_term_sig()}"
        tail = "\n".join(out.splitlines()[-25:]) or "(no output)"
        report = f"When I ran {entry} it stopped with an error (exit {code}):\n{tail}"
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        label = Gtk.Label(label=report, wrap=True, xalign=0, selectable=True, max_width_chars=48)
        box.pack_start(label, False, False, 0)
        send = Gtk.Button(label="Send to the AI")
        send.set_tooltip_text("Hand this error to the AI in its terminal")
        send.connect("clicked", lambda b: self.hand_over(report, b))
        box.pack_start(send, False, False, 0)
        box.get_style_context().add_class("bubble-ai")
        row = Gtk.ListBoxRow(activatable=False)
        row.add(box)
        self.chat.add(row)
        row.show_all()

    def hand_over(self, report: str, button: Gtk.Button) -> None:
        if self.busy is not None:  # typed into a busy agent, it would land in a permission answer
            self.bubble("ai", "The AI is still working: press Send again when it has finished (or Stop it first).")
            return
        button.set_sensitive(False)
        self.term.feed_child((" ".join(report.splitlines()) + "\n").encode())

    def send(self, entry: Gtk.Entry) -> None:
        text = entry.get_text().strip()
        if text:  # typed into the terminal, where the agent reads it (the chat shows it from the agent's events)
            entry.set_text("")
            self.term.feed_child((" ".join(text.splitlines()) + "\n").encode())

    def load_changes(self) -> None:
        for child in self.changes.get_children():
            child.destroy()
        entries = list(reversed(self.log.entries()))
        if not entries:
            self.changes.add(Gtk.Label(label="No AI changes yet. Every file the AI changes is listed here, with what "
                                             "changed and an undo.", wrap=True, xalign=0, margin=8))
        for e in entries:
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, margin=4)
            head = Gtk.Box(spacing=4)
            head.pack_start(Gtk.Label(label=f"{e['file']}  +{e['added']} −{e['removed']}"
                                            + ("  (undone)" if e.get("undone") else ""), xalign=0), True, True, 0)
            if not e.get("undone"):
                undo = Gtk.Button(label="Undo")
                undo.connect("clicked", lambda b, eid=e["id"]: (self.log.undo(eid), self.load_changes(),
                                                               self.load_tree()))
                head.pack_end(undo, False, False, 0)
            box.pack_start(head, False, False, 0)
            meta = Gtk.Label(label=f"{e['time'][11:16]} · {e.get('model', '')}" + (f" · {e['goal']}" if e.get("goal") else ""),
                             xalign=0, wrap=True)
            meta.get_style_context().add_class("dim-label")
            box.pack_start(meta, False, False, 0)
            diff = Gtk.Expander(label="What changed")
            view = Gtk.TextView(editable=False, monospace=True, wrap_mode=Gtk.WrapMode.NONE)
            view.get_buffer().set_text(self.log.diff(e)[:20000])
            diff.add(view)
            box.pack_start(diff, False, False, 0)
            self.changes.add(box)
        self.changes.show_all()

    # --- the working tree and the changelog ------------------------------------------------------------------
    def load_tree(self) -> None:
        self.store.clear()
        parents = {"": None}
        for rel, is_dir, status in tree(self.root):
            parent = parents.get(os.path.dirname(rel))
            it = self.store.append(parent, [os.path.basename(rel) + ("/" if is_dir else ""), status, rel])
            if is_dir:
                parents[rel] = it
        state = env_state(self.root)  # the environment: one line, never its thousands of files
        if state != "none":
            h = env_header(self.root) or {}
            what = {"built": f"Python {h.get('python', '')} · " + (", ".join(h.get("packages", [])) or "no packages"),
                    "declared": "not built yet" + (f" — asked for: {', '.join(h['wanted'])}" if h.get("wanted")
                                                   else ": waiting to know what the project needs"),
                    "external": "made outside AICUI"}[state]
            self.store.append(None, [f".venv — Python environment: {what}", "", ".venv"])

    def offer_project(self) -> bool:
        """A folder AICUI works in becomes a project only on the person's yes, and only below their home folder; a
        project's environment is offered, and made only as a header until the work shows what it needs (PLAN §1b
        closure 4: Ian's design)."""
        if not token_of(self.root):
            if not can_be_project(self.root):
                self.bubble("ai", "This is your home folder or a folder outside it: AICUI can work here, but it won't "
                                  "set up a project or a Python environment in it.")
                return False
            if not self.yes_no("Make this folder an AICUI project?",
                               "AICUI keeps its goals and changelog here, and the project can get its own Python "
                               "environment — nothing else changes."):
                return False
            make_project(self.root)
        if env_state(self.root) == "none" and self.yes_no(
                "Create a Python environment for this project?",
                "Only its header is made now (.venv). Nothing is installed until the AI says what the project needs "
                "and you agree; then AICUI builds it outside the project and links it here."):
            declare_env(self.root)
            self.load_tree()
        gone = orphan_envs(known_projects())
        if gone and self.yes_no(f"Remove the Python environments of {len(gone)} project(s) that are gone?",
                                "Their folders aren't there any more; the environments only take space:\n"
                                + "\n".join(gone[:8])):
            import shutil
            for path in gone:
                shutil.rmtree(path, ignore_errors=True)
        return False

    def yes_no(self, question: str, detail: str) -> bool:
        d = Gtk.MessageDialog(transient_for=self, modal=True, message_type=Gtk.MessageType.QUESTION,
                              buttons=Gtk.ButtonsType.YES_NO, text=question)
        d.format_secondary_text(detail)
        answer = d.run() == Gtk.ResponseType.YES
        d.destroy()
        return answer

    def offer_build(self) -> None:
        """The AI asked for packages: say which and why, and build only on the person's yes (D86: from PyPI)."""
        header = env_header(self.root) or {}
        wanted = header.get("wanted", [])
        if self.building or not wanted:
            return
        why = header.get("why", {})
        lines = "\n".join(f"• {p}" + (f" — {why[p]}" if why.get(p) else "") for p in wanted)
        if not self.yes_no(f"Install {', '.join(wanted)} for this project?",
                           f"The AI asks for:\n{lines}\n\nThey're downloaded from PyPI (the Python package index) "
                           "into this project's own environment, outside its folder — nothing else on the computer "
                           "changes."):
            self.bubble("ai", "Not installed. The AI can go on without " + ", ".join(wanted) + ", or ask again.")
            return
        self.building = True
        self.bubble("ai", "Building the project's environment…")

        def work() -> None:
            try:
                h = build_env(self.root, say=lambda m: GLib.idle_add(self.thought, m, "Environment"))
                done = f"Environment ready: Python {h['python']} · " + (", ".join(h["packages"]) or "no packages")
            except (OSError, RuntimeError, ValueError) as e:
                done = f"The environment couldn't be built: {e}"
            GLib.idle_add(lambda: (self.bubble("ai", done), self.load_tree(), setattr(self, "building", False))
                          and False)
        threading.Thread(target=work, daemon=True).start()

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

    def do_activate_or_open(self) -> None:
        """With AICUI up, the assistant's sidebar steps aside (Ian: not cluttered by default); Super+A brings it back."""
        try:
            bus = Gio.bus_get_sync(Gio.BusType.SESSION)
            owner = bus.call_sync("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus",
                                  "NameHasOwner", GLib.Variant("(s)", ("org.cinminai.Sidebar",)), None,
                                  Gio.DBusCallFlags.NONE, 2000, None).unpack()[0]
            if owner:  # only if it's running: don't start a hidden sidebar
                Gio.Subprocess.new(["cinminai-sidebar", "--hide"], Gio.SubprocessFlags.NONE)
        except GLib.Error:
            pass

    def do_open(self, files, n, hint) -> None:
        self.do_activate_or_open()
        for f in files:
            Workspace(self, project_root(f.get_path())).show_all()

    def do_activate(self) -> None:
        self.do_activate_or_open()
        dialog = Gtk.FileChooserNative(title="Open a project folder", action=Gtk.FileChooserAction.SELECT_FOLDER)
        if dialog.run() == Gtk.ResponseType.ACCEPT:
            Workspace(self, project_root(dialog.get_filename())).show_all()
        dialog.destroy()


def main() -> int:
    return App().run(sys.argv)
