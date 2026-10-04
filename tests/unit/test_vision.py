# SPDX-License-Identifier: GPL-3.0-or-later
"""Reading pictures (D64, D78): which model reads, how it's started, and the picture as a viewer shows it."""

import base64
import io
import os
import tempfile
import unittest

from cin_minai.daemon import vision as V
from cin_minai.inference import matcher as M
from cin_minai.sidebar import words

try:
    from PIL import Image
except ImportError:
    Image = None


class FakeStore:
    def __init__(self, files):
        self.root, self.files = "/tmp/models", set(files)

    def has(self, f):
        return f in self.files

    def path(self, f):
        return os.path.join(self.root, f)


def machine(free=11159):
    return M.Machine([{"name": "NVIDIA GeForce GTX 1080 Ti", "api": "CUDA0", "total_mib": 11264, "free_mib": free}],
                     32, 26, 4, True, 5.0, 50)


class Choosing(unittest.TestCase):
    def setUp(self):
        self.real = M.read_machine
        M.read_machine = lambda **kw: machine()

    def tearDown(self):
        M.read_machine = self.real

    def test_the_27b_when_it_is_here(self):
        c = V.choose(FakeStore({"Qwen3.8-27B-UD-IQ3_XXS.gguf"}), {"model": "/usr/share/g.gguf"})
        self.assertTrue(c["recommended"])
        self.assertEqual(c["projector"].file, "Qwen3.8-27B-mmproj-F16.gguf")
        self.assertFalse(c["projector_ready"])
        self.assertIn("2 layers", c["plan"]["mode"])  # as measured on the 1080 Ti

    def test_the_guide_otherwise(self):
        c = V.choose(FakeStore({"Qwen3.5-4B-mmproj-F16.gguf"}), {"model": "/usr/share/g.gguf"})
        self.assertFalse(c["recommended"])
        self.assertTrue(c["projector_ready"])
        self.assertEqual(c["path"], "/usr/share/g.gguf")

    def test_started_with_its_projector_on_the_processor(self):
        store = FakeStore({"Qwen3.8-27B-UD-IQ3_XXS.gguf", "Qwen3.8-27B-mmproj-F16.gguf"})
        cfg = V.backend_settings(V.choose(store, {}), store, {"context": 8192})
        args = cfg["extra_args"]
        self.assertEqual(args[args.index("--mmproj") + 1], store.path("Qwen3.8-27B-mmproj-F16.gguf"))
        self.assertIn("--no-mmproj-offload", args)
        self.assertEqual(cfg["context"], M.VISION_CONTEXT)
        self.assertEqual(cfg["socket_name"], "llama-vision.sock")

    def test_projectors_download_from_their_own_names(self):
        for p in M.PROJECTORS.values():
            self.assertEqual(p.remote, "mmproj-F16.gguf")
            self.assertTrue(p.source and len(p.sha256) == 64 and p.size > 600 << 20)


@unittest.skipIf(Image is None, "needs Pillow (to make the test photo; the daemon itself uses GdkPixbuf)")
class ThePicture(unittest.TestCase):
    def test_sideways_phone_photo_comes_upright_and_big_ones_shrink(self):
        im = Image.new("RGB", (4000, 3000), "white")
        exif = im.getexif()
        exif[0x0112] = 6  # stored sideways: "rotate 90° to view"
        path = os.path.join(tempfile.mkdtemp(), "letter.jpg")
        im.save(path, exif=exif)
        mime, data = V.picture(path)
        out = Image.open(io.BytesIO(base64.b64decode(data)))
        self.assertEqual(mime, "image/jpeg")
        self.assertGreater(out.size[1], out.size[0])        # portrait now, as the phone showed it
        self.assertEqual(max(out.size), V.LONG_SIDE)


@unittest.skipIf(Image is None, "needs Pillow (on Mint's image)")
class FindingByColour(unittest.TestCase):
    """Ctrl+F for pictures (Ian, 2026-10-04): the places where the colours meet go to the model as close-ups."""

    def shirt(self):
        from PIL import ImageDraw
        im = Image.new("RGB", (1200, 800), (200, 180, 140))
        d = ImageDraw.Draw(im)
        for i in range(8):
            d.rectangle((900, 600 + i * 8, 928, 603 + i * 8), fill=(210, 30, 35))
            d.rectangle((900, 604 + i * 8, 928, 607 + i * 8), fill=(245, 245, 245))
        path = os.path.join(tempfile.mkdtemp(), "beach.png")
        im.save(path)
        return path

    def test_a_search_by_colour_sends_close_ups(self):
        path = self.shirt()
        close = V.places(path, "Where's the guy in the red and white striped shirt?")
        self.assertTrue(close)
        self.assertEqual(close[0]["where"], "bottom right")
        self.assertGreaterEqual(max(Image.open(io.BytesIO(base64.b64decode(close[0]["data"]))).size), V.CLOSE_UP)
        msg = V.messages(path, "Where's the guy in the red and white striped shirt?", close)[0]["content"]
        self.assertEqual(sum(c["type"] == "image_url" for c in msg), 1 + len(close))
        self.assertIn("place 1 (bottom right)", msg[-1]["text"])

    def test_other_questions_get_just_the_picture(self):
        path = self.shirt()
        self.assertEqual(V.places(path, "What colour is the shirt, red or white?"), [])  # not a search
        self.assertEqual(V.places(path, "Find the dog"), [])                             # no colour to go by
        self.assertEqual(len(V.messages(path, "Find the dog")[0]["content"]), 2)


class Words(unittest.TestCase):
    def test_the_caveat_is_always_said(self):
        self.assertIn("check what matters against the original", words.vision_caveat({"recommended": True}))
        self.assertIn("built-in guide", words.vision_caveat({"recommended": False}))
        self.assertIn("MB", words.vision_setup({"model": "Qwen3.8-27B IQ3_XXS", "size_mb": 885, "recommended": True}))


if __name__ == "__main__":
    unittest.main()


class NumbersAreNamed(unittest.TestCase):
    """The sidebar names the numbers read from a picture, whatever the model does (2026-10-04)."""

    def test_the_letters_numbers(self):
        # the 27B's real answer on the SSD: two phone numbers it misread, no "(check the original)"
        answer = ("You can contact NPU by calling 860-872-7207. For questions about notification, you can also call "
                  "Customer Service Center at 860-882-2555. Dated 12/30/2025, balance $1,204.50, account no. 4471-22.")
        found = words.numbers_read(answer)
        self.assertEqual(found[:2], ["860-872-7207", "860-882-2555"])
        self.assertIn("12/30/2025", found)
        self.assertIn("$1,204.50", found)
        caveat = words.vision_caveat({"recommended": True}, answer)
        self.assertIn("860-872-7207", caveat)
        self.assertIn("Check them against the original", caveat)

    def test_no_numbers_no_list(self):
        self.assertNotIn("Numbers read", words.vision_caveat({"recommended": True}, "Six pairs of shoes on a rack."))
