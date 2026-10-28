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

from cin_minai.inference.backend import BackendError, Cancelled, InferenceBackend

from .helpcards import HelpIndex
from .office import Office, OfficeError
from . import facts, intent, library, offline, websearch
from .repetition import LoopDetected, ReplyGuard
from .config import live_session
from .tools import Tools

TEXT_START = re.compile(r'^\s*\{\s*"tool"\s*:\s*"(answer|decline)"\s*,\s*"args"\s*:\s*\{\s*"text"\s*:\s*"')
ESCAPES = {'"': '"', "\\": "\\", "/": "/", "b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t"}


TERMINAL_MIN_SCORE = 8.0
# D84-19 (2026-10-24): on the live USB the guide is told so in its prompt; asked "will my files be saved?" it had
# found the card on removing a USB stick and said yes
LIVE_SYSTEM = ("\nThis computer is running from the USB stick (the live session), not installed: files saved now are "
               "kept in memory and lost at shutdown. Install Cin-MinAI to keep them, or copy them to another USB "
               "drive first.\n")


class TextStream:
    """Feeds on the tool call as it is generated; hands out the answer/decline text as soon as it comes."""

    def __init__(self, emit: Callable[[str], None]) -> None:
        self.emit, self.buf, self.pos, self.done, self.tool = emit, "", None, False, None

    def feed(self, piece: str) -> None:
        self.buf += piece
        if self.done:
            return
        if self.pos is None:
            m = TEXT_START.match(self.buf)
            if not m:
                return
            self.tool = m.group(1)
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
# the search offer's words are in say.py, in six languages
# Nothing on this computer has it (Ian, 2026-10-23: "This is what I have in memory about x, would you like to search the
# web for more information?"): the daemon says where the answer comes from and offers more; the model writes the middle.
NOT_HERE = {"wikipedia": "This computer's Wikipedia has no article on that.",
            "lookup_help": "Nothing in the built-in help or this computer's Wikipedia matches this."}
NOT_IN_PAGES = "NOT_IN_PAGES"  # websearch.ANSWER: what the model writes when the pages don't answer the question
STANDALONE = ("Rewrite the user's last message as a question that someone who hasn't seen the conversation would "
              "understand: name the people, places and things it refers to, and keep what it asks about. Keep its "
              "language and its meaning. If it already stands alone, copy it unchanged. Write only the question.\n"
              "Example. The conversation: User: Who wrote Hamlet? Assistant: William Shakespeare. The last message: "
              "When did he die? Rewritten: When did William Shakespeare die?\n\n"
              "The conversation so far:\n{talk}\n\nThe user's last message: {message}")
FROM_MEMORY = ("Now write your reply to the user as plain text (not JSON), in the language of their message: what you "
               "know about it, in a few plain sentences, without saying where it comes from (that is said for you). "
               "Numbered steps only for something the person does, one action each, with enough detail to follow.")


class Gate:
    """Streams a reply from pages but never the marker NOT_IN_PAGES: a tail that could be its start is held back, and
    when it comes (the 4B often writes "The pages don't answer the question. NOT_IN_PAGES"), what was shown is
    cleared (the sidebar's Replace, as the reply guard uses) and the guide answers from memory instead."""

    def __init__(self, emit: Callable[[str], None]) -> None:
        self.emit, self.text, self.shown, self.marked = emit, "", 0, False

    def feed(self, piece: str) -> None:
        if self.marked:
            return
        self.text += piece
        if NOT_IN_PAGES in self.text:
            self.marked = True
            replace = getattr(self.emit, "replace", None)
            if self.shown and replace is not None:
                replace("")
            return
        if not self.text.strip():
            return
        safe = len(self.text)
        for k in range(min(len(NOT_IN_PAGES) - 1, len(self.text)), 0, -1):
            if self.text.endswith(NOT_IN_PAGES[:k]):
                safe -= k
                break
        if safe > self.shown and self.text[:safe].strip():
            self.emit(self.text[self.shown:safe])
            self.shown = safe

    __call__ = feed

    def replace(self, text: str) -> None:  # the reply guard's repair of what was shown (repetition.py)
        replace = getattr(self.emit, "replace", None)
        if not self.marked and replace is not None:
            self.text, self.shown = text, len(text)
            replace(text)

    def finish(self) -> None:
        if not self.marked and self.shown < len(self.text):
            self.emit(self.text[self.shown:])
            self.shown = len(self.text)


class Guide:
    def __init__(self, backend: InferenceBackend, data: dict, help_index: HelpIndex, tools: Tools, cfg: dict,
                 office: Office | None = None, notebook=None) -> None:
        self.backend, self.data, self.help, self.tools, self.cfg = backend, data, help_index, tools, cfg
        self.office = office
        self.notebook = notebook  # D40: the transcript, the notes and recall (notebook.py); None in tests
        self.caught_up = False  # an earlier session's last turns folded into the notes, at the first turn
        self.asked = ""  # this turn's own words, for the transcript
        self.history: list[dict] = []
        self.searches: dict[str, dict] = {}  # offered web searches, by id (D55): nothing is sent before Search
        self.terminal_question: str | None = None  # this turn's message with the terminal in front of it (M3)
        self.terminal_hint = ""  # the failed command and its error, added to this turn's help lookups
        self.last_card: str | None = ""  # the last lookup's card id; None = nothing in the built-in help fit

    def reply_guard(self, on_text: Callable[[str], None]) -> ReplyGuard:
        names = (row.get(self.tools.lang) or row.get("en", "") for row in self.help.names.values())
        return ReplyGuard(on_text, names)

    def search(self, sid: str, query: str, on_text: Callable[[str], None], on_action, cancel: threading.Event) -> dict:
        """The user clicked Search (SPEC §7.5): fetch, then answer from the pages only, with their numbers."""
        from . import websearch
        offer = self.searches.pop(sid, None)
        if offer is None:
            raise BackendError("That search was already done or dismissed.")
        query = (query or offer["query"]).strip()[:200]
        tool = offer.get("tool", "web_search")
        on_action(tool, {"query": query}, "running", "")
        try:
            if tool == "wikipedia":  # D68: the article from Wikipedia itself, once the person agreed
                found = library.read_online(query, self.tools.lang)
            else:
                found = websearch.gather(query, self.tools.lang)
        except library.NoArticle:  # Wikipedia, then the web (Ian, 2026-10-23): another place, so asked again
            on_action(tool, {"query": query}, "done", json.dumps({"query": query, "sources": []}))
            from .say import say
            reply = say(self.tools.lang, "wiki_none")
            on_text(reply)
            sid = self.offer("web_search", query, offer["question"], on_action)
            return {"reply": reply, "tool": tool, "args": {"query": query}, "sources": 0, "proposal": sid,
                    "timings": []}
        except (websearch.SearchError, library.LibraryError) as e:
            self.searches[sid] = offer  # can be tried again (e.g. once online)
            raise BackendError(f"The search didn't work: {e}.")
        turn = None
        if offer.get("said") and self.history and self.history[-1]["content"] == offer["said"]:
            del self.history[-2:]  # the offer's own turn, nothing since: the answer takes its place
            turn = [{"role": "user", "content": offer["question"]}, {"role": "assistant", "content": offer["call"]}]
        return self.answer_from(found, offer["question"], tool, query, on_text, on_action, cancel,
                                then="web_search" if tool == "wikipedia" else None, turn=turn,
                                asked=offer.get("asked"))

    def answer_from(self, found: dict, question: str, tool: str, query: str, on_text, on_action,
                    cancel: threading.Event, then: str | None = None, turn: list | None = None,
                    recorded: tuple[str, str] | None = None, asked: str | None = None) -> dict:
        """The reply from fetched material only (web pages, Wikipedia articles), each point with its number. When they
        don't answer the question (Ian, 2026-10-23): what the guide knows, said as that, and `then` offered (Wikipedia
        itself after this computer's, the web after Wikipedia; nothing after the web).

        turn: the person's message and the call, for the from-memory reply (default: a call made from the query);
        recorded: (tool, words before the result) when the call was another tool's; asked: the question as it stands
        alone (standalone), what the pages are checked against. The history keeps the talk alone (remember)."""
        on_action(tool, {"query": query}, "done",
                  json.dumps({"query": query, "shelf": found.get("shelf", ""),
                              "sources": [{k: s[k] for k in ("n", "title", "url", "pictures") if k in s}
                                          for s in found["sources"]]},
                             ensure_ascii=False))
        prompt = websearch.answer_prompt(asked or question, found)
        gate = Gate(on_text)
        guard = self.reply_guard(gate)
        try:
            reply, timings = self.backend.chat([{"role": "user", "content": prompt}], max_tokens=500,
                                               on_text=guard.feed, cancel=cancel)
            guard.finish()
            gate.finish()
            loop_stopped = False
        except LoopDetected as e:
            reply, timings, loop_stopped = e.reply, {}, True
        if turn is None:
            turn = [{"role": "user", "content": question}, {"role": "assistant", "content": json.dumps(
                {"tool": tool, "args": {"title" if tool == "wikipedia" else "query": query}}, ensure_ascii=False)}]
        rec_tool, before_titles = recorded or (tool, "")
        if gate.marked or NOT_IN_PAGES in reply:
            from .say import say
            lead = say(self.tools.lang, "not_in_article" if tool == "wikipedia" else "not_in_pages")
            out = self.from_memory([{"role": "system", "content": self.data["system"]}] + self.history, turn, rec_tool,
                                   before_titles + "The pages don't answer this.", {"query": query}, query, then,
                                   on_text, on_action, cancel, [timings], lead=lead, question=question)
            return {**out, "sources": len(found["sources"])}
        # the conversation goes on from here as if the guide had answered (follow-up questions work)
        self.remember(turn[0], reply)
        return {"reply": reply, "tool": tool, "args": {"query": query}, "sources": len(found["sources"]),
                "timings": [timings], "loop_stopped": loop_stopped}

    def offer(self, tool: str, query: str, question: str, on_action, call: str | None = None) -> str:
        """A search card (D55): the sidebar shows exactly what would be sent; nothing goes until the user clicks
        Search. Only the newest offer stands. Returns its id. call: the model's call, kept in the history."""
        import uuid
        sid = uuid.uuid4().hex[:12]
        self.searches = {sid: {"query": query, "question": question, "tool": tool, "call": call}}
        provider = "Wikipedia" if tool == "wikipedia" else websearch.PROVIDER
        on_action("web_search", {"query": query}, "proposal", json.dumps(
            {"id": sid, "query": query, "online": self.tools.online(), "provider": provider}, ensure_ascii=False))
        return sid

    def from_memory(self, before: list, turn: list, tool: str, result: str, args: dict, subject: str,
                    offer_tool: str | None, on_text, on_action, cancel: threading.Event, timings: list,
                    lead: str = "", question: str | None = None) -> dict:
        """Nothing here answers it: what the guide knows, said as that, then more offered online (`offer_tool`:
        Wikipedia for a subject, the web when the help had nothing; None after the web). In offline mode, how to go
        online instead of a card. before: the system prompt and history; turn: the person's message and the call."""
        from .say import say
        lang = self.tools.lang
        intro = (lead + " " if lead else "") + say(lang, "memory_intro", subject=subject)
        on_text(intro + "\n\n")
        followup = {"role": "user", "content": self.data["result_format"].format(
            tool=tool, result=result, style=FROM_MEMORY)}
        guard = self.reply_guard(on_text)
        try:
            reply, t2 = self.backend.chat(before + turn + [followup],
                                          max_tokens=600, on_text=guard.feed, cancel=cancel)
            guard.finish()
            timings.append(t2)
            loop_stopped = False
        except LoopDetected as e:
            reply, loop_stopped = e.reply, True
        out = {"tool": tool, "args": args, "timings": timings, "loop_stopped": loop_stopped}
        more = ""
        if offer_tool and offline.on():
            more = offline.words("assistant", lang)
        elif offer_tool:
            more = say(lang, "memory_more" if self.tools.online() else "memory_more_offline")
            out["proposal"] = self.offer(offer_tool, subject, question or turn[0]["content"], on_action)
        if more:
            on_text("\n\n" + more)
        reply = f"{intro}\n\n{reply}" + (f"\n\n{more}" if more else "")
        self.remember(turn[0], reply)
        return {**out, "reply": reply}

    def standalone(self, text: str, cancel: threading.Event, timings: list) -> str:
        """The message rewritten so it stands alone, from the last two turns ("Did he ever say why he did it?" ->
        "Did Mark David Chapman ever say why he shot John Lennon?"); the message itself with no earlier turns. Probe on
        the 4070 with the shipped guide (2026-10-23, 10 follow-ups and fresh questions in four languages): 8 right,
        2 left as they were, no fresh question given an old topic (a wording without the example changed a Japanese
        question's meaning)."""
        talk = self.history[-4:]
        if not talk:
            return text
        lines = "\n".join(f"{'User' if m['role'] == 'user' else 'Assistant'}: {m['content'][:400]}" for m in talk)
        try:
            out, t = self.backend.chat([{"role": "user", "content": STANDALONE.format(talk=lines, message=text)}],
                                       max_tokens=80, cancel=cancel)
        except LoopDetected:
            return text
        timings.append(t)
        out = out.strip().splitlines()[0].strip().strip('"') if out.strip() else ""
        return out if 0 < len(out) <= 3 * len(text) + 80 else text

    def remember(self, user: dict, reply: str, keep: bool = True) -> None:
        """A turn kept as the talk alone: the person's message and the reply the person saw, no calls or results.
        2026-10-23: with the calls kept, the 4B copied the tools of the turns before (after the help, subjects went to
        the help; after one web search, every subject to the web): Ian's talk 3/11 on the conversation eval, 7/10 kept
        plain (prompt v2.7); follow-ups ("How cold does it get?") still work, the reply carries what was said."""
        self.history += [user, {"role": "assistant", "content": reply}]
        if self.notebook is not None and keep:  # a declined request leaves nothing on disk (memory-design §5)
            said = self.asked if self.asked and user["content"].endswith(self.asked) else user["content"]
            try:
                self.notebook.record(said, reply)
            except OSError:
                pass  # a full disk doesn't stop the answer

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
        if self.notebook is not None:
            self.notebook.fresh()

    def budget(self) -> int:
        on_cpu = self.backend.status().build == "cpu"
        return int(self.cfg["cpu_history_chars"] if on_cpu else self.cfg["history_chars"])

    def turns(self) -> int:
        return sum(m["role"] == "user" and not m["content"].startswith("Result of ") for m in self.history)

    def trim(self) -> None:
        """Drop whole turns from the start until the history is under half the budget, and past `history_turns`
        turns back to the last half of them (in steps: then the prompt cache holds for a while). 2026-10-23: after
        about 23 turns the guide sent subjects to the help that it sends to Wikipedia in a fresh conversation."""
        size = lambda: sum(len(m["content"]) for m in self.history)
        most = int(self.cfg.get("history_turns", 8))
        over_size, over_turns = size() > self.budget(), self.turns() > most
        dropped = []
        while self.history and ((over_size and size() > self.budget() // 2) or (over_turns and self.turns() > most // 2)):
            dropped.append(self.history.pop(0))
            while self.history and not (self.history[0]["role"] == "user"
                                        and not self.history[0]["content"].startswith("Result of ")):
                dropped.append(self.history.pop(0))  # a turn starts with the user's own message
        return dropped

    def fold(self, dropped: list[dict], on_action) -> None:
        """D40: the turns trimmed from the history (and, at the first turn, the end of an earlier session) folded into
        the notes, and the person shown what was kept. A model that can't answer leaves the notes as they were."""
        nb = self.notebook
        pairs = [(a["content"], b["content"]) for a, b in zip(dropped, dropped[1:])
                 if a["role"] == "user" and b["role"] == "assistant"]
        turns = ([] if self.caught_up else nb.earlier()) + nb.timed(pairs)
        self.caught_up = True
        if not turns:
            return
        try:
            lines = nb.fold(turns, self.backend.chat)
        except BackendError:
            return
        on_action("notebook", {}, "done", json.dumps({"lines": lines}, ensure_ascii=False))

    def run_tool(self, tool: str, args: dict, doc: dict | None = None, request: str = "") -> str:
        if doc is not None and tool in self.data["documents"][doc["type"]]["read"]:
            return json.dumps(self.office.read(doc, tool, args), ensure_ascii=False, default=str)
        if tool == "lookup_help":
            # a terminal error needs a confident match (measured 2026-10-04: real ones score 14-29, an unknown error's
            # stray-word matches 2-6, e.g. `git push rejected` -> the printers card)
            query = str(args.get("query", ""))
            if self.terminal_question:  # what failed, from the terminal itself: the model's query is often generic
                query = f"{query} {self.terminal_hint}"
            cid, card = self.help.lookup(query, self.tools.lang, TERMINAL_MIN_SCORE if self.terminal_question else 1.0)
            self.last_card = cid  # None: nothing in the built-in help fits
            return card
        if tool == "inspect_system":
            return json.dumps(self.tools.inspect(str(args.get("topic", "overview"))), ensure_ascii=False)
        if tool == "open_app":
            return json.dumps(self.tools.open_app(str(args.get("app", ""))), ensure_ascii=False)
        if tool == "make_spreadsheet":
            from .sheets import wants_by_month
            args = {**args, "total": wants_by_month(request, str(args.get("total", "none")))}
            return json.dumps(self.tools.make_spreadsheet(args), ensure_ascii=False)
        if tool == "compose_email":
            return json.dumps(self.tools.compose_email(args), ensure_ascii=False)
        if tool == "request_install":
            return json.dumps(self.tools.request_install(str(args.get("package", ""))), ensure_ascii=False)
        if tool == "calculate":  # D68: the answer comes from the calculator, not the model's memory
            from .calc import calculate
            return json.dumps(calculate(str(args.get("expression", ""))), ensure_ascii=False)
        return json.dumps({"error": f"unknown tool {tool}"})

    def turn(self, text: str, on_text: Callable[[str], None], on_action: Callable[[str, dict, str, str], None],
             cancel: threading.Event) -> dict:
        """Answer one message. Returns {"reply", "tool", "args", "timings": [...]}; raises BackendError."""
        dropped = self.trim()
        if self.notebook is not None:
            self.fold(dropped, on_action)
        self.asked = text
        user = {"role": "user", "content": text}
        # a message about the terminal gets the shared terminal's last commands in front of it (M3, §11.5; D77)
        from . import commands as cmdfacts, terminal
        explained = cmdfacts.is_explain(text)
        if explained:  # "Explain" on a command card: the system's facts in front, no terminal context
            user["content"] = cmdfacts.context(explained) + "\n\n" + text
        commands = [] if explained else terminal.latest()
        self.terminal_question, self.last_card, think = None, "", None
        if terminal.about_terminal(text, commands):
            user["content"] = terminal.context(commands) + "\n\n" + text
            self.terminal_question = user["content"]  # for the bigger model, if no card fits (Ian, 2026-10-04)
            self.terminal_hint = terminal.lookup_hint(commands)
            on_action("terminal", {}, "done", json.dumps({"commands": [c.get("cmd") for c in commands[-terminal.MAX_COMMANDS:]
                                                                         if c.get("cmd")]}, ensure_ascii=False))
        doc, system, schema = self.document()
        if doc is None:
            schema = intent.narrow(schema, text)  # the email tool only when an email is asked for (D88)
            if live_session():
                system += LIVE_SYSTEM
            if self.notebook is not None:  # D40: the notes, and an earlier turn these words recall, after the prompt
                self.notebook.recent = {m["content"] for m in self.history if m["role"] == "assistant"}
                system += self.notebook.system_note(text)
        messages = [{"role": "system", "content": system}] + self.history + [user]
        edits = set(self.data["documents"][doc["type"]]["edit"]) if doc else set()
        timings = []
        for attempt in range(2):  # a call LibreOffice refuses goes back to the model once (spike, eval)
            guard = self.reply_guard(on_text)
            stream = TextStream(guard.feed)
            try:
                raw, t1 = self.backend.chat(messages, schema=schema, max_tokens=700,
                                            on_text=stream.feed, cancel=cancel)
                guard.finish()
            except LoopDetected as e:
                tool = stream.tool or "answer"
                args = {"text": e.reply}
                self.remember(user, e.reply)
                return {"reply": e.reply, "tool": tool, "args": args, "timings": timings,
                        "loop_stopped": True}
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
                self.remember(user, reply, keep=tool != "decline")
                return {"reply": reply, "tool": tool, "args": args, "timings": timings}
            if tool == "wikipedia":
                shelves = library.shelves_for(self.tools.lang)
                query = str(args.get("title", "")).strip()[:200] or text[:200]
                if shelves:  # D68: the shelves on this computer: nothing is sent, nothing to agree to
                    on_action(tool, {"query": query}, "running", "")
                    try:
                        found = library.read_shelves(shelves, query)
                    except library.LibraryError:
                        found = None  # not on the shelves (a "top articles" file alone): Wikipedia itself is offered
                    if found is not None:
                        out = self.answer_from(found, text, tool, query, on_text, on_action, cancel, then=tool,
                                               turn=[user, {"role": "assistant", "content": raw}])
                        out["timings"] = timings + out["timings"]
                        return out
                # not on this computer: what the guide knows, then Wikipedia itself offered (Ian, 2026-10-23)
                return self.from_memory(messages[:-1], [user, {"role": "assistant", "content": raw}], tool,
                                        NOT_HERE[tool], args, query, tool, on_text, on_action, cancel, timings)
            if tool == "web_search" and offline.on():  # D28: offline mode offers no search, it says how to go online
                reply = offline.words("assistant", self.tools.lang)
                on_text(reply)
                self.remember(user, reply)
                return {"reply": reply, "tool": "offline", "args": args, "timings": timings}
            if tool == "web_search":
                # nothing is sent here: the sidebar shows the query; the user clicks Search (D55, §7.5)
                asked = self.standalone(text, cancel, timings)
                query = intent.follow_up_query(str(args.get("query", "")), text, asked)
                sid = self.offer(tool, query, text, on_action, call=raw)
                self.searches[sid]["asked"] = asked
                from .say import say
                reply = say(self.tools.lang, "search_offer" if self.tools.online() else "search_offline")
                on_text(reply)
                self.searches[sid]["said"] = reply  # Search answers in this turn's place, if nothing came between
                self.remember(user, reply)
                return {"reply": reply, "tool": tool, "args": {"query": query}, "proposal": sid, "timings": timings}
            try:
                if tool in edits:
                    # an edit is never made here: it becomes a preview the user applies or discards (§7.8)
                    pv = self.office.preview(doc, tool, args)
                    on_action(tool, args, "proposal", json.dumps(pv, ensure_ascii=False, default=str))
                    reply = PROPOSED.format(summary=pv.get("summary", "an edit").rstrip("."))
                    on_text(reply)
                    self.remember(user, reply)
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
        if tool == "lookup_help" and self.last_card is None and not self.terminal_question and doc is None:
            # nothing in the help (Ian, 2026-10-23): Wikipedia on this computer first, then what the guide knows
            query = str(args.get("query", "")).strip()[:200]
            shelves = library.shelves_for(self.tools.lang) if query else []
            try:
                found = library.read_shelves(shelves, query) if shelves else None
            except library.LibraryError:
                found = None
            if found is not None:
                on_action("wikipedia", {"query": query}, "running", "")
                out = self.answer_from(found, text, "wikipedia", query, on_text, on_action, cancel, then="wikipedia",
                                       turn=[user, {"role": "assistant", "content": raw}],
                                       recorded=(tool, "Nothing in the built-in help matches this. This computer's "
                                                       "Wikipedia has:\n"))
                out["timings"] = timings + out["timings"]
                return out
            return self.from_memory(messages[:-1], [user, {"role": "assistant", "content": raw}], tool,
                                    NOT_HERE[tool], args, query or text[:200], "web_search", on_text, on_action, cancel,
                                    timings)
        if tool == "inspect_system":  # a fault found: its tree is walked on a card (D51, D7), the guide explains
            self.tools.asked = text  # the person's words, for Think it through at the tree's end (D7)
            step = self.tools.walk_start(result)
            if step:
                on_action("diagnosis", {"code": step["code"]}, "proposal", json.dumps(step, ensure_ascii=False))
            elif self.tools.past_the_trees(str(args.get("topic", "overview")), result):
                think = (text, result)  # no tree for it: "Think it through?" may be offered (D7)
        followup = {"role": "user", "content": self.data["result_format"].format(
            tool=tool, result=result, style=self.data["style"])}
        direct = facts.direct_reply(tool, args, result, self.tools.lang)
        if direct:  # a plain fact (the time): said by the daemon, the same way every time
            on_text(direct)
            self.remember(user, direct)
            return {"reply": direct, "tool": tool, "args": args, "result": result, "timings": timings,
                    "loop_stopped": False}
        guard = self.reply_guard(on_text)
        try:
            reply, t2 = self.backend.chat(messages + [{"role": "assistant", "content": raw}, followup],
                                          max_tokens=600, on_text=guard.feed, cancel=cancel)
            guard.finish()
            timings.append(t2)
            loop_stopped = False
        except LoopDetected as e:
            reply, loop_stopped = e.reply, True
        self.remember(user, reply)
        out = {"reply": reply, "tool": tool, "args": args, "result": result, "timings": timings,
               "loop_stopped": loop_stopped}
        if think:
            out["think"] = think
        if self.terminal_question and tool == "lookup_help" and self.last_card is None:
            out["unusual"] = self.terminal_question  # a terminal error no card covers: the bigger model may be offered
        return out
