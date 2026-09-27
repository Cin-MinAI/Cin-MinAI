#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Teacher server for the transition corpus: Qwen3-14B (read-only testbed file), our pinned CUDA build, port 18091.
# 36 of 40 layers on the GPU keeps the SPEC §4.2 desktop reserve (~1.9 GB free on the 1080 Ti at 4K).
# Tuning (PLAN D33) — measured options, not yet adopted; set TEACHER_TUNE=1 to use them:
#   --parallel 2 + generate.py --workers 2   batch two conversations (GPU was 36-41 % busy with one)
#   --cpu-mask 0xf --cpu-strict 1 (+ batch)   one compute thread per physical core (scheduler put two on core 0)
#   --poll 0                                  main thread stops busy-waiting on the GPU (was 98 % of a core)
tune=()
if [ "${TEACHER_TUNE:-0}" = 1 ]; then
  tune=(--parallel 2 --ctx-size 8192 --cpu-mask 0xf --cpu-strict 1 --cpu-mask-batch 0xf --cpu-strict-batch 1 --poll 0)
else
  tune=(--parallel 1 --ctx-size 4096)
fi
exec ~/cin-minai/llama.cpp/build-cuda/bin/llama-server --host 127.0.0.1 --port 18091 \
  --model /home/mint/Documents/Codex/2026-08-23/h/work/local-ai-testbed/models/Qwen3-14B-Q4_K_M.gguf \
  --ubatch-size 256 --gpu-layers 36 --cache-type-k q8_0 --cache-type-v q8_0 --flash-attn on --fit off \
  --reasoning off --alias Qwen3-14B-Q4_K_M "${tune[@]}"
