# SPDX-License-Identifier: GPL-3.0-or-later
"""How AICUI's chat history looks, chosen by the person (Ian, 2026-10-14): bubbles, boxes or a straight terminal; the
chat's background; a default font, size and text colour; and each speaker's own — its font, size, text colour and,
in bubbles or boxes, its background. In the terminal style there are no bubbles or boxes, so only the chat's
background has a colour. Kept per person (~/.config/cinminai/aicui-chat.json), not per project, and turned into the
CSS AICUI applies above its own (css())."""

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
STYLES = (("bubbles", "Bubbles"), ("boxes", "Boxes"), ("terminal", "Straight terminal"))
FIELDS = ("background", "font", "color")   # "" = as the theme (or the chat's default) has it


def defaults() -> dict:
    return {"style": "bubbles", "background": "", "font": "", "color": "",
            "who": {w: {f: "" for f in FIELDS} for w, _ in WHO}}


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


def dark(color: str) -> bool:
    """Whether text needs to be light on this colour (its luminance; a see-through colour counts as it shows)."""
    if color.startswith("#"):
        h = color[1:]
        h = "".join(c * 2 for c in h[:3]) if len(h) in (3, 4) else h[:6]
        r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    else:
        r, g, b = (float(x) for x in re.findall(r"[\d.]+", color)[:3])
    return 0.2126 * r + 0.7152 * g + 0.0722 * b < 128


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
