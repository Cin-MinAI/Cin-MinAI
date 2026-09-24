#!/usr/bin/env bash
# Install the desktop-surface spike for the current user (run inside the Cinnamon session, or with
# DISPLAY/DBUS_SESSION_BUS_ADDRESS pointing at it). Undo with ./uninstall.sh.
#   - ~/.local/bin/cinminai-sidebar              -> sidebar.py
#   - D-Bus activation for org.cinminai.Assistant1 -> daemon.py
#   - panel applet cinminai@cinminai (right side of panel1)
#   - custom keybinding <Super>a -> cinminai-sidebar --toggle
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
uuid=cinminai@cinminai
kb=/org/cinnamon/desktop/keybindings/custom-keybindings/custom-cinminai/

chmod +x "$here/sidebar.py" "$here/daemon.py"
mkdir -p ~/.local/bin ~/.local/share/dbus-1/services ~/.local/share/cinnamon/applets
ln -sfn "$here/sidebar.py" ~/.local/bin/cinminai-sidebar
ln -sfn "$here/applet/$uuid" ~/.local/share/cinnamon/applets/$uuid
cat > ~/.local/share/dbus-1/services/org.cinminai.Assistant1.service <<EOF
[D-BUS Service]
Name=org.cinminai.Assistant1
Exec=/usr/bin/python3 $here/daemon.py
EOF
dbus-send --session --type=method_call --dest=org.freedesktop.DBus / org.freedesktop.DBus.ReloadConfig

# Applet: append to enabled-applets with the next free instance id.
python3 - "$uuid" <<'PY'
import ast, subprocess, sys
uuid = sys.argv[1]
cur = ast.literal_eval(subprocess.check_output(["gsettings", "get", "org.cinnamon", "enabled-applets"], text=True))
if not any(f":{uuid}:" in a for a in cur):
    nid = max(int(a.rsplit(":", 1)[1]) for a in cur) + 1
    cur.append(f"panel1:right:0:{uuid}:{nid}")
    subprocess.check_call(["gsettings", "set", "org.cinnamon", "enabled-applets", str(cur)])
PY

# Hotkey. Cinnamon (keybindings.js) reads custom bindings only when custom-list changes, and only
# removes entries whose name contains "custom": write the binding first, then list it.
schema="org.cinnamon.desktop.keybindings.custom-keybinding:$kb"
gsettings set "$schema" name "Cin-MinAI assistant"
gsettings set "$schema" command "$HOME/.local/bin/cinminai-sidebar --toggle"
gsettings set "$schema" binding "['<Super>a']"
python3 - <<'PY'
import ast, subprocess
cur = ast.literal_eval(subprocess.check_output(
    ["gsettings", "get", "org.cinnamon.desktop.keybindings", "custom-list"], text=True).replace("@as ", ""))
if "custom-cinminai" not in cur:
    subprocess.check_call(["gsettings", "set", "org.cinnamon.desktop.keybindings", "custom-list",
                           str(cur + ["custom-cinminai"])])
PY
echo "installed"
