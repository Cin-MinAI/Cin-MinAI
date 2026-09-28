#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Build hook (build-packages.sh): the Python code from src/, and the guide's data (prompt, tools, help cards)
# generated from training/ by gen_data.py.
#   build.sh STAGE REPO
set -euo pipefail
stage=$1 repo=$2
py=$stage/usr/lib/python3/dist-packages/cin_minai
install -d "$py"
for pkg in daemon inference; do
    cp -r "$repo/src/cin_minai/$pkg" "$py/"
done
find "$py" -name __pycache__ -prune -exec rm -rf {} +
python3 gen_data.py "$stage/usr/share/cinminai/guide" "$repo"
install -d "$stage/usr/share/doc/cinminai-daemon"
cat > "$stage/usr/share/doc/cinminai-daemon/copyright" <<COPY
Cin-MinAI assistant daemon: GPL-3.0-or-later (/usr/share/common-licenses/GPL-3).
The guide's help cards and prompt (usr/share/cinminai/guide): CC BY-SA 4.0.
Source: https://github.com/Brickmii/Cin-MinAI
COPY
