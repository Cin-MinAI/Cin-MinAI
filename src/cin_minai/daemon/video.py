# SPDX-License-Identifier: GPL-3.0-or-later
"""The assistant watches a video (D64, D78): what is said (whisper.cpp) and what is shown (key frames, read by the
vision model), then a summary focused on what the person asked — from the lab's script (spikes/vision/
video_summary.py: Ian's 2:38 tutorial in 8½ min, a 28:29 reballing video in 13 min on the 1080 Ti and the i7).

A job that can take minutes: each step says where it is. ffmpeg takes the sound and the frames out (cinminai-whisper
depends on it); the speech model is fetched once, asked first, like the picture reader.
"""

from __future__ import annotations

import glob
import os
import re
import shutil
import subprocess
import tempfile

from cin_minai.inference.matcher import Model

WHISPER_CLI = "/usr/lib/cinminai/whisper/whisper-cli"
# multilingual (D25's six languages, detected by itself); the lab used small.en — same size, English only
WHISPER = Model("Speech recognition (whisper small)", "ggml-small.bin", 487601967, 0, 0, 0,
                source="ggerganov/whisper.cpp@5359861c739e955e79d9a303bcbc70fb988958b1",
                sha256="1be3a9b2063867b937e64e2ec7483364a79917e157fa98c5d94b5c1fffea987b", size=487601967)
VIDEOS = (".mp4", ".mkv", ".webm", ".mov", ".avi", ".m4v", ".mpg", ".mpeg", ".wmv", ".flv", ".3gp", ".ts")
# key frames: where the picture changes, at least one every GAP seconds; long videos sparser (the lab's settings)
SHORT, LONG = {"gap": 10, "scene": 0.25, "max": 40}, {"gap": 30, "scene": 0.35, "max": 60}
FRAME = ("A frame from a video, at {when}. In two or three sentences: what is shown (people, things, what is being "
         "done), and any on-screen text you can actually read. Don't guess at what you can't see.{said}")
SUMMARY = ("Below are the timestamped transcript of a video (automatic speech recognition: it may get names and "
           "numbers wrong) and descriptions of its key frames. The person asked: \"{request}\"\n"
           "Answer that first, in plain words, in the language of the request. Then, as far as it helps them: what the "
           "video is about; the main points or steps in order, each with its time [m:ss]; any warnings or tips it "
           "gives. Use only what's in the transcript and the frames, and say where something is unclear. Numbers, "
           "names and part numbers heard or read: put (check the video) after each one.\n\nTRANSCRIPT:\n{transcript}"
           "\n\nKEY FRAMES:\n{frames}")
DEFAULT_REQUEST = "Summarize this video: tell me what I need to know."


def is_video(path: str) -> bool:
    return path.lower().endswith(VIDEOS)


def hms(s: float) -> str:
    return f"{int(s) // 3600}:{int(s) % 3600 // 60:02}:{int(s) % 60:02}" if s >= 3600 else f"{int(s) // 60}:{int(s) % 60:02}"


def duration(path: str) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                       capture_output=True, text=True, timeout=60)
    try:
        return float(r.stdout.strip())
    except ValueError:
        raise ValueError("I can't read that video file.") from None


def parse_srt(srt: str) -> list[tuple[float, str]]:
    """[(start seconds, words)] from whisper's SRT."""
    out = []
    for block in srt.strip().split("\n\n"):
        parts = block.strip().split("\n")
        if len(parts) >= 3 and " --> " in parts[1]:
            h, m, s = parts[1].split(" --> ")[0].replace(",", ".").split(":")
            text = " ".join(parts[2:]).strip()
            if text and not re.fullmatch(r"\[.*\]|\(.*\)", text):  # "[Music]", "(silence)"
                out.append((int(h) * 3600 + int(m) * 60 + float(s), text))
    return out


def transcript(video: str, work: str, model_path: str, threads: int | None = None) -> list[tuple[float, str]]:
    """The speech, timestamped; [] when there's no sound track or nothing said."""
    wav = os.path.join(work, "audio.wav")
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", video, "-vn", "-ar", "16000", "-ac", "1", wav],
                       capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(wav) or os.path.getsize(wav) < 1000:
        return []  # no sound track
    threads = threads or max(1, min(8, (os.cpu_count() or 4) // 2))
    subprocess.run([WHISPER_CLI, "-m", model_path, "-f", wav, "-l", "auto", "-t", str(threads), "-osrt",
                    "-of", os.path.join(work, "transcript"), "-np"], check=True, capture_output=True)
    with open(os.path.join(work, "transcript.srt"), encoding="utf-8", errors="replace") as f:
        return parse_srt(f.read())


def key_frames(video: str, work: str, length: float) -> list[tuple[float, str]]:
    """[(time, jpeg path)] where the picture changes, spread evenly if there are too many."""
    k = SHORT if length < 300 else LONG
    frames_dir = os.path.join(work, "frames")
    os.makedirs(frames_dir, exist_ok=True)
    select = (f"(gt(scene,{k['scene']})*gte(t-prev_selected_t,{k['gap']}))+isnan(prev_selected_t)"
              f"+gte(t-prev_selected_t,{k['gap']}*3)")
    r = subprocess.run(["ffmpeg", "-v", "info", "-y", "-i", video, "-an", "-vf", f"select='{select}',showinfo,"
                        "scale='min(960,iw)':-2", "-vsync", "vfr", "-q:v", "3",
                        os.path.join(frames_dir, "f%04d.jpg")], capture_output=True, text=True)
    times = [float(t) for t in re.findall(r"pts_time:([0-9.]+)", r.stderr)]
    files = sorted(glob.glob(os.path.join(frames_dir, "*.jpg")))
    pairs = list(zip(times, files))
    if len(pairs) > k["max"]:
        keep = sorted({round(i * (len(pairs) - 1) / (k["max"] - 1)) for i in range(k["max"])})
        pairs = [pairs[i] for i in keep]
    return pairs


def said_before(lines: list[tuple[float, str]], t: float, chars: int = 300) -> str:
    return " ".join(text for start, text in lines if start <= t)[-chars:]


def frame_prompt(t: float, lines: list[tuple[float, str]]) -> str:
    said = said_before(lines, t)
    return FRAME.format(when=hms(t), said=f"\n(What was being said just before: \"{said}\")" if said else "")


def summary_prompt(request: str, lines: list[tuple[float, str]], frames: list[tuple[float, str]]) -> str:
    text = "\n".join(f"[{hms(t)}] {w}" for t, w in lines) or "(nothing is said in this video)"
    return SUMMARY.format(request=request.strip() or DEFAULT_REQUEST, transcript=text,
                          frames="\n".join(f"[{hms(t)}] {d}" for t, d in frames))


def workdir() -> str:
    base = os.path.join(os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache"), "cinminai")
    os.makedirs(base, exist_ok=True)
    return tempfile.mkdtemp(prefix="video-", dir=base)


def cleanup(work: str) -> None:
    shutil.rmtree(work, ignore_errors=True)
