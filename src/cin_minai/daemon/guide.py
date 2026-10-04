# SPDX-License-Identifier: GPL-3.0-or-later
"""The guide's conversation: one user message -> one reply, the way the guide was trained and measured.

1. A schema-constrained call (D6): {"tool": ..., "args": {...}} with the system prompt v2 and the tool
   list from guide.json (generated from training/eval/guide/run_eval.py, never retyped).
2. `answer` / `decline`: the text is the reply. It is streamed out while the JSON is still being written.
3. A tool: it runs (read-only), its result goes back as "Result of <tool>:\n<result>\n\n<style>", and the
   reply is written as plain text, streamed.
The history keeps the raw tool calls and results, as in the training sessions. It is trimmed from the
oldest turn, in steps, so the model's prompt cache stays valid most of the time (on the processor every
re-read token costs time, PLAN D27).
"""

from __future__ import annotations

import json
import re
import threading
from typing import Callable

from cin_minai.inference.backend import BackendError, InferenceBackend

from .helpcards import HelpIndex
from .office import Office, OfficeError
from .tools import Tools

TEXT_START = re.compile(r'^\s*\{\s*"tool"\s*:\s*"(answer|decline)"\s*,\s*"args"\s*:\s*\{\s*"text"\s*:\s*"')
ESCAPES = {'"': '"', "\\": "\\", "/": "/", "b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t"}


class TextStream:
    """Feeds on the tool call as it is generated; hands out the answer/decline text as soon as it comes."""

    def __init__(self, emit: Callable[[str], None]) -> None:
        self.emit, self.buf, self.pos, self.done = emit, "", None, False

    def feed(self, piece: str) -> None:
        self.buf += piece
        if self.done:
            return
        if self.pos is None:
            m = TEXT_START.match(self.buf)
            if not m:
                return
            self.pos = m.end()
        out, i = [], self.pos
        while i < len(self.buf):
            c = self.buf[i]
            if c == '"':
                self.done = True
                break
            if c == "\\":
                if i + 1 >= len(self.buf):
                    break  # wait for the rest of the escape
                e = self.buf[i + 1]
                if e == "u":
                    if i + 6 > len(self.buf):
                        break
                    code = int(self.buf[i + 2:i + 6], 16)
                    if 0xD800 <= code < 0xDC00:  # a surrogate pair: wait for the second half
                        if i + 12 > len(self.buf):
                            break
                        low = int(self.buf[i + 8:i + 12], 16)
                        out.append(chr(0x10000 + ((code - 0xD800) << 10) + (low - 0xDC00)))
                        i += 12
                        continue
                    out.append(chr(code))
                    i += 6
                    continue
                out.append(ESCAPES.get(e, e))
                i += 2
                continue
            out.append(c)
            i += 1
        self.pos = i
        if out:
            self.emit("".join(out))


PROPOSED = ("I've prepared this change: {summary}. It's shown below — nothing changes until you click Apply, "
            "and one Ctrl+Z in LibreOffice undoes it.")
SEARCH_OFFER = ("I can look that up on the web. Below is exactly what would be sent; nothing leaves this computer "
                "until you click Search.")
SEARCH_OFFLINE = ("I'd need to look that up on the web, and this computer isn't online right now. Connect to the "
                  "internet, then click Search below.")


class Guide:
    def __init__(self, backend: InferenceBackend, data: dict, help_index: HelpIndex, tools: Tools, cfg: dict,
                 office: Office | None = None) -> None:
        self.backend, self.data, self.help, self.tools, self.cfg = backend, data, help_index, tools, cfg
        self.office = office
        self.history: list[dict] = []
        self.searches: dict[str, dict] = {}  # offered web searches, by id (D55): nothing is sent before Search

    def search(self, sid: str, query: str, on_text: Callable[[str], None], on_action, cancel: threading.Event) -> dict:
        """The user clicked Search (SPEC §7.5): fetch, then answer from the pages only, with their numbers."""
        from . import websearch
        offer = self.searches.pop(sid, None)
        if offer is None:
            raise BackendError("That search was already done or dismissed.")
        query = (query or offer["query"]).strip()[:200]
        on_action("web_search", {"query": query}, "running", "")
        try:
            found = websearch.gather(query, self.tools.lang)
        except websearch.SearchError as e:
            self.searches[sid] = offer  # can be tried again (e.g. once online)
            raise BackendError(f"The search didn't work: {e}.")
        on_action("web_search", {"query": query}, "done",
                  json.dumps({"query": query, "sources": [{k: s[k] for k in ("n", "title", "url")} for s in found["sources"]]},
                             ensure_ascii=False))
        prompt = websearch.answer_prompt(offer["question"], found)
        reply, timings = self.backend.chat([{"role": "user", "content": prompt}], max_tokens=500, on_text=on_text,
                                           cancel=cancel)
        # the conversation goes on from here as if the guide had answered (follow-up questions work)
        self.history += [{"role": "user", "content": offer["question"]}, {"role": "assistant", "content": reply}]
        return {"reply": reply, "tool": "web_search", "args": {"query": query}, "sources": len(found["sources"]),
                "timings": [timings]}

    def document(self) -> tuple[dict | None, str, dict]:
        """(the shared document or None, the system prompt, the schema): with a document shared, the prompt
        and tools the guide was trained on for it (D20; guide.json "documents")."""
        doc = None
        if self.office is not None and "documents" in self.data:
            try:
                doc = self.office.current()
            except OfficeError:
                doc = None
        if doc is None or doc.get("type") not in self.data.get("documents", {}):
            return None, self.data["system"], self.data["schema"]
        d = self.data["documents"][doc["type"]]
        try:
            ctx = self.office.context(doc)
        except OfficeError:
            return None, self.data["system"], self.data["schema"]
        return doc, d["system"].replace(d["context_slot"], json.dumps(ctx, ensure_ascii=False)), d["schema"]

    def reset(self) -> None:
        self.history.clear()

    def budget(self) -> int:
        on_cpu = self.backend.status().build == "cpu"
        return int(self.cfg["cpu_history_chars"] if on_cpu else self.cfg["history_chars"])

    def trim(self) -> None:
        """Drop whole turns from the start until the history is under half the budget (then the
        prompt cache holds for a while)."""
        size = lambda: sum(len(m["content"]) for m in self.history)
        if size() <= self.budget():
            return
        while self.history and size() > self.budget() // 2:
            del self.history[0]
            while self.history and not (self.history[0]["role"] == "user"
                                        and not self.history[0]["content"].startswith("Result of ")):
                del self.history[0]  # a turn starts with the user's own message

    def run_tool(self, tool: str, args: dict, doc: dict | None = None, request: str = "") -> str:
        if doc is not None and tool in self.data["documents"][doc["type"]]["read"]:
            return json.dumps(self.office.read(doc, tool, args), ensure_ascii=False, default=str)
        if tool == "lookup_help":
            _, card = self.help.lookup(str(args.get("query", "")), self.tools.lang)
            return card
        if tool == "inspect_system":
            return json.dumps(self.tools.inspect(str(args.get("topic", "overview"))), ensure_ascii=False)
        if tool == "open_app":
            return json.dumps(self.tools.open_app(str(args.get("app", ""))), ensure_ascii=False)
        if tool == "make_spreadsheet":
            from .sheets import wants_by_month
            args = {**args, "total": wants_by_month(request, str(args.get("total", "none")))}
            return json.dumps(self.tools.make_spreadsheet(args), ensure_ascii=False)
        if tool == "request_install":
            return json.dumps(self.tools.request_install(str(args.get("package", ""))), ensure_ascii=False)
        return json.dumps({"error": f"unknown tool {tool}"})

    def turn(self, text: str, on_text: Callable[[str], None], on_action: Callable[[str, dict, str, str], None],
             cancel: threading.Event) -> dict:
        """Answer one message. Returns {"reply", "tool", "args", "timings": [...]}; raises BackendError."""
        self.trim()
        user = {"role": "user", "content": text}
        # a message about the terminal gets the shared terminal's last commands in front of it (M3, §11.5; D77)
        from . import terminal
        commands = terminal.latest()
        if terminal.about_terminal(text, commands):
            user["content"] = terminal.context(commands) + "\n\n" + text
            on_action("terminal", {}, "done", json.dumps({"commands": [c.get("cmd") for c in commands[-terminal.MAX_COMMANDS:]
                                                                         if c.get("cmd")]}, ensure_ascii=False))
        doc, system, schema = self.document()
        messages = [{"role": "system", "content": system}] + self.history + [user]
        edits = set(self.data["documents"][doc["type"]]["edit"]) if doc else set()
        timings = []
        for attempt in range(2):  # a call LibreOffice refuses goes back to the model once (spike, eval)
            stream = TextStream(on_text)
            raw, t1 = self.backend.chat(messages, schema=schema, max_tokens=700, on_text=stream.feed, cancel=cancel)
            timings.append(t1)
            try:
                call = json.loads(raw)
                tool, args = call["tool"], call.get("args", {})
            except (ValueError, KeyError, TypeError):
                raise BackendError("The model's answer didn't come out right. Please ask again.")
            if tool in ("answer", "decline"):
                reply = str(args.get("text", ""))
                if stream.pos is None:  # the stream didn't recognise the layout: send the text whole
                    on_text(reply)
                self.history += [user, {"role": "assistant", "content": raw}]
                return {"reply": reply, "tool": tool, "args": args, "timings": timings}
            if tool == "web_search":
                # nothing is sent here: the sidebar shows the query; the user clicks Search (D55, §7.5)
                import uuid
                sid = uuid.uuid4().hex[:12]
                query = str(args.get("query", "")).strip()[:200] or text[:200]
                self.searches = {sid: {"query": query, "question": text}}  # only the newest offer stands
                online = self.tools.online()
                on_action(tool, {"query": query}, "proposal", json.dumps({"id": sid, "query": query, "online": online,
                                                                          "provider": "DuckDuckGo"}, ensure_ascii=False))
                reply = SEARCH_OFFER if online else SEARCH_OFFLINE
                on_text(reply)
                self.history += [user, {"role": "assistant", "content": raw}]
                return {"reply": reply, "tool": tool, "args": {"query": query}, "proposal": sid, "timings": timings}
            try:
                if tool in edits:
                    # an edit is never made here: it becomes a preview the user applies or discards (§7.8)
                    pv = self.office.preview(doc, tool, args)
                    on_action(tool, args, "proposal", json.dumps(pv, ensure_ascii=False, default=str))
                    reply = PROPOSED.format(summary=pv.get("summary", "an edit").rstrip("."))
                    on_text(reply)
                    self.history += [user, {"role": "assistant", "content": raw}]
                    return {"reply": reply, "tool": tool, "args": args, "proposal": pv["id"], "timings": timings}
                on_action(tool, args, "running", "")
                result = self.run_tool(tool, args, doc, text)
            except OfficeError as e:
                if attempt:
                    raise BackendError(f"LibreOffice didn't accept that: {e}")
                messages = messages + [{"role": "assistant", "content": raw},
                                       {"role": "user", "content": f"That call failed: {e}. Send a corrected call."}]
                continue
            break
        on_action(tool, args, "done", result)
        followup = {"role": "user", "content": self.data["result_format"].format(
            tool=tool, result=result, style=self.data["style"])}
        reply, t2 = self.backend.chat(messages + [{"role": "assistant", "content": raw}, followup],
                                      max_tokens=600, on_text=on_text, cancel=cancel)
        timings.append(t2)
        self.history += [user, {"role": "assistant", "content": raw}, followup, {"role": "assistant", "content": reply}]
        return {"reply": reply, "tool": tool, "args": args, "result": result, "timings": timings}
