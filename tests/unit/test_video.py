# SPDX-License-Identifier: GPL-3.0-or-later
"""Watching a video (D64, D78): the speech's timestamps, the prompts with the person's focus, and what the sidebar
says while it works and after."""

import shutil
import unittest

from cin_minai.daemon import video as V
from cin_minai.sidebar import words

SRT = """1
00:00:00,000 --> 00:00:04,200
Today we're replacing the timing belt.

2
00:00:04,200 --> 00:00:06,000
[Music]

3
00:01:12,500 --> 00:01:16,000
Torque the bolt to 25 newton metres.
"""


class Speech(unittest.TestCase):
    def test_srt_times_and_no_sound_marks(self):
        lines = V.parse_srt(SRT)
        self.assertEqual([t for t, _ in lines], [0.0, 72.5])
        self.assertEqual(lines[1][1], "Torque the bolt to 25 newton metres.")

    def test_what_was_said_before_a_frame(self):
        lines = V.parse_srt(SRT)
        self.assertIn("timing belt", V.said_before(lines, 30))
        self.assertNotIn("Torque", V.said_before(lines, 30))
        self.assertIn("Torque", V.frame_prompt(80, lines))
        self.assertNotIn("being said", V.frame_prompt(80, []))

    def test_times(self):
        self.assertEqual(V.hms(72.5), "1:12")
        self.assertEqual(V.hms(3725), "1:02:05")


class Prompts(unittest.TestCase):
    def test_the_request_leads_and_numbers_are_flagged(self):
        p = V.summary_prompt("what torque for the bolt?", V.parse_srt(SRT), [(70.0, "A hand with a torque wrench.")])
        self.assertIn('"what torque for the bolt?"', p)
        self.assertIn("[1:12] Torque the bolt", p)
        self.assertIn("[1:10] A hand with a torque wrench.", p)
        self.assertIn("(check the video)", p)

    def test_a_silent_video_says_so(self):
        p = V.summary_prompt("", [], [(0.0, "A cat.")])
        self.assertIn(V.DEFAULT_REQUEST, p)
        self.assertIn("nothing is said", p)

    def test_the_pages_title_and_channel_win_over_a_misread_logo(self):
        # 2026-10-04: "League of Joy" read as "League of Legends" from a preview picture, then a "branding mismatch"
        f = V.frame_prompt(30, [], "How to DRAW RICK - Rick and Morty", "League of Joy - How to Draw")
        self.assertIn('"How to DRAW RICK - Rick and Morty" by League of Joy - How to Draw', f)
        s = V.summary_prompt("", [], [(0.0, "A drawing.")], "How to DRAW RICK", "League of Joy")
        self.assertIn("misreading of small text", s)
        self.assertIn("Don't speculate about mistakes", s)
        self.assertNotIn("misreading", V.summary_prompt("", [], [(0.0, "A cat.")]))  # a file: no title to trust

    def test_which_files_are_videos(self):
        self.assertTrue(V.is_video("/home/a/Clip.MP4"))
        self.assertFalse(V.is_video("/home/a/letter.jpg"))
        self.assertEqual(V.VIDEOS, words.VIDEO_TYPES)  # the sidebar offers what the daemon watches


class LongVideos(unittest.TestCase):
    """2026-10-05: a 42-minute video (834 lines, 60 frames) was 28,813 tokens against a 16,384 window."""

    def long_video(self):
        lines = [(i * 3.0, "and then you take the turkey and you rub the butter all over the skin like this " * 1)
                 for i in range(834)]
        frames = [(i * 42.0, "A chef in a white jacket holds a roasting pan with a golden turkey on a wooden board.")
                  for i in range(60)]
        return lines, frames

    def test_too_long_is_split_into_parts_that_fit(self):
        lines, frames = self.long_video()
        self.assertFalse(V.fits(V.summary_prompt("", lines, frames), 16384, V.SUMMARY_TOKENS))
        parts = V.parts(lines, frames, 16384)
        self.assertGreater(len(parts), 1)
        for i, p in enumerate(parts, 1):
            self.assertTrue(V.fits(V.notes_prompt(p, i, len(parts), "Turkey", "Chef"), 16384, V.NOTES_TOKENS))
        self.assertEqual(sum(len(p["lines"]) for p in parts), len(lines))  # nothing lost
        self.assertEqual(sum(len(p["frames"]) for p in parts), len(frames))
        self.assertEqual([p["start"] for p in parts], sorted(p["start"] for p in parts))  # in order

    def test_the_summary_from_notes_fits_and_keeps_the_request(self):
        s = V.summary_from_notes("how long per pound?", ["[0:10] Oven at 325 F (check the video)."] * 6, "T", "C")
        self.assertTrue(V.fits(s, 16384, V.SUMMARY_TOKENS))
        self.assertIn('"how long per pound?"', s)
        self.assertIn("Part 6:", s)

    def test_a_short_video_stays_in_one_go(self):
        self.assertTrue(V.fits(V.summary_prompt("", V.parse_srt(SRT), [(0.0, "A belt.")]), 16384, V.SUMMARY_TOKENS))

    def test_the_server_refusal_in_plain_words(self):
        from cin_minai.inference.llamacpp import server_error
        body = ('{"error":{"code":400,"message":"request (28813 tokens) exceeds the available context size (16384 '
                'tokens), try increasing it","type":"exceed_context_size_error","n_prompt_tokens":28813,"n_ctx":16384}}')
        said = server_error(400, body)
        self.assertTrue(said.startswith("That was more than the model can read at once"))
        self.assertNotIn("{", said)
        self.assertIn("couldn't answer", server_error(500, "boom"))


class TheModel(unittest.TestCase):
    def test_pinned_and_checked(self):
        self.assertEqual(len(V.WHISPER.sha256), 64)
        self.assertTrue(V.WHISPER.source.startswith("ggerganov/whisper.cpp@"))
        self.assertEqual(V.WHISPER.size, 487601967)


class Words(unittest.TestCase):
    def test_the_offer_names_each_download(self):
        both = words.vision_setup({"video": True, "reader": True, "speech": True, "size_mb": 1350,
                                   "recommended": True})
        self.assertIn("picture reader", both)
        self.assertIn("speech recognizer", both)
        self.assertIn("1350 MB", both)
        speech = words.vision_setup({"video": True, "speech": True, "size_mb": 465, "recommended": True})
        self.assertNotIn("picture reader", speech)

    def test_words_are_not_numbers(self):
        # 2026-10-05, the 42-minute turkey: "refrigerator" was named as a number to check ("ref" + "rigerator")
        found = words.numbers_heard("Keep it in the refrigerator, roast to 155°F. Reference: the video. Ref# AB-1234.")
        self.assertNotIn("refrigerator", " ".join(found))
        self.assertIn("155°F", found)
        self.assertIn("Ref# AB-1234", found)
        self.assertEqual(words.numbers_heard("Refer to the referee's account of it."), [])

    def test_steps_and_caveat(self):
        line = words.video_step({"file": "belt.mp4", "model": "Qwen3.8-27B"}, {"stage": "frame", "n": 4, "of": 23,
                                                                                "at": "1:10"})
        self.assertIn("4 of 23", line)
        said = words.video_caveat({"recommended": True, "speech": True, "frames": 23, "took": "6:40"},
                                  "Torque it to 25 Nm, part 06H109119.")
        self.assertIn("6:40", said)
        self.assertIn("Check them in the video", said)
        silent = words.video_caveat({"recommended": False, "speech": False, "frames": 5})
        self.assertIn("no speech", silent)
        self.assertIn("built-in guide", silent)


@unittest.skipIf(shutil.which("ffmpeg") is None, "needs ffmpeg (cinminai-whisper brings it)")
class WithFfmpeg(unittest.TestCase):
    def test_frames_from_a_made_video(self):
        import os
        import subprocess
        import tempfile
        work = tempfile.mkdtemp()
        clip = os.path.join(work, "clip.mp4")
        # 30 s: red, then blue from 15 s — a change the scene filter should catch, no sound
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=red:s=320x240:d=15", "-f", "lavfi",
                        "-i", "color=blue:s=320x240:d=15", "-filter_complex", "[0][1]concat=n=2:v=1", clip], check=True)
        self.assertAlmostEqual(V.duration(clip), 30, delta=0.5)
        frames = V.key_frames(clip, work, 30)
        self.assertTrue(any(abs(t - 15) < 1 for t, _ in frames), frames)
        self.assertEqual(V.transcript(clip, work, "/nonexistent"), [])  # no sound track: nothing to hear


if __name__ == "__main__":
    unittest.main()
