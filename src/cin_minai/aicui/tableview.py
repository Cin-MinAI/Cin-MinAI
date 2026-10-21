# SPDX-License-Identifier: GPL-3.0-or-later
"""The Team Table window (Ian, 2026-10-21): a conference table, seen from above. Two seats to start and a + to add
more; click a seat to choose who sits there (a local model, a cloud model, or an outside agent) and to give it the
crown; click the paper in the middle for the session goals, each assigned to a seat. "Sit down" seats the team: the
AI restarts as the table (conference.py)."""

from __future__ import annotations

import math
import os
import shutil
import socket

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Gdk, GLib, Gtk, Pango, PangoCairo  # noqa: E402

from . import conference  # noqa: E402

WOOD, WOOD_EDGE, PAPER, SEAT, EMPTY, CROWN = ((0.45, 0.29, 0.16), (0.30, 0.18, 0.09), (0.98, 0.97, 0.92),
                                             (0.22, 0.36, 0.55), (0.55, 0.55, 0.55), (0.95, 0.75, 0.15))
KIND_WORD = {"local": "local", "cloud": "cloud", "outside": "outside", "": "empty — choose"}


class TableWindow(Gtk.Window):
    def __init__(self, workspace) -> None:
        super().__init__(title="Team Table", transient_for=workspace)
        self.ws, self.root = workspace, workspace.root
        self.setup = conference.load(self.root)
        self.set_default_size(1100, 760)
        self.spots: list[tuple[str, float, float, float, object]] = []  # (what, x, y, r, which) to hit-test clicks
        self.area = Gtk.DrawingArea(hexpand=True, vexpand=True)
        self.area.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.POINTER_MOTION_MASK)
        self.area.connect("draw", self.draw)
        self.area.connect("button-press-event", self.click)
        self.area.connect("motion-notify-event", self.hover)
        self.status = Gtk.Label(xalign=0, wrap=True, max_width_chars=110)
        sit = Gtk.Button(label="Sit down")
        sit.get_style_context().add_class("suggested-action")
        sit.set_tooltip_text("Save the table and start the AI as this team (it restarts in the terminal)")
        sit.connect("clicked", lambda b: self.sit_down())
        close = Gtk.Button(label="Close")
        close.connect("clicked", lambda b: (conference.save(self.root, self.setup), self.destroy()))
        bar = Gtk.Box(spacing=8, margin=10)
        bar.pack_start(self.status, True, True, 0)
        bar.pack_end(sit, False, False, 0)
        bar.pack_end(close, False, False, 0)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.pack_start(self.area, True, True, 0)
        box.pack_end(bar, False, False, 0)
        self.add(box)
        self.refresh()

    # --- the picture ------------------------------------------------------------------------------------------------
    def geometry(self) -> tuple[float, float, float, float]:
        w, h = self.area.get_allocated_width(), self.area.get_allocated_height()
        return w / 2, h / 2, w * 0.28, h * 0.22  # the table's centre and its half-axes

    def seat_spots(self) -> list[tuple[float, float]]:
        cx, cy, a, b = self.geometry()
        n = len(self.setup["seats"]) + 1  # and the + seat
        return [(cx + (a + 80) * math.cos(-math.pi / 2 + 2 * math.pi * i / n),
                 cy + (b + 78) * math.sin(-math.pi / 2 + 2 * math.pi * i / n)) for i in range(n)]

    def text(self, cr, x: float, y: float, s: str, size: int = 11, bold: bool = False, rgb=(0.1, 0.1, 0.1),
             width: int = 0) -> None:
        layout = PangoCairo.create_layout(cr)
        desc = Pango.FontDescription.from_string(f"Sans {'Bold ' if bold else ''}{size}")
        layout.set_font_description(desc)
        if width:
            layout.set_width(width * Pango.SCALE)
            layout.set_wrap(Pango.WrapMode.WORD_CHAR)
            layout.set_alignment(Pango.Alignment.CENTER)
        layout.set_text(s, -1)
        tw, th = layout.get_pixel_size()
        cr.set_source_rgb(*rgb)
        cr.move_to(x - (width or tw) / 2, y - th / 2)
        PangoCairo.show_layout(cr, layout)

    def draw(self, area, cr) -> bool:
        cx, cy, a, b = self.geometry()
        cr.set_source_rgb(0.93, 0.93, 0.95)
        cr.paint()
        self.spots = []
        # the table
        cr.new_path()
        cr.save()
        cr.translate(cx, cy)
        cr.scale(a, b)
        cr.arc(0, 0, 1, 0, 2 * math.pi)
        cr.restore()
        cr.set_source_rgb(*WOOD)
        cr.fill_preserve()
        cr.set_line_width(6)
        cr.set_source_rgb(*WOOD_EDGE)
        cr.stroke()
        # the paper: the session goals
        goals = self.ws.goals.load()
        pw, ph = min(320, a * 1.1), min(180, b * 1.3)
        cr.rectangle(cx - pw / 2, cy - ph / 2, pw, ph)
        cr.set_source_rgb(*PAPER)
        cr.fill_preserve()
        cr.set_source_rgb(0.7, 0.7, 0.65)
        cr.set_line_width(1)
        cr.stroke()
        open_goals = [g for g in goals if not g["done"]]
        self.text(cr, cx, cy - ph / 2 + 20, "The session goals", 13, True)
        lines = [f"{g['id']}. {g['text'][:44]}" + (f"  → {g['who']}" if g.get("who") not in (None, "", "senior",
                                                                                         "junior") else "")
                 for g in open_goals[:4]]
        self.text(cr, cx, cy + 6, "\n".join(lines) or "none yet — click to add", 9, width=int(pw - 20))
        self.text(cr, cx, cy + ph / 2 - 14, f"{len(open_goals)} open, {len(goals) - len(open_goals)} done — click",
                  8, rgb=(0.4, 0.4, 0.4))
        self.spots.append(("paper", cx, cy, max(pw, ph) / 2, None))
        # the seats, and the + seat
        fits = self.fits
        for i, ((x, y), seat) in enumerate(zip(self.seat_spots(), self.setup["seats"] + [None])):
            r = 46
            cr.new_path()  # no line from the last thing drawn to this seat
            cr.arc(x, y, r, 0, 2 * math.pi)
            if seat is None:
                cr.set_source_rgb(0.85, 0.85, 0.85)
                cr.fill_preserve()
                cr.set_source_rgb(*EMPTY)
                cr.set_dash([5, 4])
                cr.set_line_width(2)
                cr.stroke()
                cr.set_dash([])
                self.text(cr, x, y - 6, "+", 26, True, (0.35, 0.35, 0.35))
                self.text(cr, x, y + 22, "add a seat", 8, rgb=(0.35, 0.35, 0.35))
                self.spots.append(("add", x, y, r, None))
                continue
            kind = seat.get("kind", "")
            bad = kind == "local" and seat["name"] in fits and fits[seat["name"]][1] is None
            cr.set_source_rgb(*((0.75, 0.25, 0.2) if bad else SEAT if kind else EMPTY))
            cr.fill()
            self.text(cr, x, y - 10, seat["name"], 10, True, (1, 1, 1), width=2 * r - 8)
            self.text(cr, x, y + 12, KIND_WORD.get(kind, kind), 8, rgb=(0.92, 0.92, 0.92))
            if seat.get("lead"):  # the crown on its shoulder, clear of its label
                self.text(cr, x + r * 0.8, y - r * 0.8, "♛", 22, True, CROWN)
            under = conference.describe(seat).split("(", 1)[-1].rstrip(")") if kind else ""
            if kind == "local" and seat["name"] in fits:
                under = fits[seat["name"]][0]
            # its label on the side away from the table, so it never sits on the wood
            self.text(cr, x, y + (r + 16 if y >= cy else -r - 16), under[:60], 8, rgb=(0.25, 0.25, 0.25), width=190)
            self.spots.append(("seat", x, y, r, seat))
        return False

    def hit(self, x: float, y: float):
        for what, sx, sy, r, which in reversed(self.spots):
            if (x - sx) ** 2 + (y - sy) ** 2 <= r * r:
                return what, which
        return None, None

    def hover(self, area, ev) -> bool:
        what, _ = self.hit(ev.x, ev.y)
        win = area.get_window()
        if win:
            win.set_cursor(Gdk.Cursor.new_from_name(area.get_display(), "pointer" if what else "default"))
        return False

    def click(self, area, ev) -> bool:
        what, which = self.hit(ev.x, ev.y)
        if what == "seat":
            self.seat_dialog(which)
        elif what == "add":
            n = len(self.setup["seats"]) + 1
            names = {s["name"] for s in self.setup["seats"]}
            while f"Seat {n}" in names:
                n += 1
            seat = {"name": f"Seat {n}", "kind": ""}
            self.setup["seats"].append(seat)
            self.refresh()
            self.seat_dialog(seat)
        elif what == "paper":
            self.goals_dialog()
        return True

    def refresh(self) -> None:
        try:
            self.fits = conference.fit(self.setup)
        except Exception:
            self.fits = {}
        bad = conference.problems(self.setup)
        bad += [f"{n}: doesn't fit beside the seats before it" for n, (_, p, _m) in self.fits.items() if p is None]
        self.status.set_text("To sit down: " + "; ".join(bad) if bad else
                             f"Ready: {len(self.setup['seats'])} seats, {conference.lead_of(self.setup)['name']} leads.")
        self.area.queue_draw()

    # --- a seat ----------------------------------------------------------------------------------------------------
    def local_models(self) -> list[str]:
        from cin_minai.daemon.models import ModelStore
        return [f for f, e in ModelStore().models().items() if e.get("present") and "mmproj" not in f.lower()]

    def seat_dialog(self, seat: dict) -> None:
        from cin_minai.inference import cloud as cloud_mod
        d = Gtk.Dialog(title=f"Seat: {seat['name']}", transient_for=self, modal=True)
        d.add_button("Remove the seat", 2)
        d.add_button("Cancel", Gtk.ResponseType.CANCEL)
        d.add_button("OK", Gtk.ResponseType.OK)
        box = d.get_content_area()
        box.set_spacing(8)
        box.set_border_width(16)
        name = Gtk.Entry(text=seat["name"], max_length=24)
        crown = Gtk.CheckButton(label="♛ Wears the crown: the lead (plans, and accepts or rejects the others' work)",
                                active=bool(seat.get("lead")))
        local = Gtk.RadioButton(label="A local model (on this computer, free)")
        cloud = Gtk.RadioButton(label="A cloud model (your key; paid by the token)", group=local)
        outside = Gtk.RadioButton(label="An outside agent (Claude Code or Codex, joining over SSH)", group=local)
        lpick, cpick, opick = Gtk.ComboBoxText(), Gtk.ComboBoxText(), Gtk.ComboBoxText()
        for f in self.local_models():
            lpick.append(f, os.path.splitext(f)[0])
        for m in self.ws.cloud_models():
            cpick.append(m, cloud_mod.label(m))
        for agent in conference.OUTSIDE_AGENTS:
            opick.append(agent, agent)
        if not self.ws.connected():
            cpick.append("", "no cloud key yet: add one in Cloud models")
        here = Gtk.RadioButton(label="On this computer")
        away = Gtk.RadioButton(label="From another computer (its SSH public key, one line from its .pub file):",
                               group=here)
        key = Gtk.Entry(placeholder_text="ssh-ed25519 AAAA… you@other-computer")
        connect = Gtk.Label(xalign=0, selectable=True, wrap=True, max_width_chars=90)
        connect.get_style_context().add_class("monospace")
        for w in (Gtk.Label(label="Name", xalign=0), name, crown, local, lpick, cloud, cpick, outside, opick, here, away,
                  key, connect):
            box.pack_start(w, False, False, 0)
        kind = seat.get("kind") or "local"
        {"local": local, "cloud": cloud, "outside": outside}[kind].set_active(True)
        for pick, value in ((lpick, seat.get("model")), (cpick, seat.get("model")), (opick, seat.get("agent"))):
            if value:
                pick.set_active_id(value)
            if pick.get_active() < 0:
                pick.set_active(0)
        (away if seat.get("where") == "away" else here).set_active(True)

        def where() -> str:
            user = os.environ.get("USER", "you")
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(("192.0.2.1", 9))  # no packet is sent: this only picks the address other computers reach
                ip = s.getsockname()[0]
                s.close()
            except OSError:
                ip = socket.gethostname()
            return f"{user}@{ip}"

        def update(*_) -> None:
            for w, on in ((lpick, local), (cpick, cloud), (opick, outside)):
                w.set_sensitive(on.get_active())
            for w in (here, away, key, connect):
                w.set_visible(outside.get_active())
            key.set_sensitive(away.get_active())
            if outside.get_active():
                lines = conference.connect_lines({"name": name.get_text() or "seat"}, self.root,
                                                 where() if away.get_active() else "")
                agent = opick.get_active_id() or "Claude Code"
                sshd = shutil.which("sshd") or os.path.exists("/usr/sbin/sshd")
                connect.set_text(f"Give {agent} this, once:\n{lines[agent]}"
                                 + ("" if not away.get_active() or sshd else
                                    "\n\nThis computer has no SSH server yet: in a terminal, sudo apt install "
                                    "openssh-server")
                                 + ("\n\nOK adds that key to ~/.ssh/authorized_keys, locked to this seat: it can "
                                    "start only this seat's table server — no shell, no files outside the project. "
                                    "Removing the seat removes it." if away.get_active() else ""))
        for w in (local, cloud, outside, here, away):
            w.connect("toggled", update)
        opick.connect("changed", update)
        name.connect("changed", update)
        d.show_all()
        update()
        while True:
            r = d.run()
            if r == 2:
                if len(self.setup["seats"]) > 2:
                    conference.remove_key(self.root, seat["name"])
                    self.setup["seats"].remove(seat)
                    if not conference.lead_of(self.setup):
                        self.setup["seats"][0]["lead"] = True
                    break
                self.ws.bubble("app", "A table keeps two seats at least: change this one instead.")
                continue
            if r != Gtk.ResponseType.OK:
                break
            new = {"name": name.get_text().strip() or seat["name"], "lead": crown.get_active()}
            if local.get_active():
                new.update(kind="local", model=lpick.get_active_id() or "")
            elif cloud.get_active():
                m = cpick.get_active_id() or ""
                new.update(kind="cloud", model=m, provider=cloud_mod.provider_of(m) if m else "")
            else:
                new.update(kind="outside", agent=opick.get_active_id() or "Claude Code",
                           where="away" if away.get_active() else "here")
                if away.get_active() and key.get_text().strip():
                    try:
                        conference.add_key(self.root, new["name"], key.get_text())
                    except (ValueError, OSError) as e:
                        err = Gtk.MessageDialog(transient_for=d, modal=True, message_type=Gtk.MessageType.ERROR,
                                                buttons=Gtk.ButtonsType.OK, text="The key wasn't added")
                        err.format_secondary_text(str(e))
                        err.run()
                        err.destroy()
                        continue
            if new["name"] != seat["name"] or new.get("where") != "away":  # renamed, or no longer an outside
                conference.remove_key(self.root, seat["name"])  # agent from away: its old key goes (2026-10-21: a
                #   seat changed from outside to cloud kept its key, and the agent sat down in the wrong seat)
            if new["lead"]:
                for s in self.setup["seats"]:
                    s.pop("lead", None)
            elif seat.get("lead"):
                new["lead"] = True  # the crown moves by giving it to another seat
            seat.clear()
            seat.update({k: v for k, v in new.items() if v not in (False,)})
            break
        d.destroy()
        conference.save(self.root, self.setup)
        self.refresh()

    # --- the paper -----------------------------------------------------------------------------------------------------
    def goals_dialog(self) -> None:
        d = Gtk.Dialog(title="The session goals", transient_for=self, modal=True)
        d.add_button("Close", Gtk.ResponseType.CLOSE)
        d.set_default_size(720, 520)
        box = d.get_content_area()
        box.set_spacing(6)
        box.set_border_width(14)
        lead = (conference.lead_of(self.setup) or {}).get("name", "the lead")
        names = [s["name"] for s in self.setup["seats"]]
        grid = Gtk.Grid(column_spacing=10, row_spacing=6)
        scroll = Gtk.ScrolledWindow(min_content_height=360)
        scroll.add(grid)
        box.pack_start(Gtk.Label(label="Each goal goes to the seat it's assigned to (the lead keeps the rest):",
                                 xalign=0), False, False, 0)
        box.pack_start(scroll, True, True, 0)

        first = next((s["name"] for s in self.setup["seats"] if not s.get("lead") and s.get("kind") != "outside"), lead)

        def who_of(g: dict) -> str:
            w = g.get("who") or ""
            return w if w in names else first if w == "junior" else lead  # a plan's "junior" goal: the first seat

        def picker(current: str) -> Gtk.ComboBoxText:
            c = Gtk.ComboBoxText()
            for n in names:
                c.append(n, n + (" ♛" if n == lead else ""))
            c.set_active_id(current)
            return c

        def fill() -> None:
            for child in grid.get_children():
                grid.remove(child)
            for row, g in enumerate(self.ws.goals.load()):
                label = Gtk.Label(label=f"{g['id']}. {'✔ ' if g['done'] else ''}{g['text']}", xalign=0, wrap=True,
                                  max_width_chars=60)
                grid.attach(label, 0, row, 1, 1)
                c = picker(who_of(g))
                c.set_sensitive(not g["done"] and not g.get("queued"))
                c.connect("changed", lambda w, gid=g["id"]: self.assign(gid, w.get_active_id(), lead))
                grid.attach(c, 1, row, 1, 1)
            grid.show_all()
        add = Gtk.Box(spacing=6)
        text = Gtk.Entry(placeholder_text="A new goal…", hexpand=True)
        to = picker(lead)
        button = Gtk.Button(label="Add")

        def added(*_) -> None:
            t = text.get_text().strip()
            if not t:
                return
            g = self.ws.goals.add(t, by="user")
            self.assign(g["id"], to.get_active_id(), lead)
            text.set_text("")
            fill()
            self.ws.load_goals()
        button.connect("clicked", added)
        text.connect("activate", added)
        for w in (text, to, button):
            add.pack_start(w, w is text, w is text, 0)
        box.pack_start(add, False, False, 0)
        fill()
        d.show_all()
        d.run()
        d.destroy()
        self.ws.load_goals()
        self.area.queue_draw()

    def assign(self, gid: int, seat: str, lead: str) -> None:
        self.ws.goals.update(gid, who="senior" if seat == lead else seat)

    # --- sitting down ------------------------------------------------------------------------------------------------
    def sit_down(self) -> None:
        conference.save(self.root, self.setup)
        self.refresh()
        bad = conference.problems(self.setup)
        if bad:
            self.ws.bubble("app", "The table can't sit down yet: " + "; ".join(bad) + ".")
            return
        self.ws.set_team("table")
        self.ws.bubble("app", f"The Team Table sits down: {conference.lead_of(self.setup)['name']} leads, with "
                              f"{conference.describe_all(self.setup)}.")
        GLib.idle_add(self.destroy)
