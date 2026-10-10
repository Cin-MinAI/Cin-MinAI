#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Build hook (build-packages.sh): copy the SearXNG build (distro/build-searxng.sh, run first).
#   build.sh STAGE REPO
set -euo pipefail
stage=$1 repo=$2
source "$repo/distro/config.env"
src=$M1/searxng/$SEARXNG_COMMIT
[[ -f $src/BUILDINFO ]] || { echo "no SearXNG build at $src: run distro/build-searxng.sh first" >&2; exit 1; }
install -d "$stage/usr/lib/cinminai/searxng" "$stage/usr/share/doc/cinminai-search"
cp -a "$src/app" "$src/lib" "$stage/usr/lib/cinminai/searxng/"
cp "$src/BUILDINFO" "$stage/usr/share/doc/cinminai-search/BUILDINFO"
{
    echo "SearXNG: GNU Affero General Public License v3.0 or later. Source: $SEARXNG_REPO at $SEARXNG_COMMIT"
    echo "(unchanged; the launcher, Cin-MinAI's own, sets two things before it starts: see /usr/lib/cinminai/searxng/run)."
    echo
    cat "$src/LICENSE"
    echo
    echo "Its libraries and their licenses:"
    cat "$src/LICENSES"
} > "$stage/usr/share/doc/cinminai-search/copyright"
