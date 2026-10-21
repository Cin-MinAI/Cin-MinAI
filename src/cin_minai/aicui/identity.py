# SPDX-License-Identifier: GPL-3.0-or-later
"""This computer's developer identity (PLAN D62): the name its owner gives it and who maintains it, the way people name
their cars (Ian, 2026-10-20: "My machines name is Simon… enjoy what you name it"). It goes on the GitHub profile the
computer publishes under — Name: Simon, Bio: "Simon is maintained by Brickmii" — and commits carry that name.

Offered by AICUI's GitHub menu, never forced (Rule 9). Kept in ~/.config/cinminai/machine.json; GitHub's own profile
is filled in by the person on GitHub's page (AICUI shows and copies the two lines, then reads the profile back), so the
GitHub app needs no permission to change a profile.
"""

from __future__ import annotations

import json
import os

PROFILE_PAGE = "https://github.com/settings/profile"
SIGNUP_PAGE = "https://github.com/signup"
SECURE_PAGE = "https://docs.github.com/en/authentication/securing-your-account-with-two-factor-authentication-2fa"
MAX_NAME = 40


def path() -> str:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, "cinminai", "machine.json")


def load() -> dict:
    """{"name", "maintainer"}: empty strings until the person names the computer."""
    try:
        with open(path(), encoding="utf-8") as f:
            got = json.load(f)
    except (OSError, ValueError):
        got = {}
    return {"name": str(got.get("name", "")), "maintainer": str(got.get("maintainer", ""))}


def problem(name: str, maintainer: str) -> str:
    """What stops these from being saved, in plain words; "" when they're fine."""
    for what, v in (("the computer's name", name), ("who maintains it", maintainer)):
        if not v.strip():
            return f"Type {what}."
        if len(v.strip()) > MAX_NAME:
            return f"Keep {what} to {MAX_NAME} characters."
        if any(c in v for c in "\n\r\t"):
            return f"Keep {what} on one line."
    return ""


def save(name: str, maintainer: str) -> dict:
    why = problem(name, maintainer)
    if why:
        raise ValueError(why)
    ident = {"name": name.strip(), "maintainer": maintainer.strip()}
    os.makedirs(os.path.dirname(path()), exist_ok=True)
    tmp = path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(ident, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path())
    return ident


def bio(ident: dict) -> str:
    return f"{ident['name']} is maintained by {ident['maintainer']}"


def differences(profile: dict, ident: dict) -> list[str]:
    """What GitHub's profile still says differently, in plain words; [] when it matches."""
    out = []
    if profile.get("name", "").strip() != ident["name"]:
        now = profile.get("name", "").strip()
        out.append(f"Name on GitHub is {now!r}, not {ident['name']!r}" if now else
                   f"Name on GitHub is empty (it should be {ident['name']!r})")
    # the bio may say it in the owner's own words (Simon's: "…the development test bed… you can call me Simon!"):
    # it only has to name who maintains it
    if ident["maintainer"].casefold() not in profile.get("bio", "").casefold():
        out.append(f"Bio on GitHub doesn't name {ident['maintainer']} as who maintains it yet (for example: "
                   f"{bio(ident)!r})")
    return out
