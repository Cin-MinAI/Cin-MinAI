# SPDX-License-Identifier: GPL-3.0-or-later
"""Thinking on vs off for "Think it through" (PLAN D7, D33: adopted only if it helps, measured). Runs each case of
tasks_think.py with the request the daemon would send (src/cin_minai/diag/think.py) in each mode, and scores
mechanically: the cause named, nothing destructive, short, not cut off; with the time each took.

    python3 think_eval.py --url http://127.0.0.1:8091 [--modes plain,think,think-sampled] [--only K1,W1] [-v]

Results: one JSON line per case and mode in bench-results/think/ (git-ignored). Stdlib only.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / "src"))
from cin_minai.diag import think  # noqa: E402

from tasks_think import CASES, FORBIDDEN  # noqa: E402

MODES = {
    "plain": {"think": False, "max_tokens": 600, "sampling": {"temperature": 0}},
    "think": {"think": True, "max_tokens": 4096, "sampling": {"temperature": 0}},
    # Qwen's own advice for thinking (greedy decoding can loop while it thinks)
    "think-sampled": {"think": True, "max_tokens": 4096,
                      "sampling": {"temperature": 0.6, "top_p": 0.95, "top_k": 20, "seed": 1}},
}
MAX_WORDS = 220  # the prompt asks for 180; a little slack


def ask(url: str, model: str, msgs: list[dict], mode: dict) -> dict:
    body = {"model": model, "messages": msgs, "max_tokens": mode["max_tokens"], "stream": False,
            "chat_template_kwargs": {"enable_thinking": mode["think"]}, **mode["sampling"]}
    req = urllib.request.Request(url.rstrip("/") + "/v1/chat/completions", json.dumps(body).encode(),
                                 {"Content-Type": "application/json"})
    t0 = time.monotonic()
    with urllib.request.urlopen(req, timeout=900) as r:
        out = json.load(r)
    took = time.monotonic() - t0
    choice = out["choices"][0]
    content = choice["message"].get("content") or ""
    reasoning = choice["message"].get("reasoning_content") or ""
    m = re.search(r"<think>(.*?)</think>", content, re.S)  # a server that leaves the thinking in the text
    if m:
        reasoning, content = reasoning or m.group(1), content.replace(m.group(0), "")
    return {"reply": content.strip(), "reasoning_chars": len(reasoning), "finish": choice.get("finish_reason"),
            "tokens": out.get("usage", {}).get("completion_tokens"), "seconds": round(took, 1)}


def score(case: dict, got: dict) -> list[str]:
    fails = []
    reply = got["reply"]
    if got["finish"] == "length":
        fails.append("cut off")
    if not reply:
        fails.append("no answer")
    if not any(re.search(p, reply, re.I) for p in case["cause"]):
        fails.append("cause not named")
    wrong = [p for p in case.get("not", []) if re.search(p, reply, re.I)]  # a case's own wrong answers
    if wrong:
        fails.append(f"says {wrong}")
    bad = [p for p in FORBIDDEN if re.search(p, reply, re.I)]
    if bad:
        fails.append(f"destructive: {bad}")
    if len(reply.split()) > MAX_WORDS:
        fails.append(f"long: {len(reply.split())} words")
    return fails


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--model", default="guide")
    ap.add_argument("--modes", default="plain,think,think-sampled")
    ap.add_argument("--only", default="")
    ap.add_argument("--max-think", type=int, default=4096, help="tokens a thinking answer may use, thinking included")
    ap.add_argument("-v", action="store_true")
    a = ap.parse_args()
    only = set(filter(None, a.only.split(",")))
    cases = [c for c in CASES if not only or c["id"] in only]
    out_dir = HERE / "bench-results" / "think"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{a.model}-{dt.datetime.now():%Y%m%d-%H%M}.jsonl"
    summary = {}
    with out.open("w", encoding="utf-8") as f:
        for name in a.modes.split(","):
            mode = dict(MODES[name], max_tokens=a.max_think) if MODES[name]["think"] else MODES[name]
            for c in cases:
                got = ask(a.url, a.model, think.messages(c["question"], c["evidence"]), mode)
                fails = score(c, got)
                f.write(json.dumps({"mode": name, "id": c["id"], "source": c["source"], "fails": fails, **got},
                                   ensure_ascii=False) + "\n")
                f.flush()  # a run cut short keeps what it did
                s = summary.setdefault(name, {"pass": 0, "n": 0, "seconds": 0.0})
                s["n"] += 1
                s["pass"] += not fails
                s["seconds"] += got["seconds"]
                print(f"{name:14} {c['id']:3} {'PASS' if not fails else 'FAIL ' + '; '.join(fails):40} "
                      f"{got['seconds']:6.1f}s  {got['tokens']} tokens, thinking {got['reasoning_chars']} chars")
                if a.v:
                    print("   ", got["reply"].replace("\n", "\n    "))
    for name, s in summary.items():
        print(f"{name:14} {s['pass']}/{s['n']} pass, {s['seconds'] / s['n']:.1f} s per answer")
    print(f"results: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
