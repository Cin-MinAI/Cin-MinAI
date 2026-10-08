#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Build hook (build-packages.sh): Team Table's core from the pinned submodule third_party/team-table (SPEC §22.4).
# Only the stdlib-only core and the operator command: the MCP server (server.py, tools/, notifications) needs the
# mcp library and stays an optional extra.
#   build.sh STAGE REPO
set -euo pipefail
stage=$1 repo=$2
src=$repo/third_party/team-table
[[ -f $src/src/team_table/db.py ]] || { echo "third_party/team-table is missing: git submodule update --init" >&2; exit 1; }
py=$stage/usr/lib/python3/dist-packages/team_table
install -d "$py"
for f in __init__ config db validation admin; do
    install -m 644 "$src/src/team_table/$f.py" "$py/$f.py"
done
commit=$(git -C "$src" rev-parse --short HEAD 2>/dev/null || echo unknown)
install -d "$stage/usr/share/doc/cinminai-table"
cat > "$stage/usr/share/doc/cinminai-table/copyright" <<COPY
Team Table: GPL-3.0-or-later (/usr/share/common-licenses/GPL-3), by Brickmii (Ian McClenathan), Claude and Codex.
Source: https://github.com/Brickmii/team-table at commit $commit (the core only; the MCP server is not included).
COPY
