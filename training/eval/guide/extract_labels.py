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
# Cin-MinAI's own windows and the names inside them: in no Mint catalogue, so read from this repository (the words the
# person sees). The Updates window is a program open_app can open; the Library is a card in the sidebar.
REPO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..")
OWN_LABELS = {"updates_window": "distro/packages/cinminai-daemon/root/usr/share/applications/cinminai-updates.desktop"}
OWN_UI = {  # key -> (module, table, word). Not the Install button: it shows the count ("Install 4 updates")
    "ui_updates_expert": ("cin_minai.daemon.updates", "WORDS", "expert"),
    "ui_updates_wait": ("cin_minai.daemon.updates", "WORDS_HOLDS", "wait_check"),
    "ui_updates_daily": ("cin_minai.daemon.updates", "WORDS_HOLDS", "auto"),
    "ui_updates_hold": ("cin_minai.daemon.updates", "WORDS_HOLDS", "hold_menu"),
    "ui_updates_hold_update": ("cin_minai.daemon.updates", "WORDS_HOLDS", "hold_update"),
    "ui_updates_hold_program": ("cin_minai.daemon.updates", "WORDS_HOLDS", "hold_program"),
    "ui_updates_save": ("cin_minai.daemon.updates", "WORDS_HOLDS", "save"),
    "ui_library": ("cin_minai.sidebar.words", "T", "library"),
    "ui_library_look": ("cin_minai.sidebar.words", "T", "lib_look"),
    "ui_library_get": ("cin_minai.sidebar.words", "T", "lib_get"),
    "ui_library_remove": ("cin_minai.sidebar.words", "T", "h_remove"),
    "ui_models": ("cin_minai.sidebar.words", "T", "models"),
    "ui_models_ours": ("cin_minai.sidebar.words", "T", "m_use_ours"),
    "ui_models_more": ("cin_minai.sidebar.words", "T", "h_more"),
    "ui_models_check": ("cin_minai.sidebar.words", "T", "h_check"),
    "ui_models_drives": ("cin_minai.sidebar.words", "T", "h_drives"),
    "ui_models_system": ("cin_minai.sidebar.words", "T", "job_system"),
    "ui_requests": ("cin_minai.sidebar.words", "T", "requests"),
    "ui_requests_stop": ("cin_minai.sidebar.words", "T", "stop"),
    "ui_requests_refresh": ("cin_minai.sidebar.words", "T", "refresh"),
    "ui_terminal_share": ("cin_minai.sidebar.words", "T", "t_share"),
}
# the panel icon's internet log (applet.js LOG_WORDS: [switch, open]) and LibreOffice's Assistant menu (Addons.xcu),
# read from the files that show them
APPLET = "distro/packages/cinminai-applet/root/usr/share/cinnamon/applets/cinminai@cinminai/applet.js"
OWN_LOG = {"ui_log_switch": 0, "ui_log_open": 1}
ADDONS = "src/libreoffice-extension/Addons.xcu"
OWN_LO = {"ui_lo_menu": "Assistant", "ui_lo_ask": "Ask about selection", "ui_lo_rewrite": "Rewrite selection…",
          "ui_lo_explain": "Explain this formula", "ui_lo_summarize": "Summarize document",
          "ui_lo_share": "Share this document with the assistant", "ui_lo_unshare": "Stop sharing this document"}
# names the sidebar shows in English in every language (words.py: only its newer views are translated yet); a name
# moves up to OWN_UI once it has a translation
OWN_UI_EN = {
    "ui_open_assistant": "Open assistant", "ui_new_conversation": "New conversation",
    "ui_write_start": "Start a writing project", "ui_write_new": "New writing project…", "ui_write_notes": "Notes",
    "ui_write_up": "Write it up", "ui_write_plan": "Plan the chapter", "ui_write_it": "Write it",
    "ui_write_manuscript": "Make a manuscript",
    "ui_journal_open": "Open the journal", "ui_journal": "Journal", "ui_journal_private": "Private",
    "ui_journal_write": "Write today's entry", "ui_journal_entries": "Entries",
    "ui_lo_apply": "Apply", "ui_lo_discard": "Discard",
}


def applet_log() -> dict:
    """The internet log's two menu names per language, from the panel icon's own table."""
    table = open(os.path.join(REPO, APPLET), encoding="utf-8").read().split("const LOG_WORDS", 1)[1].split("};", 1)[0]
    rows = {lang: (a, b) for lang, a, b in re.findall(r'^\s*(\w\w): \["([^"]+)", "([^"]+)"\],', table, re.M)}
    return {key: {lang: pair[i] for lang, pair in rows.items()} for key, i in OWN_LOG.items()}


def addons_menu() -> dict:
    """LibreOffice's Assistant menu per language, from the extension's Addons.xcu (en-US is English)."""
    import xml.etree.ElementTree as ET
    lang_attr = "{http://www.w3.org/XML/1998/namespace}lang"
    titles = {}
    for prop in ET.parse(os.path.join(REPO, ADDONS)).iter("prop"):
        if prop.get("{http://openoffice.org/2001/registry}name") == "Title":
            vals = {v.get(lang_attr, "en-US").split("-")[0]: v.text for v in prop.findall("value")}
            titles[vals.get("en")] = vals
    return {key: titles[en] for key, en in OWN_LO.items()}


def own() -> tuple[dict, dict]:
    """(labels, ui) for Cin-MinAI's own names, in the six languages."""
    import importlib
    sys.path.insert(0, os.path.join(REPO, "src"))
    labels = {}
    for key, rel in OWN_LABELS.items():
        e = entry(os.path.join(REPO, rel))
        labels[key] = {"en": e["Name"], **{lang: e[f"Name[{lang}]"] for lang in LANGS if f"Name[{lang}]" in e}}
    ui = {}
    for key, (module, table, word) in OWN_UI.items():
        t = getattr(importlib.import_module(module), table)
        ui[key] = {lang: t[lang][word] for lang in ("en", *LANGS) if word in t.get(lang, {})}
    ui.update({key: {"en": text} for key, text in OWN_UI_EN.items()})
    ui.update(applet_log())
    ui.update(addons_menu())
    return labels, ui
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


TEMPLATES = "/var/cache/debconf/templates.dat"
# the installer's words (ubiquity, from its debconf templates: they aren't gettext), with what it fills in at run time:
# the system's name (Ian, 2026-10-29: the screen says Cin-MinAI) and the name UEFI gives Windows. key -> (template, field)
INSTALLER = {
    "ui_installation_type": ("ubiquity/text/part_auto_heading_label", "Description"),
    "ui_install_alongside": ("ubiquity/partitioner/single_os_resize", "Description"),
    "ui_erase_disk_install": ("ubiquity/partitioner/no_systems_format", "Description"),
    "ui_something_else": ("ubiquity/partitioner/advanced", "Description"),
    "ui_third_party": ("ubiquity/text/prepare_nonfree_software", "Extended_description"),
    "ui_uefi_secure_boot": ("ubiquity/text/efi_secureboot", "Extended_description"),
}
INSTALLER_FILL = {"${DISTRO}": "Cin-MinAI", "${OS}": "Windows Boot Manager"}


def installer_labels(path: str) -> dict:
    """The installer's names in the v1 languages, from its debconf templates (Portuguese: pt_BR first)."""
    blocks = {}
    with open(path, encoding="utf-8", errors="replace") as f:
        for block in f.read().split("\n\n"):
            m = re.search(r"^Name: (\S+)$", block, re.M)
            if m:
                blocks[m.group(1)] = block
    out = {}
    for key, (name, field) in INSTALLER.items():
        block = blocks.get(name)
        if block is None:
            continue
        row = {}
        for lang, codes in (("en", [""]), *((lang, [f"-{c.lower()}.utf-8" for c in codes])
                                            for lang, codes in LANGS.items())):
            for suffix in codes:
                m = re.search(rf"^{field}{re.escape(suffix)}: (.+)$", block, re.M)
                if m and m.group(1).strip():
                    text = m.group(1).strip()
                    for k, v in INSTALLER_FILL.items():
                        text = text.replace(k, v)
                    row[lang] = text
                    break
        if "en" in row:
            out[key] = row
    return out


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
    own_labels, own_ui = own()
    labels.update(own_labels)
    ui.update(own_ui)
    if os.path.exists(at(TEMPLATES)):
        ui.update(installer_labels(at(TEMPLATES)))
    if missing:
        print("missing .desktop files: " + ", ".join(missing), file=sys.stderr)
    info = at("/etc/linuxmint/info")
    json.dump({"source": "Linux Mint " + open(info).read().split("RELEASE=")[1].split()[0]
               if os.path.exists(info) else "unknown", "labels": labels, "ui": ui},
              sys.stdout, ensure_ascii=False, indent=1)
    print()


if __name__ == "__main__":
    main()
