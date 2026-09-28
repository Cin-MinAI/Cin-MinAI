#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Build llama.cpp for cinminai-llama and cinminai-llama-cuda (PLAN D5, Alpha).
#
#   wsl -d Ubuntu-24.04 -u root -- /path/to/distro/build-llama.sh     (root for the build root; no password)
#
# Builds in a clean Ubuntu 24.04 build root ($WORK/buildroot-noble: the pinned ubuntu-base tarball, with
# apt pointed at a dated snapshot.ubuntu.com, so the compilers and headers are the same on every run);
# nothing is installed on the build machine itself. One build, one llama-server, the backends as modules
# that llama-server loads at start (GGML_BACKEND_DL):
#   - CPU: one module per instruction-set level (GGML_CPU_ALL_VARIANTS); the best one for the running CPU
#     is picked at start, so an older PC gets AVX2 and a newer one AVX-512 from the same package;
#   - Vulkan (AMD, Intel, and NVIDIA without the CUDA module);
#   - CUDA 12 (Ubuntu's toolkit 12.0 with gcc-12, the testbed recipe, PLAN §2), architectures from config.env.
# Output: $M1/llama/$LLAMA_COMMIT/{bin/,BUILDINFO} — the packages' build.sh copy from there. A finished
# build is reused; FORCE=1 rebuilds. ~40 min on the 3900X, mostly the CUDA kernels.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
source "$here/config.env"
[[ $EUID -eq 0 ]] || { echo "run as root" >&2; exit 1; }
owner=${SUDO_USER:-$(stat -c %U "$here/config.env")}
[[ $WORK == /root/* ]] && { WORK=$(getent passwd "$owner" | cut -d: -f6)/cinminai-build; M1=$WORK/m1; }

out=$M1/llama/$LLAMA_COMMIT
if [[ -f $out/BUILDINFO && ${FORCE:-0} != 1 ]]; then
    echo "already built: $out (FORCE=1 to rebuild)"; exit 0
fi
free=$(df --output=avail -BG "$WORK" 2>/dev/null | tail -1 | tr -dc 0-9)
(( ${free:-0} >= 15 )) || { echo "only ${free} GB free under $WORK (need 15)" >&2; exit 1; }
for fs in /mnt/c; do
    [[ -d $fs ]] || continue
    free=$(df --output=avail -BG "$fs" | tail -1 | tr -dc 0-9)
    (( free >= 20 )) || { echo "only ${free} GB free on $fs (need 20): WSL's disk file lives there" >&2; exit 1; }
done

br=$WORK/buildroot-noble
log() { printf '\n== %s\n' "$*"; }
mounted=()
cleanup() {
    for ((i=${#mounted[@]}-1; i>=0; i--)); do umount -l "${mounted[i]}" 2>/dev/null || true; done
}
trap cleanup EXIT
bind() { mkdir -p "$2"; mount --bind "$1" "$2"; mounted+=("$2"); }

# --- 1. the build root -------------------------------------------------------------------------
PKGS="build-essential gcc-12 g++-12 cmake ninja-build git ca-certificates
      nvidia-cuda-toolkit libvulkan-dev glslc spirv-headers"
stamp="$UBUNTU_BASE_SHA256 $UBUNTU_SNAPSHOT $(echo $PKGS)"
if [[ ! -f $br/.cinminai-stamp || $(cat "$br/.cinminai-stamp") != "$stamp" ]]; then
    log "build root: ubuntu-base + snapshot $UBUNTU_SNAPSHOT"
    rm -rf "$br"; mkdir -p "$br" "$WORK/cache"
    tarball=$WORK/cache/$(basename "$UBUNTU_BASE_URL")
    [[ -f $tarball ]] || curl -fL -o "$tarball" "$UBUNTU_BASE_URL"
    echo "$UBUNTU_BASE_SHA256  $tarball" | sha256sum -c -
    tar -xzf "$tarball" -C "$br"
    rm -f "$br/etc/apt/sources.list.d/"*
    cat > "$br/etc/apt/sources.list.d/ubuntu.sources" <<EOF
Types: deb
URIs: https://snapshot.ubuntu.com/ubuntu/$UBUNTU_SNAPSHOT
Suites: noble noble-updates noble-security
Components: main restricted universe multiverse
Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg
EOF
    cp /etc/resolv.conf "$br/etc/resolv.conf"
    bind /proc "$br/proc"; bind /dev "$br/dev"; bind /sys "$br/sys"
    # the base tarball has no CA certificates (the snapshot server is https only): borrow the host's
    # bundle until ca-certificates is installed (apt checks the archive signatures either way)
    mkdir -p "$br/etc/ssl/certs"; cp /etc/ssl/certs/ca-certificates.crt "$br/etc/ssl/certs/"
    chroot "$br" apt-get -q update
    chroot "$br" env DEBIAN_FRONTEND=noninteractive apt-get -q -y install ca-certificates
    chroot "$br" env DEBIAN_FRONTEND=noninteractive apt-get -q -y --no-install-recommends install $PKGS
    chroot "$br" apt-get clean
    cleanup; mounted=()
    echo "$stamp" > "$br/.cinminai-stamp"
fi

# --- 2. the source, at the pinned commit -------------------------------------------------------
log "source $LLAMA_TAG ($LLAMA_COMMIT)"
src=$WORK/src/llama.cpp
if [[ ! -d $src/.git ]]; then
    mkdir -p "$WORK/src"
    git clone --quiet "$LLAMA_REPO" "$src"
fi
git -c safe.directory='*' -C "$src" cat-file -e "$LLAMA_COMMIT^{commit}" 2>/dev/null \
    || git -c safe.directory='*' -C "$src" fetch --quiet --tags origin
git -c safe.directory='*' -C "$src" checkout --quiet --force "$LLAMA_COMMIT"
git -c safe.directory='*' -C "$src" clean -qfdx
[[ $(git -c safe.directory='*' -C "$src" rev-parse HEAD) == "$LLAMA_COMMIT" ]]
tagged=$(git -c safe.directory='*' -C "$src" rev-parse "$LLAMA_TAG^{commit}" 2>/dev/null || echo none)
[[ $tagged == "$LLAMA_COMMIT" ]] || { echo "tag $LLAMA_TAG is $tagged, not $LLAMA_COMMIT" >&2; exit 1; }

# --- 3. build ----------------------------------------------------------------------------------
log "build (CPU variants + Vulkan + CUDA $LLAMA_CUDA_ARCHS)"
bind /proc "$br/proc"; bind /dev "$br/dev"; bind /sys "$br/sys"
bind "$src" "$br/src"
flags=(
    -G Ninja
    -DCMAKE_BUILD_TYPE=Release
    -DCMAKE_C_COMPILER=/usr/bin/gcc-12 -DCMAKE_CXX_COMPILER=/usr/bin/g++-12
    -DCMAKE_CUDA_HOST_COMPILER=/usr/bin/g++-12
    -DBUILD_SHARED_LIBS=ON
    -DCMAKE_BUILD_RPATH_USE_ORIGIN=ON -DCMAKE_BUILD_RPATH='$ORIGIN' -DCMAKE_SKIP_INSTALL_RPATH=ON
    -DGGML_NATIVE=OFF -DGGML_BACKEND_DL=ON -DGGML_CPU_ALL_VARIANTS=ON
    -DGGML_CUDA=ON "-DCMAKE_CUDA_ARCHITECTURES=$LLAMA_CUDA_ARCHS"
    -DGGML_VULKAN=ON
    -DLLAMA_CURL=OFF -DLLAMA_BUILD_TESTS=OFF -DLLAMA_BUILD_EXAMPLES=OFF
)
# the source's own date, so the binaries don't carry the build time
epoch=$(git -c safe.directory='*' -C "$src" log -1 --format=%ct)
chroot "$br" env SOURCE_DATE_EPOCH="$epoch" cmake -S /src -B /src/build "${flags[@]}" > "$WORK/src/llama-cmake.log"
chroot "$br" env SOURCE_DATE_EPOCH="$epoch" cmake --build /src/build -j "$(nproc)" --target llama-server
cleanup; mounted=()

# --- 4. collect ---------------------------------------------------------------------------------
log "collect -> $out"
rm -rf "$out"; mkdir -p "$out/bin"
cp -a "$src/build/bin/llama-server" "$src/build/bin/"lib*.so* "$out/bin/"
cp "$src/LICENSE" "$out/LICENSE"
strip --strip-unneeded "$out/bin/"*
{
    echo "llama.cpp $LLAMA_TAG ($LLAMA_COMMIT) from $LLAMA_REPO"
    echo "build root: $(basename "$UBUNTU_BASE_URL") ($UBUNTU_BASE_SHA256), apt snapshot $UBUNTU_SNAPSHOT"
    echo "cmake flags: ${flags[*]}"
    echo "toolchain:"
    chroot "$br" dpkg-query -W -f='  ${Package} ${Version}\n' gcc-12 g++-12 cmake ninja-build nvidia-cuda-toolkit \
        libvulkan-dev glslc spirv-headers libcublas12 libcudart12
    echo "files (sha256):"
    (cd "$out/bin" && sha256sum * | sed 's/^/  /')
} > "$out/BUILDINFO"
chown -R "$owner:" "$M1/llama" "$WORK/src"
ls -la "$out/bin"
