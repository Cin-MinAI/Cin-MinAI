# SPDX-License-Identifier: GPL-3.0-or-later
""""Summarize this video" for the YouTube video open in Firefox (D78): when it's asked, the storyboard cut into
frames, the frames that change kept, and plain words when it can't be done — never a summarizer site."""

import io
import json
import shutil
import tempfile
import unittest

from cin_minai.daemon import webvideo as W
from cin_minai.firefox import host as H

try:
    from PIL import Image
except ImportError:
    Image = None

SPEC = ("https://i.ytimg.com/sb/939uGzs484M/storyboard3_L$L/$N.jpg?sqp=abc|48#27#100#10#10#0#default#rs$A1|"
        "160#90#77#5#5#5000#M$M#rs$B2|320#180#77#3#3#5000#M$M#rs$C3")


class Asking(unittest.TestCase):
    def test_this_video(self):
        for t in ("summarize this video", "Can you summarize the YouTube video I have open?",
                  "what does this video say about the wishbone?", "watch this video for me",
                  "resume este vídeo", "fasse dieses Video zusammen", "この動画を要約して"):
            self.assertTrue(W.asks_about_video(t), t)

    def test_not_about_a_video(self):
        for t in ("what is a video codec?", "my video driver crashed", "how do I watch videos on Linux?",
                  "summarize this letter"):
            self.assertFalse(W.asks_about_video(t), t)


class Storyboard(unittest.TestCase):
    def test_the_largest_level(self):
        sheets, step = W.storyboard_sheets(SPEC, 378)
        self.assertEqual(step, 5.0)
        self.assertEqual(len(sheets), 9)  # 77 frames, 9 a sheet
        self.assertEqual(sheets[0]["url"], "https://i.ytimg.com/sb/939uGzs484M/storyboard3_L2/M0.jpg?sqp=abc&sigh=rs%24C3")
        self.assertEqual(sheets[-1]["count"], 77 - 8 * 9)
        self.assertTrue(all(W.allowed(s["url"]) for s in sheets))

    def test_only_youtubes_pictures(self):
        self.assertFalse(W.allowed("https://evil.example/sb.jpg"))
        self.assertFalse(W.allowed("http://i.ytimg.com/sb.jpg"))
        self.assertEqual(W.storyboard_sheets("", 100), ([], 0))
        self.assertEqual(W.storyboard_sheets("x|1#2", 100), ([], 0))

    @unittest.skipIf(Image is None, "needs Pillow (on Mint's image)")
    def test_frames_cut_and_only_changes_kept(self):
        colours = ["red"] * 4 + ["blue"] * 5  # one sheet: 4 red frames, then 5 blue
        sheet = Image.new("RGB", (960, 540))
        for i, c in enumerate(colours):
            r, col = divmod(i, 3)
            sheet.paste(Image.new("RGB", (320, 180), c), (col * 320, r * 180))
        buf = io.BytesIO()
        sheet.save(buf, "JPEG")
        spec = "https://i.ytimg.com/sb/x/storyboard3_L$L/$N.jpg?a=1|320#180#9#3#3#5000#M$M#rs$C"
        fetched = []

        def fetch(url):
            fetched.append(url)
            return buf.getvalue()
        work = tempfile.mkdtemp()
        try:
            frames = W.key_frames({"storyboard": spec, "length": 45}, work, fetch)
        finally:
            shutil.rmtree(work)
        self.assertEqual(len(fetched), 1)
        self.assertEqual([t for t, _ in frames], [0.0, 20.0])  # the first frame, and where it turns blue


class Words(unittest.TestCase):
    def test_transcript_lines(self):
        self.assertEqual(W.lines({"transcript": [[3, " Carving a turkey "], [9, "[Music]"], ["x", "bad"]]}),
                         [(3.0, "Carving a turkey")])

    def test_plain_words_when_it_cant(self):
        self.assertIn("can't reach Firefox", W.problem({"error": "no_extension"}))
        self.assertIn("isn't a YouTube video", W.problem({"error": "no_video"}))
        self.assertIn("live stream", W.problem({"live": True, "storyboard": SPEC}))
        self.assertIsNone(W.problem({"transcript": [[0, "hi"]], "storyboard": SPEC}))
        for err in ("no_extension", "no_video", "read"):
            self.assertNotIn("summarizer", W.problem({"error": err}).lower())


class Host(unittest.TestCase):
    def test_framing_round_trip(self):
        out = io.BytesIO()
        H.Host(out).send({"type": "current_video", "req": 1})
        self.assertEqual(H.read_message(io.BytesIO(out.getvalue())), {"type": "current_video", "req": 1})
        self.assertIsNone(H.read_message(io.BytesIO(b"")))

    def test_the_reply_goes_to_its_question(self):
        host = H.Host(io.BytesIO())
        got = []
        host.reply = lambda inv, data: got.append((inv, data))
        host.waiting = {7: "inv7"}
        host.handle({"type": "video", "req": 7, "title": "How to Carve a Turkey"})
        self.assertEqual(got, [("inv7", {"title": "How to Carve a Turkey"})])
        host.handle({"type": "video", "req": 7})  # answered already: ignored
        self.assertEqual(len(got), 1)


if __name__ == "__main__":
    unittest.main()
