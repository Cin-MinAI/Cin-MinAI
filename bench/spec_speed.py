# SPDX-License-Identifier: GPL-3.0-or-later
"""Speculative decoding, measured (PLAN D33: adopted only if it helps): the same model and prompts with no drafting,
n-gram drafting (tokens guessed from what's already in the context) and the model's own multi-token-prediction head
(MTP). Greedy decoding, so a speedup must give the same text: each answer is compared with the run without drafting.

Three kinds of prompt, because drafting pays where answers copy from the context:
- diag: the 14 "think it through" cases (training/eval/guide/tasks_think.py), short answers quoting the evidence;
- edit: a whole file given back with one change (AICUI's writes copy most of a file);
- write: new code, nothing to copy.

    python3 bench/spec_speed.py --server PATH/llama-server --model M.gguf --name 27b [--configs none,ngram-simple,mtp]
        [--ngl 99] [--ctx 8192]

Results: bench-results/spec/NAME-DATE.jsonl (git-ignored) and a summary table. Stdlib only.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "training" / "eval" / "guide"))
from cin_minai.diag import think  # noqa: E402
from tasks_think import CASES  # noqa: E402

PORT = 8092
CONFIGS = {
    "none": [],
    "ngram-simple": ["--spec-type", "ngram-simple", "--spec-ngram-simple-size-n", "4",
                     "--spec-ngram-simple-size-m", "16"],
    "ngram-mod": ["--spec-type", "ngram-mod"],
    "ngram-cache": ["--spec-type", "ngram-cache"],
    "mtp": ["--spec-type", "draft-mtp"],
}


def prompts() -> list[tuple[str, str, list[dict], int]]:
    """(kind, id, messages, max_tokens)"""
    out = [("diag", c["id"], think.messages(c["question"], c["evidence"]), 600) for c in CASES]
    src = (ROOT / "src" / "cin_minai" / "diag" / "walk.py").read_text(encoding="utf-8")
    out.append(("edit", "E1", [{"role": "user", "content": "Here is a Python file. Give back the whole file, "
                                "unchanged except one thing: rename KEEP_DAYS to KEEP_WALK_DAYS everywhere. Only the "
                                "file, no comments before or after.\n\n```python\n" + src + "```"}], 4096))
    src2 = (ROOT / "src" / "cin_minai" / "daemon" / "offline.py").read_text(encoding="utf-8").split("WORDS = {")[0]
    out.append(("edit", "E2", [{"role": "user", "content": "Give back this Python code whole, with type hints "
                                "unchanged, but change CONNECT_S from 90 to 120 and say so in its comment. Only the "
                                "code.\n\n```python\n" + src2 + "```"}], 2048))
    out.append(("write", "W1", [{"role": "user", "content": "Write a Python function that reads /proc/meminfo and "
                                 "returns total, available and swap-used memory in MiB as a dict, with a docstring "
                                 "and error handling. Only the code."}], 1024))
    out.append(("write", "W2", [{"role": "user", "content": "Write a bash script that lists the five largest "
                                 "folders in the home directory with their sizes, sorted, with comments. Only the "
                                 "script."}], 1024))
    return out


def start(server: str, model: str, ngl: str, ctx: int, extra: list[str]) -> subprocess.Popen:
    cmd = [server, "-m", model, "--host", "127.0.0.1", "--port", str(PORT), "-c", str(ctx), "-ngl", ngl,
           "-fa", "on", "--jinja", "-np", "1"] + extra
    log = open(f"/tmp/spec-{os.getpid()}.log", "w")
    p = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT)
    for _ in range(240):
        time.sleep(1)
        if p.poll() is not None:
            raise RuntimeError(f"server exited: see {log.name}")
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=2) as r:
                if b"ok" in r.read():
                    return p
        except OSError:
            pass
    p.kill()
    raise RuntimeError("server didn't start")


def ask(msgs: list[dict], max_tokens: int) -> dict:
    body = {"messages": msgs, "max_tokens": max_tokens, "temperature": 0, "stream": False,
            "chat_template_kwargs": {"enable_thinking": False}}
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}/v1/chat/completions", json.dumps(body).encode(),
                                 {"Content-Type": "application/json"})
    t0 = time.monotonic()
    with urllib.request.urlopen(req, timeout=900) as r:
        out = json.load(r)
    took = time.monotonic() - t0
    t = out.get("timings", {})
    return {"text": out["choices"][0]["message"].get("content") or "", "seconds": round(took, 2),
            "tokens": t.get("predicted_n"), "tok_s": round(t.get("predicted_per_second") or 0, 1),
            "draft": t.get("draft_n"), "accepted": t.get("draft_n_accepted")}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--configs", default="none,ngram-simple,ngram-mod,mtp")
    ap.add_argument("--ngl", default="99")
    ap.add_argument("--ctx", type=int, default=8192)
    a = ap.parse_args()
    out_dir = ROOT / "bench-results" / "spec"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{a.name}-{dt.datetime.now():%Y%m%d-%H%M}.jsonl"
    ps = prompts()
    base: dict[str, str] = {}
    table = {}
    with path.open("w", encoding="utf-8") as f:
        for cfg in a.configs.split(","):
            try:
                srv = start(a.server, a.model, a.ngl, a.ctx, CONFIGS[cfg])
            except RuntimeError as e:
                print(f"{cfg}: {e}")
                continue
            try:
                for kind, pid, msgs, mx in ps:
                    r = ask(msgs, mx)
                    if cfg == "none":
                        base[pid] = r["text"]
                    r.update(config=cfg, kind=kind, id=pid, same=(r["text"] == base.get(pid)))
                    f.write(json.dumps({k: v for k, v in r.items() if k != "text"}) + "\n")
                    f.flush()
                    row = table.setdefault((cfg, kind), {"tokens": 0, "seconds": 0.0, "draft": 0, "acc": 0, "n": 0,
                                                         "same": 0})
                    row["tokens"] += r["tokens"] or 0
                    row["seconds"] += r["seconds"]
                    row["draft"] += r["draft"] or 0
                    row["acc"] += r["accepted"] or 0
                    row["n"] += 1
                    row["same"] += bool(r["same"])
                    print(f"{cfg:13} {kind:5} {pid:3} {r['tok_s']:6.1f} tok/s  {r['seconds']:6.1f}s  "
                          f"drafted {r['draft']} accepted {r['accepted']}  same={r['same']}", flush=True)
            finally:
                srv.terminate()
                srv.wait(30)
    print(f"\n{'config':13} {'kind':5} {'tok/s':>7} {'accept':>7} {'same':>6}")
    for (cfg, kind), r in table.items():
        acc = f"{r['acc'] / r['draft']:.0%}" if r["draft"] else "-"
        print(f"{cfg:13} {kind:5} {r['tokens'] / r['seconds']:7.1f} {acc:>7} {r['same']:>3}/{r['n']}")
    print(f"results: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
