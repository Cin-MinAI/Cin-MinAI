#!/usr/bin/env bash
# Remove everything install.sh added (the audit log is kept unless --purge).
set -uo pipefail
[[ $EUID -eq 0 ]] || { echo "run as root" >&2; exit 1; }
systemctl stop cinminai-admin.service cinminai-demo.service 2>/dev/null
systemctl disable cinminai-demo.service 2>/dev/null
rm -f /usr/libexec/cinminai/cinminai-admin /usr/share/dbus-1/system.d/org.cinminai.Admin1.conf \
      /usr/share/dbus-1/system-services/org.cinminai.Admin1.service \
      /usr/lib/systemd/system/cinminai-admin.service /usr/lib/systemd/system/cinminai-demo.service \
      /usr/share/polkit-1/actions/org.cinminai.admin.policy /usr/bin/cinminai-admin-demo \
      /etc/polkit-1/rules.d/49-cinminai-test.rules /run/cinminai-polkit-test /run/cinminai-polkit-count /etc/cinminai-test.conf
rmdir /usr/libexec/cinminai 2>/dev/null
if [[ ${1:-} == --purge ]]; then
    chattr -a /var/log/cinminai/admin.log 2>/dev/null
    rm -rf /var/log/cinminai /var/lib/cinminai/admin-backups
fi
systemctl daemon-reload
dbus-send --system --type=method_call --dest=org.freedesktop.DBus / org.freedesktop.DBus.ReloadConfig
systemctl restart polkit
echo "uninstalled"
