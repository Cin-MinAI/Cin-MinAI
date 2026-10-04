#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Make sure the signing key exists; print its fingerprint.
#
# Default: a DEVELOPMENT key, made on first use, with no passphrase, in $M1/gnupg-dev, named
# "not for release" — for local builds and VM tests only. The release key is generated and kept
# offline (Ian decides where) and signs through a subkey (PLAN M1); point SIGNING_GNUPGHOME and
# SIGNING_KEY at it for a release build. This script never creates anything but the development key.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
source "$here/config.env"
export GNUPGHOME=$SIGNING_GNUPGHOME
mkdir -p "$GNUPGHOME"; chmod 700 "$GNUPGHOME"
# The release key (D72) lives only on the key stick: building packages needs just its public half (this PC's
# public keyring); signing (make-repo.sh, run by release-sign.sh) passes --secret to require the secret subkey.
list=--list-keys; [[ ${1:-} == --secret || $SIGNING_KEY == cinminai-dev ]] && list=--list-secret-keys
if ! gpg $list "$SIGNING_KEY" >/dev/null 2>&1; then
    [[ $SIGNING_KEY == cinminai-dev ]] || { echo "signing key $SIGNING_KEY not found in $GNUPGHOME ($list)" >&2; exit 1; }
    gpg --batch --pinentry-mode loopback --passphrase '' \
        --quick-gen-key 'Cin-MinAI development archive key, not for release (cinminai-dev) <dev@cinminai.invalid>' \
        ed25519 sign 2y >&2
fi
gpg $list --with-colons "$SIGNING_KEY" | awk -F: '/^fpr/ {print $10; exit}'
