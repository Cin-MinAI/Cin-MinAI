#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Make the release signing key (PLAN M1, D46, D70, D72) — once, with Ian at the keyboard. Run it in a WSL terminal
# window (the passphrase prompts need one), with the key stick plugged in:
#
#   bash /mnt/c/Users/Ian/Cin-minAI/distro/release-key.sh D        (D = the stick's drive letter)
#
# Ian (2026-10-04): "Require the key any time for a signing." So no secret key ever stays on this PC: the master key
# (certify only, 5 years) and the signing subkey (2 years) are made in memory (/dev/shm) and saved only to the
# stick, both protected by Ian's passphrase. This PC keeps the public key alone ($WORK/gnupg-release-public), which
# is all that building packages needs. Signing a release is release-sign.sh: stick in, passphrase, signed in
# memory, stick out. Nothing is written anywhere until every step has worked.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
source "$here/config.env"
die() { echo "STOP: $*" >&2; exit 1; }
letter=${1:?drive letter of the key stick, e.g. D}; letter=${letter%:}; lower=${letter,,}
stick=/mnt/$lower out=/mnt/$lower/cinminai-signing-key pub=$WORK/gnupg-release-public
# rehearsal only (CINMINAI_KEY_REHEARSAL=DIR): a folder instead of the stick and the PC keyring, a scripted pinentry
if [[ -n ${CINMINAI_KEY_REHEARSAL:-} ]]; then
    stick=$CINMINAI_KEY_REHEARSAL out=$CINMINAI_KEY_REHEARSAL/cinminai-signing-key pub=$CINMINAI_KEY_REHEARSAL/gnupg-release-public
fi
[[ -t 0 || -n ${CINMINAI_KEY_REHEARSAL:-} ]] || die "run this in a terminal window (it asks for passphrases)"
export GPG_TTY=$(tty || true)
[[ -e $pub ]] && die "$pub already exists: a release key was made before"

if [[ -z ${CINMINAI_KEY_REHEARSAL:-} ]] && ! mountpoint -q "$stick"; then
    echo "Connecting the stick ($letter:) to Linux at $stick — sudo asks for your Linux password."
    sudo mkdir -p "$stick"
    sudo mount -t drvfs "$letter:" "$stick" -o "uid=$(id -u),gid=$(id -g)"
fi
[[ -e $out ]] && die "the stick already has $out"

tmp=$(mktemp -d /dev/shm/cinminai-key.XXXXXX)
chmod 700 "$tmp"
trap 'gpgconf --homedir "$tmp" --kill all 2>/dev/null; rm -rf "$tmp"' EXIT
export GNUPGHOME=$tmp
echo "pinentry-program ${CINMINAI_PINENTRY:-/usr/bin/pinentry-curses}" > "$tmp/gpg-agent.conf"
uid="Cin-MinAI Archive Key"

cat <<'EOF'

== 1/3  The master key ==
Choose a passphrase only you know, and write it down where you keep important papers. You'll type it every
time a release is signed, and to renew the key. GnuPG asks for it twice now, then a few more times below.
EOF
gpg --quick-gen-key "$uid" ed25519 cert 5y
fpr=$(gpg --list-keys --with-colons "$uid" | awk -F: '/^fpr/ {print $10; exit}')
echo; echo "== 2/3  The signing subkey =="
gpg --quick-add-key "$fpr" ed25519 sign 2y

echo; echo "== 3/3  Saving to the stick =="
gpg --armor --export "$fpr" > "$tmp/cinminai-archive-key.public.asc"
gpg --armor --export-secret-keys "$fpr" > "$tmp/cinminai-archive-key.MASTER-SECRET.asc"
gpg --armor --export-secret-subkeys "$fpr" > "$tmp/cinminai-archive-key.signing-subkey.asc"
cp "$tmp/openpgp-revocs.d/$fpr.rev" "$tmp/cinminai-archive-key.revocation.asc"

# everything worked: write the stick, then this PC's public keyring
mkdir -p "$out"
cp "$tmp"/cinminai-archive-key.{public,MASTER-SECRET,signing-subkey,revocation}.asc "$out/"
cat > "$out/README.txt" <<EOF
CIN-MINAI ARCHIVE SIGNING KEY — keep this stick in a drawer. Every release signing needs it.

Made $(date -u +%F) with distro/release-key.sh.
Fingerprint: $fpr
User ID:     $uid
Master key:  ed25519, certify only, expires in 5 years (renewable)
Subkey:      ed25519, signing, expires in 2 years (renewable)
Both are protected by Ian's passphrase. No secret key is kept on any computer.

Files
  cinminai-archive-key.signing-subkey.asc  what release-sign.sh uses: the signing subkey (the master is a stub in it)
  cinminai-archive-key.MASTER-SECRET.asc   the master key: only to renew or replace the subkey
  cinminai-archive-key.public.asc          the public key (it's in the cinminai-archive-keyring package)
  cinminai-archive-key.revocation.asc      the emergency switch: publishing it declares the key dead. Only if the
                                           master key is lost or stolen. (Neutralised with a ':' on its block
                                           line; remove that ':' to use it.)

Sign a release (dev PC, WSL terminal, stick in):
  bash /mnt/c/Users/Ian/Cin-minAI/distro/release-sign.sh $letter
Renew the subkey (before $(date -u -d '+2 years' +%F)):
  import MASTER-SECRET.asc into a temporary keyring in /dev/shm, gpg --quick-set-expire, then export the
  subkey file and the public key again (the keyring package needs the new public key).
EOF
mkdir -p "$pub"; chmod 700 "$pub"
GNUPGHOME=$pub gpg --batch --import "$tmp/cinminai-archive-key.public.asc" 2>/dev/null
echo "$fpr:6:" | GNUPGHOME=$pub gpg --batch --import-ownertrust 2>/dev/null
echo "$fpr" > "$pub/fingerprint"
sync

echo; echo "== Done =="
echo "Fingerprint: $fpr"
echo "On the stick: $(ls "$out" | tr '\n' ' ')"
echo "This PC keeps the public key only ($pub): secret keys here: $(GNUPGHOME=$pub gpg -K 2>/dev/null | grep -c '^sec' || true)"
echo
echo "Now eject the stick in Windows (Safely Remove) and keep it in a drawer. Tell Claude: 'the key is made'."
