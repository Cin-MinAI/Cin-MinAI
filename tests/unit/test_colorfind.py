# SPDX-License-Identifier: GPL-3.0-or-later
"""Find by colour (the practical part of Ian's Color Frame): colours named from the opponent axes, and a striped
red-and-white shirt found among clutter."""

import random
import unittest

from cin_minai.daemon import colorfind as F

try:
    from PIL import Image, ImageDraw
except ImportError:
    Image = None


class Words(unittest.TestCase):
    def test_colours_in_the_order_named(self):
        self.assertEqual(F.colours_in("find the guy in the red and white striped shirt"), ["red", "white"])
        self.assertEqual(F.colours_in("¿dónde está la camisa roja y blanca?"), ["red", "white"])
        self.assertEqual(F.colours_in("赤と白のシャツ"), ["red", "white"])
        self.assertEqual(F.colours_in("where's the rotation button"), [])  # "rot" only as a word


@unittest.skipIf(Image is None, "needs Pillow (on Mint's image)")
class Naming(unittest.TestCase):
    CASES = {
        "red": [(220, 30, 30), (180, 20, 40), (200, 60, 50)],
        "orange": [(240, 140, 20), (230, 120, 40)],
        "yellow": [(240, 220, 30), (250, 240, 80)],
        "green": [(30, 180, 40), (60, 140, 60), (20, 120, 90)],
        "blue": [(30, 60, 200), (40, 110, 220), (20, 30, 120)],
        "purple": [(140, 40, 180), (120, 30, 140)],
        "white": [(255, 255, 255), (235, 232, 228)],
        "black": [(0, 0, 0), (25, 30, 28)],
        "grey": [(128, 128, 128), (90, 92, 95)],
    }

    def test_each_colour_is_named_and_not_mistaken(self):
        for name, rgbs in self.CASES.items():
            for rgb in rgbs:
                maps, _ = F.shares(Image.new("RGB", (8, 8), rgb), list(F.COLOURS), grid=1)
                named = {n for n, m in maps.items() if m[0][0] > 0.5}
                self.assertIn(name, named, rgb)
                # red/orange and blue/purple meet at their edges; nothing else should overlap
                allowed = {name, *{"red": {"orange"}, "orange": {"red"}, "blue": {"purple"},
                                   "purple": {"blue"}}.get(name, set())}
                self.assertLessEqual(named, allowed, rgb)


@unittest.skipIf(Image is None, "needs Pillow (on Mint's image)")
class Finding(unittest.TestCase):
    def crowd(self, seed=4):
        rnd = random.Random(seed)
        im = Image.new("RGB", (1200, 800), (200, 180, 140))
        d = ImageDraw.Draw(im)
        for _ in range(900):  # a busy beach: blobs of every colour, some red, some white, rarely together
            x, y = rnd.randrange(1200), rnd.randrange(800)
            d.ellipse((x, y, x + rnd.randrange(6, 30), y + rnd.randrange(6, 30)),
                      fill=tuple(rnd.randrange(256) for _ in range(3)))
        return im, d

    def test_the_striped_shirt_comes_first(self):
        im, d = self.crowd()
        x0, y0 = 860, 520
        for i in range(8):  # red and white stripes, 4 px each: Waldo's shirt
            d.rectangle((x0, y0 + i * 8, x0 + 28, y0 + i * 8 + 3), fill=(210, 30, 35))
            d.rectangle((x0, y0 + i * 8 + 4, x0 + 28, y0 + i * 8 + 7), fill=(245, 245, 245))
        found = F.candidates(im, ["red", "white"])
        self.assertTrue(found)
        bx = found[0]["box"]
        self.assertTrue(bx[0] <= x0 + 14 <= bx[2] and bx[1] <= y0 + 32 <= bx[3], found[:2])
        self.assertEqual(F.where(bx, im.size), "bottom right")

    def test_nothing_named_nothing_found(self):
        im, _ = self.crowd()
        self.assertEqual(F.candidates(im, []), [])

    def test_where(self):
        self.assertEqual(F.where((0, 0, 10, 10), (300, 300)), "top left")
        self.assertEqual(F.where((140, 140, 160, 160), (300, 300)), "middle")
        self.assertEqual(F.where((140, 0, 160, 10), (300, 300)), "top middle")


if __name__ == "__main__":
    unittest.main()
