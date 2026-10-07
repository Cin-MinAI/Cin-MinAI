# SPDX-License-Identifier: GPL-3.0-or-later
"""D84 coverage, step 1: list what an ISO offers a person, from its own files.

    unsquashfs -d root filesystem.squashfs usr/share/applications usr/share/cinnamon/cinnamon-settings/modules
    python3 -I training/kb/coverage_inventory.py root > inventory.json

Visible menu apps and System Settings entries (.desktop files, Cinnamon's own rules for hiding), and the Cinnamon
settings modules. Result for 0.0.1: docs/d84-coverage.md.
"""
import configparser
import glob
import json
import os
import re
import sys

root = sys.argv[1]
apps = []
for path in sorted(glob.glob(os.path.join(root, "usr/share/applications/*.desktop"))):
    cp = configparser.RawConfigParser(strict=False, interpolation=None)
    cp.optionxform = str
    try:
        cp.read(path, encoding="utf-8")
        e = cp["Desktop Entry"]
    except Exception as exc:  # noqa: BLE001
        print("skip", path, exc, file=sys.stderr)
        continue
    if e.get("Type", "Application") != "Application":
        continue
    only, not_in = e.get("OnlyShowIn", ""), e.get("NotShowIn", "")
    hidden = e.get("NoDisplay", "false").lower() == "true" or e.get("Hidden", "false").lower() == "true"
    if only and "X-Cinnamon" not in only and "GNOME" not in only:
        hidden = True
    if "X-Cinnamon" in not_in:
        hidden = True
    cats = [c for c in e.get("Categories", "").split(";") if c]
    where = "settings" if ("Settings" in cats or any(c.startswith("X-Cinnamon-Settings") for c in cats)) else "menu"
    apps.append({"file": os.path.basename(path), "name": e.get("Name", ""), "generic": e.get("GenericName", ""),
                 "comment": e.get("Comment", ""), "categories": cats, "hidden": hidden, "where": where,
                 "exec": e.get("Exec", "").split()[0] if e.get("Exec") else ""})

modules = []
for path in sorted(glob.glob(os.path.join(root, "usr/share/cinnamon/cinnamon-settings/modules/cs_*.py"))):
    text = open(path, encoding="utf-8").read()
    m = re.search(r"SidePage\(\s*_\(\"([^\"]+)\"\)", text)
    keywords = re.search(r"keywords\s*=\s*_\(\"([^\"]+)\"\)", text)
    cat = re.search(r"self\.category\s*=\s*\"([a-z]+)\"", text)
    modules.append({"file": os.path.basename(path), "name": m.group(1) if m else "?",
                    "keywords": keywords.group(1) if keywords else "", "category": cat.group(1) if cat else ""})

json.dump({"apps": apps, "modules": modules}, sys.stdout, indent=1, ensure_ascii=False)
