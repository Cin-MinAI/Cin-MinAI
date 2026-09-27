#!/usr/bin/env bash
# Phase 4 (training/guide/README.md): bake a tuned adapter into the base model and quantize it — the file
# that ships. Runs in WSL (~/cinminai-train), CPU only, with the pinned llama.cpp (7fe450e = v0.5.0, the
# same commit as the Mint box's builds). Same path as the eval: the GGUF adapter applied to a GGUF base,
# so the merged file should score what the adapter scored at run time (checked by re-running the eval).
#
#   bash merge_quantize.sh RUN BASE [QUANT]      e.g.  bash merge_quantize.sh HO Qwen3.5-4B Q4_K_M
#
# Writes out/<BASE>-guide-<RUN>-<QUANT>.gguf + .sha256; the f16 intermediates are removed afterwards.
set -euo pipefail
RUN=$1 BASE=$2 QUANT=${3:-Q4_K_M}
cd ~/cinminai-train
LC=llama.cpp
[ "$(git -C $LC rev-parse --short=7 HEAD)" = 7fe450e ] || { echo "llama.cpp is not at the pinned 7fe450e"; exit 1; }

# 1. the two tools we need, CPU-only (cmake from pip: no system package, no sudo)
~/.local/bin/uv pip install --quiet --python .venv cmake   # the venv is uv-made (setup_train.sh): no pip inside
if [ ! -x $LC/build-cpu/bin/llama-export-lora ] || [ ! -x $LC/build-cpu/bin/llama-quantize ]; then
  .venv/bin/cmake -S $LC -B $LC/build-cpu -DCMAKE_BUILD_TYPE=Release -DGGML_NATIVE=OFF -DGGML_CUDA=OFF \
    -DGGML_VULKAN=OFF -DLLAMA_CURL=OFF > out/build-cpu.log 2>&1
  .venv/bin/cmake --build $LC/build-cpu -j "$(nproc)" --target llama-export-lora llama-quantize >> out/build-cpu.log 2>&1
fi

# 2. base model -> f16 GGUF;  3. adapter baked in;  4. quantize
F16=out/$BASE-f16.gguf MERGED=out/$BASE-guide-$RUN-f16.gguf FINAL=out/$BASE-guide-$RUN-$QUANT.gguf
[ -f "$F16" ] || .venv/bin/python $LC/convert_hf_to_gguf.py base/$BASE --outtype f16 --outfile "$F16"
$LC/build-cpu/bin/llama-export-lora -m "$F16" --lora out/sweep-$RUN-lora.gguf -o "$MERGED" -t "$(nproc)"
$LC/build-cpu/bin/llama-quantize "$MERGED" "$FINAL" "$QUANT" "$(nproc)"
( cd out && sha256sum "$(basename "$FINAL")" > "$(basename "$FINAL").sha256" && cat "$(basename "$FINAL").sha256" )
rm -f "$MERGED" "$F16"
ls -la "$FINAL"
