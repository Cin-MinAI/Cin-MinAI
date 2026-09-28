# SPDX-License-Identifier: GPL-3.0-or-later
"""Compact marks for the menu button (square, 16-48 px), from the logo's parts: the Signal-blue fill,
the Neon-green rim and Archivo at the logo's fitted width/weight (build_logo.py). Three candidates for
Ian to choose from; writes mark-a.svg, mark-b.svg, mark-c.svg and, with --preview, a PNG showing each at
panel sizes on Mint-Y-Dark's panel colour.

    uv run --with fonttools python build_mark.py [--preview out.png]   (--preview also needs cairosvg, pillow)
"""
import argparse
import io
import os

from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen

import build_logo as L

WDTH, WGHT = 70, 840          # the logo's fit (build_logo.py output)
S = 256                        # mark design size (square)


def text_path(text, italic, cap_height, cx, baseline, tracking=0.0):
    """Outline of `text` at `cap_height` px, centred horizontally on cx."""
    font = L.IT if italic else L.UP
    gs = font.getGlyphSet(location={"wdth": WDTH, "wght": WGHT})
    cmap = font.getBestCmap()
    capb = BoundsPen(gs); gs[cmap[ord("M")]].draw(capb)
    s = cap_height / (capb.bounds[3] - capb.bounds[1])
    names = [cmap[ord(c)] for c in text]
    inks = []
    for n in names:
        b = BoundsPen(gs); gs[n].draw(b); inks.append(b.bounds)
    # lay out by advance width, then centre the ink
    x, placed = 0.0, []
    for n, b in zip(names, inks):
        placed.append((n, x)); x += gs[n].width * s + tracking
    left = placed[0][1] + inks[0][0] * s
    right = placed[-1][1] + inks[-1][2] * s
    shift = cx - (left + right) / 2
    d = []
    for (n, x0), b in zip(placed, inks):
        pen = SVGPathPen(gs)
        gs[n].draw(TransformPen(pen, (s, 0, 0, -s, x0 + shift, baseline)))
        d.append(pen.getCommands())
    return " ".join(d)


def svg(body):
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {S} {S}" width="{S}" height="{S}">{body}</svg>\n'


def mark_a():  # the oval, compact
    rx, ry, rim = 124, 80, 12
    t = text_path("AI", True, 74, S / 2, S / 2 + 37)
    return svg(f'<ellipse cx="128" cy="128" rx="{rx}" ry="{ry}" fill="{L.GREEN}"/>'
               f'<ellipse cx="128" cy="128" rx="{rx - rim}" ry="{ry - rim}" fill="{L.BLUE}"/>'
               f'<path d="{t}" fill="{L.INK}"/>')


def mark_b():  # round
    t = text_path("AI", True, 110, S / 2, S / 2 + 55)
    return svg(f'<circle cx="128" cy="128" r="124" fill="{L.GREEN}"/><circle cx="128" cy="128" r="108" fill="{L.BLUE}"/>'
               f'<path d="{t}" fill="{L.INK}"/>')


def mark_c():  # round, the name's initials
    t = text_path("CM", False, 84, S / 2, S / 2 + 42, tracking=2)
    return svg(f'<circle cx="128" cy="128" r="124" fill="{L.GREEN}"/><circle cx="128" cy="128" r="108" fill="{L.BLUE}"/>'
               f'<path d="{t}" fill="{L.INK}"/>')


MARKS = {"a": mark_a, "b": mark_b, "c": mark_c}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview")
    o = ap.parse_args()
    out = {}
    for k, make in MARKS.items():
        out[k] = make()
        open(os.path.join(L.HERE, f"mark-{k}.svg"), "w", encoding="utf-8", newline="\n").write(out[k])
    print("mark-a.svg mark-b.svg mark-c.svg")
    if o.preview:
        import cairosvg
        from PIL import Image, ImageDraw, ImageFont
        sizes, panel = (16, 24, 32, 48, 128), "#2F2F2F"      # Mint-Y-Dark panel
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 22)
        W = 60 + sum(s + 40 for s in sizes)
        img = Image.new("RGB", (W, 60 + 3 * 190), panel)
        d = ImageDraw.Draw(img)
        for row, k in enumerate(MARKS):
            y = 40 + row * 190
            d.text((20, y), f"{k.upper()}", fill="#E6F4F8", font=font)
            x = 60
            for s in sizes:
                m = Image.open(io.BytesIO(cairosvg.svg2png(bytestring=out[k].encode(), output_width=s, output_height=s)))
                img.paste(m, (x, y + 130 - s), m)
                d.text((x, y + 140), f"{s}px", fill="#9FB3BA", font=ImageFont.truetype(
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14))
                x += s + 40
        img.save(o.preview)
        print("preview:", o.preview)


if __name__ == "__main__":
    main()
