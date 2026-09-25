#!/usr/bin/env bash
# Hands-on test on the Mint desktop: a *separate* LibreOffice (throwaway profile in /tmp) with the
# extension and three sample documents. Your normal LibreOffice profile is not touched.
#   ./live.sh          start       ./live.sh stop     close it and delete the profile + samples
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
profile=/tmp/cinminai-lo-live
samples=/tmp/cinminai-lo-samples
export DISPLAY=${DISPLAY:-:0} DBUS_SESSION_BUS_ADDRESS=${DBUS_SESSION_BUS_ADDRESS:-unix:path=/run/user/$(id -u)/bus}

if [[ ${1:-} == stop ]]; then
    pkill -f "UserInstallation=file://$profile" || true
    sleep 2
    rm -rf "$profile" "$samples" /tmp/cinminai-live.oxt
    echo "stopped and cleaned up"
    exit 0
fi

python3 "$here/build_oxt.py" /tmp/cinminai-live.oxt >/dev/null
rm -rf "$profile" && mkdir -p "$samples"
unopkg add --suppress-license "-env:UserInstallation=file://$profile" /tmp/cinminai-live.oxt
python3 - "$samples" <<'PY'
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath("lo.py")))
sys.path.insert(0, os.path.expanduser("~/cin-minai/spikes/libreoffice"))
import lo
out = sys.argv[1]
o = lo.Office()
try:
    for name, make in (("kestrel.odt", lo.writer_doc), ("weather.ods", lo.calc_doc), ("kestrel.odp", lo.impress_doc)):
        d = make(o)
        d.storeToURL(f"file://{out}/{name}", ())
        d.close(True)
finally:
    o.close()
PY
setsid soffice "-env:UserInstallation=file://$profile" --norestore --nologo \
    "$samples/kestrel.odt" "$samples/weather.ods" "$samples/kestrel.odp" >/dev/null 2>&1 < /dev/null &
echo "LibreOffice (test profile) is opening kestrel.odt, weather.ods, kestrel.odp"
