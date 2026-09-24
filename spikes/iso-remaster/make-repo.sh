#!/usr/bin/env bash
# Build the spike packages at a given version and publish them to a signed apt repo.
#
#   ./make-repo.sh 0.1     # initial repo, baked into the ISO
#   ./make-repo.sh 0.2     # later: an update the installed system should pick up
#
# Runs as a normal user. Spike-only signing key: no passphrase, lives in $WORK/gnupg.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
source "$here/config.env"

version=${1:?usage: make-repo.sh VERSION}
export GNUPGHOME=$WORK/gnupg
repo=$WORK/repo
pkgs=$WORK/pkgs/$version
mkdir -p "$GNUPGHOME" "$repo/conf" "$pkgs"
chmod 700 "$GNUPGHOME"

# --- signing key -------------------------------------------------------------
if ! gpg --list-secret-keys cinminai-spike >/dev/null 2>&1; then
    gpg --batch --pinentry-mode loopback --passphrase '' \
        --quick-gen-key 'Cin-minAI spike archive key <cinminai-spike@invalid>' ed25519 sign 1y
fi
keyid=$(gpg --list-secret-keys --with-colons cinminai-spike | awk -F: '/^fpr/ {print $10; exit}')
gpg --export "$keyid" > "$WORK/cinminai-archive-keyring.gpg"

# --- packages ----------------------------------------------------------------
build_pkg() {  # name, then files are staged by the caller in $root
    local name=$1 desc=$2 depends=${3:-}
    mkdir -p "$root/DEBIAN"
    {
        echo "Package: $name"
        echo "Version: $version"
        echo "Architecture: all"
        echo "Maintainer: Cin-minAI <cinminai-spike@invalid>"
        [[ -n $depends ]] && echo "Depends: $depends"
        echo "Section: misc"
        echo "Priority: optional"
        echo "Description: $desc"
    } > "$root/DEBIAN/control"
    dpkg-deb --root-owner-group --build "$root" "$pkgs/${name}_${version}_all.deb" >/dev/null
}

# cinminai-archive-keyring: our key + apt source, so the installed system tracks our repo.
root=$(mktemp -d)
install -Dm644 "$WORK/cinminai-archive-keyring.gpg" "$root/usr/share/keyrings/cinminai-archive-keyring.gpg"
install -d "$root/etc/apt/sources.list.d"
echo "deb [arch=amd64 signed-by=/usr/share/keyrings/cinminai-archive-keyring.gpg] $REPO_URL $REPO_SUITE $REPO_COMPONENT" \
    > "$root/etc/apt/sources.list.d/cinminai.list"
install -d "$root/DEBIAN"
echo /etc/apt/sources.list.d/cinminai.list > "$root/DEBIAN/conffiles"
build_pkg cinminai-archive-keyring "Cin-minAI archive key and apt source (spike)"
rm -rf "$root"

# cinminai-hello: stands in for the real components; prints its version.
root=$(mktemp -d)
install -d "$root/usr/bin"
printf '#!/bin/sh\necho "cinminai-hello %s"\n' "$version" > "$root/usr/bin/cinminai-hello"
chmod 755 "$root/usr/bin/cinminai-hello"
build_pkg cinminai-hello "Cin-minAI placeholder component (spike)"
rm -rf "$root"

# cinminai-desktop: meta-package, as in SPEC §4.
root=$(mktemp -d)
build_pkg cinminai-desktop "Cin-minAI desktop meta-package (spike)" "cinminai-archive-keyring, cinminai-hello"
rm -rf "$root"

# --- repository --------------------------------------------------------------
cat > "$repo/conf/distributions" <<EOF
Origin: Cin-minAI
Label: Cin-minAI
Codename: $REPO_SUITE
Architectures: amd64
Components: $REPO_COMPONENT
Description: Cin-minAI spike repository
SignWith: $keyid
EOF
for deb in "$pkgs"/*.deb; do
    reprepro -b "$repo" includedeb "$REPO_SUITE" "$deb"
done
reprepro -b "$repo" list "$REPO_SUITE"
