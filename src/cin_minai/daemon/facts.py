# SPDX-License-Identifier: GPL-3.0-or-later
"""Replies the daemon writes itself from a system check, no model needed (toward voice operation, D88).

Round 3 (2026-10-07): asked the time, the 4B said it and then added "1. Click Restart to restart your computer." from
the earlier topic; asking it not to add steps made it drop facts elsewhere (prompt v2.5, not adopted). A plain fact is
said plainly, instantly, and the same way every time.
"""

from __future__ import annotations

import datetime as dt
import json

WEEKDAYS = {
    "en": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
    "es": ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"],
    "pt": ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"],
    "fr": ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"],
    "de": ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"],
    "ja": ["月", "火", "水", "木", "金", "土", "日"],
}
MONTHS = {
    "en": ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
           "November", "December"],
    "es": ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
           "noviembre", "diciembre"],
    "pt": ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro",
           "novembro", "dezembro"],
    "fr": ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre",
           "novembre", "décembre"],
    "de": ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober",
           "November", "Dezember"],
}


def say_time(now: dt.datetime, lang: str) -> str:
    wd, d, mo, y, hh, mm = now.weekday(), now.day, now.month, now.year, now.hour, now.minute
    if lang == "es":
        return f"{'Es la' if hh == 1 else 'Son las'} {hh}:{mm:02d} del {WEEKDAYS['es'][wd]} {d} de {MONTHS['es'][mo - 1]} de {y}."
    if lang == "pt":
        return f"{'É' if hh == 1 else 'São'} {hh}:{mm:02d} de {WEEKDAYS['pt'][wd]}, {d} de {MONTHS['pt'][mo - 1]} de {y}."
    if lang == "fr":
        return f"Il est {hh} h {mm:02d}, le {WEEKDAYS['fr'][wd]} {d} {MONTHS['fr'][mo - 1]} {y}."
    if lang == "de":
        return f"Es ist {hh}:{mm:02d} Uhr, {WEEKDAYS['de'][wd]}, {d}. {MONTHS['de'][mo - 1]} {y}."
    if lang == "ja":
        return f"今は{y}年{mo}月{d}日（{WEEKDAYS['ja'][wd]}）{hh}時{mm:02d}分です。"
    h12 = hh % 12 or 12
    return f"It's {h12}:{mm:02d} {'AM' if hh < 12 else 'PM'}, {WEEKDAYS['en'][wd]} {d} {MONTHS['en'][mo - 1]} {y}."


def direct_reply(tool: str, args: dict, result: str, lang: str) -> str | None:
    """The reply for a check whose answer is a plain fact, or None (the model writes it)."""
    if tool != "inspect_system" or str(args.get("topic")) != "time":
        return None
    try:
        now = dt.datetime.fromisoformat(json.loads(result)["iso"])
    except (ValueError, KeyError, TypeError):
        return None
    return say_time(now, lang if lang in WEEKDAYS else "en")
