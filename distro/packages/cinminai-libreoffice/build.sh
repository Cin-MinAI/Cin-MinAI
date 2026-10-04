#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Build hook (build-packages.sh): the extension from src/libreoffice-extension/, installed unpacked as a
# bundled extension (LibreOffice registers it at its next start; dpkg owns every file, no unopkg).
#   build.sh STAGE REPO
set -euo pipefail
stage=$1 repo=$2
ext=$stage/usr/lib/libreoffice/share/extensions/cinminai
install -d "$ext" "$stage/usr/share/doc/cinminai-libreoffice"
cp -r "$repo/src/libreoffice-extension/." "$ext/"
find "$ext" -name __pycache__ -prune -exec rm -rf {} +
cat > "$stage/usr/share/doc/cinminai-libreoffice/copyright" <<COPY
Cin-MinAI LibreOffice extension: GPL-3.0-or-later (/usr/share/common-licenses/GPL-3).
Source: https://github.com/Cin-MinAI/Cin-MinAI
COPY
