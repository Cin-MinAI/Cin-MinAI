#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Build our .deb packages from distro/packages/<name>/ (M1).
#
#   ./build-packages.sh            (in WSL, as the normal user)
#
# Each package directory has `control` (with @VERSION@ etc.), an optional `conffiles`, and `root/`, the
# files as installed. @PLACEHOLDERS@ in control and in root/ are filled from config.env. The archive key
# is exported from the signing keyring into cinminai-archive-keyring. Reproducible: file dates are the
# last git commit's (SOURCE_DATE_EPOCH), owners root:root, fixed compression.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
source "$here/config.env"
export SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH:-$(git -C "$here" log -1 --format=%ct)}
out=$M1/pkgs/$CINMINAI_VERSION
mkdir -p "$out"
"$here/signing-key.sh" >/dev/null   # makes the development key on first use
export GNUPGHOME=$SIGNING_GNUPGHOME

fill() {  # file: replace @PLACEHOLDERS@ in place
    sed -i -e "s#@VERSION@#$CINMINAI_VERSION#g" -e "s#@MINT_VERSION@#$MINT_VERSION#g" \
           -e "s#@REPO_URL@#$REPO_URL#g" -e "s#@REPO_SUITE@#$REPO_SUITE#g" \
           -e "s#@REPO_COMPONENT@#$REPO_COMPONENT#g" "$1"
}

for dir in "$here"/packages/*/; do
    name=$(basename "$dir")
    stage=$(mktemp -d)
    mkdir -p "$stage/DEBIAN"
    [[ -d $dir/root ]] && cp -a "$dir/root/." "$stage/"
    cp "$dir/control" "$stage/DEBIAN/control"
    [[ -f $dir/conffiles ]] && cp "$dir/conffiles" "$stage/DEBIAN/conffiles"
    if [[ $name == cinminai-archive-keyring ]]; then
        install -Dm644 /dev/null "$stage/usr/share/keyrings/cinminai-archive-keyring.gpg"
        gpg --export "$SIGNING_KEY" > "$stage/usr/share/keyrings/cinminai-archive-keyring.gpg"
    fi
    find "$stage" -type f ! -path "$stage/usr/share/keyrings/*" -exec grep -Il . {} + 2>/dev/null \
        | while read -r f; do fill "$f"; done
    find "$stage" -type d -exec chmod 755 {} +
    find "$stage" -type f -exec chmod 644 {} +
    find "$stage" -exec touch -h -d "@$SOURCE_DATE_EPOCH" {} +
    deb=$out/${name}_${CINMINAI_VERSION}_all.deb
    dpkg-deb -Zxz --root-owner-group --build "$stage" "$deb" >/dev/null
    rm -rf "$stage"
    printf '%s  %s\n' "$(sha256sum "$deb" | cut -d' ' -f1)" "$(basename "$deb")"
done
