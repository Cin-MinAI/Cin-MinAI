#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Build hook (build-packages.sh): render the wallpapers and the boot splash from artwork/ into the package.
#   build.sh STAGE REPO
# Uses uv (setup_train.sh installs it) to run render.py with cairosvg and Pillow in a throwaway
# environment: nothing is installed on the build machine.
set -euo pipefail
stage=$1 repo=$2
uv=${UV:-$(command -v uv || echo "$HOME/.local/bin/uv")}
"$uv" run --quiet --no-project --with cairosvg==2.9.1 --with pillow==12.3.0 python render.py "$stage" "$repo"
