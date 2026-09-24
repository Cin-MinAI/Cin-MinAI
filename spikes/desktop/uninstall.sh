#!/usr/bin/env bash
# Remove everything install.sh added.
set -uo pipefail
uuid=cinminai@cinminai
kb=/org/cinnamon/desktop/keybindings/custom-keybindings/custom-cinminai/

~/.local/bin/cinminai-sidebar --quit 2>/dev/null
pkill -f "desktop/daemon.py" 2>/dev/null

python3 - "$uuid" <<'PY'
import ast, subprocess, sys
uuid = sys.argv[1]
def strv(items):
    return str(items) if items else "@as []"  # an empty list needs its type spelled out
cur = ast.literal_eval(subprocess.check_output(["gsettings", "get", "org.cinnamon", "enabled-applets"], text=True))
subprocess.check_call(["gsettings", "set", "org.cinnamon", "enabled-applets",
                       strv([a for a in cur if f":{uuid}:" not in a])])
cur = ast.literal_eval(subprocess.check_output(
    ["gsettings", "get", "org.cinnamon.desktop.keybindings", "custom-list"], text=True).replace("@as ", ""))
subprocess.check_call(["gsettings", "set", "org.cinnamon.desktop.keybindings", "custom-list",
                       strv([k for k in cur if k != "custom-cinminai"])])
PY
dconf reset -f "$kb"
rm -f ~/.local/bin/cinminai-sidebar ~/.local/share/cinnamon/applets/$uuid \
      ~/.local/share/dbus-1/services/org.cinminai.Assistant1.service
dbus-send --session --type=method_call --dest=org.freedesktop.DBus / org.freedesktop.DBus.ReloadConfig
echo "uninstalled"
