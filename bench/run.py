#!/usr/bin/env python3
"""Portable llama.cpp bakeoff harness for Cin-MinAI (Python 3.12 stdlib only)."""

from __future__ import annotations

import argparse
import ast
import datetime as dt
import hashlib
import json
import os
import pathlib
import platform
import re
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request


ROOT = pathlib.Path.home() / "cin-minai"
DEFAULT_SERVERS = {
    "cuda": ROOT / "llama.cpp/build-cuda/bin/llama-server",
    "vulkan": ROOT / "llama.cpp/build-vulkan/bin/llama-server",
    "cpu": ROOT / "llama.cpp/build-cpu/bin/llama-server",
}
DEFAULT_SCHEMA_SOURCE = ROOT / "spikes/libreoffice/assist.py"
GPU_BUILDS = {"cuda", "vulkan"}
QWEN_IDLE_VRAM_MIB = 512


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--model", required=True, type=pathlib.Path)
    p.add_argument("--quant", required=True)
    p.add_argument("--build", required=True, choices=("cuda", "vulkan", "cpu"))
    p.add_argument("--server", type=pathlib.Path, help="override llama-server path")
    p.add_argument("--context", type=int, default=8192)
    p.add_argument("--ngl", default="all", help="GPU layers: integer, auto, or all")
    p.add_argument("--port", type=int, default=18080)
    p.add_argument("--threads", type=int, default=max(1, (os.cpu_count() or 4) // 2))
    p.add_argument("--pin", action="store_true",
                   help="pin one compute thread per physical core (--cpu-mask/--cpu-strict); threads = cores")
    p.add_argument("--poll", type=int, help="llama-server --poll level (0 = don't busy-wait on the GPU)")
    p.add_argument("--budget-gb", type=float)
    p.add_argument("--json-calls", type=int, default=50)
    p.add_argument("--schema-source", type=pathlib.Path, default=DEFAULT_SCHEMA_SOURCE)
    p.add_argument("--results-root", type=pathlib.Path, default=ROOT / "bench-results")
    p.add_argument("--startup-timeout", type=float, default=180)
    p.add_argument("--request-timeout", type=float, default=300)
    return p.parse_args()


def run_text(cmd: list[str], timeout: float = 15) -> str:
    return subprocess.run(cmd, check=True, text=True, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, timeout=timeout).stdout.strip()


def http_json(url: str, body: dict | None = None, timeout: float = 300) -> dict:
    data = None if body is None else json.dumps(body).encode()
    headers = {"Content-Type": "application/json"} if data is not None else {}
    request = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def port_is_free(port: int) -> bool:
    with socket.socket() as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def nvidia_snapshot() -> dict | None:
    try:
        line = run_text([
            "nvidia-smi", "--query-gpu=name,memory.used,memory.free,memory.total",
            "--format=csv,noheader,nounits",
        ], timeout=5).splitlines()[0]
        name, used, free, total = [part.strip() for part in line.split(",", 3)]
        return {"name": name, "used_mib": int(used), "free_mib": int(free),
                "total_mib": int(total)}
    except (FileNotFoundError, subprocess.SubprocessError, ValueError, IndexError):
        return None


def nvidia_processes() -> dict[int, dict]:
    try:
        output = run_text([
            "nvidia-smi", "--query-compute-apps=pid,process_name,used_gpu_memory",
            "--format=csv,noheader,nounits",
        ], timeout=5)
    except (FileNotFoundError, subprocess.SubprocessError):
        return {}
    processes = {}
    for line in output.splitlines():
        parts = [part.strip() for part in line.split(",", 2)]
        if len(parts) != 3:
            continue
        try:
            processes[int(parts[0])] = {"name": parts[1], "vram_mib": int(parts[2])}
        except ValueError:
            continue
    return processes


def qwen_main_pid() -> int:
    try:
        value = run_text([
            "systemctl", "--user", "show", "qwen14b.service", "-p", "MainPID", "--value"
        ], timeout=5)
        return int(value or 0)
    except (FileNotFoundError, subprocess.SubprocessError, ValueError):
        return 0


def gpu_preflight() -> dict:
    snapshot = nvidia_snapshot()
    if snapshot is None:
        raise RuntimeError("nvidia-smi is unavailable; refusing a GPU run")
    processes = nvidia_processes()
    qwen_pid = qwen_main_pid()
    blockers = []
    for pid, info in processes.items():
        if pid == qwen_pid and info["vram_mib"] <= QWEN_IDLE_VRAM_MIB:
            continue
        blockers.append({"pid": pid, **info})
    if blockers:
        raise RuntimeError(f"GPU is busy; refusing run: {blockers}")
    return {"gpu": snapshot, "compute_processes": processes, "qwen_main_pid": qwen_pid,
            "qwen_model_loaded": bool(qwen_pid in processes and
                                      processes[qwen_pid]["vram_mib"] > QWEN_IDLE_VRAM_MIB)}


def process_rss_bytes(pid: int) -> int:
    try:
        for line in pathlib.Path(f"/proc/{pid}/status").read_text().splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) * 1024
    except (FileNotFoundError, ProcessLookupError, PermissionError, ValueError):
        pass
    return 0


class ResourceMonitor:
    def __init__(self, pid: int):
        self.pid = pid
        self.peak_rss_bytes = 0
        self.peak_process_vram_mib = 0
        self.peak_card_used_mib = 0
        self.minimum_card_free_mib: int | None = None
        self.samples = 0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=3)

    def _loop(self) -> None:
        while not self._stop.wait(0.2):
            self.peak_rss_bytes = max(self.peak_rss_bytes, process_rss_bytes(self.pid))
            snapshot = nvidia_snapshot()
            if snapshot:
                self.peak_card_used_mib = max(self.peak_card_used_mib, snapshot["used_mib"])
                free = snapshot["free_mib"]
                self.minimum_card_free_mib = (free if self.minimum_card_free_mib is None
                                              else min(self.minimum_card_free_mib, free))
            info = nvidia_processes().get(self.pid)
            if info:
                self.peak_process_vram_mib = max(self.peak_process_vram_mib, info["vram_mib"])
            self.samples += 1

    def as_dict(self) -> dict:
        return {
            "peak_process_rss_bytes": self.peak_rss_bytes,
            "peak_process_vram_mib": self.peak_process_vram_mib,
            "peak_card_used_mib": self.peak_card_used_mib,
            "minimum_card_free_mib": self.minimum_card_free_mib,
            "samples": self.samples,
        }


def load_libreoffice_schemas(source: pathlib.Path):
    """Load only constants and schema/prompt functions, avoiding assist.py's user config read."""
    tree = ast.parse(source.read_text(), filename=str(source))
    wanted_assignments = {"S", "I", "CELL", "TOOLS", "ANSWER"}
    nodes = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            names = {part.id for target in node.targets for part in ast.walk(target)
                     if isinstance(part, ast.Name)}
            if names & wanted_assignments:
                nodes.append(node)
        elif isinstance(node, ast.FunctionDef) and node.name in {"schema", "prompt"}:
            nodes.append(node)
    namespace = {"json": json}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), "exec"), namespace)
    return namespace["schema"], namespace["prompt"]


def schema_accepts(value, spec: dict) -> bool:
    if "const" in spec and value != spec["const"]:
        return False
    if "oneOf" in spec:
        return sum(schema_accepts(value, item) for item in spec["oneOf"]) == 1
    if "anyOf" in spec:
        return any(schema_accepts(value, item) for item in spec["anyOf"])
    kind = spec.get("type")
    if kind == "object":
        if not isinstance(value, dict):
            return False
        props = spec.get("properties", {})
        if any(key not in value for key in spec.get("required", [])):
            return False
        if spec.get("additionalProperties") is False and any(key not in props for key in value):
            return False
        return all(key not in props or schema_accepts(item, props[key])
                   for key, item in value.items())
    if kind == "array":
        return isinstance(value, list) and all(schema_accepts(item, spec.get("items", {}))
                                               for item in value)
    if kind == "string":
        return isinstance(value, str)
    if kind == "integer":
        return (isinstance(value, int) and not isinstance(value, bool) and
                value >= spec.get("minimum", value))
    if kind == "number":
        return (isinstance(value, (int, float)) and not isinstance(value, bool) and
                value >= spec.get("minimum", value))
    return True


def synthetic_case(index: int) -> tuple[str, dict, str]:
    cases = [
        ("writer", {"document": {"type": "writer", "title": "Notes", "paragraphs": 8},
                    "selection": "draft sentence", "outline": []},
         "Replace the selected sentence with: Final sentence."),
        ("writer", {"document": {"type": "writer", "title": "Report", "paragraphs": 20},
                    "selection": "", "outline": [{"level": 1, "text": "Summary", "paragraph": 0}]},
         "Read paragraphs 3 through 5."),
        ("calc", {"document": {"type": "calc", "sheets": ["Sheet1"], "active": "Sheet1"},
                  "selection": {"range": "B2:B7"}, "used_range": "A1:C8"},
         "Put the average of B2:B7 into C8."),
        ("calc", {"document": {"type": "calc", "sheets": ["Budget"], "active": "Budget"},
                  "selection": {"range": "A1:D12"}, "used_range": "A1:D12"},
         "Read the selected cells."),
        ("impress", {"document": {"type": "impress", "slides": 5}, "slides": []},
         "Read the text on slide 3."),
        ("impress", {"document": {"type": "impress", "slides": 5}, "slides": []},
         "Set slide 2's title to Results and body to Fast, local, private."),
    ]
    return cases[index % len(cases)]


def make_approx_4k_prompt(base_url: str, timeout: float) -> tuple[str, int]:
    seed = ("Cin-MinAI is a local desktop assistant. It helps with documents, terminal tasks, "
            "and system guidance while preserving user control and privacy. ")
    low, high = 1, 2000
    best = (seed, 0)
    while low <= high:
        count = (low + high) // 2
        text = seed * count
        tokenized = http_json(base_url + "/tokenize", {"content": text}, timeout)
        n_tokens = len(tokenized.get("tokens", []))
        if abs(n_tokens - 4000) < abs(best[1] - 4000):
            best = (text, n_tokens)
        if n_tokens < 4000:
            low = count + 1
        elif n_tokens > 4000:
            high = count - 1
        else:
            return text, n_tokens
    return best


def stream_benchmark(base_url: str, prompt: str, timeout: float) -> dict:
    body = {"prompt": prompt, "n_predict": 128, "temperature": 0, "stream": True,
            "cache_prompt": False}
    request = urllib.request.Request(base_url + "/completion", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
    started = time.monotonic()
    first_token_at = None
    final = {}
    generated = []
    with urllib.request.urlopen(request, timeout=timeout) as response:
        for raw in response:
            line = raw.decode(errors="replace").strip()
            if not line.startswith("data: "):
                continue
            payload = line[6:]
            if payload == "[DONE]":
                break
            chunk = json.loads(payload)
            content = chunk.get("content", "")
            if content and first_token_at is None:
                first_token_at = time.monotonic()
            generated.append(content)
            if chunk.get("stop") or chunk.get("timings"):
                final = chunk
    finished = time.monotonic()
    timings = final.get("timings", {})
    return {
        "time_to_first_token_s": None if first_token_at is None else first_token_at - started,
        "request_elapsed_s": finished - started,
        "prompt_tokens": timings.get("prompt_n"),
        "generated_tokens": timings.get("predicted_n"),
        "prompt_tok_s": timings.get("prompt_per_second"),
        "generation_tok_s": timings.get("predicted_per_second"),
        "generated_text_sha256": hashlib.sha256("".join(generated).encode()).hexdigest(),
    }


def json_rate(base_url: str, schema_source: pathlib.Path, count: int, timeout: float) -> dict:
    schema_fn, prompt_fn = load_libreoffice_schemas(schema_source)
    parsed = valid = 0
    failures = []
    elapsed = []
    for index in range(count):
        kind, context, user_request = synthetic_case(index)
        spec = schema_fn(kind)
        body = {
            "model": "local",
            "temperature": 0,
            "max_tokens": 128,
            "messages": [
                {"role": "system", "content": prompt_fn(kind, context)},
                {"role": "user", "content": user_request},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "call", "schema": spec},
            },
        }
        started = time.monotonic()
        try:
            response = http_json(base_url + "/v1/chat/completions", body, timeout)
            text = response["choices"][0]["message"]["content"]
            value = json.loads(text)
            parsed += 1
            if schema_accepts(value, spec):
                valid += 1
            else:
                failures.append({"index": index, "kind": kind, "error": "schema mismatch"})
        except Exception as exc:  # each failed request counts; continue the 50-call sample
            failures.append({"index": index, "kind": kind,
                             "error": f"{type(exc).__name__}: {exc}"[:300]})
        elapsed.append(time.monotonic() - started)
    return {
        "requested": count,
        "json_parse_valid": parsed,
        "schema_valid": valid,
        "valid_json_rate": None if count == 0 else valid / count,
        "elapsed_s": sum(elapsed),
        "mean_call_s": None if not elapsed else sum(elapsed) / len(elapsed),
        "failures": failures,
        "schema_source": str(schema_source),
        "schema_source_sha256": hashlib.sha256(schema_source.read_bytes()).hexdigest(),
    }


def stop_server(process: subprocess.Popen | None) -> None:
    if process is None or process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=15)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass


def wait_healthy(base_url: str, process: subprocess.Popen, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    last_error = "not attempted"
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"llama-server exited during startup with code {process.returncode}")
        try:
            health = http_json(base_url + "/health", timeout=3)
            if health.get("status") == "ok":
                return
            last_error = repr(health)
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
        time.sleep(1)
    raise TimeoutError(f"health check timed out: {last_error}")


def physical_core_mask() -> tuple[str, int]:
    """Hex CPU mask with the first logical CPU of each physical core (from sysfs), and the core count.

    SMT siblings share a core's execution units, so for llama.cpp's compute threads one thread per
    physical core is usually fastest; letting the scheduler place them can put two on one core."""
    first: dict[tuple[str, str], int] = {}
    for d in sorted(pathlib.Path("/sys/devices/system/cpu").glob("cpu[0-9]*"), key=lambda p: int(p.name[3:])):
        topo = d / "topology"
        if not (topo / "core_id").exists():
            continue
        key = ((topo / "physical_package_id").read_text().strip(), (topo / "core_id").read_text().strip())
        first.setdefault(key, int(d.name[3:]))
    mask = sum(1 << cpu for cpu in first.values())
    return hex(mask), len(first)


def machine_name() -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", platform.node() or "unknown")


def append_result(root: pathlib.Path, result: dict) -> pathlib.Path:
    directory = root / machine_name()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{dt.date.today().isoformat()}.jsonl"
    line = json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        os.write(fd, line.encode())
    finally:
        os.close(fd)
    return path


def main() -> int:
    args = parse_args()
    server = (args.server or DEFAULT_SERVERS[args.build]).expanduser().resolve()
    model = args.model.expanduser().resolve()
    started_at = dt.datetime.now(dt.timezone.utc)
    result = {
        "schema_version": 1,
        "status": "failed",
        "started_at": started_at.isoformat(),
        "machine": machine_name(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "build": args.build,
        "server": str(server),
        "model": str(model),
        "model_size_bytes": model.stat().st_size if model.is_file() else None,
        "quant": args.quant,
        "context": args.context,
        "ngl": "0" if args.build == "cpu" else str(args.ngl),
        "kv_cache": "q8_0",
        "flash_attention": "on",
        "parallel_slots": 1,
        "reasoning": "off",
        "port": args.port,
        "budget_gb": args.budget_gb,
    }
    process = None
    monitor = None
    log_path = None
    try:
        if args.port == 8080:
            raise ValueError("port 8080 is reserved for qwen14b.service")
        if not port_is_free(args.port):
            raise RuntimeError(f"port {args.port} is already in use")
        if not model.is_file():
            raise FileNotFoundError(model)
        if not os.access(server, os.X_OK):
            raise FileNotFoundError(f"llama-server is missing or not executable: {server}")
        result["server_version"] = run_text([str(server), "--version"], timeout=15)
        result["gpu_before"] = nvidia_snapshot()
        if args.build in GPU_BUILDS:
            result["gpu_preflight"] = gpu_preflight()

        ngl = "0" if args.build == "cpu" else str(args.ngl)
        command = [
            str(server), "--host", "127.0.0.1", "--port", str(args.port),
            "--model", str(model), "--ctx-size", str(args.context),
            "--gpu-layers", ngl, "--cache-type-k", "q8_0", "--cache-type-v", "q8_0",
            "--flash-attn", "on", "--fit", "off", "--metrics",
            "--parallel", "1", "--reasoning", "off",
            "--threads", str(args.threads), "--threads-batch", str(args.threads),
        ]
        if args.build == "cpu":
            command += ["--device", "none"]
        if args.pin:
            mask, cores = physical_core_mask()
            command += ["--cpu-mask", mask, "--cpu-strict", "1", "--cpu-mask-batch", mask, "--cpu-strict-batch", "1"]
            command[command.index("--threads") + 1] = command[command.index("--threads-batch") + 1] = str(cores)
        if args.poll is not None:
            command += ["--poll", str(args.poll)]
        result["command"] = command
        log_dir = args.results_root / machine_name() / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        stamp = started_at.strftime("%Y%m%dT%H%M%SZ")
        log_path = log_dir / f"{stamp}-{args.build}-{model.stem}.log"
        with log_path.open("w") as log:
            process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
                                       text=True, start_new_session=True)
        result["server_log"] = str(log_path)
        monitor = ResourceMonitor(process.pid)
        monitor.start()
        base_url = f"http://127.0.0.1:{args.port}"
        wait_healthy(base_url, process, args.startup_timeout)
        prompt, measured_tokens = make_approx_4k_prompt(base_url, args.request_timeout)
        result["benchmark_prompt_tokenized_count"] = measured_tokens
        result["throughput"] = stream_benchmark(base_url, prompt, args.request_timeout)
        result["json_schema"] = json_rate(base_url, args.schema_source,
                                           args.json_calls, args.request_timeout)
        result["status"] = "ok"
        stop_server(process)
        process = None
        if monitor:
            monitor.stop()
            result["resources"] = monitor.as_dict()
            monitor = None
        result["server_log_tail"] = log_path.read_text(errors="replace").splitlines()[-30:]

        peak_mib = result.get("resources", {}).get("peak_process_vram_mib", 0)
        if args.budget_gb is not None:
            # The PLAN's 6 GB guide mode gives the model process 4.7 GiB at 8K.
            limit_gib = args.budget_gb - 0.5 - 0.8
            limit_mib = int(limit_gib * 1024)
            result["guide_budget"] = {
                "card_budget_gb": args.budget_gb,
                "process_limit_gib": limit_gib,
                "process_limit_mib": limit_mib,
                "context_required": 8192,
                "context_ok": args.context == 8192,
                "peak_process_vram_mib": peak_mib,
                "pass": args.context == 8192 and peak_mib <= limit_mib,
            }
    except BaseException as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        if log_path and log_path.exists():
            result["server_log_tail"] = log_path.read_text(errors="replace").splitlines()[-50:]
    finally:
        stop_server(process)
        if monitor:
            monitor.stop()
            result["resources"] = monitor.as_dict()
        result["gpu_after"] = nvidia_snapshot()
        result["finished_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
        result["elapsed_s"] = (dt.datetime.now(dt.timezone.utc) - started_at).total_seconds()
        output_path = append_result(args.results_root, result)
        print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
        print(f"result_jsonl={output_path}", file=sys.stderr)
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
