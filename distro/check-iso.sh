#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Check a built ISO without booting it (M1). Booting is checked in a VM, and on the Mint box (PLAN D45).
#
#   wsl -d Ubuntu-24.04 -u root -- /path/to/distro/check-iso.sh [--rebuild]
#
# 1. the live system differs from upstream by exactly our packages (manifest diff: added lines only);
# 2. the boot setup is upstream's, unchanged (El Torito and partition-table report identical), so the image
#    is still a hybrid that USB writers handle in one step;
# 3. md5sum.txt matches the files it lists (casper's "check disc for defects" uses it);
# 4. with --rebuild: build again into a second directory and compare SHA-256 (reproducibility).
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
source "$here/config.env"
owner=${SUDO_USER:-$(stat -c %U "$here/config.env")}
[[ $WORK == /root/* ]] && { WORK=$(getent passwd "$owner" | cut -d: -f6)/cinminai-build; M1=$WORK/m1; }
iso=$M1/out/$OUT_ISO up=$WORK/upstream/$MINT_ISO
fail=0; ok() { echo "PASS  $*"; }; bad() { echo "FAIL  $*"; fail=1; }

diff=$M1/out/$OUT_ISO.manifest-diff
removed=$(grep -c '^<' "$diff" || true); added=$(grep '^>' "$diff" | cut -c3- | cut -f1 | sort | tr '\n' ' ')
want="cinminai-archive-keyring cinminai-branding cinminai-desktop "
[[ $removed == 0 && $added == "$want" ]] && ok "manifest: only our packages added ($added)" \
    || bad "manifest: removed $removed, added: $added"

# The boot entries, their types, flags and sizes must match upstream's; their block positions may move
# (xorriso lays the image out again around the bigger live filesystem), so positions are left out.
report() { xorriso -indev "$1" -report_el_torito plain -report_system_area plain 2>/dev/null \
           | grep -v -E 'Volume id|Creation|Modif|Expir|Effective|size|Media summary' \
           | awk '/^El Torito catalog/ {$NF=""; $(NF-1)=""} /^El Torito boot img/ {$NF=""}
                  /^MBR partition/ && NF>=8 {$(NF-1)=""} /^GPT (start|partname|type)/ {} {print}'; }
if cmp -s <(report "$up") <(report "$iso"); then ok "boot setup identical to upstream except block positions (hybrid USB image kept)"
else bad "boot setup differs from upstream:"; diff <(report "$up") <(report "$iso") | head -20 || true; fi

mnt=$(mktemp -d); mount -o loop,ro "$iso" "$mnt"
if ( cd "$mnt" && grep -E ' \./casper/filesystem\.(squashfs|manifest|size)$' md5sum.txt | md5sum -c --quiet - ); then
    ok "md5sum.txt matches the changed files"; else bad "md5sum.txt"; fi
umount "$mnt"; rmdir "$mnt"

if [[ ${1:-} == --rebuild ]]; then
    OUTDIR=$M1/out-rebuild "$here/build-iso.sh" > "$M1/rebuild.log" 2>&1
    a=$(cut -d' ' -f1 "$M1/out/$OUT_ISO.sha256"); b=$(cut -d' ' -f1 "$M1/out-rebuild/$OUT_ISO.sha256")
    [[ $a == "$b" ]] && ok "reproducible: a second build gives the same SHA-256 ($a)" \
        || bad "not reproducible: $a vs $b (see $M1/rebuild.log)"
fi
exit $fail
