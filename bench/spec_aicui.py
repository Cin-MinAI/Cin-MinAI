# SPDX-License-Identifier: GPL-3.0-or-later
"""N-gram drafting in AICUI's own work (PLAN D33: adopted only if quality holds): the Benchmark's coding run
(aicui/benchcode.py — one project grows in stages, every stage judged by our tests, never the model's word) with the
same model and context, once without drafting and once with it. Nothing goes to the Benchmark's store.

    python3 bench/spec_aicui.py --server-dir DIR --model M.gguf --name 9b [--configs none,ngram-mod] [--ctx 32768]
        [--stages 4] [--reserve 200]

Results: bench-results/spec/aicui-NAME-DATE.jsonl (git-ignored) and a summary per config."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from cin_minai.aicui import benchcode  # noqa: E402
from cin_minai.aicui.agent import Agent  # noqa: E402
from cin_minai.inference.llamacpp import LlamaCppBackend  # noqa: E402

CONFIGS = {"none": [], "ngram-mod": ["--spec-type", "ngram-mod"],
           "ngram-simple": ["--spec-type", "ngram-simple", "--spec-ngram-simple-size-n", "4",
                            "--spec-ngram-simple-size-m", "16"]}


def out_dir_of(out) -> Path:
    return Path(out.name).parent


def run(cfg_name: str, a, out) -> list[dict]:
    cfg = {"server_dir": a.server_dir, "build": "cuda", "model": a.model, "model_name": a.name, "context": a.ctx,
           "cache_type": "q8_0", "extra_args": CONFIGS[cfg_name], "desktop_reserve_mib": a.reserve,
           "socket_name": "llama-spec.sock", "request_timeout_s": 1800}
    backend = LlamaCppBackend(cfg, lambda m: None)
    stats = {"tokens": 0, "seconds": 0.0, "draft": 0, "accepted": 0}

    def counted(messages, **kw):
        t0 = time.monotonic()
        text, timings = backend.chat(messages, **kw)
        t = timings[-1] if isinstance(timings, list) and timings else timings or {}
        stats["tokens"] += int(t.get("predicted_n") or 0)
        stats["seconds"] += time.monotonic() - t0
        stats["draft"] += int(t.get("draft_n") or 0)
        stats["accepted"] += int(t.get("draft_n_accepted") or 0)
        return text, timings

    root = tempfile.mkdtemp(prefix="cinminai-spec-")
    project, rows = benchcode.Project(root), []
    try:
        for target in benchcode.TARGETS[:a.stages]:
            before, start, tok0 = project.lines(), time.monotonic(), stats["tokens"]
            gen0 = stats["seconds"]
            task = project.grow(target)
            new_types = len([e for e in project.ents if e["stage"] == project.stage])
            said: list[str] = []
            junior = Agent(root, counted, a.name, "auto", ctx=a.ctx, say=said.append)
            junior.role, junior.max_steps = "junior", min(400, 30 + 6 * new_types)
            err = ""
            try:
                junior.work(task, None)
            except Exception as e:
                err = str(e)[:200]
            res = project.check()
            row = {"config": cfg_name, "stage": project.stage, "target": target, "ok": res["ok"],
                   "total": project.lines(), "added": max(0, project.lines() - before),
                   "steps": 1 + len([s for s in junior.steps if isinstance(s, dict) and s.get("did")]),
                   "seconds": round(time.monotonic() - start), "tokens": stats["tokens"] - tok0,
                   "gen_seconds": round(stats["seconds"] - gen0, 1), "draft": stats["draft"],
                   "accepted": stats["accepted"], "error": err,
                   **{k: res[k] for k in ("new", "held", "changed", "report", "why") if k in res}}
            rows.append(row)
            trace = out_dir_of(out) / f"{Path(out.name).stem}-{cfg_name}-stage{row['stage']}.json"
            trace.write_text(json.dumps({"said": said, "steps": junior.steps}, default=str, ensure_ascii=False,
                                        indent=1), encoding="utf-8")  # what the junior did, to study a failure
            out.write(json.dumps(row) + "\n")
            out.flush()
            print(f"{cfg_name:12} stage {row['stage']}: {'held' if row['ok'] else 'FAILED'}  {row['total']:5} lines "
                  f"(+{row['added']})  {row['steps']} steps  {row['seconds']} s  {row['tokens']} tokens  "
                  f"{row['tokens'] / max(1, row['gen_seconds']):.0f} tok/s" + (f"  {err}" if err else ""), flush=True)
            if not res["ok"]:
                print("   why:", str(res.get("why", ""))[:300], flush=True)
                keep = out_dir_of(out) / f"{Path(out.name).stem}-{cfg_name}-project"
                shutil.copytree(root, keep, dirs_exist_ok=True)  # the project as the failing stage left it
                break
    finally:
        backend.unload()
        shutil.rmtree(root, ignore_errors=True)
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--server-dir", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--configs", default="none,ngram-mod")
    ap.add_argument("--ctx", type=int, default=32768)
    ap.add_argument("--stages", type=int, default=4)
    ap.add_argument("--reserve", type=int, default=0)
    a = ap.parse_args()
    out_dir = ROOT / "bench-results" / "spec"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"aicui-{a.name}-{dt.datetime.now():%Y%m%d-%H%M}.jsonl"
    summary = {}
    with path.open("w", encoding="utf-8") as f:
        for c in a.configs.split(","):
            rows = run(c, a, f)
            summary[c] = rows
    print(f"\n{'config':12} {'held':>5} {'lines':>6} {'minutes':>8} {'tok/s':>6} {'accept':>7}")
    for c, rows in summary.items():
        held = [r for r in rows if r["ok"]]
        secs, toks, gen = sum(r["seconds"] for r in rows), sum(r["tokens"] for r in rows), sum(r["gen_seconds"] for r in rows)
        last = rows[-1] if rows else {}
        acc = f"{last['accepted'] / last['draft']:.0%}" if last.get("draft") else "-"
        print(f"{c:12} {len(held):>5} {max([r['total'] for r in held] or [0]):>6} {secs / 60:>8.1f} "
              f"{toks / max(1, gen):>6.0f} {acc:>7}")
    print(f"results: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
