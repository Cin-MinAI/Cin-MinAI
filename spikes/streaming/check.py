#!/usr/bin/env python3
"""Streaming spike checks (M0): llama-server → daemon → sidebar, on the Mint box.

    DISPLAY=:0 python3 check.py

Needs the desktop spike installed (spikes/desktop/install.sh) and ~/.config/cinminai/config.toml
pointing at a running llama-server. Measures, idle vs. while the model generates into the
visible sidebar: compositor frame timing of an animated window, shell keystroke echo latency,
GPU memory/utilisation; then cancel, unreachable-server and multi-turn behaviour.
"""

from __future__ import annotations

import json
import os
import pty
import select
import statistics
import subprocess
import sys
import textwrap
import threading
import time
import urllib.request

import gi

gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gio, GLib  # noqa: E402

SIDEBAR = os.path.expanduser("~/.local/bin/cinminai-sidebar")
DAEMON = ("org.cinminai.Assistant1", "/org/cinminai/Assistant1", "org.cinminai.Assistant1")
LONG = "Explain in about 350 words how Linux boots, from firmware to the login screen."
results: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""), flush=True)


# --- D-Bus -----------------------------------------------------------------------------------

def bus() -> Gio.DBusConnection:
    return Gio.bus_get_sync(Gio.BusType.SESSION)


def prop(name: str):
    v = bus().call_sync(DAEMON[0], DAEMON[1], "org.freedesktop.DBus.Properties", "Get",
                        GLib.Variant("(ss)", (DAEMON[2], name)), None, Gio.DBusCallFlags.NONE, 5000, None)
    return v.unpack()[0]


def call(method: str, sig: str = "", *args):
    params = GLib.Variant(f"({sig})", args) if sig else None
    return bus().call_sync(DAEMON[0], DAEMON[1], DAEMON[2], method, params, None,
                           Gio.DBusCallFlags.NONE, 5000, None)


def wait_state(state: str, timeout: float) -> float | None:
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        if prop("State") == state:
            return time.monotonic() - start
        time.sleep(0.02)
    return None


def stats() -> dict:
    return json.loads(prop("LastStats"))


# --- probes ------------------------------------------------------------------------------------

FRAME_PROBE = textwrap.dedent("""
    import sys, time, gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk, GLib
    secs = float(sys.argv[1]); times = []
    w = Gtk.Window(title="cinminai-frameprobe"); w.set_default_size(160, 90); w.move(0, 0)
    w.set_keep_above(True)
    area = Gtk.DrawingArea(); w.add(area)
    def draw(a, cr):
        t = time.monotonic(); cr.set_source_rgb((t * 2) % 1, 0.4, 0.6); cr.paint()
    area.connect("draw", draw)
    def tick(widget, clock):
        times.append(clock.get_frame_time() / 1e6); widget.queue_draw(); return True
    area.add_tick_callback(tick)
    w.show_all()
    GLib.timeout_add(int(secs * 1000), Gtk.main_quit)
    Gtk.main()
    print(" ".join(f"{t:.6f}" for t in times))
""")


class FrameProbe:
    """Animated window; the frame clock follows the compositor, so its intervals show hitches."""

    def __init__(self, seconds: float) -> None:
        self.proc = subprocess.Popen([sys.executable, "-c", FRAME_PROBE, str(seconds)],
                                     stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)

    def result(self) -> dict:
        times = [float(t) for t in self.proc.communicate()[0].split()][10:]  # skip start-up
        iv = sorted((b - a) * 1000 for a, b in zip(times, times[1:]))
        if not iv:
            return {"frames": 0}
        return {"frames": len(iv), "fps": round(1000 / statistics.mean(iv), 1),
                "p50_ms": round(iv[len(iv) // 2], 1), "p99_ms": round(iv[int(len(iv) * 0.99)], 1),
                "max_ms": round(iv[-1], 1), "hitches_50ms": sum(1 for i in iv if i > 50)}


def echo_latency(seconds: float) -> dict:
    """Keystroke → echo round trip in an interactive bash, sampled for `seconds`."""
    pid, fd = pty.fork()
    if pid == 0:
        os.execvpe("bash", ["bash", "--norc", "-i"], {**os.environ, "PS1": "$ "})
    time.sleep(0.5)
    os.read(fd, 65536)
    samples, end, i = [], time.monotonic() + seconds, 0
    while time.monotonic() < end:
        key = b"x" if i % 2 == 0 else b"\x7f"
        i += 1
        t0 = time.perf_counter()
        os.write(fd, key)
        if select.select([fd], [], [], 2.0)[0]:
            samples.append((time.perf_counter() - t0) * 1000)
            os.read(fd, 65536)
        time.sleep(0.02)
    os.kill(pid, 9)
    os.waitpid(pid, 0)
    s = sorted(samples)
    return {"n": len(s), "p50_ms": round(s[len(s) // 2], 2), "p99_ms": round(s[int(len(s) * 0.99)], 2),
            "max_ms": round(s[-1], 2)}


class GpuSampler(threading.Thread):
    def __init__(self) -> None:
        super().__init__(daemon=True)
        self.stop = threading.Event()
        self.mem, self.util = [], []

    def run(self) -> None:
        while not self.stop.is_set():
            out = subprocess.run(["nvidia-smi", "--query-gpu=memory.used,utilization.gpu",
                                  "--format=csv,noheader,nounits"], capture_output=True, text=True).stdout
            try:
                m, u = (int(x) for x in out.strip().split(","))
                self.mem.append(m)
                self.util.append(u)
            except ValueError:
                pass
            time.sleep(0.25)

    def result(self) -> dict:
        self.stop.set()
        self.join()
        return {"vram_peak_mib": max(self.mem, default=0), "gpu_util_mean": round(statistics.mean(self.util or [0]))}


def measure(seconds: float) -> tuple[dict, dict, dict]:
    fp, gpu = FrameProbe(seconds), GpuSampler()
    gpu.start()
    lat = echo_latency(seconds - 0.5)
    return fp.result(), lat, gpu.result()


def server_busy() -> int | None:
    """llama-server's own view: requests being processed (from /metrics)."""
    cfg = open(os.path.expanduser("~/.config/cinminai/config.toml")).read()
    url = next(l.split("=", 1)[1].strip().strip('"') for l in cfg.splitlines() if l.startswith("url"))
    key = next((l.split("=", 1)[1].strip().strip('"') for l in cfg.splitlines() if l.startswith("api_key")), "")
    req = urllib.request.Request(url.rstrip("/") + "/metrics", headers={"Authorization": f"Bearer {key}"})
    try:
        text = urllib.request.urlopen(req, timeout=3).read().decode()
    except OSError:
        return None
    for line in text.splitlines():
        if line.startswith("llamacpp:requests_processing"):
            return int(float(line.split()[-1]))
    return None


# --- checks ------------------------------------------------------------------------------------

def main() -> int:
    subprocess.run(["pkill", "-f", "desktop/daemon.py"])  # pick up the current daemon code
    time.sleep(0.5)
    model = prop("Model")  # D-Bus activates the daemon
    time.sleep(2)
    model = prop("Model")
    record("daemon talks to llama-server", "LOCAL" in model and "unreachable" not in model, model)
    call("Reset")

    # Warm up (the server unloads when idle); report the first answer's latency on its own.
    call("Ask", "s", "Reply with one word: ready")
    wait_state("idle", 120)
    s = stats()
    record("first answer (may include waking the model)", s.get("error") is None,
           f"ttft {s.get('ttft_s')} s, {s.get('gen_tps')} tok/s")

    idle = measure(8)
    print(f"      idle:       frames {idle[0]}  echo {idle[1]}  gpu {idle[2]}")

    subprocess.Popen([SIDEBAR, "--show"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True)
    time.sleep(1)
    call("Reset")
    call("Ask", "s", LONG)
    time.sleep(1.5)  # past the first token; the answer runs ~15 s, the window is 8 s
    busy = measure(8)
    print(f"      generating: frames {busy[0]}  echo {busy[1]}  gpu {busy[2]}")
    wait_state("idle", 120)
    s = stats()
    record("long answer streamed", not s.get("error") and (s.get("gen_tokens") or 0) > 200,
           f"{s.get('gen_tokens')} tokens, ttft {s.get('ttft_s')} s, {s.get('gen_tps')} tok/s, "
           f"prompt {s.get('prompt_tps')} tok/s")
    record("tokens arrive evenly (p99 gap < 150 ms)", (s.get("gap_p99_ms") or 1e9) < 150,
           f"gap p50 {s.get('gap_p50_ms')} p99 {s.get('gap_p99_ms')} max {s.get('gap_max_ms')} ms")
    wid = subprocess.run(["wmctrl", "-lx"], capture_output=True, text=True).stdout
    wid = next((l.split()[0] for l in wid.splitlines() if "cinminai-sidebar" in l), None)
    info = subprocess.run(["xwininfo", "-id", wid], capture_output=True, text=True).stdout if wid else ""
    geo = dict(l.strip().split(": ", 1) for l in info.splitlines() if ": " in l)
    scale = Gdk.Display.get_default().get_monitor(0).get_scale_factor()
    sw = Gdk.Display.get_default().get_monitor(0).get_geometry().width * scale
    record("sidebar keeps its width with a real model name",
           geo.get("Width") == str(380 * scale) and int(geo.get("Absolute upper-left X", 0)) + 380 * scale == sw,
           f"x={geo.get('Absolute upper-left X')} w={geo.get('Width')} at scale {scale}")
    subprocess.run(["python3", "-c",
                    "import sys; sys.argv=['x']; sys.path.insert(0, '" + os.path.expanduser("~/cin-minai/spikes/desktop") + "');"
                    "import check; check.screenshot('stream-sidebar', None, 1600)"],
                   env={**os.environ, "PYTHONWARNINGS": "ignore"}, capture_output=True)

    f0, f1 = idle[0], busy[0]
    record("desktop frames: no extra hitches while generating",
           f1.get("frames", 0) > 0 and f1["hitches_50ms"] <= f0["hitches_50ms"] + 1 and f1["p99_ms"] < 2 * f0["p99_ms"] + 5,
           f"idle p99 {f0.get('p99_ms')} ms/{f0.get('hitches_50ms')} hitches, generating p99 {f1.get('p99_ms')} ms/{f1.get('hitches_50ms')} hitches")
    e0, e1 = idle[1], busy[1]
    record("terminal echo unaffected (p99 < 10 ms)", e1["p99_ms"] < 10,
           f"idle p99 {e0['p99_ms']} ms, generating p99 {e1['p99_ms']} ms")
    record("(info) GPU", True, f"idle {idle[2]}, generating {busy[2]}")

    # Cancel.
    call("Ask", "s", LONG)
    time.sleep(2.0)
    t0 = time.monotonic()
    call("Cancel")
    took = wait_state("idle", 5)
    time.sleep(0.5)
    record("Stop ends the answer quickly", took is not None and took < 1.0 and stats().get("cancelled"),
           f"{took and round(took * 1000)} ms")
    record("llama-server stops generating after Stop", server_busy() == 0, f"requests_processing={server_busy()}")

    # Unreachable server.
    call("SetBackendUrl", "s", "http://127.0.0.1:9")
    call("Ask", "s", "hello?")
    took = wait_state("error", 5)
    err = stats().get("error")
    record("unreachable server → error state + message, no hang", took is not None and bool(err), f"{err}")
    call("SetBackendUrl", "s", "")
    time.sleep(1)

    # Multi-turn.
    call("Reset")
    call("Ask", "s", "My name is Brick. Reply with just: OK")
    wait_state("idle", 60)
    call("Ask", "s", "What is my name? One word.")
    wait_state("idle", 60)
    reply = prop("LastReply")
    record("multi-turn: remembers the previous turn", "brick" in reply.lower(), repr(reply[:80]))

    subprocess.run([SIDEBAR, "--hide"], capture_output=True)
    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks pass")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
