# SPDX-License-Identifier: GPL-3.0-or-later
"""How AICUI's chat history looks, chosen by the person (Ian, 2026-10-14): bubbles, boxes or a straight terminal; the
chat's background; a default font, size and text colour; and each speaker's own — its font, size, text colour and,
in bubbles or boxes, its background. In the terminal style there are no bubbles or boxes, so only the chat's
background has a colour. Kept per person (~/.config/cinminai/aicui-chat.json), not per project, and turned into the
CSS AICUI applies above its own (css()).

The AI terminal too (Ian, 2026-10-14: "I want the AI terminal customizable also… people like to be creative and feel
personalized when they sit down"): its background, text colour, one font and size (a terminal has one), and a text
colour for each speaker's lines — which the agent itself prints in that colour (paint())."""

from __future__ import annotations

import json
import os
import re

# the speakers in the chat: the class each one's rows carry is bubble-<key>
WHO = (("user", "You"),
       ("ai", "The AI (the lead model)"),
       ("junior", "The second model (Junior, helper, contributor)"),
       ("cloud", "The cloud advisor"),
       ("app", "AICUI's own notes"))
NAMES = {"user": "you", "ai": "ai", "junior": "junior", "cloud": "☁ advisor", "app": "aicui"}  # the terminal's prompts
# the speakers in the AI terminal: the lines the agent prints for each (the AI's own, the second model's, the advisor's)
TERM_WHO = (("user", "You (your prompt)"),
            ("ai", "The AI (the lead model)"),
            ("junior", "The second model (Junior, helpers, contributors)"),
            ("cloud", "The cloud advisor"))
STYLES = (("bubbles", "Bubbles"), ("boxes", "Boxes"), ("terminal", "Straight terminal"))
FIELDS = ("background", "font", "color")   # "" = as the theme (or the chat's default) has it


def defaults() -> dict:
    return {"style": "bubbles", "background": "", "font": "", "color": "",
            "who": {w: {f: "" for f in FIELDS} for w, _ in WHO},
            "terminal": {"background": "", "color": "", "font": "", "who": {w: {"color": ""} for w, _ in TERM_WHO}}}


def path() -> str:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, "cinminai", "aicui-chat.json")


COLOR = re.compile(r"^(rgba?\(\s*[\d.]+\s*,\s*[\d.]+\s*,\s*[\d.]+\s*(,\s*[\d.]+\s*)?\)|#[0-9a-fA-F]{3,8})$")


def clean(prefs: dict) -> dict:
    """Only known keys and values that are what they say (a colour, a font name): the file is read into CSS."""
    out = defaults()
    if not isinstance(prefs, dict):
        return out
    if prefs.get("style") in dict(STYLES):
        out["style"] = prefs["style"]

    def fill(dst: dict, src) -> None:
        if not isinstance(src, dict):
            return
        for f in FIELDS:
            v = src.get(f)
            if not isinstance(v, str):
                continue
            v = v.strip()
            if f == "font":
                dst[f] = re.sub(r"[^\w .,\-]", "", v)[:80]
            elif COLOR.match(v):
                dst[f] = v
    fill(out, prefs)
    for w, _ in WHO:
        fill(out["who"][w], (prefs.get("who") or {}).get(w))
    term = prefs.get("terminal") if isinstance(prefs.get("terminal"), dict) else {}
    fill(out["terminal"], term)
    for w, _ in TERM_WHO:
        fill(out["terminal"]["who"][w], (term.get("who") or {}).get(w))
        for f in ("background", "font"):  # one font in a terminal; no backgrounds behind lines
            out["terminal"]["who"][w].pop(f, None)
    return out


def load(file: str | None = None) -> dict:
    try:
        with open(file or path(), encoding="utf-8") as f:
            return clean(json.load(f))
    except (OSError, ValueError):
        return defaults()


def save(prefs: dict, file: str | None = None) -> None:
    file = file or path()
    os.makedirs(os.path.dirname(file), exist_ok=True)
    with open(file + ".tmp", "w", encoding="utf-8") as f:
        json.dump(clean(prefs), f, indent=1)
    os.replace(file + ".tmp", file)


WEIGHTS = {"thin": 100, "ultra-light": 200, "light": 300, "book": 400, "regular": 400, "medium": 500,
           "semi-bold": 600, "bold": 700, "ultra-bold": 800, "heavy": 900}


def font_css(font: str) -> str:
    """A font name as the font chooser gives it ("DejaVu Sans Mono Bold Italic 11") → CSS properties."""
    words = font.split()
    props = []
    if words and re.fullmatch(r"\d+(\.\d+)?", words[-1]):
        props.append(f"font-size: {words.pop()}pt;")
    while words and (words[-1].lower() in WEIGHTS or words[-1].lower() in ("italic", "oblique")):
        w = words.pop().lower()
        props.append(f"font-style: {w};" if w in ("italic", "oblique") else f"font-weight: {WEIGHTS[w]};")
    if words:
        props.append(f'font-family: "{" ".join(words)}";')
    return " ".join(props)


def rgb(color: str) -> tuple[int, int, int]:
    """A colour as written here (#rgb, #rrggbb, rgb(), rgba()) → its red, green and blue, 0-255."""
    if color.startswith("#"):
        h = color[1:]
        h = "".join(c * 2 for c in h[:3]) if len(h) in (3, 4) else h[:6]
        r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
        return r, g, b
    r, g, b = (int(float(x)) for x in re.findall(r"[\d.]+", color)[:3])
    return r, g, b


def dark(color: str) -> bool:
    """Whether text needs to be light on this colour (its luminance; a see-through colour counts as it shows)."""
    r, g, b = rgb(color)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b < 128


# --- the AI terminal: the agent prints each speaker's lines in the colour chosen for it -------------------------------
_cache = {"mtime": None, "prefs": None}


def current() -> dict:
    """The person's choices, read again only when the file changed — so a new colour holds from the next line."""
    try:
        mtime = os.path.getmtime(path())
    except OSError:
        mtime = None
    if _cache["prefs"] is None or mtime != _cache["mtime"]:
        _cache["mtime"], _cache["prefs"] = mtime, load()
    return _cache["prefs"]


def paint(who: str, text: str, fallback: str = "", prefs: dict | None = None) -> str:
    """text in the terminal colour chosen for this speaker (24-bit colour, as VTE shows it), else in fallback (the
    agent's own ANSI code for it); the resets inside the text keep the speaker's colour after them."""
    p = prefs or current()
    color = p["terminal"]["who"].get(who, {}).get("color", "")
    code = "\033[38;2;{};{};{}m".format(*rgb(color)) if color else fallback
    if not code:
        return text
    return code + text.replace("\033[0m", "\033[0m" + code) + "\033[0m"


def rules(spec: dict, background: bool) -> str:
    out = []
    if spec.get("font"):
        out.append(font_css(spec["font"]))
    if spec.get("color"):
        out.append(f"color: {spec['color']};")
    if background and spec.get("background"):
        out.append(f"background-color: {spec['background']};")
    return " ".join(out)


def css(prefs: dict) -> str:
    """The chat's CSS for these choices, applied above AICUI's own (which draws the default bubbles)."""
    p = clean(prefs)
    style = p["style"]
    out = []
    if p["background"]:
        out.append(f".chat-pane, .chat-pane row {{ background-color: {p['background']}; }}")
    default = rules(p, background=False)
    if p["background"] and not p["color"]:  # a background chosen, its text not: readable on it, not the theme's
        default += f" color: {'#e8e8e8' if dark(p['background']) else '#1e1e1e'};"
    if default:
        out.append(f".chat-pane {{ {default} }}")
    shapes = [f".bubble-{w}" for w, _ in WHO]
    if style == "boxes":
        out.append(", ".join(f".chat-boxes {s}" for s in shapes) +
                   " { border-radius: 0; border: 1px solid rgba(128, 128, 128, 0.45); }")
        out.append(".chat-boxes .bubble-cloud { border-left: 4px solid #3584e4; }")
    elif style == "terminal":  # no bubbles or boxes: lines, as a terminal shows them
        out.append(".chat-terminal { font-family: monospace; }")
        out.append(", ".join(f".chat-terminal {s}" for s in shapes) +
                   " { background: none; border: none; border-radius: 0; padding: 1px 4px; }")
        out.append(".chat-terminal row { padding: 0; }")
    for w, _ in WHO:
        r = rules(p["who"][w], background=style != "terminal")
        if r:
            out.append(f".chat-pane .bubble-{w} {{ {r} }}")
    return "\n".join(out) + "\n"
