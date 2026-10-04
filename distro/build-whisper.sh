#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Build whisper.cpp for cinminai-whisper (D64, D78: the speech in a video, for its summary).
#
#   wsl -d Ubuntu-24.04 -u root -- /path/to/distro/build-whisper.sh     (after build-llama.sh: same build root)
#
# The processor only, as the lab measured it (small model, 4 threads on the i7-4790K: faster than real time): the
# graphics card is busy with the vision model in the same job. Like llama.cpp, one module per instruction-set level,
# the best picked at start (GGML_CPU_ALL_VARIANTS), so one package fits old and new processors.
# Output: $M1/whisper/$WHISPER_COMMIT/{bin/,BUILDINFO,LICENSE}. A finished build is reused; FORCE=1 rebuilds. ~3 min.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
source "$here/config.env"
[[ $EUID -eq 0 ]] || { echo "run as root" >&2; exit 1; }
owner=${SUDO_USER:-$(stat -c %U "$here/config.env")}
[[ $WORK == /root/* ]] && { WORK=$(getent passwd "$owner" | cut -d: -f6)/cinminai-build; M1=$WORK/m1; }

out=$M1/whisper/$WHISPER_COMMIT
if [[ -f $out/BUILDINFO && ${FORCE:-0} != 1 ]]; then
    echo "already built: $out (FORCE=1 to rebuild)"; exit 0
fi
br=$WORK/buildroot-noble
[[ -f $br/.cinminai-stamp ]] || { echo "no build root at $br: run build-llama.sh first" >&2; exit 1; }

log() { printf '\n== %s\n' "$*"; }
mounted=()
cleanup() {
    for ((i=${#mounted[@]}-1; i>=0; i--)); do umount -l "${mounted[i]}" 2>/dev/null || true; done
}
trap cleanup EXIT
bind() { mkdir -p "$2"; mount --bind "$1" "$2"; mounted+=("$2"); }

log "source $WHISPER_TAG ($WHISPER_COMMIT)"
src=$WORK/src/whisper.cpp
if [[ ! -d $src/.git ]]; then
    mkdir -p "$WORK/src"
    git clone --quiet "$WHISPER_REPO" "$src"
fi
git -c safe.directory='*' -C "$src" cat-file -e "$WHISPER_COMMIT^{commit}" 2>/dev/null \
    || git -c safe.directory='*' -C "$src" fetch --quiet --tags origin
git -c safe.directory='*' -C "$src" checkout --quiet --force "$WHISPER_COMMIT"
git -c safe.directory='*' -C "$src" clean -qfdx
[[ $(git -c safe.directory='*' -C "$src" rev-parse HEAD) == "$WHISPER_COMMIT" ]]
tagged=$(git -c safe.directory='*' -C "$src" rev-parse "$WHISPER_TAG^{commit}" 2>/dev/null || echo none)
[[ $tagged == "$WHISPER_COMMIT" ]] || { echo "tag $WHISPER_TAG is $tagged, not $WHISPER_COMMIT" >&2; exit 1; }

log "build (CPU variants)"
bind /proc "$br/proc"; bind /dev "$br/dev"; bind /sys "$br/sys"
bind "$src" "$br/src"
flags=(
    -G Ninja
    -DCMAKE_BUILD_TYPE=Release
    -DCMAKE_C_COMPILER=/usr/bin/gcc-12 -DCMAKE_CXX_COMPILER=/usr/bin/g++-12
    -DBUILD_SHARED_LIBS=ON
    -DCMAKE_BUILD_RPATH_USE_ORIGIN=ON -DCMAKE_BUILD_RPATH='$ORIGIN' -DCMAKE_SKIP_INSTALL_RPATH=ON
    -DGGML_NATIVE=OFF -DGGML_BACKEND_DL=ON -DGGML_CPU_ALL_VARIANTS=ON
    -DWHISPER_BUILD_TESTS=OFF -DWHISPER_BUILD_SERVER=OFF -DWHISPER_SDL2=OFF -DWHISPER_CURL=OFF
)
epoch=$(git -c safe.directory='*' -C "$src" log -1 --format=%ct)
chroot "$br" env SOURCE_DATE_EPOCH="$epoch" cmake -S /src -B /src/build "${flags[@]}" > "$WORK/src/whisper-cmake.log"
chroot "$br" env SOURCE_DATE_EPOCH="$epoch" cmake --build /src/build -j "$(nproc)" --target whisper-cli
cleanup; mounted=()

log "collect -> $out"
rm -rf "$out"; mkdir -p "$out/bin"
cp -a "$src/build/bin/whisper-cli" "$src/build/bin/"lib*.so* "$out/bin/"
cp "$src/LICENSE" "$out/LICENSE"
strip --strip-unneeded "$out/bin/"*
{
    echo "whisper.cpp $WHISPER_TAG ($WHISPER_COMMIT) from $WHISPER_REPO"
    echo "build root: $(basename "$UBUNTU_BASE_URL") ($UBUNTU_BASE_SHA256), apt snapshot $UBUNTU_SNAPSHOT"
    echo "cmake flags: ${flags[*]}"
    echo "toolchain:"
    chroot "$br" dpkg-query -W -f='  ${Package} ${Version}\n' gcc-12 g++-12 cmake ninja-build
    echo "files (sha256):"
    (cd "$out/bin" && sha256sum * | sed 's/^/  /')
} > "$out/BUILDINFO"
chown -R "$owner:" "$M1/whisper" "$WORK/src"
ls -la "$out/bin"
