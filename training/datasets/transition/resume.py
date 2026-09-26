#!/usr/bin/env python3
"""Resume an interrupted corpus run (power cut, reboot) without redoing finished work.

Reads the generator's progress log(s) — one line per finished (topic, language) batch — and prints the
generate.py commands for the batches that never finished, appending to the same output directory.
Examples are flushed one by one, so at most the example in progress is lost; a half-written last line
is dropped at merge time. Duplicates across the two sessions are removed at merge time too.

    python3 resume.py --log full-rest.log --out full-rest --per 7 --seed 21 \
        --topics install,uninstall,...            # the topic list the run was started with
    (prints commands; add --run to run them one after another)
"""

import argparse
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "kb"))
import transition as KB  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", required=True, action="append", help="progress log(s) of the interrupted run")
    ap.add_argument("--out", required=True), ap.add_argument("--topics", required=True)
    ap.add_argument("--per", type=int, required=True), ap.add_argument("--seed", type=int, default=21)
    ap.add_argument("--url", default="http://127.0.0.1:18091"), ap.add_argument("--model", default="Qwen3-14B-Q4_K_M")
    ap.add_argument("--run", action="store_true")
    o = ap.parse_args()
    done = set()
    for log in o.log:
        if os.path.exists(log):
            for line in open(log, encoding="utf-8", errors="ignore"):
                m = re.match(r"^\d\d:\d\d:\d\d (\S+)\s+(\w\w)\s+accepted", line)
                if m:
                    done.add((m.group(1), m.group(2)))
    wanted = [t for t in KB.TOPICS if t["id"] in o.topics.split(",")]
    todo = [(t["id"], lang) for t in wanted for lang in t.get("langs", KB.ALL) if (t["id"], lang) not in done]
    print(f"# finished batches: {len(done)}; still to do: {len(todo)}", flush=True)
    gen = os.path.join(HERE, "generate.py")
    for i, (topic, lang) in enumerate(todo):
        cmd = [sys.executable, gen, "--url", o.url, "--model", o.model, "--out", o.out, "--topics", topic,
               "--langs", lang, "--per", str(o.per), "--seed", str(o.seed + i)]
        print(" ".join(cmd), flush=True)
        if o.run:
            with open(o.out + "-resume.log", "a") as log:
                subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, check=False)


if __name__ == "__main__":
    main()
