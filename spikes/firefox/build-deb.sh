#!/usr/bin/env bash
# Build cinminai-firefox-spike_VERSION_all.deb and add it to the spike apt repo (spikes/iso-remaster).
# Test B of the Firefox spike: the extension arrives the way the ISO will ship it, with no user step.
#   - /etc/firefox/policies/policies.json      ExtensionSettings force_installed from a file:// URL
#   - /usr/share/cinminai/firefox/…-VERSION.xpi   the AMO-signed xpi (versioned path: a new
#                                                  install_url is what makes Firefox pick up an update)
#   - /usr/lib/mozilla/native-messaging-hosts/org.cinminai.assistant.json  (system-wide host manifest)
#   - /usr/libexec/cinminai/cinminai-firefox-host
#   - the spike daemon, D-Bus activated on the session bus (stub replies unless config.toml says otherwise)
#   ./build-deb.sh VERSION        (WSL, as the normal user; VERSION must match a signed xpi in dist/)
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
source "$here/../iso-remaster/config.env"
version=${1:?usage: build-deb.sh VERSION (e.g. 0.1.1)}
xpi="$here/dist/cinminai_assistant-$version.xpi"
[[ -f $xpi ]] || { echo "no signed xpi $xpi" >&2; exit 1; }
root=$(mktemp -d)
trap 'rm -rf "$root"' EXIT
chmod 755 "$root"

xpi_dest=/usr/share/cinminai/firefox/assistant-$version.xpi
install -Dm644 "$xpi" "$root$xpi_dest"
install -Dm755 "$here/host/cinminai-firefox-host" "$root/usr/libexec/cinminai/cinminai-firefox-host"
install -d "$root/usr/lib/mozilla/native-messaging-hosts"
sed "s|@HOST_PATH@|/usr/libexec/cinminai/cinminai-firefox-host|" "$here/host/org.cinminai.assistant.json.in" \
    > "$root/usr/lib/mozilla/native-messaging-hosts/org.cinminai.assistant.json"
install -Dm755 "$here/../desktop/daemon.py" "$root/usr/libexec/cinminai/cinminai-daemon-spike"
install -d "$root/usr/share/dbus-1/services"
cat > "$root/usr/share/dbus-1/services/org.cinminai.Assistant1.service" <<EOF
[D-BUS Service]
Name=org.cinminai.Assistant1
Exec=/usr/bin/python3 /usr/libexec/cinminai/cinminai-daemon-spike
EOF
install -d "$root/etc/firefox/policies"
cat > "$root/etc/firefox/policies/policies.json" <<EOF
{
  "policies": {
    "ExtensionSettings": {
      "assistant@cinminai.org": {
        "installation_mode": "force_installed",
        "install_url": "file://$xpi_dest"
      }
    }
  }
}
EOF
chmod 644 "$root/usr/lib/mozilla/native-messaging-hosts/org.cinminai.assistant.json" \
    "$root/usr/share/dbus-1/services/org.cinminai.Assistant1.service" "$root/etc/firefox/policies/policies.json"

mkdir -p "$root/DEBIAN"
echo /etc/firefox/policies/policies.json > "$root/DEBIAN/conffiles"
cat > "$root/DEBIAN/control" <<EOF
Package: cinminai-firefox-spike
Version: $version
Architecture: all
Maintainer: Cin-MinAI <cinminai-spike@invalid>
Depends: firefox, python3 (>= 3.11), python3-gi, dbus
Section: web
Priority: optional
Description: Cin-MinAI Firefox integration (M0 spike)
 Force-installs the signed Cin-MinAI Firefox extension by enterprise policy and registers its
 native messaging host, which relays to the assistant daemon (stub replies in this spike).
EOF

out="$WORK/pkgs/firefox"
mkdir -p "$out"
deb="$out/cinminai-firefox-spike_${version}_all.deb"
dpkg-deb --root-owner-group --build "$root" "$deb" >/dev/null
GNUPGHOME=$WORK/gnupg reprepro -b "$WORK/repo" includedeb "$REPO_SUITE" "$deb"
echo "built and published: $deb"
