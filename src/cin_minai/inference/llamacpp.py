# SPDX-License-Identifier: GPL-3.0-or-later
"""LlamaCppBackend (SPEC §10.2): runs our llama-server (cinminai-llama) and talks to it.

- **Supervisor.** llama-server runs as the daemon's child, in the daemon's systemd unit (one cgroup: when
  the daemon stops, the server stops; it also gets SIGTERM if the daemon dies). It listens on a Unix
  socket in $XDG_RUNTIME_DIR (only this user can reach it; the sandbox mounts neither, D15).
- **Budget at load time, step down, never crash-loop** (SPEC §4.2). Before each load the free graphics
  memory is read and the desktop reserve kept; the profiles are tried in order — graphics card at full
  context, graphics card at 4K, processor — at most once each, and the reason for a reduced profile is
  kept in plain words for the sidebar and applet. A server that dies while answering starts again one
  step down.
- **The measured settings.** Flags as in bench/run.py and the model card: q8_0 KV cache, flash
  attention on, one slot, reasoning off, automatic fitting off, one thread per core.
"""

from __future__ import annotations

import collections
import ctypes
import dataclasses
import http.client
import json
import os
import queue
import re
import signal
import struct
import socket
import subprocess
import threading
import time
from typing import Callable

from . import gguf, hardware
from .backend import BackendError, Cancelled, InferenceBackend, Status

LIVE_MEDIA = ("/cdrom/", "/run/live/medium/")  # where the live USB keeps the model (model_path)

SERVER_DIR = "/usr/lib/cinminai/llama"
DEVICE_RE = re.compile(r"^\s*((?:CUDA|Vulkan)\d+): (.*?) \((\d+) MiB, (\d+) MiB free\)", re.M)


@dataclasses.dataclass
class Profile:
    build: str          # cuda | vulkan | cpu
    device: str         # CUDA0 | Vulkan0 | none
    context: int
    gpu_layers: str     # "all" | "0"
    reduced: str = ""   # "" = the full profile for this machine; else why not, in plain words


class UnixHTTPConnection(http.client.HTTPConnection):
    def __init__(self, path: str, timeout: float) -> None:
        super().__init__("localhost", timeout=timeout)
        self.socket_path = path

    def connect(self) -> None:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(self.timeout)
        s.connect(self.socket_path)
        self.sock = s


def _set_pdeathsig() -> None:
    """In the child before exec: SIGTERM when the daemon dies, however it dies; and no core dumps — llama-server
    v0.5.0 segfaults on exit, and a 27B on the processor left a 5.1 GB dump that helped fill the disk (2026-10-02)."""
    try:
        ctypes.CDLL("libc.so.6", use_errno=True).prctl(1, signal.SIGTERM)  # PR_SET_PDEATHSIG
    except OSError:
        pass
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    except (ImportError, ValueError, OSError):
        pass


class Spawner:
    """Starts child processes from one thread that lives as long as the daemon. PR_SET_PDEATHSIG fires
    when the *thread* that forked the child exits, not the process: started from a worker thread, the
    server was killed as soon as that load or answer finished (found 2026-09-28)."""

    def __init__(self) -> None:
        self.q: queue.Queue = queue.Queue()
        threading.Thread(target=self._run, name="llama-spawner", daemon=True).start()

    def _run(self) -> None:
        while True:
            argv, kw, box, done = self.q.get()
            try:
                # its own session: Ctrl+C in a terminal (AICUI's Stop) is for the agent, not the model server — it
                # killed the server, and the next step loaded the model again (2026-10-03); PDEATHSIG still ends it
                box.append(subprocess.Popen(argv, preexec_fn=_set_pdeathsig, start_new_session=True, **kw))
            except Exception as e:
                box.append(e)
            done.set()

    def popen(self, argv: list[str], **kw) -> subprocess.Popen:
        box, done = [], threading.Event()
        self.q.put((argv, kw, box, done))
        done.wait()
        if isinstance(box[0], Exception):
            raise box[0]
        return box[0]


def server_error(status: int, body: str) -> str:
    """What the person reads when llama-server refuses a request: plain words, the server's own text after them for
    the log (2026-10-05: a 42-minute video's summary showed the raw JSON of "exceeds the available context size")."""
    try:
        err = json.loads(body).get("error", {})
    except ValueError:
        err = {}
    if err.get("type") == "exceed_context_size_error":
        return ("That was more than the model can read at once "
                f"({err.get('n_prompt_tokens', '?')} pieces of text, room for {err.get('n_ctx', '?')}). "
                "Try a shorter text, or ask about one part of it.")
    detail = (err.get("message") or body or "").strip()[:200]
    return f"The model couldn't answer this time (its server said {status}{': ' + detail if detail else ''})."


def need_mib(model_bytes: int, context: int) -> int:
    """Graphics memory a load needs: the weights plus KV cache and buffers. Calibrated on the shipped
    guide (2,654 MiB file, 8K context, q8_0 cache: 3,032 MiB peak, MODEL_CARD.md), with a margin."""
    return (model_bytes >> 20) + 200 + int(context * 0.022)


class LlamaCppBackend(InferenceBackend):
    def __init__(self, cfg: dict, log: Callable[[str], None] = print) -> None:
        self.cfg = cfg
        self.log = log
        self.server_dir = cfg.get("server_dir", SERVER_DIR)
        self.server = os.path.join(self.server_dir, "llama-server")
        run = os.environ.get("XDG_RUNTIME_DIR") or f"/tmp/cinminai-{os.getuid()}"
        os.makedirs(os.path.join(run, "cinminai"), mode=0o700, exist_ok=True)
        self.sock = os.path.join(run, "cinminai", os.path.basename(str(cfg.get("socket_name") or "llama.sock")))
        self.proc: subprocess.Popen | None = None
        self.stderr_tail: collections.deque[str] = collections.deque(maxlen=40)
        self.lock = threading.RLock()
        self.skip = 0   # profiles below this index failed at runtime: start lower next time
        self.profile: Profile | None = None
        self._status = Status(model=self.model_name())
        self.active: http.client.HTTPConnection | None = None
        self.spawner = Spawner()
        self.on_progress: Callable[[], None] = lambda: None  # the daemon tells the sidebar (the stick's read)

    # --- what to run -------------------------------------------------------------------------------
    def model_path(self) -> str:
        """The configured model file; on the live USB it's read from the stick itself (/cdrom), where the
        ISO carries it outside the live filesystem (distro/build-iso.sh)."""
        path = self.cfg.get("model", "")
        if os.path.isfile(path):
            return path
        for media in ("/cdrom", "/run/live/medium"):
            alt = os.path.join(media, "cinminai", "models", os.path.basename(path))
            if os.path.isfile(alt):
                return alt
        return path

    def warm(self, path: str) -> None:
        """On the live USB, read the model once from start to finish before the server starts. The server maps the
        file and reads it in small scattered pieces, which a USB stick does very slowly: on Ian's PC (2026-10-07,
        blue USB 3 port) only ~2 of 2.6 GB were in after 10 minutes and the load gave up; after one straight read
        (as `dd`) the next load took 3 seconds. The read is shown as a percentage in the sidebar's header."""
        if not path.startswith(LIVE_MEDIA):
            return
        size = os.path.getsize(path) or 1
        done, shown, t0 = 0, -1, time.monotonic()
        buf = bytearray(8 << 20)
        try:
            with open(path, "rb", buffering=0) as f:
                while n := f.readinto(buf):
                    done += n
                    pct = done * 100 // size
                    if pct // 5 != shown // 5:
                        shown = pct
                        self._status = Status("loading", self.model_name(), detail=f"stick:{pct}")
                        self.on_progress()
        except OSError as e:  # the server still tries; it reads what it needs itself
            self.log(f"reading the model from the stick: {e}")
            return
        secs = time.monotonic() - t0
        self.log(f"read the model from the stick in {secs:.0f} s ({size / 2**20 / max(secs, 0.1):.0f} MB/s)")

    def model_name(self) -> str:
        return self.cfg.get("model_name") or os.path.splitext(os.path.basename(self.cfg.get("model", "")))[0]

    def list_devices(self) -> list[tuple[str, str, int, int]]:
        """[(CUDA0, name, total MiB, free MiB), ...] as the pinned llama-server sees them."""
        try:
            out = subprocess.run([self.server, "--list-devices"], capture_output=True, text=True, timeout=60).stdout
        except (OSError, subprocess.SubprocessError):
            return []
        return [(m[0], m[1], int(m[2]), int(m[3])) for m in DEVICE_RE.findall(out)]

    def ladder(self) -> list[Profile]:
        """The profiles to try, best first (SPEC §4.2, §9)."""
        ctx, cpu_ctx = int(self.cfg.get("context", 8192)), int(self.cfg.get("cpu_context", 4096))
        want = self.cfg.get("build", "auto")
        gpus = hardware.gpus()
        has = lambda b: os.path.exists(os.path.join(self.server_dir, f"libggml-{b}.so"))
        builds = []
        if want in ("cuda", "vulkan"):
            builds = [want]
        elif want == "auto":
            if any(g.driver == "nvidia" for g in gpus):
                builds = ["cuda"] if has("cuda") else ["vulkan"]   # NVIDIA's driver also does Vulkan
            elif any(g.driver == "amdgpu" for g in gpus):
                builds = ["vulkan"]
        builds = [b for b in builds if has(b)]
        steps: list[Profile] = []
        for b in builds:
            dev = "CUDA0" if b == "cuda" else "Vulkan0"
            steps.append(Profile(b, dev, ctx, "all"))
            if ctx > 4096:
                steps.append(Profile(b, dev, 4096, "all", "smaller context (4K): the graphics card's memory is busy"))
        if builds:
            cpu_why = "on the processor (slower): the graphics card's memory is busy"
        elif any(g.vendor == "nvidia" and g.driver != "nvidia" for g in gpus):
            cpu_why = "on the processor (slower): the graphics card's driver isn't installed yet"
        else:
            cpu_why = ""
        steps.append(Profile("cpu", "none", cpu_ctx, "0", cpu_why))
        return steps

    @staticmethod
    def pick_device(build: str, devices: list) -> str:
        """The device for a build, by name, not by index: on a laptop with Intel graphics next to an
        NVIDIA or AMD card, Vulkan0 can be the Intel one."""
        prefix = "CUDA" if build == "cuda" else "Vulkan"
        mine = [d for d in devices if d[0].startswith(prefix)]
        discrete = [d for d in mine if re.search(r"NVIDIA|GeForce|RTX|AMD|Radeon", d[1], re.I)]
        return (discrete or mine or [(prefix + "0",)])[0][0]

    def free_mib(self, profile: Profile, devices: list) -> int | None:
        for name, _, _, free in devices:
            if name == profile.device:
                return free
        if profile.build == "cuda":
            return hardware.nvidia_free_mib()
        return None

    def cache_type(self) -> str:
        """The KV cache type: q8_0, or q4_0 where the matcher planned a tight fit (settings: cache_type)."""
        c = str(self.cfg.get("cache_type") or "q8_0")
        return c if c in ("q8_0", "q4_0", "f16") else "q8_0"

    # --- the server ----------------------------------------------------------------------------------
    def argv(self, p: Profile) -> list[str]:
        threads = self.cfg.get("threads", "auto")
        threads = str(hardware.physical_cores() if threads == "auto" else int(threads))
        a = [self.server, "--model", self.model_path(), "--alias", self.model_name(),
             "--host", self.sock, "--port", "8080",   # the port is ignored for a socket, but must be set
             "--ctx-size", str(p.context), "--gpu-layers", p.gpu_layers, "--device", p.device,
             "--cache-type-k", self.cache_type(), "--cache-type-v", self.cache_type(), "--flash-attn", "on", "--fit", "off",
             "--parallel", "1", "--reasoning", "off", "--no-webui",
             "--threads", threads, "--threads-batch", threads]
        if int(self.cfg.get("idle_unload_s", 0)) > 0:
            a += ["--sleep-idle-seconds", str(int(self.cfg["idle_unload_s"]))]
        return a + [str(x) for x in self.cfg.get("extra_args", [])]

    def _drain(self, stream) -> None:
        for line in iter(stream.readline, ""):
            self.stderr_tail.append(line.rstrip())
        stream.close()

    def _start(self, p: Profile) -> str | None:
        """Start and wait until the model is loaded. None on success, else what went wrong."""
        self._stop()  # never two servers
        try:
            os.unlink(self.sock)
        except FileNotFoundError:
            pass
        self.stderr_tail.clear()
        argv = self.argv(p)
        self.log(f"llama-server: {' '.join(argv)}")
        try:
            self.proc = self.spawner.popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                           stderr=subprocess.PIPE, text=True, errors="replace")
        except OSError as e:
            return f"can't start llama-server: {e}"
        threading.Thread(target=self._drain, args=(self.proc.stderr,), daemon=True).start()
        deadline = time.monotonic() + float(self.cfg.get("load_timeout_s", 600))
        while time.monotonic() < deadline:
            if self.proc.poll() is not None:
                return f"llama-server exited ({self.proc.returncode}): " + " | ".join(list(self.stderr_tail)[-4:])
            try:
                c = UnixHTTPConnection(self.sock, 5)
                c.request("GET", "/health")
                r = c.getresponse()
                r.read()
                c.close()
                if r.status == 200:
                    return None
            except OSError:
                pass
            time.sleep(0.5)
        self._stop()
        return "llama-server took too long to load the model"

    def _stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()
        self.proc = None

    def alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    # --- InferenceBackend ------------------------------------------------------------------------------
    def status(self) -> Status:
        return dataclasses.replace(self._status)

    def load(self) -> None:
        with self.lock:
            if self.alive():
                return
            model = self.model_path()
            if not os.path.isfile(model):
                self._status = Status("error", self.model_name(), detail=f"the model file is missing: {model}")
                raise BackendError("The assistant's model isn't installed on this computer.")
            self.warm(model)
            size = os.path.getsize(model)
            try:  # the model's own numbers (gguf.py); the old estimate if the file can't be read
                meta = gguf.read(model)
                cpu_moe = gguf.cpu_moe_layers(self.cfg.get("extra_args", []))
                extra = self.cfg.get("extra_args", [])
                need_for = lambda ctx: gguf.need_mib(meta, ctx, self.cache_type(), cpu_moe,  # noqa: E731
                                                     gguf.cpu_overrides(extra), gguf.ubatch(extra))
            except (OSError, ValueError, KeyError, struct.error, UnicodeDecodeError):
                need_for = lambda ctx: need_mib(size, ctx)  # noqa: E731
            steps = self.ladder()
            devices = self.list_devices() if any(p.build != "cpu" for p in steps) else []
            # the desktop's share (SPEC §4.2), or the user's own figure (settings: desktop_reserve_mib)
            reserve = int(self.cfg.get("desktop_reserve_mib") or hardware.desktop_reserve_mib())
            errors, reason = [], ""
            for i, p in enumerate(steps):
                if p.build != "cpu" and devices:
                    p = dataclasses.replace(p, device=self.pick_device(p.build, devices))
                if i < self.skip and i < len(steps) - 1:
                    reason = p.reduced or "the graphics card ran out of memory earlier"
                    continue
                if p.build != "cpu":
                    free = self.free_mib(p, devices)
                    need = need_for(p.context)
                    if free is not None and free - reserve < need:
                        self.log(f"skip {p.build} {p.context}: {free} MiB free - {reserve} reserve < {need} needed")
                        continue
                if p.build == "cpu" and not p.reduced and reason:
                    p = dataclasses.replace(p, reduced=reason)
                self._status = Status("loading", self.model_name(), p.build, p.context, p.reduced)
                err = self._start(p)
                if err is None:
                    self.profile = p
                    self._status = Status("ready", self.model_name(), p.build, p.context, p.reduced)
                    self.log(f"loaded: {p}")
                    return
                self.log(f"load failed ({p.build}, {p.context}): {err}")
                errors.append(err)
            self._status = Status("error", self.model_name(), detail=errors[-1] if errors else "no profile to try")
            raise BackendError("The assistant's model couldn't be loaded on this computer.")

    def unload(self) -> None:
        with self.lock:
            self._stop()
            self.profile = None
            self._status = Status("off", self.model_name())

    def interrupt(self) -> None:
        """Cancel: close the running request's connection (llama-server then stops generating)."""
        c = self.active
        if c and c.sock:
            try:
                c.sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    def chat(self, messages, *, schema=None, max_tokens=600, on_text=None, cancel=None, sampling=None):
        self.load()
        body = {"model": self.model_name(), "messages": messages, "stream": True, "max_tokens": max_tokens,
                "temperature": float(self.cfg.get("temperature", 0)), "cache_prompt": True,
                "chat_template_kwargs": {"enable_thinking": False}}
        if sampling:  # writing (writer.py): a little randomness; tool calls stay at the configured temperature
            body.update({k: v for k, v in sampling.items() if k in ("temperature", "top_p", "top_k", "min_p",
                                                                     "repeat_penalty", "presence_penalty",
                                                                     "dry_multiplier", "dry_base", "dry_allowed_length",
                                                                     "dry_penalty_last_n")})
        if schema:
            body["response_format"] = {"type": "json_schema", "json_schema": {"name": "call", "schema": schema}}
        conn = UnixHTTPConnection(self.sock, float(self.cfg.get("request_timeout_s", 600)))
        self.active = conn
        text, timings = [], {}
        try:
            conn.request("POST", "/v1/chat/completions", body=json.dumps(body).encode(),
                         headers={"Content-Type": "application/json"})
            r = conn.getresponse()
            if r.status != 200:
                raise BackendError(server_error(r.status, r.read(2000).decode(errors="replace")))
            for raw in r:
                if cancel is not None and cancel.is_set():
                    raise Cancelled("cancelled")
                line = raw.decode(errors="replace").strip()
                if not line.startswith("data: ") or line == "data: [DONE]":
                    continue
                chunk = json.loads(line[6:])
                timings = chunk.get("timings", timings)
                for choice in chunk.get("choices", []):
                    piece = (choice.get("delta") or {}).get("content")
                    if piece:
                        text.append(piece)
                        if on_text:
                            on_text(piece)
            if cancel is not None and cancel.is_set():
                raise Cancelled("cancelled")  # a closed connection can also end the stream quietly
        except (OSError, http.client.HTTPException, ValueError) as e:
            if cancel is not None and cancel.is_set():
                raise Cancelled("cancelled") from e
            if not self.alive():
                # died while answering: most likely out of memory; next load starts one step lower
                with self.lock:
                    idx = next((i for i, p in enumerate(self.ladder()) if p == self.profile), 0)
                    self.skip = max(self.skip, idx + 1)
                    self._stop()
                    self._status = Status("off", self.model_name(), detail="the model server stopped")
                raise BackendError("The model stopped while answering; it will restart with a smaller setting.") from e
            raise BackendError(f"lost the connection to the model: {e}") from e
        finally:
            self.active = None
            conn.close()
        return "".join(text), timings
