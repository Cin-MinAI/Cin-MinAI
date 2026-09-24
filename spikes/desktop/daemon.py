#!/usr/bin/env python3
"""Assistant daemon for the M0 desktop-surface and streaming spikes.

Owns org.cinminai.Assistant1 on the session bus, like the real cinminai-daemon will (SPEC §4).
With `[inference] url` in ~/.config/cinminai/config.toml it streams real replies from llama-server
(OpenAI-compatible /v1/chat/completions, SSE); without it, it fakes a canned reply (stub mode).
D-Bus activated via org.cinminai.Assistant1.service. Uses only what Mint ships (PyGObject, stdlib).

HTTP runs on a worker thread; tokens reach the main loop with GLib.idle_add, so the bus never
waits on the model.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
import tomllib
import urllib.error
import urllib.request

from gi.repository import Gio, GLib

NAME = "org.cinminai.Assistant1"
PATH = "/org/cinminai/Assistant1"
IFACE = "org.cinminai.Assistant1"
CONFIG = os.path.expanduser("~/.config/cinminai/config.toml")

XML = f"""
<node>
  <interface name="{IFACE}">
    <method name="Ask">
      <arg type="s" name="text" direction="in"/>
      <arg type="u" name="id" direction="out"/>
    </method>
    <method name="Cancel"/>
    <method name="Reset"/>
    <!-- spike only: force a state so the applet's icons can be checked -->
    <method name="SetState">
      <arg type="s" name="state" direction="in"/>
    </method>
    <!-- spike only: point at another server (error-path test); "" = back to config -->
    <method name="SetBackendUrl">
      <arg type="s" name="url" direction="in"/>
    </method>
    <signal name="Token"><arg type="u" name="id"/><arg type="s" name="text"/></signal>
    <signal name="Done"><arg type="u" name="id"/></signal>
    <signal name="Error"><arg type="u" name="id"/><arg type="s" name="message"/></signal>
    <property name="State" type="s" access="read"/>
    <property name="Model" type="s" access="read"/>
    <property name="Awareness" type="a{{sb}}" access="readwrite"/>
    <property name="LastAsk" type="s" access="read"/>
    <property name="LastStats" type="s" access="read"/>
    <property name="LastReply" type="s" access="read"/>
  </interface>
</node>
"""

STATES = {"idle", "thinking", "approval", "off", "error"}
SYSTEM = ("You are the local engineering assistant of this Linux system (Cin-MinAI OS, based on "
          "Linux Mint). Be brief and practical. Put commands in fenced code blocks.")
STUB_REPLY = ("This is the stub daemon answering {q!r}. Set [inference] url in "
              "~/.config/cinminai/config.toml to stream from llama-server instead.")


def load_config() -> dict:
    try:
        with open(CONFIG, "rb") as f:
            return tomllib.load(f).get("inference", {})
    except (OSError, tomllib.TOMLDecodeError):
        return {}


class LlamaServer:
    """Client for llama-server's OpenAI-compatible API."""

    def __init__(self, url: str, api_key: str = "", model: str = "") -> None:
        self.url = url.rstrip("/")
        self.api_key = api_key
        self.model = model

    def request(self, path: str, body: dict | None = None) -> urllib.request.Request:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        data = json.dumps(body).encode() if body is not None else None
        return urllib.request.Request(self.url + path, data=data, headers=headers)

    def describe(self) -> str:
        with urllib.request.urlopen(self.request("/props"), timeout=5) as r:
            props = json.load(r)
        alias = props.get("model_alias") or os.path.basename(props.get("model_path", "?"))
        ctx = props.get("default_generation_settings", {}).get("n_ctx", 0)
        return f"{alias}  {ctx // 1024}K  LOCAL"

    def stream(self, messages: list[dict], cancel: threading.Event):
        """Yield content chunks; ends early when cancel is set. Returns llama.cpp timings."""
        body = {"model": self.model, "messages": messages, "stream": True,
                "temperature": 0.3, "max_tokens": 1024}
        timings = None
        with urllib.request.urlopen(self.request("/v1/chat/completions", body), timeout=300) as r:
            for raw in r:
                if cancel.is_set():
                    break  # closing the connection makes llama-server stop generating
                line = raw.decode(errors="replace").strip()
                if not line.startswith("data: ") or line == "data: [DONE]":
                    continue
                chunk = json.loads(line[6:])
                timings = chunk.get("timings", timings)
                for choice in chunk.get("choices", []):
                    text = choice.get("delta", {}).get("content")
                    if text:
                        yield text
        return timings


class Daemon:
    def __init__(self, loop: GLib.MainLoop) -> None:
        self.loop = loop
        self.conn: Gio.DBusConnection | None = None
        self.state = "idle"
        self.awareness = {"terminals": True, "browser": False, "web": False}
        self.last_ask = ""
        self.last_stats = "{}"
        self.last_reply = ""
        self.next_id = 0
        self.history: list[dict] = []
        self.cancel = threading.Event()
        self.busy = False
        self.configure()

    def configure(self, url: str | None = None) -> None:
        cfg = load_config()
        url = url or cfg.get("url")
        self.backend = LlamaServer(url, cfg.get("api_key", ""), cfg.get("model", "")) if url else None
        self.model = "stub-model  LOCAL" if not self.backend else "connecting…"
        if self.backend:
            threading.Thread(target=self.fetch_model, daemon=True).start()

    def fetch_model(self) -> None:
        try:
            desc = self.backend.describe()
        except (OSError, ValueError) as e:
            desc = f"backend unreachable ({getattr(e, 'reason', e)})"
        GLib.idle_add(self.set_model, desc)

    def set_model(self, desc: str) -> bool:
        self.model = desc
        if self.conn:
            self.changed("Model")
        return False

    # --- bus plumbing ---------------------------------------------------------------------
    def acquired(self, conn: Gio.DBusConnection, name: str) -> None:
        self.conn = conn
        info = Gio.DBusNodeInfo.new_for_xml(XML).interfaces[0]
        conn.register_object(PATH, info, self.call, self.get, self.set)

    def lost(self, conn, name) -> None:
        print(f"lost {name} (another daemon running?)", file=sys.stderr)
        self.loop.quit()

    def variant(self, prop: str) -> GLib.Variant:
        return {
            "State": lambda: GLib.Variant("s", self.state),
            "Model": lambda: GLib.Variant("s", self.model),
            "Awareness": lambda: GLib.Variant("a{sb}", self.awareness),
            "LastAsk": lambda: GLib.Variant("s", self.last_ask),
            "LastStats": lambda: GLib.Variant("s", self.last_stats),
            "LastReply": lambda: GLib.Variant("s", self.last_reply),
        }[prop]()

    def changed(self, *props: str) -> None:
        self.conn.emit_signal(
            None, PATH, "org.freedesktop.DBus.Properties", "PropertiesChanged",
            GLib.Variant("(sa{sv}as)", (IFACE, {p: self.variant(p) for p in props}, [])))

    def emit(self, signal: str, fmt: str, *args) -> None:
        self.conn.emit_signal(None, PATH, IFACE, signal, GLib.Variant(fmt, args))

    def get(self, conn, sender, path, iface, prop) -> GLib.Variant:
        return self.variant(prop)

    def set(self, conn, sender, path, iface, prop, value) -> bool:
        if prop == "Awareness":
            self.awareness.update(value.unpack())
            self.changed("Awareness")
            return True
        return False

    def call(self, conn, sender, path, iface, method, params, inv) -> None:
        if method == "Ask":
            (text,) = params.unpack()
            if self.busy:
                inv.return_dbus_error(f"{IFACE}.Error.Busy", "still answering; Cancel first")
                return
            self.next_id += 1
            inv.return_value(GLib.Variant("(u)", (self.next_id,)))
            self.last_ask = text
            self.changed("LastAsk")
            self.ask(self.next_id, text)
        elif method == "Cancel":
            self.cancel.set()
            inv.return_value(None)
        elif method == "Reset":
            self.history.clear()
            inv.return_value(None)
        elif method == "SetState":
            (state,) = params.unpack()
            if state not in STATES:
                inv.return_dbus_error(f"{IFACE}.Error.BadState", f"unknown state {state!r}")
                return
            self.set_state(state)
            inv.return_value(None)
        elif method == "SetBackendUrl":
            (url,) = params.unpack()
            self.configure(url or None)
            self.changed("Model")
            inv.return_value(None)

    # --- answering ------------------------------------------------------------------------
    def set_state(self, state: str) -> None:
        if state != self.state:
            self.state = state
            self.changed("State")

    def ask(self, rid: int, text: str) -> None:
        self.busy = True
        self.cancel.clear()
        self.set_state("thinking")
        self.history.append({"role": "user", "content": text})
        if self.backend:
            messages = [{"role": "system", "content": SYSTEM}] + self.history
            threading.Thread(target=self.worker, args=(rid, messages), daemon=True).start()
        else:
            self.fake(rid, STUB_REPLY.format(q=text))

    def worker(self, rid: int, messages: list[dict]) -> None:
        """Worker thread: stream from llama-server, hand every chunk to the main loop."""
        start, first, stamps, reply = time.monotonic(), None, [], []
        error = None
        try:
            gen = self.backend.stream(messages, self.cancel)
            while True:
                try:
                    chunk = next(gen)
                except StopIteration as stop:
                    timings = stop.value
                    break
                now = time.monotonic()
                first = first or now
                stamps.append(now)
                reply.append(chunk)
                GLib.idle_add(self.emit, "Token", "(us)", rid, chunk)
        except (OSError, ValueError) as e:
            timings, error = None, f"{getattr(e, 'reason', None) or e}"
        gaps = sorted(b - a for a, b in zip(stamps, stamps[1:]))
        stats = {
            "ttft_s": round(first - start, 3) if first else None,
            "chunks": len(stamps),
            "gap_p50_ms": round(gaps[len(gaps) // 2] * 1000, 1) if gaps else None,
            "gap_p99_ms": round(gaps[int(len(gaps) * 0.99)] * 1000, 1) if gaps else None,
            "gap_max_ms": round(gaps[-1] * 1000, 1) if gaps else None,
            "cancelled": self.cancel.is_set(),
            "error": error,
        }
        if timings:
            stats.update(prompt_tps=round(timings.get("prompt_per_second", 0), 1),
                         gen_tps=round(timings.get("predicted_per_second", 0), 1),
                         gen_tokens=timings.get("predicted_n"))
        GLib.idle_add(self.finish, rid, "".join(reply), stats)

    def finish(self, rid: int, reply: str, stats: dict) -> bool:
        if stats["error"]:
            self.history.pop()  # the question wasn't answered; don't keep it
            self.emit("Error", "(us)", rid, stats["error"])
            self.set_state("error")
        else:
            self.history.append({"role": "assistant", "content": reply})
            self.set_state("idle")
        self.last_stats = json.dumps(stats)
        self.last_reply = reply
        self.changed("LastStats", "LastReply")
        self.emit("Done", "(u)", rid)
        self.busy = False
        return False

    def fake(self, rid: int, text: str) -> None:
        words = iter(text.split(" "))

        def tick() -> bool:
            word = next(words, None)
            if word is None or self.cancel.is_set():
                self.finish(rid, text, {"error": None, "cancelled": self.cancel.is_set()})
                return False
            self.emit("Token", "(us)", rid, word + " ")
            return True

        GLib.timeout_add(25, tick)


def main() -> None:
    loop = GLib.MainLoop()
    d = Daemon(loop)
    Gio.bus_own_name(Gio.BusType.SESSION, NAME, Gio.BusNameOwnerFlags.NONE, d.acquired, None, d.lost)
    loop.run()


if __name__ == "__main__":
    main()
