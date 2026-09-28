#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Build our .deb packages from distro/packages/<name>/ (M1).
#
#   ./build-packages.sh            (in WSL, as the normal user)
#
# Each package directory has `control` (with @VERSION@ etc.), an optional `conffiles`, an optional `links`
# ("link-path target" per line: git on the Windows dev PC stores no symlinks), and `root/`, the files as
# installed; files starting with #! are made executable. packages/ go to $M1/pkgs (the repo);
# test-packages/ (the boot test) go to $M1/pkgs-test and never into the repository. @PLACEHOLDERS@ in control and in root/ are filled from config.env. The archive key
# is exported from the signing keyring into cinminai-archive-keyring. Reproducible: file dates are the
# last git commit's (SOURCE_DATE_EPOCH), owners root:root, fixed compression.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
source "$here/config.env"
export SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH:-$(git -C "$here" log -1 --format=%ct)}
"$here/signing-key.sh" >/dev/null   # makes the development key on first use
export GNUPGHOME=$SIGNING_GNUPGHOME

fill() {  # file: replace @PLACEHOLDERS@ in place
    sed -i -e "s#@VERSION@#$CINMINAI_VERSION#g" -e "s#@MINT_VERSION@#$MINT_VERSION#g" \
           -e "s#@REPO_URL@#$REPO_URL#g" -e "s#@REPO_SUITE@#$REPO_SUITE#g" \
           -e "s#@REPO_COMPONENT@#$REPO_COMPONENT#g" "$1"
}

for dir in "$here"/packages/*/ "$here"/test-packages/*/; do
    name=$(basename "$dir")
    case $dir in */test-packages/*) out=$M1/pkgs-test/$CINMINAI_VERSION ;; *) out=$M1/pkgs/$CINMINAI_VERSION ;; esac
    mkdir -p "$out"
    stage=$(mktemp -d)
    mkdir -p "$stage/DEBIAN"
    [[ -d $dir/root ]] && cp -a "$dir/root/." "$stage/"
    cp "$dir/control" "$stage/DEBIAN/control"
    [[ -f $dir/conffiles ]] && cp "$dir/conffiles" "$stage/DEBIAN/conffiles"
    for s in preinst postinst prerm postrm triggers; do
        [[ -f $dir/$s ]] && install -m755 "$dir/$s" "$stage/DEBIAN/$s"
    done
    # A package may generate files at build time (e.g. branding renders its images from the SVGs):
    # build.sh STAGE_DIR REPO_ROOT, run from its own directory.
    [[ -f $dir/build.sh ]] && ( cd "$dir" && bash ./build.sh "$stage" "$(cd "$here/.." && pwd)" )
    if [[ $name == cinminai-archive-keyring ]]; then
        install -Dm644 /dev/null "$stage/usr/share/keyrings/cinminai-archive-keyring.gpg"
        gpg --export "$SIGNING_KEY" > "$stage/usr/share/keyrings/cinminai-archive-keyring.gpg"
    fi
    find "$stage" -type f ! -path "$stage/usr/share/keyrings/*" -exec grep -Il . {} + 2>/dev/null \
        | while read -r f; do fill "$f"; done
    # Installed-Size (KiB, apparent sizes: the same on every build host); build-iso.sh adds it to the
    # installer's space estimate.
    kib=$(du -s --apparent-size --block-size=1024 --exclude=DEBIAN "$stage" | cut -f1)
    sed -i "/^Architecture:/a Installed-Size: $kib" "$stage/DEBIAN/control"
    find "$stage" -type d -exec chmod 755 {} +
    find "$stage" -type f -exec chmod 644 {} +
    find "$stage" -type f -exec sh -c 'head -c2 "$1" | grep -q "#!"' _ {} \; -exec chmod 755 {} \;
    [[ -f $stage/DEBIAN/triggers ]] && chmod 644 "$stage/DEBIAN/triggers"
    if [[ -f $dir/links ]]; then
        grep -v '^#' "$dir/links" | while read -r link target; do
            [[ -n $link ]] || continue
            mkdir -p "$stage$(dirname "$link")"; ln -sfn "$target" "$stage$link"
        done
    fi
    find "$stage" -exec touch -h -d "@$SOURCE_DATE_EPOCH" {} +
    deb=$out/${name}_${CINMINAI_VERSION}_all.deb
    dpkg-deb -Zxz --root-owner-group --build "$stage" "$deb" >/dev/null
    rm -rf "$stage"
    printf '%s  %s\n' "$(sha256sum "$deb" | cut -d' ' -f1)" "$(basename "$deb")"
done
