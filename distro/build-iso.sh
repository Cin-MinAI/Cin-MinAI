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
[[ $GUIDE_LOCAL == /root/* ]] && GUIDE_LOCAL=$(getent passwd "$owner" | cut -d: -f6)${GUIDE_LOCAL#/root}
export SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH:-$(git -c safe.directory='*' -C "$here" log -1 --format=%ct)}

# Free space first. WSL's disk file lives on the Windows drive and grows with every build (a build needs
# ~15 GB while it runs); on 2026-09-27 two builds plus a comparison filled C: to 0 bytes free.
need_gb=${MIN_FREE_GB:-20}
for fs in /mnt/c /; do
    [[ -d $fs ]] || continue
    free=$(df --output=avail -BG "$fs" | tail -1 | tr -dc 0-9)
    (( free >= need_gb )) || { echo "only ${free} GB free on $fs (need ${need_gb}); free space first" >&2; exit 1; }
done

# BOOTTEST=1: the boot-test variant for distro/vm-boottest.ps1 — adds cinminai-boottest (test-packages/)
# and a 5 s timeout to the live boot menu (upstream's waits for a key press). Separate name and folder;
# never published.
BOOTTEST=${BOOTTEST:-0}
[[ $BOOTTEST == 1 ]] && OUT_ISO=${OUT_ISO%.iso}-boottest.iso

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
# The guide model (D23): its own file on the ISO, next to the live system — inside the squashfs it would
# push that past 4 GiB (ISO 9660's file limit; also what Rufus's FAT32 mode can't copy). The live session
# reads it from the stick; cinminai-guide-model copies it into an installed system.
log "verify the guide model"
model=$WORK/models/$GUIDE_FILE
mkdir -p "$WORK/models"
if [[ ! -f $model ]]; then
    if [[ -f $GUIDE_LOCAL ]]; then cp "$GUIDE_LOCAL" "$model"
    elif [[ -n $GUIDE_URL ]]; then curl -fL -o "$model" "$GUIDE_URL"
    else echo "no guide model: set GUIDE_LOCAL or GUIDE_URL (config.env)" >&2; exit 1; fi
fi
echo "$GUIDE_SHA256  $model" | sha256sum -c -
touch -d "@$SOURCE_DATE_EPOCH" "$model"   # our cached copy: its date goes into the ISO
keyring=$(ls "$M1/pkgs/$CINMINAI_VERSION"/cinminai-archive-keyring_*.deb)
mkdir -p "$M1"
dpkg-deb --fsys-tarfile "$keyring" | tar -xO ./usr/share/keyrings/cinminai-archive-keyring.gpg > "$M1/build-key.gpg"

# --- 2. unpack ------------------------------------------------------------------------
log "unpack"
rm -rf "$b"; mkdir -p "$b/iso"
xorriso -osirrox on -indev "$iso_in" \
    -extract /casper/filesystem.squashfs "$b/filesystem.squashfs.orig" \
    -extract /casper/filesystem.manifest "$b/manifest.upstream" \
    -extract /casper/filesystem.size "$b/size.upstream" \
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
# apt's update hooks rebuild the command-not-found database and the software catalogue (AppStream) from
# the lists apt can see — during the build, only ours — so Mint's would be replaced by near-empty ones
# (found 2026-09-27: commands.db 3.8 vs 4.05 MB, swcatalog caches rewritten; also the one thing that made
# two builds differ). Our packages add nothing to either: keep upstream's exactly.
upstream_kept=(var/lib/command-not-found var/cache/swcatalog var/lib/swcatalog)
mkdir -p "$b/kept"
for d in "${upstream_kept[@]}"; do [[ -d $rootfs/$d ]] && { mkdir -p "$b/kept/$(dirname "$d")"; cp -a "$rootfs/$d" "$b/kept/$d"; }; done
aptopts=(-o Dir::Etc::sourcelist=/tmp/cinminai-build.list -o Dir::Etc::sourceparts=-
         -o Dir::State::Lists=/tmp/cinminai-lists -o APT::Get::List-Cleanup=0)
chroot "$rootfs" apt-get "${aptopts[@]}" update
chroot "$rootfs" env DEBIAN_FRONTEND=noninteractive SOURCE_DATE_EPOCH="$SOURCE_DATE_EPOCH" \
    apt-get "${aptopts[@]}" install -y --no-install-recommends "cinminai-desktop=$CINMINAI_VERSION"
if [[ $BOOTTEST == 1 ]]; then
    log "chroot: add the boot test (test variant only)"
    cp "$M1/pkgs-test/$CINMINAI_VERSION"/cinminai-boottest_*.deb "$rootfs/tmp/boottest.deb"
    chroot "$rootfs" dpkg -i /tmp/boottest.deb
    rm -f "$rootfs/tmp/boottest.deb"
fi

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
for d in "${upstream_kept[@]}"; do
    [[ -d $b/kept/$d ]] && { rm -rf "${rootfs:?}/$d"; cp -a "$b/kept/$d" "$rootfs/$d"; }
done
rm -rf "$b/kept"

# --- 4. repack ------------------------------------------------------------------------
log "manifest + size"
# Upstream's manifest format ("name[:arch]<TAB>version", as ${binary:Package} prints it).
chroot "$rootfs" dpkg-query -W --showformat='${binary:Package}\t${Version}\n' > "$b/iso/filesystem.manifest"
# The installer reads filesystem.size to estimate the space an install needs. `du` on the unpacked tree
# isn't reproducible (directories keep the blocks they grew while apt ran: two builds differed by 8 KB),
# so: upstream's size + the Installed-Size of what we added (KiB, from dpkg).
ours=$(chroot "$rootfs" dpkg-query -W --showformat='${Package} ${Installed-Size}\n' \
       | awk '$1 ~ /^cinminai-/ {s += $2} END {print s + 0}')
echo $(( $(cat "$b/size.upstream") + ours * 1024 )) > "$b/iso/filesystem.size"
diff "$b/manifest.upstream" "$b/iso/filesystem.manifest" > "$b/manifest.diff" || true
cat "$b/manifest.diff"

log "squashfs ($comp, block $bsize)"
# mksquashfs takes the filesystem's and every file's time from SOURCE_DATE_EPOCH (and refuses
# -mkfs-time/-all-time on top of it: "can't be used at the same time").
mksquashfs "$rootfs" "$b/iso/filesystem.squashfs" -comp "$comp" -b "$bsize" -noappend -no-progress \
    -processors "$(nproc)" 2>&1 | tail -3

log "md5sum.txt"
maps=(-map "$b/iso/filesystem.squashfs" /casper/filesystem.squashfs
      -map "$b/iso/filesystem.manifest" /casper/filesystem.manifest
      -map "$b/iso/filesystem.size" /casper/filesystem.size)
if [[ $BOOTTEST == 1 ]]; then   # boot the first menu entry after 5 s (the config isn't signed; shim/GRUB are untouched)
    xorriso -osirrox on -indev "$iso_in" -extract /boot/grub/grub.cfg "$b/iso/grub.cfg" >/dev/null 2>&1
    chmod u+w "$b/iso/grub.cfg"
    sed -i '1i set timeout=5' "$b/iso/grub.cfg"
    maps+=(-map "$b/iso/grub.cfg" /boot/grub/grub.cfg)
fi
maps+=(-map "$model" "/cinminai/models/$GUIDE_FILE")
grep -q "cinminai/models/$GUIDE_FILE\$" "$b/iso/md5sum.txt" ||
    echo "$(md5sum "$model" | cut -d' ' -f1)  ./cinminai/models/$GUIDE_FILE" >> "$b/iso/md5sum.txt"
for f in casper/filesystem.squashfs casper/filesystem.manifest casper/filesystem.size boot/grub/grub.cfg; do
    [[ -f $b/iso/$(basename "$f") ]] || continue
    sum=$(md5sum "$b/iso/$(basename "$f")" | cut -d' ' -f1)
    sed -i "s#^[0-9a-f]\{32\}  \./$f\$#$sum  ./$f#" "$b/iso/md5sum.txt"
done

log "write ISO (upstream boot setup replayed; dates from SOURCE_DATE_EPOCH)"
out=${OUTDIR:-$M1/out}
[[ $BOOTTEST == 1 ]] && out=${OUTDIR:-$M1/out-test}
mkdir -p "$out"
rm -f "$out/$OUT_ISO"
touch -d "@$SOURCE_DATE_EPOCH" "$b/iso"/*
xorriso -indev "$iso_in" -outdev "$out/$OUT_ISO" "${maps[@]}" \
    -map "$b/iso/md5sum.txt" /md5sum.txt \
    -boot_image any replay 2>&1 | tail -2
( cd "$out" && sha256sum "$OUT_ISO" | tee "$OUT_ISO.sha256" )
cp "$b/manifest.diff" "$out/$OUT_ISO.manifest-diff"
chown -R "$owner:" "$out" 2>/dev/null || true
[[ ${KEEP_BUILD:-0} == 1 ]] || rm -rf "$b"   # the unpacked live system (~11 GB); KEEP_BUILD=1 keeps it
ls -l "$out"
