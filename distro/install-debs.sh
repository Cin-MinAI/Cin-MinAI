#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Install Cin-MinAI test packages, but never let apt remove anything on the way (2026-10-03: a daemon update made apt
# remove the sidebar, the panel icon and the desktop meta-package, and the removal was easy to miss in its list).
#
#   ~/cinminai-debs/install-debs.sh cinminai-aicui_*.deb cinminai-daemon_*.deb ...   (from ~/cinminai-debs)
set -euo pipefail
cd "$(dirname "$0")"
[ $# -gt 0 ] || { echo "Name the .deb files to install."; exit 1; }
debs=()
for f in "$@"; do debs+=("./${f#./}"); done
plan=$(apt-get -s install "${debs[@]}" 2>&1) || { echo "$plan"; exit 1; }
removed=$(printf '%s\n' "$plan" | grep '^Remv ' || true)
if [ -n "$removed" ] || ! printf '%s\n' "$plan" | grep -q ' 0 to remove'; then
    echo "STOPPED: installing these would REMOVE packages:"
    printf '%s\n' "$removed" | sed 's/^Remv /  - /'
    echo "Nothing was changed. Tell Claude (or install the matching new versions of those packages too)."
    exit 2
fi
if printf '%s\n' "$plan" | grep -q 'DOWNGRADED'; then
    echo "STOPPED: this would install OLDER versions than the ones you have:"
    printf '%s\n' "$plan" | sed -n '/DOWNGRADED/,/upgraded/p' | sed '1d;$d'
    echo "Nothing was changed. Run it again with ALLOW_DOWNGRADE=1 in front if that's what you want."
    [ "${ALLOW_DOWNGRADE:-}" = 1 ] || exit 3
fi
printf '%s\n' "$plan" | grep -E '^Inst ' | sed 's/^Inst /  + /'
sudo apt-get install -y "${debs[@]}"
