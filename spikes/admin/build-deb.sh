#!/usr/bin/env bash
# Build cinminai-admin-spike_VERSION_all.deb (mechanism + demo client + harmless demo service) and
# add it to the spike apt repo (spikes/iso-remaster). No test polkit rule: real auth_admin only.
#   ./build-deb.sh [VERSION]      (WSL, as the normal user)
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
source "$here/../iso-remaster/config.env"
version=${1:-0.1}
root=$(mktemp -d)
trap 'rm -rf "$root"' EXIT

install -Dm755 "$here/mechanism/cinminai-admin" "$root/usr/libexec/cinminai/cinminai-admin"
install -Dm644 "$here/mechanism/org.cinminai.Admin1.conf" "$root/usr/share/dbus-1/system.d/org.cinminai.Admin1.conf"
install -Dm644 "$here/mechanism/org.cinminai.Admin1.service" "$root/usr/share/dbus-1/system-services/org.cinminai.Admin1.service"
install -Dm644 "$here/mechanism/cinminai-admin.service" "$root/usr/lib/systemd/system/cinminai-admin.service"
install -Dm644 "$here/mechanism/org.cinminai.admin.policy" "$root/usr/share/polkit-1/actions/org.cinminai.admin.policy"
install -Dm755 "$here/client/cinminai-admin-demo" "$root/usr/bin/cinminai-admin-demo"
install -Dm644 "$here/test/cinminai-demo.service" "$root/usr/lib/systemd/system/cinminai-demo.service"

mkdir -p "$root/DEBIAN"
cat > "$root/DEBIAN/control" <<EOF
Package: cinminai-admin-spike
Version: $version
Architecture: all
Maintainer: Cin-MinAI <cinminai-spike@invalid>
Depends: python3, python3-gi, dbus, polkitd | policykit-1, systemd
Section: admin
Priority: optional
Description: Cin-MinAI admin mechanism (M0 spike)
 D-Bus activated, polkit-checked root mechanism with a fixed verb set, a demo client,
 and a harmless demo service to exercise it.
EOF
cat > "$root/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
if [ "$1" = configure ]; then
    install -d -m750 -g adm /var/log/cinminai
    [ -e /var/log/cinminai/admin.log ] || install -m640 -g adm /dev/null /var/log/cinminai/admin.log
    chattr +a /var/log/cinminai/admin.log 2>/dev/null || true
    systemctl daemon-reload || true
    dbus-send --system --type=method_call --dest=org.freedesktop.DBus / org.freedesktop.DBus.ReloadConfig || true
    systemctl start cinminai-demo.service || true
fi
EOF
cat > "$root/DEBIAN/prerm" <<'EOF'
#!/bin/sh
set -e
systemctl stop cinminai-admin.service cinminai-demo.service 2>/dev/null || true
EOF
chmod 755 "$root/DEBIAN/postinst" "$root/DEBIAN/prerm"

out="$WORK/pkgs/admin"
mkdir -p "$out"
deb="$out/cinminai-admin-spike_${version}_all.deb"
dpkg-deb --root-owner-group --build "$root" "$deb" >/dev/null
GNUPGHOME=$WORK/gnupg reprepro -b "$WORK/repo" includedeb "$REPO_SUITE" "$deb"
echo "built and published: $deb"
