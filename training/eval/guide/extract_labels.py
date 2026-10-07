#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build labels.json: the names Mint actually shows for its apps and settings panels, per v1 language
(PLAN D25). Run on a Mint 22.x system (read-only):

    python3 extract_labels.py > labels.json
    python3 extract_labels.py ROOT > labels.json     (an ISO's extracted filesystem instead of this system)

The guide must say "Logithèque" to a French user, not a translation it made up, so the eval checks
replies against these names. Sources: Name[xx]= in the .desktop files, else the app's gettext
catalogue (X-*-Gettext-Domain). A language with no translation on this system is left out, and the
eval then uses that label only in English tasks. Portuguese: pt_BR (Brazil) first, pt as fallback.
"""

import gettext
import json
import os
import re
import sys

APPS = "/usr/share/applications"
LANGS = {"es": ["es"], "pt": ["pt_BR", "pt"], "fr": ["fr"], "de": ["de"], "ja": ["ja"]}
LABELS = {  # our key -> .desktop file
    "software_manager": "mintinstall", "update_manager": "mintupdate", "driver_manager": "mintdrivers",
    "system_settings": "cinnamon-settings", "display": "cinnamon-display-panel",
    "network": "cinnamon-network-panel", "sound": "cinnamon-settings-sound",
    "printers": "system-config-printer", "users": "cinnamon-settings-users",
    "account": "cinnamon-settings-user", "files": "nemo", "firefox": "firefox",
    "writer": "libreoffice-writer", "calc": "libreoffice-calc", "impress": "libreoffice-impress",
    "backup_tool": "mintbackup", "timeshift": "timeshift-gtk", "screenshot": "org.gnome.Screenshot",
    "terminal": "org.gnome.Terminal", "power": "cinnamon-settings-power",
    "backgrounds": "cinnamon-settings-backgrounds", "keyboard": "cinnamon-settings-keyboard",
    "mouse": "cinnamon-settings-mouse", "themes": "cinnamon-settings-themes", "languages": "mintlocale",
    "input_method": "mintlocale-im", "firewall": "gufw", "system_monitor": "org.gnome.SystemMonitor",
    "disks": "org.gnome.DiskUtility", "disk_usage": "org.gnome.baobab", "welcome": "mintwelcome",
    "system_info": "mintreport", "bluetooth": "blueman-manager", "document_viewer": "xreader",
    "image_viewer": "xviewer", "video_player": "io.github.celluloid_player.Celluloid",
    "email": "thunderbird", "web_apps": "webapp-manager", "startup_apps": "cinnamon-settings-startup",
    "date_time": "cinnamon-settings-calendar", "accessibility": "cinnamon-settings-universal-access",
    "privacy": "cinnamon-settings-privacy", "screensaver": "cinnamon-settings-screensaver",
    "notifications": "cinnamon-settings-notifications", "preferred_apps": "cinnamon-settings-default",
    "night_light": "cinnamon-settings-nightlight", "fonts": "cinnamon-settings-fonts",
    "panel": "cinnamon-settings-panel", "software_sources": "mintsources",
    "text_editor": "org.x.editor",
    "drawing": "com.github.maoschanz.drawing", "pix": "pix", "notes": "sticky", "onboard": "onboard",
    "archive_manager": "org.gnome.FileRoller", "warpinator": "org.x.Warpinator",
    "character_map": "gucharmap", "document_scanner": "simple-scan", "calculator": "org.gnome.Calculator",
    "music_player": "org.gnome.Rhythmbox3",
    "passwords_keys": "org.gnome.seahorse.Application", "usb_writer": "mintstick", "usb_formatter": "mintstick-format",
    "online_accounts": "gnome-online-accounts-gtk", "login_window": "lightdm-settings", "calendar": "org.gnome.Calendar",
    "install_cinminai": "ubiquity",
}
UI = {  # names inside programs (menus, buttons) the cards use as {ui_…}: (gettext domain, msgid exactly as in source)
    "ui_view": ("nemo", "_View"), "ui_show_hidden_files": ("nemo", "Show _Hidden Files"),
    "ui_select_image": ("mintstick", "Select Image"), "ui_write": ("mintstick", "Write"),
    "ui_usb_stick": ("mintstick", "USB stick:"), "ui_format": ("mintstick", "Format"),
    "ui_import_from_file": ("cinnamon-control-center", "Import from file…"),
    "ui_add": ("cinnamon", "Add"), "ui_account_type": ("cinnamon", "Account Type"),
    "ui_standard": ("cinnamon", "Standard"), "ui_administrator": ("cinnamon", "Administrator"),
    "ui_full_name": ("cinnamon", "Full Name"), "ui_username": ("cinnamon", "Username"),
    "ui_no_password_set": ("cinnamon", "No password set"), "ui_password": ("cinnamon", "Password"),
    "ui_change_password": ("seahorse", "Change _Password"),
    # D84 batch 2
    "ui_filesystem": ("mintstick", "Filesystem:"),
    "ui_official_repositories": ("mintsources", "Official Repositories"), "ui_mirror_main": ("mintsources", "Main"),
    "ui_ppas": ("mintsources", "PPAs"), "ui_apply": ("mintsources", "Apply"), "ui_sources_add": ("mintsources", "Add"),
    "ui_panel_move": ("cinnamon", "Move"), "ui_panel_settings": ("cinnamon", "Panel settings"),
    "ui_applets": ("cinnamon", "Applets"), "ui_add_to_panel": ("cinnamon", "Add to panel"),
    "ui_manage": ("cinnamon", "Manage"), "ui_download": ("cinnamon", "Download"),
    "ui_enable_notifications": ("cinnamon", "Enable notifications"),
    "ui_notification_duration": ("cinnamon", "Notification duration"),
    "ui_users_tab": ("lightdm-settings", "Users"), "ui_automatic_login": ("lightdm-settings", "Automatic login"),
    "ui_lightdm_username": ("lightdm-settings", "Username"),
    "ui_smart": ("gnome-disk-utility", "SMART Data & Self-Tests"),
    "ui_overall_assessment": ("gnome-disk-utility", "Overall Assessment"),
    "ui_system_information": ("mintreport", "System Information"), "ui_copy": ("mintreport", "Copy"),
    "ui_lid_closed": ("cinnamon", "When the lid is closed"),
    "ui_resources": ("gnome-system-monitor", "Resources"), "ui_install_updates": ("mintupdate", "Install Updates"),
}
LOCALE_DIRS = ("usr/share/locale", "usr/share/locale-langpack", "usr/share/linuxmint/locale")
ACTIONS = {  # desktop right-click menu items (Nemo actions); "_" marks the access key
    "change_background": "/usr/share/nemo/actions/change-background.nemo_action",
}


def entry(path: str, section: str = "[Desktop Entry]") -> dict:
    out, inside = {}, False
    for line in open(path, encoding="utf-8"):
        line = line.rstrip("\n")
        if line.startswith("["):
            inside = line == section
        elif inside and "=" in line:
            k, v = line.split("=", 1)
            out.setdefault(k, v)
    return out


ROOT = "/"


def at(path: str) -> str:
    return os.path.join(ROOT, path.lstrip("/"))


def catalogue(domain: str, code: str):
    for base in LOCALE_DIRS:
        mo = at(os.path.join(base, code, "LC_MESSAGES", domain + ".mo"))
        if os.path.exists(mo):
            with open(mo, "rb") as f:
                return gettext.GNUTranslations(f)
    return None


def ui_label(text: str) -> str:
    """'Show _Hidden Files' -> 'Show Hidden Files'; Japanese '表示 (V)' -> '表示'."""
    return re.sub(r"\s*\(_?\w\)$", "", text).replace("_", "")


def main() -> None:
    global ROOT
    ROOT = sys.argv[1] if len(sys.argv) > 1 else "/"
    labels, ui, missing = {}, {}, []
    for key, name in LABELS.items():
        path = at(os.path.join(APPS, name + ".desktop"))
        if not os.path.exists(path):
            missing.append(name)
            continue
        e = entry(path)
        domain = e.get("X-GNOME-Gettext-Domain") or e.get("X-Ubuntu-Gettext-Domain")
        row = {"en": e["Name"]}
        for lang, codes in LANGS.items():
            for code in codes:
                if f"Name[{code}]" in e:
                    row[lang] = e[f"Name[{code}]"]
                    break
                if domain:
                    for base in ("/usr/share/locale", "/usr/share/locale-langpack"):
                        try:
                            t = gettext.translation(domain, at(base), languages=[code]).gettext(e["Name"])
                        except OSError:
                            continue
                        row[lang] = t  # the catalogue exists, so this is its word (German "Terminal" = "Terminal")
                        break
                    if lang in row:
                        break
        labels[key] = row
    for key, path in ACTIONS.items():
        path = at(path)
        if not os.path.exists(path):
            missing.append(path)
            continue
        e = entry(path, "[Nemo Action]")
        clean = lambda v: re.sub(r"\s*\(_\w\)$", "", v).replace("_", "")
        row = {"en": clean(e["Name"])}
        for lang, codes in LANGS.items():
            for code in codes:
                if f"Name[{code}]" in e:
                    row[lang] = clean(e[f"Name[{code}]"])
                    break
        labels[key] = row
    for key, (domain, msgid) in UI.items():
        row = {"en": ui_label(msgid)}
        for lang, codes in LANGS.items():
            for code in codes:
                t = catalogue(domain, code)
                if t is not None and msgid in t._catalog:
                    row[lang] = ui_label(t._catalog[msgid])
                    break
        ui[key] = row
    if missing:
        print("missing .desktop files: " + ", ".join(missing), file=sys.stderr)
    info = at("/etc/linuxmint/info")
    json.dump({"source": "Linux Mint " + open(info).read().split("RELEASE=")[1].split()[0]
               if os.path.exists(info) else "unknown", "labels": labels, "ui": ui},
              sys.stdout, ensure_ascii=False, indent=1)
    print()


if __name__ == "__main__":
    main()
