#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Build hook (build-packages.sh): copy the llama.cpp build (distro/build-llama.sh, run as root first)
# into the package, all modules except CUDA (that's cinminai-llama-cuda).
#   build.sh STAGE REPO
set -euo pipefail
stage=$1 repo=$2
source "$repo/distro/config.env"
src=$M1/llama/$LLAMA_COMMIT
[[ -f $src/BUILDINFO ]] || { echo "no llama.cpp build at $src: run distro/build-llama.sh (as root) first" >&2; exit 1; }
install -d "$stage/usr/lib/cinminai/llama" "$stage/usr/share/doc/cinminai-llama"
for f in "$src"/bin/*; do
    case $(basename "$f") in libggml-cuda.so*) continue ;; esac
    cp -a "$f" "$stage/usr/lib/cinminai/llama/"
done
cp "$src/BUILDINFO" "$stage/usr/share/doc/cinminai-llama/BUILDINFO"
{ echo "llama.cpp: MIT License"; echo; cat "$src/LICENSE"; } > "$stage/usr/share/doc/cinminai-llama/copyright"
