#!/usr/bin/env bash
# Micro-run sweep for the guide fine-tune dose (cycle 0, Qwen3.5-4B). Run from Git Bash, detached
# (so Claude Code's memory reaper can't stop it):
#   powershell Start-Process bash -ArgumentList training/guide/sweep.sh -WindowStyle Hidden
# Each run: sample a mix -> train 1 epoch on the RTX 4070 (WSL) -> LoRA to GGUF -> public guide eval +
# vague-request eval with prompt v2 on the Mint box's 1080 Ti. Results: C:\Users\Ian\cinminai-train-out\sweep\
set -u
MINT=mint@192.168.5.70
REPO=/c/Users/Ian/Cin-minAI
OUT=/c/Users/Ian/cinminai-train-out/sweep
LOG=$OUT/sweep.log
mkdir -p "$OUT"
log() { echo "$(date '+%F %T') $*" >> "$LOG"; }
wslrun() { MSYS_NO_PATHCONV=1 wsl -d Ubuntu-24.04 -e bash -c "$1"; }
TARGETS=q_proj,k_proj,v_proj,o_proj,gate_proj,up_proj,down_proj

# eval code on the Mint box must match the repo
scp -q "$REPO/training/eval/guide/run_eval.py" "$REPO/training/eval/guide/tasks.py" "$REPO/training/eval/guide/labels.json" \
  $MINT:cin-minai/eval-guide/
ssh $MINT 'mkdir -p ~/cin-minai/eval-guide-interp'
scp -q "$REPO/training/eval/guide-interp/tasks.py" $MINT:cin-minai/eval-guide-interp/tasks.py

evaluate() {  # name, [adapter file on the Mint box or ""]
  local name=$1 lora=${2:-}
  local loraarg=""; [ -n "$lora" ] && loraarg="--lora ~/cin-minai/adapters/$lora"
  ssh $MINT "cd ~/cin-minai/eval-guide &&
    while [ \$(nvidia-smi --query-compute-apps=used_memory --format=csv,noheader,nounits | awk '{s+=\$1} END {print s+0}') -gt 512 ]; do sleep 60; done
    ~/cin-minai/llama.cpp/build-cuda/bin/llama-server --host 127.0.0.1 --port 18090 --model ~/cin-minai/models/Qwen3.5-4B-Q4_K_M.gguf $loraarg --ctx-size 8192 --gpu-layers all --cache-type-k q8_0 --cache-type-v q8_0 --flash-attn on --fit off --parallel 1 --reasoning off --alias $name > bench-results/guide/server-sweep-$name.log 2>&1 &
    pid=\$!; for i in \$(seq 120); do curl -sf http://127.0.0.1:18090/health >/dev/null && break; sleep 1; done
    python3 run_eval.py --prompt v2 --url http://127.0.0.1:18090 --model $name --out bench-results/guide/sweep-$name-public.jsonl > bench-results/guide/sweep-$name-public.txt 2>&1
    python3 run_eval.py --prompt v2 --tasks ../eval-guide-interp/tasks.py --url http://127.0.0.1:18090 --model $name --out bench-results/guide/sweep-$name-vague.jsonl > bench-results/guide/sweep-$name-vague.txt 2>&1
    kill \$pid; wait \$pid 2>/dev/null"
  scp -q "$MINT:cin-minai/eval-guide/bench-results/guide/sweep-$name-*.txt" "$MINT:cin-minai/eval-guide/bench-results/guide/sweep-$name-*.jsonl" "$OUT/" 2>/dev/null
  log "$name  public: $(grep -m1 '^ALL' "$OUT/sweep-$name-public.txt")   vague: $(grep -m1 '^ALL' "$OUT/sweep-$name-vague.txt")"
}

run() {  # name, n_transition, n_interpretation, lr
  local name=$1 nt=$2 ni=$3 lr=$4
  log "run $name: transition $nt, interpretation $ni, lr $lr"
  wslrun "cd ~/cinminai-train && .venv/bin/python /mnt/c/Users/Ian/Cin-minAI/training/guide/make_mix.py --transition $nt \
    --interpretation $ni --seed 7 --out data/mix-$name.jsonl && .venv/bin/python /mnt/c/Users/Ian/Cin-minAI/training/guide/train_lora.py \
    --base base/Qwen3.5-4B --data data/mix-$name.jsonl --out runs/sweep-$name --epochs 1 --lr $lr --targets $TARGETS &&
    .venv/bin/python llama.cpp/convert_lora_to_gguf.py runs/sweep-$name/adapter --base base/Qwen3.5-4B \
    --outfile out/sweep-$name-lora.gguf --outtype f16 && cp out/sweep-$name-lora.gguf /mnt/c/Users/Ian/cinminai-train-out/sweep/ &&
    cp runs/sweep-$name/run.json /mnt/c/Users/Ian/cinminai-train-out/sweep/run-$name.json" >> "$OUT/train-$name.log" 2>&1 \
    || { log "run $name FAILED (see train-$name.log)"; return 1; }
  scp -q "$OUT/sweep-$name-lora.gguf" $MINT:cin-minai/adapters/ && evaluate "$name" "sweep-$name-lora.gguf"
}

log "sweep started"
evaluate stock ""                       # the baseline on both sets (vague set is new)
run A 150 0   1e-4                      # transition only: does the format fix alone keep 87 %?
run B 120 60  1e-4                      # small interpretation dose (~20 % of sequences)
run C 120 60  5e-5                      # same dose, gentler
run D 320 160 5e-5                      # more data, gentle
run E 260 280 5e-5                      # bigger dose (~35 %)
log "SWEEP DONE"
