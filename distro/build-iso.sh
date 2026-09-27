#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Build the Cin-MinAI ISO (M1): the pinned Linux Mint ISO + our signed apt repository -> our ISO.
# Grown from spikes/iso-remaster/build-iso.sh (GO 2026-09-24: UEFI Secure Boot + BIOS, installs, updates).
#
#   wsl -d Ubuntu-24.04 -u root -- /path/to/distro/build-iso.sh     (root for the chroot; no password)
#
# Needs xorriso, squashfs-tools, and the repo from build-packages.sh + make-repo.sh.
# What stays upstream's: the kernel, the boot loaders (signed shim/GRUB) and the boot records — replayed
# as they are, so the image stays a hybrid ISO that Etcher, Rufus or Mint's USB Image Writer write to a
# stick in one step. What changes: our packages in the live system, and the manifest/size/checksums.
# Reproducible from pinned inputs: all dates are the last git commit's (SOURCE_DATE_EPOCH), and the
# chroot's logs and caches that vary between runs are removed (check-iso.sh builds twice and compares).
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
source "$here/config.env"
[[ $EUID -eq 0 ]] || { echo "run as root" >&2; exit 1; }
# Run through `wsl -u root` or sudo: keep the work area in the building user's home.
owner=${SUDO_USER:-$(stat -c %U "$here/config.env")}
[[ $WORK == /root/* ]] && { WORK=$(getent passwd "$owner" | cut -d: -f6)/cinminai-build; M1=$WORK/m1; }
export SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH:-$(git -c safe.directory='*' -C "$here" log -1 --format=%ct)}

up=$WORK/upstream
b=$M1/build
rootfs=$b/rootfs
iso_in=$up/$MINT_ISO
repo=$M1/repo
log() { printf '\n== %s\n' "$*"; }

# --- 1. upstream ISO, repo ----------------------------------------------------------
log "verify upstream ISO"
mkdir -p "$up"
[[ -f $iso_in ]] || curl -fL -o "$iso_in" "$MINT_MIRROR/$MINT_ISO"
echo "$MINT_ISO_SHA256  $iso_in" | sha256sum -c -
[[ -d $repo/dists/$REPO_SUITE ]] || { echo "no repo at $repo; run build-packages.sh and make-repo.sh" >&2; exit 1; }
keyring=$(ls "$M1/pkgs/$CINMINAI_VERSION"/cinminai-archive-keyring_*.deb)
mkdir -p "$M1"
dpkg-deb --fsys-tarfile "$keyring" | tar -xO ./usr/share/keyrings/cinminai-archive-keyring.gpg > "$M1/build-key.gpg"

# --- 2. unpack ------------------------------------------------------------------------
log "unpack"
rm -rf "$b"; mkdir -p "$b/iso"
xorriso -osirrox on -indev "$iso_in" \
    -extract /casper/filesystem.squashfs "$b/filesystem.squashfs.orig" \
    -extract /casper/filesystem.manifest "$b/manifest.upstream" \
    -extract /md5sum.txt "$b/iso/md5sum.txt" 2>&1 | tail -1
chmod u+w "$b/iso/md5sum.txt" "$b/manifest.upstream"
unsquashfs -s "$b/filesystem.squashfs.orig" > "$b/squashfs-info.txt"
comp=$(awk '/^Compression/ {print $2}' "$b/squashfs-info.txt")
bsize=$(awk '/^Block size/ {print $3}' "$b/squashfs-info.txt")
unsquashfs -q -d "$rootfs" "$b/filesystem.squashfs.orig"
rm "$b/filesystem.squashfs.orig"

# --- 3. install our packages in the chroot -----------------------------------------------
mounts=()
cleanup() { for ((i=${#mounts[@]}-1; i>=0; i--)); do umount -l "${mounts[i]}" 2>/dev/null || true; done; }
trap cleanup EXIT
bind() { mkdir -p "$2"; mount "${@:3}" --bind "$1" "$2"; mounts+=("$2"); }

log "chroot: install cinminai-desktop $CINMINAI_VERSION"
mount -t proc proc "$rootfs/proc"; mounts+=("$rootfs/proc")
mount -t sysfs sys "$rootfs/sys"; mounts+=("$rootfs/sys")
bind /dev "$rootfs/dev"
bind /dev/pts "$rootfs/dev/pts"
bind "$repo" "$rootfs/mnt/cinminai-repo" -o ro
printf '#!/bin/sh\nexit 101\n' > "$rootfs/usr/sbin/policy-rc.d"; chmod 755 "$rootfs/usr/sbin/policy-rc.d"   # no services start
# Build-time apt sees only our bind-mounted repo, with its own lists: the image's apt state is untouched
# and the result doesn't depend on the day's Ubuntu or Mint mirror.
cp "$M1/build-key.gpg" "$rootfs/tmp/cinminai-build.gpg"
echo "deb [signed-by=/tmp/cinminai-build.gpg] file:/mnt/cinminai-repo $REPO_SUITE $REPO_COMPONENT" > "$rootfs/tmp/cinminai-build.list"
mkdir -p "$rootfs/tmp/cinminai-lists/partial"
aptopts=(-o Dir::Etc::sourcelist=/tmp/cinminai-build.list -o Dir::Etc::sourceparts=-
         -o Dir::State::Lists=/tmp/cinminai-lists -o APT::Get::List-Cleanup=0)
chroot "$rootfs" apt-get "${aptopts[@]}" update
chroot "$rootfs" env DEBIAN_FRONTEND=noninteractive SOURCE_DATE_EPOCH="$SOURCE_DATE_EPOCH" \
    apt-get "${aptopts[@]}" install -y --no-install-recommends "cinminai-desktop=$CINMINAI_VERSION"

log "chroot: clean up (build-only files, and logs and caches that differ between runs)"
chroot "$rootfs" apt-get clean
cleanup; mounts=()
rm -rf "$rootfs/tmp/cinminai-build.gpg" "$rootfs/tmp/cinminai-build.list" "$rootfs/tmp/cinminai-lists" \
       "$rootfs/usr/sbin/policy-rc.d"
rmdir "$rootfs/mnt/cinminai-repo"
for f in var/log/apt/history.log var/log/apt/term.log var/log/apt/eipp.log.xz var/log/dpkg.log \
         var/log/alternatives.log var/cache/ldconfig/aux-cache; do
    [[ -e $rootfs/$f ]] && : > "$rootfs/$f"   # keep the file (and its owner), drop this run's lines
done
rm -f "$rootfs"/var/cache/debconf/*-old "$rootfs"/var/lib/dpkg/*-old

# --- 4. repack ------------------------------------------------------------------------
log "manifest + size"
# Upstream's manifest format ("name[:arch]<TAB>version", as ${binary:Package} prints it).
chroot "$rootfs" dpkg-query -W --showformat='${binary:Package}\t${Version}\n' > "$b/iso/filesystem.manifest"
du -sx --block-size=1 "$rootfs" | cut -f1 > "$b/iso/filesystem.size"
diff "$b/manifest.upstream" "$b/iso/filesystem.manifest" > "$b/manifest.diff" || true
cat "$b/manifest.diff"

log "squashfs ($comp, block $bsize)"
# mksquashfs takes the filesystem's and every file's time from SOURCE_DATE_EPOCH (and refuses
# -mkfs-time/-all-time on top of it: "can't be used at the same time").
mksquashfs "$rootfs" "$b/iso/filesystem.squashfs" -comp "$comp" -b "$bsize" -noappend -no-progress \
    -processors "$(nproc)" 2>&1 | tail -3

log "md5sum.txt"
for f in casper/filesystem.squashfs casper/filesystem.manifest casper/filesystem.size; do
    sum=$(md5sum "$b/iso/$(basename "$f")" | cut -d' ' -f1)
    sed -i "s#^[0-9a-f]\{32\}  \./$f\$#$sum  ./$f#" "$b/iso/md5sum.txt"
done

log "write ISO (upstream boot setup replayed; dates from SOURCE_DATE_EPOCH)"
out=${OUTDIR:-$M1/out}
mkdir -p "$out"
rm -f "$out/$OUT_ISO"
touch -d "@$SOURCE_DATE_EPOCH" "$b/iso"/*
xorriso -indev "$iso_in" -outdev "$out/$OUT_ISO" \
    -map "$b/iso/filesystem.squashfs" /casper/filesystem.squashfs \
    -map "$b/iso/filesystem.manifest" /casper/filesystem.manifest \
    -map "$b/iso/filesystem.size" /casper/filesystem.size \
    -map "$b/iso/md5sum.txt" /md5sum.txt \
    -boot_image any replay 2>&1 | tail -2
( cd "$out" && sha256sum "$OUT_ISO" | tee "$OUT_ISO.sha256" )
cp "$b/manifest.diff" "$out/$OUT_ISO.manifest-diff"
chown -R "$owner:" "$out" 2>/dev/null || true
ls -l "$out"
