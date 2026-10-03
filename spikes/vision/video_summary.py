# SPDX-License-Identifier: GPL-3.0-or-later
"""D64 video test: a video → transcript (whisper.cpp) + key frames (ffmpeg) → frame descriptions and a summary with
timestamped steps (a vision model on llama.cpp). Everything local.

    python3 video_summary.py VIDEO MODEL.gguf MMPROJ.gguf WHISPER_MODEL.bin [extra llama-server args...]

Writes VIDEO-stem/ next to the video: audio.wav, transcript.srt, frames/*.jpg, frames.md, summary.md, timings.txt.
Its own llama-server on 127.0.0.1:8091 (never 8080), always stopped.
"""
import base64
import glob
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

video, model, mmproj, wmodel = [os.path.abspath(os.path.expanduser(a)) for a in sys.argv[1:5]]
extra = sys.argv[5:]
PORT = 8091
WHISPER = os.path.expanduser("~/cinminai-src/tools/whisper.cpp/build/bin/whisper-cli")
out = os.path.splitext(video)[0]
frames_dir = os.path.join(out, "frames")
os.makedirs(frames_dir, exist_ok=True)
timings = []


def stamp(what: str, t0: float) -> None:
    timings.append(f"{what}: {time.time() - t0:.0f} s")
    print(timings[-1], flush=True)


def hms(s: float) -> str:
    return f"{int(s) // 60}:{int(s) % 60:02}"


# 1. the speech: 16 kHz mono, whisper.cpp on the processor, timestamps as SRT
t = time.time()
wav = os.path.join(out, "audio.wav")
subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", video, "-ar", "16000", "-ac", "1", wav], check=True)
subprocess.run([WHISPER, "-m", wmodel, "-f", wav, "-t", "4", "-osrt", "-of", os.path.join(out, "transcript"), "-np"],
               check=True, stdout=subprocess.DEVNULL)
stamp("transcript (whisper)", t)
srt = open(os.path.join(out, "transcript.srt"), encoding="utf-8").read()
lines = []
for block in srt.strip().split("\n\n"):
    parts = block.split("\n")
    if len(parts) >= 3:
        start = parts[1].split(" --> ")[0][:8].lstrip("0:") or "0"
        lines.append(f"[{parts[1].split(' --> ')[0][3:8]}] {' '.join(parts[2:])}")
transcript = "\n".join(lines)

# 2. key frames: where the picture changes, and at least one every GAP s (10 for short videos; long ones: env GAP=30
# SCENE=0.35 MAX_FRAMES=60); their times from ffmpeg's showinfo
GAP, SCENE, MAX_FRAMES = os.environ.get("GAP", "10"), os.environ.get("SCENE", "0.25"), int(os.environ.get("MAX_FRAMES", "999"))
t = time.time()
for f in glob.glob(os.path.join(frames_dir, "*.jpg")):
    os.remove(f)
r = subprocess.run(["ffmpeg", "-v", "info", "-y", "-i", video, "-vf",
                    f"select='(gt(scene,{SCENE})*gte(t-prev_selected_t,{GAP}))+isnan(prev_selected_t)+gte(t-prev_selected_t,{GAP}*3)',showinfo,scale=640:-2",
                    "-vsync", "vfr", "-q:v", "3", os.path.join(frames_dir, "f%03d.jpg")],
                   capture_output=True, text=True)
times = [float(m) for m in re.findall(r"pts_time:([0-9.]+)", r.stderr)]
frames = sorted(glob.glob(os.path.join(frames_dir, "*.jpg")))
if len(frames) > MAX_FRAMES:  # spread the cap evenly over the video
    keep = [round(i * (len(frames) - 1) / (MAX_FRAMES - 1)) for i in range(MAX_FRAMES)]
    frames, times = [frames[i] for i in keep], [times[i] for i in keep if i < len(times)]
stamp(f"key frames ({len(frames)})", t)

# 3. the vision model describes each frame, briefly
argv = ["/usr/lib/cinminai/llama/llama-server", "--model", model, "--mmproj", mmproj, "--host", "127.0.0.1",
        "--port", str(PORT), "-fa", "on", "--no-mmproj-offload", *extra]
log = open(os.path.join(out, "server.log"), "w")
srv = subprocess.Popen(argv, stdout=log, stderr=subprocess.STDOUT)
SAMPLING = {"temperature": 0, "repeat_penalty": 1.05, "dry_multiplier": 0.8, "dry_base": 1.75,
            "dry_allowed_length": 3, "dry_penalty_last_n": 1024, "chat_template_kwargs": {"enable_thinking": False}}


def chat(content, max_tokens):
    body = {"messages": [{"role": "user", "content": content}], "max_tokens": max_tokens, **SAMPLING}
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}/v1/chat/completions", json.dumps(body).encode(),
                                 {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=3600) as resp:
        return json.load(resp)["choices"][0]["message"]["content"].strip()


try:
    t = time.time()
    while True:
        if srv.poll() is not None:
            sys.exit("llama-server exited; see server.log")
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=2) as resp:
                if resp.status == 200:
                    break
        except Exception:
            pass
        time.sleep(1)
    stamp("model loaded", t)
    t = time.time()
    described = []
    for i, f in enumerate(frames):
        when = hms(times[i]) if i < len(times) else "?"
        said = " ".join(l for l in lines if l[1:6] <= f"{int(times[i]) // 60:02}:{int(times[i]) % 60:02}")[-300:] \
            if i < len(times) else ""
        data = base64.b64encode(open(f, "rb").read()).decode()
        text = chat([{"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{data}"}},
                     {"type": "text", "text": "This is a frame from a hardware repair/modding tutorial video. In two "
                      "or three sentences: what is shown (parts, tools, what the hands are doing), and any on-screen "
                      "text you can actually read. Don't guess at what you can't see."}], 160)
        described.append(f"[{when}] ({os.path.basename(f)}) {text}")
        print(f"  frame {i + 1}/{len(frames)} at {when}", flush=True)
    stamp("frame descriptions", t)
    with open(os.path.join(out, "frames.md"), "w", encoding="utf-8") as fh:
        fh.write("\n\n".join(described) + "\n")

    # 4. the summary and the steps, from the transcript and the frames
    t = time.time()
    summary = chat([{"type": "text", "text": (
        "Below are the timestamped transcript of a tutorial video (automatic speech recognition, may contain "
        "errors) and descriptions of key frames. Write for someone who wants to follow along with the work:\n"
        "1. What the video is about, in two or three sentences.\n"
        "2. What you need: parts, tools, skills — only what the video shows or says.\n"
        "3. The steps in order, each with its start time [m:ss] and the frame file that shows it best.\n"
        "4. Warnings and tips the video gives.\n"
        "Only use what's in the transcript and frames; say where something is unclear.\n\n"
        f"TRANSCRIPT:\n{transcript}\n\nKEY FRAMES:\n" + "\n".join(described))}], 1800)
    stamp("summary", t)
    with open(os.path.join(out, "summary.md"), "w", encoding="utf-8") as fh:
        fh.write(summary + "\n")
finally:
    srv.terminate()
    try:
        srv.wait(15)
    except subprocess.TimeoutExpired:
        srv.kill()
    with open(os.path.join(out, "timings.txt"), "w") as fh:
        fh.write("\n".join(timings) + "\n")
    print("server stopped; results in", out)
