# SPDX-License-Identifier: GPL-3.0-or-later
"""org.cinminai.Assistant1 on the session bus (SPEC §4, D15).

Compatible with the M0 spike's clients (applet, sidebar: Ask/Cancel/Reset, Token/Done/Error, State,
Model, Awareness); new: the Action signal (every tool the guide uses is shown, SPEC §5.5), the Status
property (model, where it runs, context, and why it's reduced, SPEC §4.2 "say so"), Load and Unload.
The model runs on worker threads; the bus never waits on it (GLib.idle_add hands results back).
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time

from gi.repository import Gio, GLib

from cin_minai.inference.backend import BackendError, Cancelled, InferenceBackend

from .guide import Guide
from .office import LO, OfficeError
from .journal import Interviewer, Journal, JournalError
from . import config, manuscript, selfupdate
from .models import Cancelled as DownloadStopped, ModelStore, backend_cfg, benchmark
from cin_minai.inference import matcher
from cin_minai.inference.llamacpp import LlamaCppBackend
from .projects import CIRCLE, ROOT as PROJECTS, Project
from .writer import Writer

NAME = "org.cinminai.Assistant1"
PATH = "/org/cinminai/Assistant1"
IFACE = "org.cinminai.Assistant1"
UPDATE_CHECK_S = 30            # D59: how often the daemon looks for an installed update
IDLE_BEFORE_RESTART_S = 120    # and how long it must have been idle before restarting into it

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
    <!-- an offered web search (Action "web_search" state "proposal", its result has the id): the user clicked
         Search, with the query they saw (or edited). Nothing is sent before this call (D55, SPEC §7.5) -->
    <method name="Search"><arg type="s" name="offer" direction="in"/><arg type="s" name="query" direction="in"/>
      <arg type="u" name="id" direction="out"/></method>
    <!-- a terminal error no help card covers (Action "bigger_model" state "proposal", its result has the id): the
         person chose to ask the coding model they already have (Ian, 2026-10-04); it's loaded, answers, and is
         unloaded so the guide comes back -->
    <method name="AskBigger"><arg type="s" name="offer" direction="in"/><arg type="u" name="id" direction="out"/></method>
    <!-- "To terminal" on a command card (M3, SPEC §6.4): put the command at the prompt of the terminal the assistant
         last read, as if typed, without Enter. JSON out: ok, error, warnings (root, ssh) -->
    <method name="TerminalSend"><arg type="s" name="text" direction="in"/><arg type="s" name="json" direction="out"/></method>
    <!-- "Put in Writer": a new Writer document in Documents with this text (an answer), opened; never overwrites -->
    <method name="MakeDocument"><arg type="s" name="title" direction="in"/><arg type="s" name="text" direction="in"/>
      <arg type="s" name="json" direction="out"/></method>
    <!-- stop using the shared LibreOffice document (sharing itself is switched in LibreOffice's menu) -->
    <method name="ForgetDocument"/>
    <!-- writing projects (D54): while one is open, Ask goes to the writing partner, which gathers ideas as notes -->
    <method name="ProjectNew"><arg type="s" name="title" direction="in"/><arg type="s" name="json" direction="out"/></method>
    <method name="ProjectOpen"><arg type="s" name="folder" direction="in"/><arg type="s" name="json" direction="out"/></method>
    <method name="ProjectClose"/>
    <method name="ProjectList"><arg type="s" name="json" direction="out"/></method>
    <method name="ProjectInfo"><arg type="s" name="json" direction="out"/></method>
    <!-- the story's shape (D56), as JSON: shape ("chapter" or "chapters"), chapters (2-8), next_chapter; any of them -->
    <method name="ProjectSet"><arg type="s" name="settings" direction="in"/><arg type="s" name="json" direction="out"/></method>
    <!-- a bigger model for a task (D60): what the matcher would offer here (JSON); fetch it (a job: Action
         "download" running with progress, then done with the measured speed); use one or go back to the guide
         (file ""); never ask again about a file -->
    <method name="ModelOffer"><arg type="s" name="task" direction="in"/><arg type="s" name="json" direction="out"/></method>
    <method name="ModelDownload"><arg type="s" name="task" direction="in"/><arg type="u" name="id" direction="out"/></method>
    <method name="ModelUse"><arg type="s" name="task" direction="in"/><arg type="s" name="file" direction="in"/>
      <arg type="s" name="json" direction="out"/></method>
    <method name="ModelDecline"><arg type="s" name="file" direction="in"/></method>
    <!-- the finished story as a manuscript (D58), JSON in: author, contact; out: the .odt and .docx made -->
    <method name="MakeManuscript"><arg type="s" name="options" direction="in"/><arg type="s" name="json" direction="out"/></method>
    <!-- "Write it up" (D57): review the story as it is now before the next chapter: an Action "review" with state
         "proposal" (where the story is on the circle, characters, what's missing, questions) -->
    <method name="WriteUp"><arg type="s" name="wish" direction="in"/><arg type="u" name="id" direction="out"/></method>
    <!-- plan the chapter after the review: an Action "outline" with state "proposal" (its result has the id);
         answers: the writer's answers to the review and what should change (they become notes), as text, or
         JSON with "answers" and "written" (the steps the writer ticked: they decide where the chapter starts) -->
    <method name="PlanChapter"><arg type="s" name="answers" direction="in"/><arg type="u" name="id" direction="out"/></method>
    <!-- write the planned chapter: Action "draft" running (progress) then done (the file); Cancel stops it -->
    <method name="WriteDraft"><arg type="s" name="outline" direction="in"/><arg type="u" name="id" direction="out"/></method>
    <!-- the journal (D55): while it's open, Ask goes to the interviewer; today's conversation stays in memory -->
    <method name="JournalOpen"><arg type="s" name="json" direction="out"/></method>
    <method name="JournalClose"/>
    <method name="JournalEntries"><arg type="s" name="json" direction="out"/></method>
    <method name="JournalSetPin"><arg type="s" name="pin" direction="in"/><arg type="s" name="old" direction="in"/></method>
    <method name="JournalRead"><arg type="s" name="file" direction="in"/><arg type="s" name="pin" direction="in"/>
      <arg type="s" name="json" direction="out"/></method>
    <!-- write today's entry from the conversation: Action "journal" done (the entry) -->
    <method name="JournalWrite"><arg type="b" name="private" direction="in"/><arg type="u" name="id" direction="out"/></method>
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
         document (the shared LibreOffice document the assistant sees; "" = none),
         project (the open writing project's title; "" = none), journal (b: the journal is open) -->
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
        self.project: Project | None = None  # the open writing project (D54)
        # D60: writing may use a bigger model the user chose; the card holds one model at a time
        self.store = ModelStore()
        self.writing_backend: tuple[str, LlamaCppBackend] | None = None
        self.bigger_offers: dict[str, str] = {}  # offered "ask the bigger model", by id: the question with its terminal
        self.offers: dict = {}  # task -> (time, the matcher's plan), so the machine isn't read on every open
        self.writer = Writer(self.writing_chat)
        self.outlines: dict[str, dict] = {}
        self.journal: Journal | None = None  # the open journal (D55)
        self.interviewer = Interviewer(backend.chat)
        # D59: after an update, restart into the new version when idle; reopen the project that was open
        self.watcher = selfupdate.Watcher()
        self.active_at = time.monotonic()
        reopen = selfupdate.take_reopen()
        if reopen:
            try:
                self.project = Project.open(reopen)
                log(f"updated: reopened the writing project {self.project.title!r}")
            except (OSError, ValueError):
                pass
        GLib.timeout_add_seconds(UPDATE_CHECK_S, self.check_update)

    def check_update(self) -> bool:
        """D59: restart into an installed update once it's complete, loads, and the daemon has been idle a while.
        Never while answering or loading, never with the journal open (its conversation lives only in memory)."""
        state = self.watcher.check()
        if state != "ready" or self.busy or self.loading or self.journal is not None:
            return True
        if time.monotonic() - self.active_at < IDLE_BEFORE_RESTART_S or self.watcher.refused == self.watcher.seen:
            return True
        ok, why = selfupdate.loads()
        if not ok:
            self.watcher.refused = self.watcher.seen
            log(f"an update is installed but it doesn't load, so the running version stays: {why}")
            return True
        log("an update is installed: restarting into the new version")
        self.backend.unload()
        selfupdate.restart(self.project.folder if self.project else None)
        return False

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
                "document": GLib.Variant("s", self.document),
                "project": GLib.Variant("s", self.project.title if self.project else ""),
                "journal": GLib.Variant("b", self.journal is not None)}),
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
        self.active_at = time.monotonic()  # someone is using it: no update restart now (D59)
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
        elif method in ("ProjectNew", "ProjectOpen", "ProjectClose", "ProjectList", "ProjectInfo", "ProjectSet",
                        "MakeManuscript"):
            try:
                out = self.project_call(method, *params.unpack())
            except (OSError, ValueError, KeyError) as e:
                inv.return_dbus_error(f"{IFACE}.Error.Project", str(e))
                return
            inv.return_value(None if out is None else GLib.Variant("(s)", (json.dumps(out, ensure_ascii=False),)))
        elif method in ("JournalOpen", "JournalClose", "JournalEntries", "JournalSetPin", "JournalRead"):
            try:
                out = self.journal_call(method, *params.unpack())
            except (JournalError, OSError, ValueError) as e:
                inv.return_dbus_error(f"{IFACE}.Error.Journal", str(e))
                return
            inv.return_value(None if out is None else GLib.Variant("(s)", (json.dumps(out, ensure_ascii=False),)))
        elif method == "MakeDocument":
            title, text = params.unpack()
            try:
                from . import odt
                folder = os.path.join(os.path.expanduser("~"), "Documents")
                title = (title or "").strip()[:80] or "From the assistant"
                path = odt.write(folder, title, title, [text], header="")
            except OSError as e:
                inv.return_dbus_error(f"{IFACE}.Error.Document", f"couldn't save the document: {e.strerror or e}")
                return
            self.open_file(path)
            inv.return_value(GLib.Variant("(s)", (json.dumps({"file": path, "shown": "~/" + os.path.relpath(
                path, os.path.expanduser("~"))}, ensure_ascii=False),)))
        elif method == "Search":
            sid, query = params.unpack()
            if self.busy:
                inv.return_dbus_error(f"{IFACE}.Error.Busy", "still answering; Cancel first")
                return
            self.next_id += 1
            inv.return_value(GLib.Variant("(u)", (self.next_id,)))

            def search(on_text, on_action, sid=sid, query=query):
                out = self.guide.search(sid, query, on_text, on_action, self.cancel)
                return {"tool": "web_search", "sources": out["sources"], "reply_chars": len(out["reply"])}
            self.job(self.next_id, search)
        elif method == "TerminalSend":
            (text,) = params.unpack()
            from . import terminal
            inv.return_value(GLib.Variant("(s)", (json.dumps(terminal.send(text), ensure_ascii=False),)))
        elif method == "AskBigger":
            (oid,) = params.unpack()
            question = self.bigger_offers.pop(oid, None)
            if self.busy or question is None:
                inv.return_dbus_error(f"{IFACE}.Error.Busy" if self.busy else f"{IFACE}.Error.Offer",
                                      "still answering; Cancel first" if self.busy else "that offer has expired")
                return
            self.next_id += 1
            inv.return_value(GLib.Variant("(u)", (self.next_id,)))
            self.job(self.next_id, lambda on_text, on_action, q=question: self.ask_bigger(q, on_text, on_action))
        elif method == "JournalWrite":
            (private,) = params.unpack()
            if self.busy or self.journal is None:
                inv.return_dbus_error(f"{IFACE}.Error.Journal", "still answering" if self.busy else "the journal isn't open")
                return
            self.next_id += 1
            inv.return_value(GLib.Variant("(u)", (self.next_id,)))
            self.journal_write(self.next_id, private)
        elif method in ("WriteUp", "PlanChapter", "WriteDraft"):
            (arg,) = params.unpack()
            if self.busy:
                inv.return_dbus_error(f"{IFACE}.Error.Busy", "still answering; Cancel first")
                return
            if self.project is None:
                inv.return_dbus_error(f"{IFACE}.Error.Project", "no writing project is open")
                return
            if method == "WriteDraft" and arg not in self.outlines:
                inv.return_dbus_error(f"{IFACE}.Error.Project", "that plan is gone; make a new one")
                return
            self.next_id += 1
            inv.return_value(GLib.Variant("(u)", (self.next_id,)))
            {"WriteUp": self.write_up, "PlanChapter": self.plan_chapter, "WriteDraft": self.write_draft}[method](
                self.next_id, arg)
        elif method in ("ModelOffer", "ModelUse", "ModelDecline"):
            args = params.unpack()
            try:
                if method == "ModelOffer":
                    out = self.model_offer(args[0])
                elif method == "ModelDecline":
                    self.store.decline(args[0])
                    out = None
                else:
                    task, file = args
                    plan = self.store.state()["use"].get(task) or (self.offers.get(task) or (0, None))[1]
                    if not file:  # back to the built-in guide
                        self.store.use(task, None)
                        self.release_writing_model()
                    elif not (plan and plan["file"] == file and self.store.has(file)):
                        raise ValueError("that model isn't downloaded")
                    else:
                        self.store.use(task, {**plan, "measured": plan.get("measured")})
                    out = self.model_offer(task)
            except (OSError, ValueError, KeyError) as e:
                inv.return_dbus_error(f"{IFACE}.Error.Model", str(e))
                return
            inv.return_value(None if out is None else GLib.Variant("(s)", (json.dumps(out, ensure_ascii=False),)))
        elif method == "ModelDownload":
            (task,) = params.unpack()
            if self.busy:
                inv.return_dbus_error(f"{IFACE}.Error.Busy", "still answering; Cancel first")
                return
            self.next_id += 1
            inv.return_value(GLib.Variant("(u)", (self.next_id,)))
            self.model_download(self.next_id, task)
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
        if self.journal is not None:  # the journal is open: the interviewer asks about the person (D55)
            journal = self.journal

            def interview(on_text, on_action):
                reply = self.interviewer.reply(journal, text, on_text, self.cancel)
                return {"tool": "journal", "reply_chars": len(reply)}
            self.job(rid, interview)
            return
        if self.project is not None:  # a writing project is open: the writing partner gathers (D54)
            project = self.project

            def gather(on_text, on_action):
                reply = self.writer.reply(project, text, on_text, self.cancel)
                return {"tool": "gather", "reply_chars": len(reply), "notes": sum(len(v) for v in project.notes.values())}
            self.job(rid, gather)
            return

        def answer(on_text, on_action):
            out = self.guide.turn(text, on_text, on_action, self.cancel)
            if out.get("unusual"):  # no help card fits this terminal error: offer the bigger model, if it's here
                plan = self.coding_plan()
                if plan:
                    import uuid
                    oid = uuid.uuid4().hex[:12]
                    self.bigger_offers = {oid: out["unusual"]}  # only the newest offer stands
                    on_action("bigger_model", {}, "proposal", json.dumps({"id": oid, "model": plan["model"]}))
            return {"tool": out["tool"], "args": out["args"], "reply_chars": len(out["reply"]), "timings": out["timings"]}
        self.job(rid, answer)

    # --- a bigger model for an unusual terminal error (M3; Ian, 2026-10-04: only when no card fits, and asked) ---
    BIGGER_SYSTEM = ("You help a person with an error in their Linux Mint terminal. Say what caused it in plain "
                     "words, then the exact command or steps that fix it, each with what it does. Point out anything "
                     "that changes the system or deletes something. You can't run anything yourself. Reply in the "
                     "person's language, briefly, without headings.")

    def coding_plan(self) -> dict | None:
        """The coding model the person already has on this computer (in use for AICUI, or any downloaded one that
        runs here) — never a download."""
        try:
            plan = self.store.in_use("coding")
            if plan:
                return plan
            machine = matcher.read_machine(models_dir=self.store.root)
            for m in matcher.CATALOG["coding"]:
                p = matcher.plan(m, machine, matcher.CONTEXT["coding"]) if self.store.has(m.file) else None
                if p:
                    return {"model": m.name, "file": m.file, **p, "context": matcher.CONTEXT["coding"],
                            "reserve_mib": matcher.margin_mib(machine.cards[0]) if machine.cards else 0}
        except Exception as e:  # finding a model must never take the answer down
            log(f"coding plan: {type(e).__name__}: {e}")
        return None

    def ask_bigger(self, question: str, on_text, on_action) -> dict:
        plan = self.coding_plan()
        if not plan:
            raise BackendError("The bigger model isn't on this computer any more.")
        on_action("bigger_model", {"model": plan["model"]}, "running", "")
        big = LlamaCppBackend(backend_cfg(config.load()["inference"], plan, self.store.path(plan["file"])), log)
        self.backend.unload()  # the card holds one model: the guide comes back with the next question
        try:
            reply, timing = big.chat([{"role": "system", "content": self.BIGGER_SYSTEM},
                                      {"role": "user", "content": question}],
                                     max_tokens=900, on_text=on_text, cancel=self.cancel)
        finally:
            big.unload()
        on_action("bigger_model", {"model": plan["model"]}, "done", json.dumps({"model": plan["model"]}))
        return {"tool": "bigger_model", "model": plan["model"], "reply_chars": len(reply), "timings": [timing]}

    # --- the writing model (D60) ----------------------------------------------------------------------------
    def writing_cfg(self, plan: dict) -> dict:
        return backend_cfg(config.load()["inference"], plan, self.store.path(plan["file"]))

    def writing_chat(self, messages, **kw):
        plan = self.store.in_use("writing")
        if not plan:
            self.release_writing_model()
            return self.backend.chat(messages, **kw)
        if not self.writing_backend or self.writing_backend[0] != plan["file"]:
            self.release_writing_model()
            self.writing_backend = (plan["file"], LlamaCppBackend(self.writing_cfg(plan), log))
        self.backend.unload()  # the card holds one model: the guide comes back after
        return self.writing_backend[1].chat(messages, **kw)

    def release_writing_model(self) -> None:
        if self.writing_backend:
            self.writing_backend[1].unload()
            self.writing_backend = None

    def model_offer(self, task: str) -> dict:
        """What the matcher would offer for a task, if anything: never the built-in guide, never what's in use or
        what the user declined. The machine is read once every 10 minutes at most."""
        when, plan = self.offers.get(task, (0, None))
        if time.monotonic() - when > 600:
            m = matcher.read_machine(models_dir=self.store.root)
            plan = matcher.match(m).get(task)
            self.offers[task] = (time.monotonic(), plan)
        used = self.store.in_use(task)
        offer = None
        if plan and plan.get("source") and (not used or used["file"] != plan["file"])                 and plan["file"] not in self.store.state()["declined"]:
            offer = {k: plan[k] for k in ("model", "file", "why", "mode", "tok_s", "size")}
            offer["downloaded"] = self.store.has(plan["file"])
            rec = self.store.where(plan["file"]) or {}
            if rec.get("where") == "parked" and rec.get("present"):
                offer["parked_on"] = rec.get("drive") or "another drive"  # copied back, not downloaded
            offer["space_ok"] = offer["downloaded"] or plan["size"] + (2 << 30) <= self.store.free_bytes()
        return {"task": task, "offer": offer, "in_use": used and {k: used.get(k) for k in ("model", "file", "measured")}}

    def model_download(self, rid: int, task: str) -> None:
        plan = (self.offers.get(task) or (0, None))[1]

        def fetch(on_text, on_action):
            if not plan or not plan.get("source"):
                on_text("There's no bigger model to fetch for this on this computer.")
                return {"tool": "model", "done": False}
            m = next(x for ms in matcher.CATALOG.values() for x in ms if x.file == plan["file"])
            gb = lambda b: f"{b / 2**30:.1f}"  # noqa: E731
            try:
                self.store.download(m, lambda have, total: on_action(
                    "download", {"file": m.file}, "running",
                    json.dumps({"model": m.name, "have_gb": gb(have), "total_gb": gb(total)})), self.cancel)
            except DownloadStopped:
                on_text("Stopped. What was downloaded is kept, so it can carry on later.")
                return {"tool": "model", "done": False}
            on_action("download", {"file": m.file}, "running", json.dumps({"model": m.name, "testing": True}))
            self.store.use(task, {**plan, "measured": None})
            try:
                speed = benchmark(self.writing_chat)  # loads it the way writing will
            except Exception as e:  # it doesn't run here after all: back to the guide, and say so
                self.store.use(task, None)
                self.release_writing_model()
                on_text(f"{m.name} downloaded and checked, but it didn't start on this computer ({e}). "
                        "Writing stays with the built-in guide.")
                return {"tool": "model", "done": False}
            self.store.use(task, {**plan, "measured": round(speed, 1)})
            on_action("download", {"file": m.file}, "done", json.dumps({"model": m.name, "measured": round(speed, 1)}))
            on_text(f"{m.name} is ready: downloaded, checked against its checksum, and tested here at "
                    f"{speed:.0f} tokens a second (about {speed * 45:.0f} words a minute). Writing uses it from now on; "
                    "you can switch back to the built-in guide in Notes.")
            return {"tool": "model", "done": True, "measured": speed}
        self.job(rid, fetch)

    # --- writing projects (D54) -------------------------------------------------------------------------
    def project_call(self, method: str, *args):
        if method in ("ProjectNew", "ProjectOpen"):
            self.journal = None  # one mode at a time
        if method == "ProjectNew":
            self.project = Project.new(args[0] or "Untitled", "story")
        elif method == "ProjectOpen":
            folder = os.path.realpath(args[0])
            if os.path.dirname(folder) != os.path.realpath(PROJECTS):
                raise ValueError("not a writing project folder")
            self.project = Project.open(folder)
        elif method == "ProjectClose":
            self.release_writing_model()
            self.project = None
            self.outlines.clear()
            self.changed("Status")
            return None
        elif method == "ProjectList":
            return Project.list()
        elif method == "MakeManuscript":  # our code only, no model: quick, so no job (D58)
            if self.project is None:
                raise ValueError("no writing project is open")
            o = json.loads(args[0] or "{}")
            res = manuscript.make(self.project, str(o.get("author", "")), str(o.get("contact", "")))
            self.open_file(res["odt"])
            return res
        elif method == "ProjectSet":
            if self.project is None:
                raise ValueError("no writing project is open")
            s = json.loads(args[0] or "{}")
            self.project.set_shape(s.get("shape"), s.get("chapters"), s.get("next_chapter"))
        if method != "ProjectInfo":
            self.outlines.clear()  # a plan was for the shape and chapter it was made for
            self.changed("Status")
        p = self.project
        if p is None:
            return None
        chapter, steps = p.this_chapter()
        return {"title": p.title, "folder": p.folder, "notes": p.notes, "drafts": p.data["drafts"],
                "messages": len(p.data["messages"]), "circle": p.circle, "shape": p.data["shape"],
                "chapters": p.data["chapters"], "next_chapter": chapter, "next_steps": list(steps),
                "steps": [{"key": k, "name": n, "means": m} for k, n, m, _ in CIRCLE]}

    # --- the journal (D55) -----------------------------------------------------------------------------
    def journal_call(self, method: str, *args):
        if method == "JournalOpen":
            self.project, self.journal = None, Journal()
            self.changed("Status")
            return {"entries": len(self.journal.entries()), "has_pin": self.journal.has_pin}
        if method == "JournalClose":
            self.journal = None  # today's conversation goes with it: it was never on disk
            self.changed("Status")
            return None
        j = self.journal or Journal()
        if method == "JournalEntries":
            return {"entries": j.entries(), "has_pin": j.has_pin}
        if method == "JournalSetPin":
            j.set_pin(args[0], args[1])
            return None
        return j.read_private(args[0], args[1])  # JournalRead

    def journal_write(self, rid: int, private: bool) -> None:
        journal = self.journal

        def write(on_text, on_action):
            import datetime as dt
            when = dt.datetime.now().astimezone()
            try:
                title, text = self.interviewer.entry(journal, when, self.cancel)
                e = journal.write(title, text, when, private)
            except JournalError as err:
                on_text(str(err)[0].upper() + str(err)[1:] + ".")
                return {"tool": "journal_write", "written": False}
            on_action("journal", {"private": private}, "done",
                      json.dumps({k: e[k] for k in ("file", "title", "when", "private", "words")}, ensure_ascii=False))
            journal.messages.clear()  # written: today's conversation is done
            if private:
                on_text(f"Today's entry is written and locked with your PIN ({e['words']} words). Open it from "
                        "Entries with your PIN; I can't read it while it's locked.")
            else:
                self.open_file(e["path"])
                on_text(f"Today's entry, \"{e['title']}\", is written ({e['words']} words) and open in Writer. It's in "
                        "Documents/Journal.")
            return {"tool": "journal_write", "written": True, "private": private}
        self.job(rid, write)

    def write_up(self, rid: int, wish: str) -> None:
        """The review before every chapter (D57)."""
        project = self.project

        def review(on_text, on_action):
            r = self.writer.review(project, self.cancel)
            on_action("review", {}, "proposal", json.dumps(r, ensure_ascii=False))
            what = f"chapter {r['chapter']}" if r.get("chapter") else "the story"
            asks = len(r.get("questions", []))
            on_text(f"Here's where the story stands before {what}. "
                    + (f"I have {asks} question{'s' if asks != 1 else ''} for you. " if asks else "")
                    + "Answer or add anything you like, then click Plan the chapter.")
            return {"tool": "review", "questions": asks, "next_steps": r["next_steps"]}
        self.job(rid, review)

    def plan_chapter(self, rid: int, arg: str) -> None:
        """arg: the writer's answers as text, or JSON {"answers": text, "written": [steps they ticked]} from the
        review card (D57: their ticks decide where the chapter starts)."""
        project = self.project
        try:
            a = json.loads(arg) if arg.lstrip().startswith("{") else None
        except ValueError:
            a = None
        answers, written = (str(a.get("answers", "")), a.get("written")) if isinstance(a, dict) else (arg, None)

        def plan(on_text, on_action):
            if answers.strip():  # the writer's words become notes: they decide (D57)
                project.remember("user", answers.strip())
                self.writer.take_notes(project, answers, self.cancel)
            r = project.data.get("review")
            if r is None or r.get("chapter") != project.this_chapter()[0]:
                r = self.writer.review(project, self.cancel)
            if isinstance(written, list):
                r = self.writer.set_written(project, r, written)
            outline = self.writer.outline(project, answers, self.cancel, review=r)
            oid = f"o{rid}"
            self.outlines = {oid: outline}  # only the newest plan can be written
            on_action("outline", {"answers": answers}, "proposal", json.dumps({**outline, "id": oid}, ensure_ascii=False))
            what = (f"chapter {outline['chapter']} of {outline['of']}, \"{outline['chapter_title']}\", "
                    f"{len(outline['scenes'])} scenes for the steps {', '.join(s.title() for s in outline['steps'])}"
                    if outline.get("chapter") else
                    f"\"{outline['chapter_title']}\": the whole story circle in {len(outline['scenes'])} scenes")
            on_text(f"Here's a plan for {what}. Click Write it to write the draft, or say what should change and "
                    "click Plan again.")
            return {"tool": "outline", "scenes": len(outline["scenes"])}
        self.job(rid, plan)

    def write_draft(self, rid: int, oid: str) -> None:
        project, outline = self.project, self.outlines[oid]

        def write(on_text, on_action):
            cookie = self.inhibit_sleep(True)  # a sleeping screen left the 1080 Ti 6x slower (2026-10-01)
            try:
                res = self.writer.draft(project, outline, lambda n, total, what: on_action(
                    "draft", {"scene": n, "of": total}, "running", json.dumps({"scene": n, "of": total, "title": what},
                                                                              ensure_ascii=False)), self.cancel)
            finally:
                self.inhibit_sleep(False, cookie)
            if res.get("file"):
                rel = os.path.relpath(res["file"], os.path.expanduser("~"))
                on_action("draft", {}, "done", json.dumps({**res, "shown": "~/" + rel}, ensure_ascii=False))
                self.open_file(res["file"])
                pages = -(-res["lines"] // 28)
                on_text(("I stopped as you asked. " if res["stopped"] else "") +
                        f"The rough draft is ready: {res['scenes']} scenes, about {res['words']} words "
                        f"(roughly {pages} pages). It's open in Writer and saved as ~/{rel}.")
            else:
                on_text("Stopped before anything was written.")
            return {"tool": "draft", **{k: res.get(k) for k in ("scenes", "words", "lines", "stopped")}}
        self.job(rid, write)

    def inhibit_sleep(self, on: bool, cookie: int = 0) -> int:
        """Keep the screen awake during a long job (org.gnome.SessionManager, which Cinnamon's session provides)."""
        try:
            bus = Gio.bus_get_sync(Gio.BusType.SESSION)
            if on:
                v = bus.call_sync("org.gnome.SessionManager", "/org/gnome/SessionManager", "org.gnome.SessionManager",
                                  "Inhibit", GLib.Variant("(susu)", ("cinminai-daemon", 0, "Writing a draft", 8)),
                                  None, Gio.DBusCallFlags.NONE, 3000, None)
                return v.unpack()[0]
            if cookie:
                bus.call_sync("org.gnome.SessionManager", "/org/gnome/SessionManager", "org.gnome.SessionManager",
                              "Uninhibit", GLib.Variant("(u)", (cookie,)), None, Gio.DBusCallFlags.NONE, 3000, None)
        except GLib.Error as e:
            log(f"screen-sleep inhibit: {e.message}")
        return 0

    @staticmethod
    def open_file(path: str) -> None:
        try:
            Gio.AppInfo.launch_default_for_uri(Gio.File.new_for_path(path).get_uri(), None)
        except GLib.Error as e:
            log(f"open {path}: {e.message}")

    # --- jobs -------------------------------------------------------------------------------------------
    def job(self, rid: int, fn) -> None:
        """Run fn(on_text, on_action) -> stats on a worker thread: one at a time, cancellable, never silent."""
        self.busy = True
        self.active_at = time.monotonic()
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
                stats = fn(on_text, on_action)
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
        self.active_at = time.monotonic()
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
