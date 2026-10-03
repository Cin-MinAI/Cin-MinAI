# SPDX-License-Identifier: GPL-3.0-or-later
"""D64 tests: one model with its vision projector, every image in a folder, answers and timings to a Markdown file.

    python3 vision_batch.py NAME MODEL.gguf MMPROJ.gguf FOLDER [extra llama-server args...]

The prompt depends on the picture: a document gets transcribed and summarized with what the reader has to do; any
other photo gets described. Its own llama-server on 127.0.0.1:8091 (never 8080), always stopped at the end.
Results: FOLDER/results-NAME.md
"""
import base64
import json
import mimetypes
import os
import subprocess
import sys
import time
import urllib.request

name, model, mmproj, folder = sys.argv[1:5]
extra = sys.argv[5:]
PORT = 8091
REQUESTS = {  # round 2: the user's own requests, typed (round 1 used the file names; "crapscan" sent the 27B in a loop)
    "countpairs": "How many pairs of shoes are there?",
    "crapscan": "Summarize this letter I got.",
    "goodscan": "Summarize this letter I got.",
    "whatshere": "What's in this picture?",
}
RULES = ("Rules: answer the request first, in plain words. Any number, date, phone number, code or web address you "
         "read from the picture: copy it exactly if it's clear, and if it's small or blurry write it followed by "
         "(verify) — or say it's too small to read. Never guess text, numbers, barcodes or brands you can't actually "
         "read; say what you can't see. If you count things, give the number and say how sure you are.")
SAMPLING = {"temperature": 0, "repeat_penalty": 1.05, "dry_multiplier": 0.8, "dry_base": 1.75,
            "dry_allowed_length": 3, "dry_penalty_last_n": 1024}  # round 2: both models looped at temperature 0
PROMPT = ("First say in one line what kind of picture this is (a document, a screenshot, a photo of a thing, a "
          "scene...). If it is a document — a letter, a bill, a receipt, a form, a manual page, a handwritten note — "
          "write out its text as exactly as you can (mark anything you can't read as [unreadable]), then summarize "
          "it in two or three sentences, then list anything the reader has to do and by when. If it is not a "
          "document, describe what you see and anything notable or useful to know (for a part or a tool: what it is "
          "and what it's for). Don't guess at what you can't see.")


def upright(image: str) -> tuple[str, bytes]:
    """The picture as a viewer shows it: phone photos are often stored sideways with an EXIF rotation tag, which
    llama.cpp ignores — the model would get a letter turned 90° (found 2026-10-03)."""
    try:
        import io
        from PIL import Image, ImageOps
        im = ImageOps.exif_transpose(Image.open(image)).convert("RGB")
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=95)
        return "image/jpeg", buf.getvalue()
    except ImportError:
        return mimetypes.guess_type(image)[0] or "image/jpeg", open(image, "rb").read()


def ask(image: str) -> tuple[str, dict, float]:
    mime, raw = upright(image)
    data = base64.b64encode(raw).decode()
    stem = os.path.splitext(os.path.basename(image))[0]
    request = REQUESTS.get(stem, "What's in this picture?")
    body = {"messages": [{"role": "user", "content": [
        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{data}"}},
        {"type": "text", "text": f"{request}\n\n{RULES}"}]}],
        "max_tokens": 1500, **SAMPLING, "chat_template_kwargs": {"enable_thinking": False}}
    t = time.time()
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}/v1/chat/completions", json.dumps(body).encode(),
                                 {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=3600) as r:
        out = json.load(r)
    return out["choices"][0]["message"]["content"], out.get("timings", {}), time.time() - t


images = sorted(os.path.join(folder, f) for f in os.listdir(folder)
                if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp", ".bmp")))
if not images:
    sys.exit(f"no images in {folder}")
argv = ["/usr/lib/cinminai/llama/llama-server", "--model", model, "--mmproj", mmproj, "--host", "127.0.0.1",
        "--port", str(PORT), "-fa", "on", "--no-mmproj-offload", *extra]
log = open(f"/tmp/vision-{name}.log", "w")
srv = subprocess.Popen(argv, stdout=log, stderr=subprocess.STDOUT)
results = os.path.join(folder, f"results-{name}.md")  # round 2 passes NAME like 27b-r2
try:
    t0 = time.time()
    while True:
        if srv.poll() is not None:
            sys.exit(f"server exited ({srv.returncode}); see /tmp/vision-{name}.log")
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=2) as r:
                if r.status == 200:
                    break
        except Exception:
            pass
        time.sleep(1)
    with open(results, "w", encoding="utf-8") as f:
        f.write(f"# Vision test: {name}\n\n`{' '.join(argv)}`\n\nLoaded in {time.time() - t0:.0f} s.\n\n")
    for img in images:
        print(f"{os.path.basename(img)} ...", end=" ", flush=True)
        try:
            text, t, secs = ask(img)
        except Exception as e:  # a server that died on one picture: say so and stop
            text, t, secs = f"(failed: {e})", {}, 0.0
        print(f"{secs:.0f} s", flush=True)
        with open(results, "w" if False else "a", encoding="utf-8") as f:
            f.write(f"## {os.path.basename(img)}\n\n{secs:.0f} s — image + prompt {t.get('prompt_n')} tokens in "
                    f"{(t.get('prompt_ms') or 0) / 1000:.0f} s, {t.get('predicted_n')} tokens written at "
                    f"{t.get('predicted_per_second') or 0:.1f} tok/s\n\n{text}\n\n")
        if srv.poll() is not None:
            print("server died; see the log")
            break
finally:
    srv.terminate()
    try:
        srv.wait(15)
    except subprocess.TimeoutExpired:
        srv.kill()
    print("server stopped; results in", results)
