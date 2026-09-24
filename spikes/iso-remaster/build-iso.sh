#!/usr/bin/env bash
# Stage 1 remaster spike: official Mint Cinnamon ISO + our apt repo -> our ISO.
#
#   sudo ./build-iso.sh            (in WSL: wsl -d Ubuntu-24.04 -u root -- ./build-iso.sh)
#
# Needs: xorriso, squashfs-tools, a repo made by make-repo.sh, and the upstream ISO in
# $WORK/upstream (fetched and verified here if missing).
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
source "$here/config.env"
[[ $EUID -eq 0 ]] || { echo "run as root" >&2; exit 1; }
# When run through sudo/wsl -u root, keep WORK in the invoking user's home.
if [[ -n ${SUDO_USER:-} && $WORK == /root/* ]]; then WORK=$(getent passwd "$SUDO_USER" | cut -d: -f6)/cinminai-build; fi

up=$WORK/upstream
b=$WORK/build
rootfs=$b/rootfs
iso_in=$up/$MINT_ISO
repo=$WORK/repo
log() { printf '\n== %s\n' "$*"; }

# --- 1. upstream ISO ------------------------------------------------------------
log "verify upstream ISO"
mkdir -p "$up"
[[ -f $iso_in ]] || curl -fL -o "$iso_in" "$MINT_MIRROR/$MINT_ISO"
echo "$MINT_ISO_SHA256  $iso_in" | sha256sum -c -
[[ -d $repo/dists ]] || { echo "no repo at $repo; run make-repo.sh first" >&2; exit 1; }

# --- 2. unpack ------------------------------------------------------------------
log "unpack"
rm -rf "$b"; mkdir -p "$b/iso"
xorriso -osirrox on -indev "$iso_in" \
    -extract /casper/filesystem.squashfs "$b/filesystem.squashfs.orig" \
    -extract /casper/filesystem.manifest "$b/iso/filesystem.manifest" \
    -extract /casper/filesystem.size "$b/iso/filesystem.size" \
    -extract /md5sum.txt "$b/iso/md5sum.txt" 2>&1 | tail -1
chmod u+w "$b/iso"/*
unsquashfs -s "$b/filesystem.squashfs.orig" | tee "$b/squashfs-info.txt" | grep -E 'Compression|Block size'
comp=$(awk '/^Compression/ {print $2}' "$b/squashfs-info.txt")
bsize=$(awk '/^Block size/ {print $3}' "$b/squashfs-info.txt")
unsquashfs -q -d "$rootfs" "$b/filesystem.squashfs.orig"
rm "$b/filesystem.squashfs.orig"

# --- 3. customize in chroot --------------------------------------------------------
mounts=()
cleanup() {
    for ((i=${#mounts[@]}-1; i>=0; i--)); do umount -l "${mounts[i]}" 2>/dev/null || true; done
}
trap cleanup EXIT
bind() { mkdir -p "$2"; mount "${@:3}" --bind "$1" "$2"; mounts+=("$2"); }

log "chroot: install cinminai-desktop"
mount -t proc proc "$rootfs/proc"; mounts+=("$rootfs/proc")
mount -t sysfs sys "$rootfs/sys"; mounts+=("$rootfs/sys")
bind /dev "$rootfs/dev"
bind /dev/pts "$rootfs/dev/pts"
bind "$repo" "$rootfs/mnt/cinminai-repo" -o ro

# No service starts inside the chroot; host DNS for any network access.
printf '#!/bin/sh\nexit 101\n' > "$rootfs/usr/sbin/policy-rc.d"; chmod 755 "$rootfs/usr/sbin/policy-rc.d"
mv "$rootfs/etc/resolv.conf" "$rootfs/etc/resolv.conf.cinminai-orig"
cp -L /etc/resolv.conf "$rootfs/etc/resolv.conf"

# Build-time apt config sees only our (bind-mounted) repo, with its own lists dir, so the
# image's apt state is untouched and the result doesn't depend on the day's Ubuntu mirror.
cp "$WORK/cinminai-archive-keyring.gpg" "$rootfs/tmp/cinminai-build.gpg"
echo "deb [signed-by=/tmp/cinminai-build.gpg] file:/mnt/cinminai-repo $REPO_SUITE $REPO_COMPONENT" \
    > "$rootfs/tmp/cinminai-build.list"
mkdir -p "$rootfs/tmp/cinminai-lists/partial"
aptopts=(-o Dir::Etc::sourcelist=/tmp/cinminai-build.list -o Dir::Etc::sourceparts=-
         -o Dir::State::Lists=/tmp/cinminai-lists -o APT::Get::List-Cleanup=0)
chroot "$rootfs" apt-get "${aptopts[@]}" update
chroot "$rootfs" env DEBIAN_FRONTEND=noninteractive \
    apt-get "${aptopts[@]}" install -y --no-install-recommends cinminai-desktop

# Minimal branding marker (real branding is M1). Record what owns os-release for the notes.
echo "Cin-minAI spike build $(date -u +%Y-%m-%dT%H:%MZ) on Linux Mint $MINT_VERSION" \
    > "$rootfs/etc/cinminai-release"
{
    echo "os-release owner: $(chroot "$rootfs" dpkg -S /usr/lib/os-release 2>&1)"
    echo "diversions:"; chroot "$rootfs" dpkg-divert --list | grep -iE 'release|issue|lsb' || true
    echo "sources:"; ls "$rootfs/etc/apt/sources.list.d/"
} | tee "$b/notes.txt"

log "chroot: clean up"
chroot "$rootfs" apt-get clean
rm -rf "$rootfs/tmp/cinminai-build.gpg" "$rootfs/tmp/cinminai-build.list" "$rootfs/tmp/cinminai-lists" \
       "$rootfs/usr/sbin/policy-rc.d"
mv -f "$rootfs/etc/resolv.conf.cinminai-orig" "$rootfs/etc/resolv.conf"
cleanup; mounts=()
rmdir "$rootfs/mnt/cinminai-repo"

# --- 4. repack --------------------------------------------------------------------
log "manifest + size"
# Keep upstream's manifest format ("name<TAB>version").
chroot "$rootfs" dpkg-query -W --showformat='${Package}\t${Version}\n' > "$b/iso/filesystem.manifest"
du -sx --block-size=1 "$rootfs" | cut -f1 > "$b/iso/filesystem.size"
diff <(xorriso -osirrox on -indev "$iso_in" -extract /casper/filesystem.manifest /dev/stdout 2>/dev/null) \
     "$b/iso/filesystem.manifest" | tee "$b/manifest.diff" || true

log "squashfs ($comp, block $bsize)"
mksquashfs "$rootfs" "$b/iso/filesystem.squashfs" -comp "$comp" -b "$bsize" -noappend -no-progress \
    -mkfs-time 0 -all-time 0 | tail -3

log "md5sum.txt"
for f in casper/filesystem.squashfs casper/filesystem.manifest casper/filesystem.size; do
    sum=$(md5sum "$b/iso/$(basename "$f")" | cut -d' ' -f1)
    sed -i "s#^[0-9a-f]\{32\}  \./$f\$#$sum  ./$f#" "$b/iso/md5sum.txt"
done

log "write ISO (replaying upstream boot setup)"
mkdir -p "$WORK/out"
rm -f "$WORK/out/$OUT_ISO"
xorriso -indev "$iso_in" -outdev "$WORK/out/$OUT_ISO" \
    -map "$b/iso/filesystem.squashfs" /casper/filesystem.squashfs \
    -map "$b/iso/filesystem.manifest" /casper/filesystem.manifest \
    -map "$b/iso/filesystem.size" /casper/filesystem.size \
    -map "$b/iso/md5sum.txt" /md5sum.txt \
    -boot_image any replay 2>&1 | tail -3
( cd "$WORK/out" && sha256sum "$OUT_ISO" | tee "$OUT_ISO.sha256" )
[[ -n ${SUDO_USER:-} ]] && chown -R "$SUDO_USER:" "$WORK/out"
ls -l "$WORK/out"
