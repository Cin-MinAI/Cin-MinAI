# SPDX-License-Identifier: GPL-3.0-or-later
"""The daemon's side of LibreOffice (PLAN D20, SPEC §7.6–7.8): documents the user shared, the guide's
document context, and edits that are previewed, approved, and undone in one step.

The extension (cinminai-libreoffice, org.cinminai.LibreOffice1) runs the toolkit inside LibreOffice; this
module only calls it. Sharing is switched in LibreOffice's own Assistant menu: there's no call here (or
anywhere) that shares a document, so no program can grant itself access.

The context is built in exactly the format the guide was trained and measured with (training/eval/guide/
run_eval.py system_prompt, prompt v2): the shipped guide edits a shared spreadsheet without retraining.
"""

from __future__ import annotations

import json
import re
import uuid

LO = ("org.cinminai.LibreOffice1", "/org/cinminai/LibreOffice1", "org.cinminai.LibreOffice1")
DATA_CELLS = 200  # a sheet this small goes into the context whole (as in training)
SLIDES = 10


class OfficeError(Exception):
    """A tool call LibreOffice refused (the model gets the message and one more try)."""


def compact(v):
    """412.5 stays, 388.0 -> 388: numbers as the training data shows them."""
    if isinstance(v, float) and v.is_integer():
        return int(v)
    if isinstance(v, list):
        return [compact(x) for x in v]
    return v


def short_selection(addr: str) -> str:
    """"Sheet1.B8:B8" -> "B8", "Sheet1.A1:C3" -> "A1:C3" (training shows the cell, not the sheet)."""
    a = addr.split(".", 1)[-1]
    first, _, last = a.partition(":")
    return first if not last or last == first else a


def next_empty_row(used_range: str) -> int:
    m = re.search(r"(\d+)$", used_range)
    return int(m.group(1)) + 1 if m else 1


class Office:
    """`call(method, *args) -> str` is the D-Bus call (injected: tests use a fake)."""

    def __init__(self, call) -> None:
        self.call = call
        self.proposals: dict[str, dict] = {}
        self.forgotten: set[str] = set()  # shared in LibreOffice, but the user told the assistant to stop

    def _json(self, method: str, *args: str):
        try:
            return json.loads(self.call(method, *args))
        except OfficeError:
            raise
        except Exception as e:
            raise OfficeError(str(e)) from e

    # --- which document --------------------------------------------------------------------------------
    def documents(self) -> list[dict]:
        try:
            return self._json("ListDocuments")
        except OfficeError:
            return []  # LibreOffice isn't running, or the extension isn't there: no document

    def current(self) -> dict | None:
        """The shared document the guide works on: the last one in LibreOffice's list that's shared."""
        shared = [d for d in self.documents() if d.get("shared") and d["id"] not in self.forgotten]
        return shared[-1] if shared else None

    def forget(self, doc_id: str) -> None:
        self.forgotten.add(doc_id)

    # --- tools ------------------------------------------------------------------------------------------
    def read(self, doc: dict, tool: str, args: dict) -> dict:
        return self._json("Read", doc["id"], tool, json.dumps(args, ensure_ascii=False))

    def preview(self, doc: dict, tool: str, args: dict) -> dict:
        pv = self._json("Preview", doc["id"], tool, json.dumps(args, ensure_ascii=False))
        pid = uuid.uuid4().hex[:12]
        self.proposals[pid] = {"doc": doc, "tool": tool, "args": args, "snapshot": pv["snapshot"]}
        return {**pv, "id": pid, "document": doc.get("title", ""), "kind": doc.get("type", "")}

    def decide(self, pid: str, apply: bool) -> dict:
        p = self.proposals.pop(pid, None)
        if p is None:
            raise OfficeError("this change was already applied or discarded")
        if not apply:
            return {"applied": False}
        return self._json("Apply", p["doc"]["id"], p["tool"], json.dumps(p["args"], ensure_ascii=False), p["snapshot"])

    # --- the context the guide sees ------------------------------------------------------------------
    def context(self, doc: dict) -> dict:
        kind = doc["type"]
        info = self.read(doc, "doc_info", {})
        if kind == "calc":
            ctx = {"document": {"type": "calc", "sheets": info.get("sheets", []), "active": info.get("active_sheet", ""),
                                "selection": short_selection(info.get("selection", ""))}}
            used = self.read(doc, "used_range", {})["range"]
            ctx["used_range"] = used
            data = self.read(doc, "read_range", {"range": used})
            if sum(len(r) for r in data["values"]) <= DATA_CELLS:
                ctx["data"] = {"range": used, "values": compact(data["values"])}
                ctx["next_empty_row"] = next_empty_row(used)
            return ctx
        if kind == "writer":
            ctx = {"document": {"type": "writer", "title": info.get("title", ""), "paragraphs": info.get("paragraphs", 0)}}
            try:
                ctx["selection"] = self.read(doc, "get_selection", {})["text"]
            except OfficeError:
                ctx["selection"] = ""
            ctx["outline"] = self.read(doc, "outline", {})["headings"]
            return ctx
        n = int(info.get("slides", 0))
        return {"document": {"type": "impress", "slides": n},
                "slides": [self.read(doc, "slide_text", {"slide": i}) for i in range(1, min(n, SLIDES) + 1)]}


def dbus_call():
    """The real call: org.cinminai.LibreOffice1 on the session bus (never auto-started: LibreOffice is the
    user's program, the assistant doesn't start it)."""
    from gi.repository import Gio, GLib

    def call(method: str, *args: str) -> str:
        try:
            v = Gio.bus_get_sync(Gio.BusType.SESSION).call_sync(
                *LO, method, GLib.Variant("(" + "s" * len(args) + ")", args), None,
                Gio.DBusCallFlags.NO_AUTO_START, 15000, None)
        except GLib.Error as e:
            Gio.DBusError.strip_remote_error(e)
            # "GDBus.Error:org.cinminai.LibreOffice1.Error.Tool: the document changed..." -> the plain part
            raise OfficeError(e.message.split(".Error.", 1)[-1].split(": ", 1)[-1] if ".Error." in e.message else e.message)
        return v.unpack()[0]

    return call
