#!/usr/bin/env bash
# Teacher server for the transition corpus: Qwen3-14B (read-only testbed file), our pinned CUDA build, port 18091.
exec ~/cin-minai/llama.cpp/build-cuda/bin/llama-server --host 127.0.0.1 --port 18091 \
  --model /home/mint/Documents/Codex/2026-08-23/h/work/local-ai-testbed/models/Qwen3-14B-Q4_K_M.gguf \
  --ctx-size 4096 --ubatch-size 256 --gpu-layers 36 --cache-type-k q8_0 --cache-type-v q8_0 --flash-attn on --fit off \
  --parallel 1 --reasoning off --alias Qwen3-14B-Q4_K_M
