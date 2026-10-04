#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Guide cycle 1, one training run on the dev PC (WSL, RTX 4070): sample the mix -> train the LoRA (HO's recipe)
# -> GGUF adapter -> merged, quantized file (merge_quantize.sh) -> the eval sets with prompt v2.2, on the same
# GPU build for the run and for the shipped guide (HO), so the two are compared like for like.
#
#   wsl -d Ubuntu-24.04 -e bash /mnt/c/Users/Ian/Cin-minAI/training/guide/cycle1.sh RUN PRESET [eval-only]
#   e.g. cycle1.sh C1 c1         (step 1: HO's mix + how-tos about the machine and open-an-app turns)
#
# Results: ~/cinminai-train-out/cycle1/<RUN>-<set>.{txt,jsonl} and HO-<set>.* next to them.
set -euo pipefail
RUN=${1:?run name} PRESET=${2:?mix preset} MODE=${3:-all}
REPO=/mnt/c/Users/Ian/Cin-minAI
EV=$REPO/training/eval
OUT=~/cinminai-train-out/cycle1
mkdir -p "$OUT"
cd ~/cinminai-train
# the CUDA 12 runtime comes from the training venv (WSL has none system-wide); llama.cpp is the pinned 7fe450e
V=$PWD/.venv/lib/python3.12/site-packages/nvidia
export LD_LIBRARY_PATH=$V/cuda_runtime/lib:$V/cublas/lib
LS=~/cinminai-build/src/llama.cpp/build/bin/llama-server
[ "$(git -C ~/cinminai-build/src/llama.cpp rev-parse --short=7 HEAD)" = 7fe450e ] || { echo "server build is not 7fe450e"; exit 1; }

if [ "$MODE" = all ]; then
  .venv/bin/python $REPO/training/guide/make_session_mix.py --turns 360 --preset "$PRESET" --office 115 --seed 7 \
    --out data/mix-$RUN.jsonl | tee "$OUT/$RUN-mix.json"
  .venv/bin/python $REPO/training/guide/train_lora.py --base base/Qwen3.5-4B --data data/mix-$RUN.jsonl \
    --out runs/sweep-$RUN --epochs 1 --lr 5e-5 --targets q_proj,k_proj,v_proj,o_proj,gate_proj,up_proj,down_proj \
    > "$OUT/$RUN-train.log" 2>&1
  .venv/bin/python llama.cpp/convert_lora_to_gguf.py runs/sweep-$RUN/adapter --base base/Qwen3.5-4B \
    --outfile out/sweep-$RUN-lora.gguf --outtype f16 >> "$OUT/$RUN-train.log" 2>&1
  cp runs/sweep-$RUN/run.json "$OUT/$RUN-run.json"
  bash $REPO/training/guide/merge_quantize.sh "$RUN" Qwen3.5-4B Q4_K_M > "$OUT/$RUN-merge.log" 2>&1
fi

evaluate() {  # name, GGUF
  local name=$1 gguf=$2
  $LS -m "$gguf" --port 18090 -ngl 99 -c 8192 -fa on -ctk q8_0 -ctv q8_0 --jinja --parallel 1 --alias "$name" \
    > "$OUT/$name-server.log" 2>&1 &
  local pid=$!
  for i in $(seq 120); do curl -sf localhost:18090/health >/dev/null && break; sleep 1; done
  ! grep -q "no usable GPU" "$OUT/$name-server.log" || { echo "$name: not on the GPU"; kill $pid; exit 1; }
  for t in guide/tasks guide/tasks_create guide/tasks_web guide/tasks_diag guide-interp/tasks; do
    local set=$(echo "$t" | tr / -)
    ( cd $EV/guide && PYTHONDONTWRITEBYTECODE=1 python3 run_eval.py --prompt v2.2 --tasks "$EV/$t.py" \
        --url http://127.0.0.1:18090 --model "$name" --out "$OUT/$name-$set.jsonl" > "$OUT/$name-$set.txt" 2>&1 )
    echo "$name $set  $(grep -m1 '^ALL' "$OUT/$name-$set.txt")"
  done
  kill $pid; wait $pid 2>/dev/null || true
}
[ -f "$OUT/HO-guide-tasks.txt" ] || evaluate HO ~/cinminai-build/models/Qwen3.5-4B-guide-HO-Q4_K_M.gguf
evaluate "$RUN" out/Qwen3.5-4B-guide-$RUN-Q4_K_M.gguf
