#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Build SearXNG for cinminai-search (the assistant's own search on the person's computer, PLAN D55/D68).
#
#   wsl -d Ubuntu-24.04 --cd .../distro -e bash build-searxng.sh        (as the normal user; needs uv)
#
# SearXNG at the pinned commit, its Python libraries as wheels for CPython 3.12 on x86-64 Linux (Mint 22.3 is Ubuntu
# 24.04: Python 3.12, glibc 2.39), installed into a plain folder (no virtual environment: nothing in it depends on
# where it's built). The package's launcher (packages/cinminai-search/root/usr/lib/cinminai/searxng/run) puts app/ and
# lib/ on the path.
# Output: $M1/searxng/$SEARXNG_COMMIT/{app/searx,lib/,BUILDINFO,LICENSE,LICENSES}. A finished build is reused; FORCE=1
# rebuilds. ~1 min.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
source "$here/config.env"
export PATH=$HOME/.local/bin:$PATH
command -v uv >/dev/null || { echo "uv is needed (https://docs.astral.sh/uv/)" >&2; exit 1; }

out=$M1/searxng/$SEARXNG_COMMIT
if [[ -f $out/BUILDINFO && ${FORCE:-0} != 1 ]]; then
    echo "already built: $out (FORCE=1 to rebuild)"; exit 0
fi
src=$WORK/src/searxng
if [[ ! -d $src/.git ]]; then
    mkdir -p "$WORK/src"
    git clone --quiet "$SEARXNG_REPO" "$src"
fi
git -C "$src" cat-file -e "$SEARXNG_COMMIT^{commit}" 2>/dev/null || git -C "$src" fetch --quiet origin
git -C "$src" checkout --quiet --detach "$SEARXNG_COMMIT"
git -C "$src" clean -fdxq

rm -rf "$out.tmp"
mkdir -p "$out.tmp/app" "$out.tmp/lib"
# the libraries: binary wheels only (nothing compiled here), for the target, not for this machine
uv pip install --quiet --target "$out.tmp/lib" --python-version 3.12 --python-platform x86_64-manylinux_2_28 \
    --only-binary :all: -r "$src/requirements.txt"
# the app, with its version written in (there's no git where it's installed)
cp -a "$src/searx" "$out.tmp/app/searx"
( cd "$src" && PYTHONPATH="$out.tmp/lib:$src" python3 -m searx.version freeze >/dev/null 2>&1 ) || true
[[ -f $src/searx/version_frozen.py ]] && cp "$src/searx/version_frozen.py" "$out.tmp/app/searx/"
find "$out.tmp" -name __pycache__ -prune -exec rm -rf {} +
rm -rf "$out.tmp/app/searx/static/themes"/*/src 2>/dev/null || true
cp "$src/LICENSE" "$out.tmp/LICENSE"
# every library's license, from its own metadata
python3 - "$out.tmp/lib" > "$out.tmp/LICENSES" <<'PY'
import importlib.metadata as md, sys
for d in sorted(md.distributions(path=[sys.argv[1]]), key=lambda d: d.metadata["Name"].lower()):
    m = d.metadata
    lic = m.get("License-Expression") or (m.get("License") or "").splitlines()[0:1] or \
        [c.split(" :: ")[-1] for c in m.get_all("Classifier") or [] if c.startswith("License ::")]
    print(f"{m['Name']} {m['Version']}: {lic if isinstance(lic, str) else ', '.join(lic) or 'see its files'}")
PY
{
    echo "SearXNG $SEARXNG_COMMIT ($SEARXNG_REPO), built $(date -u +%Y-%m-%dT%H:%MZ) on $(uname -n)"
    echo "Libraries (binary wheels for CPython 3.12, x86_64-manylinux_2_28):"
    sed 's/^/  /' "$out.tmp/LICENSES"
} > "$out.tmp/BUILDINFO"
rm -rf "$out"
mv "$out.tmp" "$out"
echo "built $out ($(du -sh "$out" | cut -f1))"
