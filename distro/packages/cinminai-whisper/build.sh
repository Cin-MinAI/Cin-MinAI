#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Build hook (build-packages.sh): copy the whisper.cpp build (distro/build-whisper.sh, run as root first).
#   build.sh STAGE REPO
set -euo pipefail
stage=$1 repo=$2
source "$repo/distro/config.env"
src=$M1/whisper/$WHISPER_COMMIT
[[ -f $src/BUILDINFO ]] || { echo "no whisper.cpp build at $src: run distro/build-whisper.sh (as root) first" >&2; exit 1; }
install -d "$stage/usr/lib/cinminai/whisper" "$stage/usr/share/doc/cinminai-whisper"
cp -a "$src"/bin/* "$stage/usr/lib/cinminai/whisper/"
cp "$src/BUILDINFO" "$stage/usr/share/doc/cinminai-whisper/BUILDINFO"
{ echo "whisper.cpp: MIT License"; echo; cat "$src/LICENSE"; } > "$stage/usr/share/doc/cinminai-whisper/copyright"
