#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Publish the built packages to our signed apt repository (M1): $M1/repo, the tree that goes to GitHub
# Pages (PLAN D46) and that build-iso.sh bind-mounts into the chroot.
#
#   ./make-repo.sh                 (in WSL, as the normal user, after build-packages.sh)
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
source "$here/config.env"
export SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH:-$(git -C "$here" log -1 --format=%ct)}
fpr=$("$here/signing-key.sh")
export GNUPGHOME=$SIGNING_GNUPGHOME
repo=$M1/repo
# Rebuilt from scratch each time: the repo carries the current packages only (apt needs no history), and a
# rebuilt package with the same version but new dates would otherwise be refused by reprepro.
rm -rf "$repo/db" "$repo/dists" "$repo/pool"
mkdir -p "$repo/conf"
cat > "$repo/conf/distributions" <<EOF
Origin: Cin-MinAI
Label: Cin-MinAI
Codename: $REPO_SUITE
Architectures: amd64
Components: $REPO_COMPONENT
Description: Cin-MinAI packages (based on Linux Mint $MINT_VERSION)
SignWith: $fpr
EOF
for deb in "$M1/pkgs/$CINMINAI_VERSION"/*.deb; do
    reprepro -b "$repo" includedeb "$REPO_SUITE" "$deb"
done
gpg --armor --export "$fpr" > "$repo/cinminai-archive-keyring.asc"   # for people who add the repo by hand
reprepro -b "$repo" list "$REPO_SUITE"
[[ $SIGNING_KEY == cinminai-dev ]] && echo "NOTE: signed with the DEVELOPMENT key — not for publishing" >&2
exit 0
