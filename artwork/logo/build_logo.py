# SPDX-License-Identifier: GPL-3.0-or-later
"""Build the vector Cin-MinAI logo from Ian's original (logo-ian-original.png, 1672x941).

Ian's logo: a Signal-blue oval with a Neon-green rim, "Cin-Min AI" in a bold condensed grotesque, "AI" in
italics. The lettering's font can't be redistributed, so this rebuilds it with Archivo (OFL,
../fonts/archivo/), fitting Archivo's width and weight axes to the letters measured in the original and
placing every letter where it sits there. The oval and rim use the measured sizes. Output (vector, text as
outlines, no font needed to display it):
    logo.svg    the logo, cropped to the rim
    splash.svg  the boot splash: the logo centred on black, 16:9

    uv run --with fonttools python build_logo.py [--compare out.png]    (--compare also needs pillow, cairosvg)
"""
from __future__ import annotations

import argparse
import itertools
import os

from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont

HERE = os.path.dirname(os.path.abspath(__file__))
FONTS = os.path.join(HERE, "..", "fonts", "archivo")
BLUE, GREEN, INK = "#00A4EC", "#18D42C", "#000000"   # ../colors.md

# Measured in logo-ian-original.png (pixels): canvas, oval (fill and rim outer edge), and each letter's ink
# box. Baseline 491, cap height 83, x-height 61.
W, H = 1672, 941
CX, CY = 835.5, 450.5
FILL_R, RIM_R = (332.0, 97.5), (341.5, 108.5)
BASELINE, CAP = 491.0, 83.0
LETTERS = [  # char, italic?, ink x0, ink x1, ink top y
    ("C", False, 603, 663, 407), ("i", False, 670, 688, 408), ("n", False, 697, 748, 430),
    ("-", False, 755, 784, 453), ("M", False, 792, 868, 408), ("i", False, 878, 896, 408),
    ("n", False, 904, 955, 430), ("A", True, 981, 1041, 408), ("I", True, 1046, 1081, 408),
]


def glyphsets(wdth: float, wght: float):
    loc = {"wdth": wdth, "wght": wght}
    return {False: (UP, UP.getGlyphSet(location=loc)), True: (IT, IT.getGlyphSet(location=loc))}


def ink(gs, font, ch):
    name = font.getBestCmap()[ord(ch)]
    pen = BoundsPen(gs)
    gs[name].draw(pen)
    return name, pen.bounds   # xMin, yMin, xMax, yMax in font units


def fit():
    """Width and weight whose letter widths (at the measured cap height) best match the original."""
    best = None
    for wdth, wght in itertools.product(range(62, 101, 2), range(600, 901, 20)):
        sets = glyphsets(wdth, wght)
        cap = ink(sets[False][1], UP, "M")[1]
        s = CAP / (cap[3] - cap[1])
        err = 0.0
        for ch, it, x0, x1, top in LETTERS:
            font, gs = sets[it]
            b = ink(gs, font, ch)[1]
            err += ((b[2] - b[0]) * s - (x1 - x0)) ** 2
        # the hyphen's thickness shows the stroke weight (15 px in the original)
        b = ink(sets[False][1], UP, "-")[1]
        err += 2 * ((b[3] - b[1]) * s - 15) ** 2
        if best is None or err < best[0]:
            best = (err, wdth, wght)
    return best


def letters_svg(wdth, wght):
    sets = glyphsets(wdth, wght)
    cap = ink(sets[False][1], UP, "M")[1]
    s = CAP / (cap[3] - cap[1])
    paths = []
    for ch, it, x0, x1, top in LETTERS:
        font, gs = sets[it]
        name, b = ink(gs, font, ch)
        # scale, flip y, put the ink's left edge at x0 and the baseline at BASELINE
        tx = x0 - b[0] * s
        pen = SVGPathPen(gs)
        gs[name].draw(TransformPen(pen, (s, 0, 0, -s, tx, BASELINE)))
        paths.append(pen.getCommands())
    return " ".join(paths)


def logo_group(d):
    return (f'<ellipse cx="{CX}" cy="{CY}" rx="{RIM_R[0]}" ry="{RIM_R[1]}" fill="{GREEN}"/>'
            f'<ellipse cx="{CX}" cy="{CY}" rx="{FILL_R[0]}" ry="{FILL_R[1]}" fill="{BLUE}"/>'
            f'<path d="{d}" fill="{INK}"/>')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--compare", help="also write a side-by-side PNG: original | ours | difference")
    o = ap.parse_args()
    err, wdth, wght = fit()
    d = letters_svg(wdth, wght)
    note = f"<!-- Cin-MinAI logo (after Ian's original). Archivo wdth {wdth} wght {wght}. CC BY-SA 4.0 -->"
    m = 4
    x0, y0 = CX - RIM_R[0] - m, CY - RIM_R[1] - m
    w, h = 2 * (RIM_R[0] + m), 2 * (RIM_R[1] + m)
    logo = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{x0} {y0} {w} {h}" width="{w:.0f}" height="{h:.0f}">'
            f'{note}{logo_group(d)}</svg>\n')
    splash = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">'
              f'{note}<rect width="{W}" height="{H}" fill="#000000"/>{logo_group(d)}</svg>\n')
    open(os.path.join(HERE, "logo.svg"), "w", encoding="utf-8", newline="\n").write(logo)
    open(os.path.join(HERE, "..", "boot", "splash.svg"), "w", encoding="utf-8", newline="\n").write(splash)
    print(f"Archivo wdth {wdth}, wght {wght} (fit error {err:.0f} px^2) -> logo.svg, ../boot/splash.svg")
    if o.compare:
        import io
        import cairosvg
        from PIL import Image, ImageChops
        orig = Image.open(os.path.join(HERE, "logo-ian-original.png")).convert("RGB")
        ours = Image.open(io.BytesIO(cairosvg.svg2png(bytestring=splash.encode(), output_width=W,
                                                      output_height=H))).convert("RGB")
        box = (int(x0), int(y0), int(x0 + w), int(y0 + h))
        a, b = orig.crop(box), ours.crop(box)
        diff = ImageChops.difference(a, b)
        out = Image.new("RGB", (a.width, a.height * 3 + 20), "#303030")
        out.paste(a, (0, 0)); out.paste(b, (0, a.height + 10)); out.paste(diff, (0, 2 * a.height + 20))
        out.save(o.compare)
        print("comparison:", o.compare)


UP = TTFont(os.path.join(FONTS, "Archivo[wdth,wght].ttf"))
IT = TTFont(os.path.join(FONTS, "Archivo-Italic[wdth,wght].ttf"))

if __name__ == "__main__":
    main()
