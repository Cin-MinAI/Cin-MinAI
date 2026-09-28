# SPDX-License-Identifier: GPL-3.0-or-later
"""Render cinminai-branding's images from the artwork sources (called by build.sh at package build time).

    python render.py STAGE REPO

- STAGE/usr/share/backgrounds/cinminai/<name>.jpg — the wallpapers, 3840x2160, from
  artwork/wallpapers/generate.py (data-stream is the default, set in zz_cinminai.gschema.override);
- STAGE/usr/share/plymouth/themes/cinminai/ — the boot splash: throbber-NNNN.png (Ian's logo, the
  green rim's glow rising and falling), and the password-prompt images two-step uses (entry, bullet,
  lock, capslock, keyboard), drawn in the palette.
Rendering is deterministic (cairo, no timestamps), so the package stays reproducible.
"""
import io
import math
import os
import re
import sys

import cairosvg
from PIL import Image

stage, repo = sys.argv[1], sys.argv[2]
art = os.path.join(repo, "artwork")
sys.path.insert(0, os.path.join(art, "wallpapers"))
import generate  # noqa: E402

BLUE, GREEN, PANEL, TEXT = "#00A4EC", "#18D42C", "#02141C", "#E6F4F8"


def png(svg_text, w, h):
    return Image.open(io.BytesIO(cairosvg.svg2png(bytestring=svg_text.encode(), output_width=w, output_height=h)))


# --- wallpapers ---------------------------------------------------------------------------------------
bg = os.path.join(stage, "usr/share/backgrounds/cinminai")
os.makedirs(bg, exist_ok=True)
for name, make in generate.WALLPAPERS.items():
    img = png(make().text(), generate.W, generate.H).convert("RGB")
    img.save(os.path.join(bg, f"{name}.jpg"), quality=92, optimize=True, subsampling=0)
    print("wallpaper", name)

# --- boot splash --------------------------------------------------------------------------------------
ply = os.path.join(stage, "usr/share/plymouth/themes/cinminai")
os.makedirs(ply, exist_ok=True)
logo = open(os.path.join(art, "logo", "logo.svg"), encoding="utf-8").read()
inner = re.search(r"<svg[^>]*>(.*)</svg>", logo, re.S).group(1)
x0, y0, w, h = map(float, re.search(r'viewBox="([^"]+)"', logo).group(1).split())
pad = 70                                         # room for the glow
vb = f"{x0 - pad} {y0 - pad} {w + 2 * pad} {h + 2 * pad}"
cx, cy, rx, ry = 835.5, 450.5, 341.5, 108.5      # the rim (build_logo.py)
FRAMES, WIDTH = 24, 520
for i in range(FRAMES):
    level = 0.5 - 0.5 * math.cos(2 * math.pi * i / FRAMES)          # 0 -> 1 -> 0
    # many thin rings, fading outwards: a smooth glow (five wide rings showed bands)
    glow = "".join(f'<ellipse cx="{cx}" cy="{cy}" rx="{rx + g}" ry="{ry + g}" fill="none" stroke="{GREEN}" '
                   f'stroke-width="3.2" opacity="{(0.10 + 0.32 * level) * (1 - g / 62) ** 2:.3f}"/>'
                   for g in range(2, 60, 3))
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vb}">{glow}{inner}</svg>'
    height = round(WIDTH * (h + 2 * pad) / (w + 2 * pad))
    png(svg, WIDTH, height).save(os.path.join(ply, f"throbber-{i + 1:04d}.png"), optimize=True)
print("splash frames", FRAMES)


def small(name, body, w, h):
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}">{body}</svg>'
    png(svg, w, h).save(os.path.join(ply, f"{name}.png"), optimize=True)


small("entry", f'<rect x="1.5" y="1.5" width="297" height="37" rx="8" fill="{PANEL}" stroke="{BLUE}" stroke-width="3"/>', 300, 40)
small("bullet", f'<circle cx="7" cy="7" r="5.5" fill="{TEXT}"/>', 14, 14)
small("lock", f'<rect x="6" y="18" width="28" height="22" rx="4" fill="{BLUE}"/>'
              f'<path d="M12 18 v-6 a8 8 0 0 1 16 0 v6" fill="none" stroke="{BLUE}" stroke-width="4"/>', 40, 42)
small("capslock", f'<path d="M16 4 L28 18 H21 V26 H11 V18 H4 Z" fill="{GREEN}"/><rect x="11" y="28" width="10" height="3" fill="{GREEN}"/>', 32, 32)
small("keyboard", f'<rect x="2" y="8" width="36" height="20" rx="3" fill="none" stroke="{TEXT}" stroke-width="2"/>'
                  + "".join(f'<rect x="{6 + 7 * k}" y="13" width="4" height="4" fill="{TEXT}"/>' for k in range(4))
                  + f'<rect x="10" y="21" width="20" height="3" fill="{TEXT}"/>', 40, 36)
print("prompt images: entry bullet lock capslock keyboard")

# --- menu button ----------------------------------------------------------------------------------------
# Ian's choice (2026-09-27): mark A, the logo's oval with "AI" (artwork/logo/mark-a.svg, build_mark.py);
# zz_cinminai.gschema.override points org.cinnamon app-menu-icon-name at it.
icons = os.path.join(stage, "usr/share/icons/hicolor/scalable/apps")
os.makedirs(icons, exist_ok=True)
with open(os.path.join(art, "logo", "mark-a.svg"), encoding="utf-8") as src:
    open(os.path.join(icons, "cinminai-menu.svg"), "w", encoding="utf-8", newline="\n").write(src.read())
print("menu icon cinminai-menu.svg")
