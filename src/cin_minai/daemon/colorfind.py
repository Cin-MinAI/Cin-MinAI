# SPDX-License-Identifier: GPL-3.0-or-later
"""Find by colour in a picture, fast — the first stage of "find this in the picture" (Ian, 2026-10-04: "almost like a
Ctrl+F for images"). Only the patches that look right go to the vision model, which confirms.

The encoding is the practical part of Ian's Color Frame (The Color Frame v2, PBAI, February 2026): each pixel on two
opponent axes — red–green, C_y = R − G, and yellow–blue, C_x = Y − B, where Y = min(R, G) · (1 − B / max(R, G, B))
pulls the yellow out of RGB's green channel (the Green Channel Problem) — with luminance kept apart. Those axes are
also the classic opponent pairs of colour vision (Hering; CIELAB's a*/b*), which is why naming colours from them works.

Pillow does the per-pixel work (it's on Mint's image; numpy isn't): every named colour becomes a mask, averaged over
a grid of patches, so a patch knows what share of it is red, white, blue… and where two colours meet.
"""

from __future__ import annotations

import re

# a pixel's colour name from its opponent coordinates (0–255 scale): sectors of the C_y/C_x plane, bounded by ratios
# (hue angles), so a dark red is red too; whites, greys and black by luminance and colourfulness. Chosen on the cases
# in tests/unit/test_colorfind.py — the AI confirms whatever this suggests, so it errs toward too many candidates.
COLOURS = {
    "red":    "(cy > 60) & (cx >= -0.6 * cy) & (cx < 0.4 * cy)",
    "orange": "(cy > 25) & (cx >= 0.4 * cy) & (cy >= 0.4 * cx)",
    "yellow": "(cx > 60) & (cy < 0.4 * cx) & (cy > -35)",
    "green":  "(cy < -35) & (cy < 0.6 * cx)",
    "blue":   "(cx < -45) & (cy <= -0.25 * cx) & (cy >= 0.6 * cx)",
    "purple": "(cx < -45) & (cy > -0.25 * cx) & (cx < -0.6 * cy)",
    "white":  "(lum > 185) & (chroma < 45)",
    "black":  "(lum < 45)",
    "grey":   "(lum >= 45) & (lum <= 185) & (chroma < 30)",
}
# colour words in the six languages (D25) -> our names; Japanese has no spaces, so it matches inside words
WORDS = {
    "red": ("red rojo roja rojos rojas vermelho vermelha rouge rouges rot rote roten rotes", "赤"),
    "orange": ("orange naranja laranja", "オレンジ|橙"),
    "yellow": ("yellow amarillo amarilla amarelo amarela jaune jaunes gelb gelbe gelben", "黄"),
    "green": ("green verde verdes vert verte grün grüne grünen", "緑"),
    "blue": ("blue azul azules bleu bleue blau blaue blauen", "青"),
    "purple": ("purple violet morado morada roxo roxa lila", "紫"),
    "white": ("white blanco blanca blancos blancas branco branca blanc blanche weiß weiße weißen", "白"),
    "black": ("black negro negra preto preta noir noire schwarz schwarze schwarzen", "黒"),
    "grey": ("grey gray gris cinza grau graue", "灰色|グレー"),
}
GRID = 48  # patches along the long side


def colours_in(text: str) -> list[str]:
    """The colours a request names, in the order named ("red and white stripes" -> ["red", "white"])."""
    found = []
    for name, (latin, japanese) in WORDS.items():
        m = re.search(rf"(?<!\w)(?:{'|'.join(latin.split())})(?!\w)|{japanese}", text, re.I)
        if m:
            found.append((m.start(), name))
    return [n for _, n in sorted(found)]


def _eval(expr: str, **images):
    from PIL import ImageMath  # eval() is Mint's (Pillow 10.2); newer Pillow names it unsafe_eval
    return getattr(ImageMath, "unsafe_eval", ImageMath.eval)(expr, **images)


def _axes(img):
    """Float images for the opponent axes, luminance and colourfulness."""
    R, G, B = (c.convert("F") for c in img.convert("RGB").split())
    lo = _eval("min(min(R, G), B)", R=R, G=G, B=B)
    hi = _eval("max(max(R, G), B)", R=R, G=G, B=B)
    # the white in a colour taken out first: on raw RGB the yellow formula reads white as deep blue (Y = 255 ·
    # (1 − 255/255) = 0, so C_x = −255); on what's left it's the paper's formula, and greys sit at the centre
    r, g, b = (_eval("c - lo", c=c, lo=lo) for c in (R, G, B))
    y = _eval("min(r, g) * (1 - b / max(hi - lo, 1))", r=r, g=g, b=b, hi=hi, lo=lo)
    cy = _eval("r - g", r=r, g=g)
    cx = _eval("y - b", y=y, b=b)
    lum = _eval("(R + G + B) / 3", R=R, G=G, B=B)
    chroma = _eval("hi - lo", hi=hi, lo=lo)  # how colourful, apart from how bright
    return {"cy": cy, "cx": cx, "lum": lum, "chroma": chroma}


def masks(img, names: list[str]) -> dict:
    """Each named colour as a full-size picture: 1 where a pixel is that colour, 0 elsewhere."""
    ax = _axes(img)
    out = {}
    for name in names:
        expr = re.sub(r"(cy|cx|lum|chroma)", r"float(\1)", COLOURS[name])
        out[name] = _eval(expr.replace("&", "*"), **ax).convert("F")  # comparisons give 1/0; "and" as a product
    return out


def _grid(img, grid: int) -> tuple[int, int]:
    w, h = img.size
    return (grid, max(1, round(grid * h / w))) if w >= h else (max(1, round(grid * w / h)), grid)


def _patches(full, cols: int, rows: int) -> list[list[float]]:
    from PIL import Image
    small = full.resize((cols, rows), Image.Resampling.BOX)
    return [[small.getpixel((c, r)) for c in range(cols)] for r in range(rows)]


def shares(img, names: list[str], grid: int = GRID) -> tuple[dict, tuple[int, int]]:
    """For each colour name: a grid (cols x rows) of the share of each patch in that colour, 0..1."""
    cols, rows = _grid(img, grid)
    return {n: _patches(m, cols, rows) for n, m in masks(img, names).items()}, (cols, rows)


def meeting(img, a: str, b: str, grid: int = GRID) -> tuple[list[list[float]], tuple[int, int]]:
    """Where colour a touches colour b, per patch: the share of pixels with the other colour a step away, across
    and down. Stripes and checks are full of these edges; two blobs that happen to touch have one line of them —
    the alternation the Color Frame looks for (red alternating with white is Waldo's shirt, not a red ball on a
    white towel)."""
    from PIL import ImageChops
    m = masks(img, [a, b])
    step = max(1, max(img.size) // 600)  # a stripe a few pixels wide in a big picture still counts
    edges = None
    for dx, dy in ((step, 0), (0, step)):
        e = _eval("x * y + u * v", x=m[a], y=ImageChops.offset(m[b], dx, dy),
                  u=m[b], v=ImageChops.offset(m[a], dx, dy))
        edges = e if edges is None else _eval("p + q", p=edges, q=e)
    cols, rows = _grid(img, grid)
    return _patches(edges, cols, rows), (cols, rows)


def candidates(img, names: list[str], top: int = 4, grid: int = GRID) -> list[dict]:
    """The places that look like the request, best first: [{"box": (x0, y0, x1, y1) in pixels, "score"}]. One
    colour: where there's most of it. Several: where they meet most (each named colour next to the following one),
    so a red-and-white striped shirt beats a red thing beside a white one."""
    if not names:
        return []
    names = list(dict.fromkeys(names))
    if len(names) == 1:
        maps, (cols, rows) = shares(img, names, grid)
        score = maps[names[0]]
    else:
        pairs = [meeting(img, a, b, grid) for a, b in zip(names, names[1:])]
        cols, rows = pairs[0][1]
        score = [[min(p[0][r][c] for p in pairs) for c in range(cols)] for r in range(rows)]
    w, h = img.size
    pw, ph = w / cols, h / rows
    picked, taken = [], set()
    for s, r, c in sorted(((score[r][c], r, c) for r in range(rows) for c in range(cols)), reverse=True):
        if s <= 0 or len(picked) >= top:
            break
        if any(abs(r - pr) <= 2 and abs(c - pc) <= 2 for pr, pc in taken):
            continue  # a neighbour of one already picked: the same thing
        taken.add((r, c))
        # the patch and its neighbours, so the model sees the thing whole
        box = (max(0, int((c - 2) * pw)), max(0, int((r - 2) * ph)),
               min(w, int((c + 3) * pw)), min(h, int((r + 3) * ph)))
        picked.append({"box": box, "score": round(s, 3)})
    return picked


def where(box: tuple[int, int, int, int], size: tuple[int, int]) -> str:
    """"top left", "middle", "bottom right"… for a box in a picture of this size."""
    x = (box[0] + box[2]) / 2 / size[0]
    y = (box[1] + box[3]) / 2 / size[1]
    row = "top" if y < 1 / 3 else "bottom" if y > 2 / 3 else "middle"
    col = "left" if x < 1 / 3 else "right" if x > 2 / 3 else ""
    return (f"{row} {col}".strip() if col else ("middle" if row == "middle" else f"{row} middle"))
