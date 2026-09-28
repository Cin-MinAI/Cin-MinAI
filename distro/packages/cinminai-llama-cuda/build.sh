#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Build hook (build-packages.sh): the CUDA module from the llama.cpp build (distro/build-llama.sh).
#   build.sh STAGE REPO
set -euo pipefail
stage=$1 repo=$2
source "$repo/distro/config.env"
src=$M1/llama/$LLAMA_COMMIT
[[ -f $src/BUILDINFO ]] || { echo "no llama.cpp build at $src: run distro/build-llama.sh (as root) first" >&2; exit 1; }
install -d "$stage/usr/lib/cinminai/llama" "$stage/usr/share/doc/cinminai-llama-cuda"
cp -a "$src"/bin/libggml-cuda.so* "$stage/usr/lib/cinminai/llama/"
{ echo "llama.cpp: MIT License"; echo; cat "$src/LICENSE"; } > "$stage/usr/share/doc/cinminai-llama-cuda/copyright"
