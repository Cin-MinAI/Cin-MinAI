#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
set -euo pipefail
stage=$1 repo=$2
py=$stage/usr/lib/python3/dist-packages/cin_minai
install -d "$py" "$stage/usr/libexec/cinminai" "$stage/usr/share/doc/cinminai-admin"
cp -r "$repo/src/cin_minai/admin" "$py/"
find "$py/admin" -name __pycache__ -prune -exec rm -rf {} +
cat > "$stage/usr/libexec/cinminai/cinminai-admin" <<'PY'
#!/usr/bin/python3 -P
from cin_minai.admin.mechanism import main
raise SystemExit(main())
PY
cat > "$stage/usr/share/doc/cinminai-admin/copyright" <<'COPY'
Cin-MinAI admin mechanism: GPL-3.0-or-later (/usr/share/common-licenses/GPL-3).
Source: https://github.com/Cin-MinAI/Cin-MinAI
COPY
