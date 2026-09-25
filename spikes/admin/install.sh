#!/usr/bin/env bash
# Install the admin mechanism spike system-wide (root). WSL / test VMs only — never the Mint box (D21).
#   sudo ./install.sh [--test]     --test: also the test polkit rule, decision file for $SUDO_USER
# Undo with ./uninstall.sh.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
[[ $EUID -eq 0 ]] || { echo "run as root" >&2; exit 1; }

install -Dm755 "$here/mechanism/cinminai-admin" /usr/libexec/cinminai/cinminai-admin
install -Dm644 "$here/mechanism/org.cinminai.Admin1.conf" /usr/share/dbus-1/system.d/org.cinminai.Admin1.conf
install -Dm644 "$here/mechanism/org.cinminai.Admin1.service" /usr/share/dbus-1/system-services/org.cinminai.Admin1.service
install -Dm644 "$here/mechanism/cinminai-admin.service" /usr/lib/systemd/system/cinminai-admin.service
install -Dm644 "$here/mechanism/org.cinminai.admin.policy" /usr/share/polkit-1/actions/org.cinminai.admin.policy
install -Dm755 "$here/client/cinminai-admin-demo" /usr/bin/cinminai-admin-demo
install -Dm644 "$here/test/cinminai-demo.service" /usr/lib/systemd/system/cinminai-demo.service

# Audit log: written by root, readable by group adm (like /var/log/syslog), append-only (even root
# must drop the flag before truncating it).
install -d -m750 -g adm /var/log/cinminai
touch /var/log/cinminai/admin.log && chgrp adm /var/log/cinminai/admin.log && chmod 640 /var/log/cinminai/admin.log
chattr +a /var/log/cinminai/admin.log 2>/dev/null || echo "note: chattr +a not supported here"

if [[ ${1:-} == --test ]]; then
    install -Dm644 "$here/test/49-cinminai-test.rules" /etc/polkit-1/rules.d/49-cinminai-test.rules
    install -m644 -o "${SUDO_USER:-root}" /dev/null /run/cinminai-polkit-test
    install -m644 -o polkitd /dev/null /run/cinminai-polkit-count
    echo "test mode: rule + /run/cinminai-polkit-test (owned by ${SUDO_USER:-root})"
fi

systemctl daemon-reload
systemctl reload dbus 2>/dev/null || dbus-send --system --type=method_call --dest=org.freedesktop.DBus / org.freedesktop.DBus.ReloadConfig
systemctl restart polkit
systemctl start cinminai-demo.service
echo "installed"
