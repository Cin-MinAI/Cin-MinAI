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
# Candidate (MODEL=qwen default, MODEL=gemma): base weights in WSL, eval GGUF on the Mint box, LoRA targets.
# Qwen3.5: only the standard projections (llama.cpp can't convert adapters on its linear-attention ones).
if [ "${MODEL:-qwen}" = gemma ]; then
  BASE=gemma-4-E2B-it; EVAL_GGUF=gemma-4-E2B_q4_0-it.gguf; TARGETS=all-linear
else
  BASE=Qwen3.5-4B; EVAL_GGUF=${EVAL_GGUF:-Qwen3.5-4B-Q4_K_M.gguf}; TARGETS=q_proj,k_proj,v_proj,o_proj,gate_proj,up_proj,down_proj
fi

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
    ~/cin-minai/llama.cpp/build-cuda/bin/llama-server --host 127.0.0.1 --port 18090 --model ~/cin-minai/models/$EVAL_GGUF $loraarg --ctx-size 8192 --gpu-layers all --cache-type-k q8_0 --cache-type-v q8_0 --flash-attn on --fit off --parallel 1 --reasoning off --alias $name > bench-results/guide/server-sweep-$name.log 2>&1 &
    pid=\$!; for i in \$(seq 120); do curl -sf http://127.0.0.1:18090/health >/dev/null && break; sleep 1; done
    python3 run_eval.py --prompt v2 --url http://127.0.0.1:18090 --model $name --out bench-results/guide/sweep-$name-public.jsonl > bench-results/guide/sweep-$name-public.txt 2>&1
    python3 run_eval.py --prompt v2 --tasks ../eval-guide-interp/tasks.py --url http://127.0.0.1:18090 --model $name --out bench-results/guide/sweep-$name-vague.jsonl > bench-results/guide/sweep-$name-vague.txt 2>&1
    kill \$pid; wait \$pid 2>/dev/null"
  scp -q "$MINT:cin-minai/eval-guide/bench-results/guide/sweep-$name-*.txt" "$MINT:cin-minai/eval-guide/bench-results/guide/sweep-$name-*.jsonl" "$OUT/" 2>/dev/null
  log "$name  public: $(grep -m1 '^ALL' "$OUT/sweep-$name-public.txt")   vague: $(grep -m1 '^ALL' "$OUT/sweep-$name-vague.txt")"
}

run() {  # name, n_transition, n_interpretation, lr, [extra train_lora.py args]
  local name=$1 nt=$2 ni=$3 lr=$4 extra=${5:-}
  log "run $name: transition $nt, interpretation $ni, lr $lr"
  train "$name" "make_mix.py --transition $nt --interpretation $ni" "$lr" "$extra"
}

run_sessions() {  # name, trained turns, lr, [preset], [office examples]: balanced session mix (make_session_mix.py)
  local name=$1 turns=$2 lr=$3 preset=${4:-g} office=${5:-0}
  log "run $name: sessions, $turns trained turns, preset $preset, office $office, lr $lr"
  train "$name" "make_session_mix.py --turns $turns --preset $preset --office $office" "$lr" ""
}

train() {  # name, mix command (script in training/guide + its args), lr, extra train_lora.py args
  local name=$1 mix=$2 lr=$3 extra=$4
  wslrun "cd ~/cinminai-train && .venv/bin/python /mnt/c/Users/Ian/Cin-minAI/training/guide/$mix \
    --seed 7 --out data/mix-$name.jsonl && .venv/bin/python /mnt/c/Users/Ian/Cin-minAI/training/guide/train_lora.py \
    --base base/$BASE --data data/mix-$name.jsonl --out runs/sweep-$name --epochs 1 --lr $lr --targets $TARGETS $extra &&
    .venv/bin/python llama.cpp/convert_lora_to_gguf.py runs/sweep-$name/adapter --base base/$BASE \
    --outfile out/sweep-$name-lora.gguf --outtype f16 && cp out/sweep-$name-lora.gguf /mnt/c/Users/Ian/cinminai-train-out/sweep/ &&
    cp runs/sweep-$name/run.json /mnt/c/Users/Ian/cinminai-train-out/sweep/run-$name.json" >> "$OUT/train-$name.log" 2>&1 \
    || { log "run $name FAILED (see train-$name.log)"; wsl.exe --shutdown; return 1; }
  # WSL keeps ~10 GB of file cache after training that Windows can't reclaim (2026-09-27: 1.2 GB free);
  # nothing else uses WSL on this PC (Ian), and the eval runs on the Mint box — so stop it here.
  wsl.exe --shutdown
  scp -q "$OUT/sweep-$name-lora.gguf" $MINT:cin-minai/adapters/ && evaluate "$name" "sweep-$name-lora.gguf"
}

log "sweep started"
if [ "${1:-}" = G ]; then               # 2026-09-26: session corpus, balanced to the journal shares (~317 sequences)
  run_sessions G 160 5e-5
  log "SWEEP DONE"; exit 0
fi
if [ "${1:-}" = H ]; then               # G lost numbered steps (72 %): clear 30 %, walkthroughs train follow-ups only
  run_sessions H 160 5e-5 h
  log "SWEEP DONE"; exit 0
fi
if [ "${1:-}" = HF ]; then              # full run at H's recipe: 360 turns = the most the corpus gives at these shares (chat runs out)
  run_sessions HF 360 5e-5 h
  log "SWEEP DONE"; exit 0
fi
if [ "${1:-}" = HO ]; then              # HF + office examples (~15 % of sequences): HF lost 2 office items to stock
  run_sessions HO 360 5e-5 h 115
  log "SWEEP DONE"; exit 0
fi
if [ "${1:-}" = merged ]; then          # a merged, quantized guide file (merge_quantize.sh), no adapter: EVAL_GGUF=<file> ... merged NAME
  evaluate "${2:?name}" ""
  log "SWEEP DONE"; exit 0
fi
if [ "${1:-}" = GO ]; then              # Gemma 4 E2B at HO's recipe (MODEL=gemma); stock Gemma first, same scorer
  [ "${MODEL:-}" = gemma ] || { log "GO needs MODEL=gemma"; exit 1; }
  evaluate stock-gemma ""
  run_sessions GO 360 5e-5 h 115
  log "SWEEP DONE"; exit 0
fi
if [ "${1:-}" = F ]; then               # 2026-09-26 step (a): reply-only tuning, one micro run
  run F 300 0 5e-5 "--turns replies"
  log "SWEEP DONE"; exit 0
fi
evaluate stock ""                       # the baseline on both sets (vague set is new)
run A 150 0   1e-4                      # transition only: does the format fix alone keep 87 %?
run B 120 60  1e-4                      # small interpretation dose (~20 % of sequences)
run C 120 60  5e-5                      # same dose, gentler
run D 320 160 5e-5                      # more data, gentle
run E 260 280 5e-5                      # bigger dose (~35 %)
log "SWEEP DONE"
