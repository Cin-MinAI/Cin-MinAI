#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Build hook (build-packages.sh): the Mozilla-signed extension (distro/firefox-sign.py, run first) and the policy that
# installs it. The xpi's path carries its version: a new install_url is what makes Firefox take an update (M0 spike).
#   build.sh STAGE REPO
set -euo pipefail
stage=$1 repo=$2
source "$repo/distro/config.env"
version=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["version"])' \
    "$repo/src/cin_minai/firefox/extension/manifest.json")
xpi=$WORK/firefox/assistant-$version.xpi
[[ -f $xpi ]] || { echo "no signed extension $xpi: run distro/firefox-sign.py first" >&2; exit 1; }
dest=/usr/share/cinminai/firefox/assistant-$version.xpi
install -Dm644 "$xpi" "$stage$dest"
install -d "$stage/etc/firefox/policies" "$stage/usr/share/doc/cinminai-firefox"
cat > "$stage/etc/firefox/policies/policies.json" <<JSON
{
  "policies": {
    "ExtensionSettings": {
      "assistant@cinminai.org": {
        "installation_mode": "force_installed",
        "install_url": "file://$dest"
      }
    }
  }
}
JSON
cat > "$stage/usr/share/doc/cinminai-firefox/copyright" <<COPY
Cin-MinAI Firefox extension: GPL-3.0-or-later (/usr/share/common-licenses/GPL-3), signed by Mozilla.
Source: https://github.com/Cin-MinAI/Cin-MinAI (src/cin_minai/firefox/extension)
COPY
