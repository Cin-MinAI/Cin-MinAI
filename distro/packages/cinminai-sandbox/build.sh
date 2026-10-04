#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Build hook (build-packages.sh): the sandbox runner's Python code from src/ (M3 slice 4; the M0 spike's runner).
#   build.sh STAGE REPO
set -euo pipefail
stage=$1 repo=$2
py=$stage/usr/lib/python3/dist-packages/cin_minai
install -d "$py" "$stage/usr/share/doc/cinminai-sandbox"
cp -r "$repo/src/cin_minai/sandbox" "$py/"
find "$py" -name __pycache__ -prune -exec rm -rf {} +
cat > "$stage/usr/share/doc/cinminai-sandbox/copyright" <<COPY
Cin-MinAI sandbox: GPL-3.0-or-later (/usr/share/common-licenses/GPL-3).
Source: https://github.com/Cin-MinAI/Cin-MinAI
COPY
