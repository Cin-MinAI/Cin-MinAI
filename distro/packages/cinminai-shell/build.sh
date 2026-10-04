#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Build hook (build-packages.sh): the terminal relay's Python code from src/, and start.bash where ~/.bashrc
# finds it (D77: the line is added only when the person turns sharing on).
#   build.sh STAGE REPO
set -euo pipefail
stage=$1 repo=$2
py=$stage/usr/lib/python3/dist-packages/cin_minai
install -d "$py" "$stage/usr/share/cinminai/shell" "$stage/usr/share/doc/cinminai-shell"
cp -r "$repo/src/cin_minai/shell" "$py/"
find "$py" -name __pycache__ -prune -exec rm -rf {} +
install -m644 "$repo/src/cin_minai/shell/start.bash" "$stage/usr/share/cinminai/shell/start.bash"
cat > "$stage/usr/share/doc/cinminai-shell/copyright" <<COPY
Cin-MinAI terminal sharing: GPL-3.0-or-later (/usr/share/common-licenses/GPL-3).
Source: https://github.com/Cin-MinAI/Cin-MinAI
COPY
