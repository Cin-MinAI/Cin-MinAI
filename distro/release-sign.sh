#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Sign a release's apt repository with the key stick (PLAN D72: every signing needs the stick). Run by Ian in a WSL
# terminal window, stick plugged in, after the release packages are built:
#
#   bash /mnt/c/Users/Ian/Cin-minAI/distro/release-sign.sh D        (D = the stick's drive letter)
#
# The signing subkey is read from the stick into memory (/dev/shm), make-repo.sh signs $M1/repo with it (GnuPG asks
# for the passphrase), and the in-memory keyring is wiped. Nothing secret is written to this PC. Publishing the
# signed repo (git push to cinminai-apt) needs no key and is a separate step.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
source "$here/config.env"
die() { echo "STOP: $*" >&2; exit 1; }
letter=${1:?drive letter of the key stick, e.g. D}; letter=${letter%:}; lower=${letter,,}
stick=/mnt/$lower key=/mnt/$lower/cinminai-signing-key pub=$WORK/gnupg-release-public
if [[ -n ${CINMINAI_KEY_REHEARSAL:-} ]]; then
    stick=$CINMINAI_KEY_REHEARSAL key=$CINMINAI_KEY_REHEARSAL/cinminai-signing-key pub=$CINMINAI_KEY_REHEARSAL/gnupg-release-public
fi
[[ -t 0 || -n ${CINMINAI_KEY_REHEARSAL:-} ]] || die "run this in a terminal window (it asks for the passphrase)"
export GPG_TTY=$(tty || true)
[[ -f $pub/fingerprint ]] || die "no release key on record ($pub); make it first with release-key.sh"
fpr=$(cat "$pub/fingerprint")

if [[ -z ${CINMINAI_KEY_REHEARSAL:-} ]] && mountpoint -q "$stick" && ! ls "$key" >/dev/null 2>&1; then
    echo "Reconnecting the stick (the earlier connection went stale when it was ejected) — sudo may ask for your password."
    sudo umount -l "$stick"
fi
if [[ -z ${CINMINAI_KEY_REHEARSAL:-} ]] && ! mountpoint -q "$stick"; then
    echo "Connecting the stick ($letter:) to Linux at $stick — sudo asks for your Linux password."
    sudo mkdir -p "$stick"
    sudo mount -t drvfs "$letter:" "$stick" -o "uid=$(id -u),gid=$(id -g)"
fi
[[ -f $key/cinminai-archive-key.signing-subkey.asc ]] || die "no signing subkey on the stick ($key)"

tmp=$(mktemp -d /dev/shm/cinminai-sign.XXXXXX)
chmod 700 "$tmp"
trap 'gpgconf --homedir "$tmp" --kill all 2>/dev/null; rm -rf "$tmp"' EXIT
echo "pinentry-program ${CINMINAI_PINENTRY:-/usr/bin/pinentry-curses}" > "$tmp/gpg-agent.conf"
GNUPGHOME=$tmp gpg --batch --import "$key/cinminai-archive-key.signing-subkey.asc" 2>/dev/null
got=$(GNUPGHOME=$tmp gpg --list-keys --with-colons | awk -F: '/^fpr/ {print $10; exit}')
[[ $got == "$fpr" ]] || die "the stick's key ($got) isn't the one on record ($fpr)"
echo "$fpr:6:" | GNUPGHOME=$tmp gpg --batch --import-ownertrust 2>/dev/null

echo "Signing the apt repository with $fpr — GnuPG asks for the passphrase."
SIGNING_GNUPGHOME=$tmp SIGNING_KEY=$fpr bash "$here/make-repo.sh"
GNUPGHOME=$tmp gpg --verify "$M1/repo/dists/$REPO_SUITE/InRelease" 2>&1 | grep -q "Good signature" \
    || die "the repository's signature doesn't verify"
echo
echo "Signed. The key is wiped from memory; eject the stick (Safely Remove) and put it back in the drawer."
echo "Tell Claude: 'the release is signed'."
