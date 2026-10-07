#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build labels.json: the names Mint actually shows for its apps and settings panels, per v1 language
(PLAN D25). Run on a Mint 22.x system (read-only):

    python3 extract_labels.py > labels.json

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
}
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


def main() -> None:
    labels, missing = {}, []
    for key, name in LABELS.items():
        path = os.path.join(APPS, name + ".desktop")
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
                            t = gettext.translation(domain, base, languages=[code]).gettext(e["Name"])
                        except OSError:
                            continue
                        row[lang] = t  # the catalogue exists, so this is its word (German "Terminal" = "Terminal")
                        break
                    if lang in row:
                        break
        labels[key] = row
    for key, path in ACTIONS.items():
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
    if missing:
        print("missing .desktop files: " + ", ".join(missing), file=sys.stderr)
    json.dump({"source": "Linux Mint " + open("/etc/linuxmint/info").read().split("RELEASE=")[1].split()[0]
               if os.path.exists("/etc/linuxmint/info") else "unknown", "labels": labels},
              sys.stdout, ensure_ascii=False, indent=1)
    print()


if __name__ == "__main__":
    main()
