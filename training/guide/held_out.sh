#!/usr/bin/env bash
# Cycle 0's one-shot held-out eval (training/guide/README.md, phase 5; D31). Run ONCE, from Git Bash on the
# dev PC, on the three contenders Ian picked (2026-09-27): stock Qwen3.5-4B, tuned Qwen3.5-4B (run HO),
# stock Gemma 4 E2B (its tune, run GO, scored 50 % public and was set aside for this cycle).
# Same server settings and prompt v2 as the public eval; the 1080 Ti on the Mint box; our port 18090.
# Before running, the training data was checked against these tasks: max 3-gram similarity 0.25, none >= 0.5.
# Results: C:\Users\Ian\cinminai-train-out\held-out\ (and ~/cin-minai/eval-guide/bench-results/guide/).
set -u
MINT=mint@192.168.5.70
REPO=/c/Users/Ian/Cin-minAI
OUT=/c/Users/Ian/cinminai-train-out/held-out
mkdir -p "$OUT"
scp -q "$REPO/training/eval/guide/run_eval.py" "$REPO/training/eval/guide/labels.json" $MINT:cin-minai/eval-guide/
scp -q "$REPO/training/eval/guide-hidden/tasks.py" $MINT:cin-minai/eval-guide-hidden/tasks.py

heldout() {  # name, model GGUF, [adapter]
  local name=$1 gguf=$2 lora=${3:-}
  local loraarg=""; [ -n "$lora" ] && loraarg="--lora ~/cin-minai/adapters/$lora"
  ssh $MINT "cd ~/cin-minai/eval-guide &&
    while [ \$(nvidia-smi --query-compute-apps=used_memory --format=csv,noheader,nounits | awk '{s+=\$1} END {print s+0}') -gt 512 ]; do sleep 60; done
    ~/cin-minai/llama.cpp/build-cuda/bin/llama-server --host 127.0.0.1 --port 18090 --model ~/cin-minai/models/$gguf $loraarg --ctx-size 8192 --gpu-layers all --cache-type-k q8_0 --cache-type-v q8_0 --flash-attn on --fit off --parallel 1 --reasoning off --alias heldout-$name > bench-results/guide/server-heldout-$name.log 2>&1 &
    pid=\$!; for i in \$(seq 120); do curl -sf http://127.0.0.1:18090/health >/dev/null && break; sleep 1; done
    python3 run_eval.py --prompt v2 --tasks ../eval-guide-hidden/tasks.py --url http://127.0.0.1:18090 --model heldout-$name --out bench-results/guide/heldout-$name.jsonl > bench-results/guide/heldout-$name.txt 2>&1
    kill \$pid; wait \$pid 2>/dev/null"
  scp -q "$MINT:cin-minai/eval-guide/bench-results/guide/heldout-$name.*" "$OUT/"
  echo "$(date '+%F %T') $name  $(grep -m1 '^ALL' "$OUT/heldout-$name.txt")" >> "$OUT/held-out.log"
}

heldout stock-qwen Qwen3.5-4B-Q4_K_M.gguf
heldout HO-qwen Qwen3.5-4B-Q4_K_M.gguf sweep-HO-lora.gguf
heldout stock-gemma gemma-4-E2B_q4_0-it.gguf
echo "$(date '+%F %T') HELD-OUT DONE" >> "$OUT/held-out.log"
