# SPDX-License-Identifier: GPL-3.0-or-later
"""D64 first measurement: a model with its vision projector describes a screenshot.

    python3 vision_test.py MODEL.gguf MMPROJ.gguf IMAGE.png [extra llama-server args...]

Starts its own llama-server on 127.0.0.1:8091 (never 8080), sends the image once, prints the answer and timings,
and always stops the server.
"""
import base64
import json
import subprocess
import sys
import time
import urllib.request

model, mmproj, image = sys.argv[1:4]
extra = sys.argv[4:]
port = 8091
argv = ["/usr/lib/cinminai/llama/llama-server", "--model", model, "--mmproj", mmproj, "--host", "127.0.0.1",
        "--port", str(port), "-fa", "on", "--no-mmproj-offload", *extra]
print(" ".join(argv), flush=True)
log = open("/tmp/vision-server.log", "w")
t0 = time.time()
srv = subprocess.Popen(argv, stdout=log, stderr=subprocess.STDOUT)
try:
    while True:
        if srv.poll() is not None:
            sys.exit(f"server exited ({srv.returncode}); see /tmp/vision-server.log")
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2) as r:
                if r.status == 200:
                    break
        except Exception:
            pass
        time.sleep(1)
    print(f"loaded in {time.time() - t0:.0f} s", flush=True)
    gpu = subprocess.run(["nvidia-smi", "--query-gpu=memory.used,memory.free", "--format=csv,noheader"],
                         capture_output=True, text=True).stdout.strip()
    print("card:", gpu, flush=True)
    data = base64.b64encode(open(image, "rb").read()).decode()
    body = {"messages": [{"role": "user", "content": [
        {"type": "text", "text": "This is a screenshot of a blackjack game someone made. Describe what you see: the "
                                 "layout, the cards and totals, the buttons, the colours. Then list anything that "
                                 "looks wrong or hard to use."},
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{data}"}}]}],
        "max_tokens": 600, "temperature": 0, "chat_template_kwargs": {"enable_thinking": False}}
    t1 = time.time()
    req = urllib.request.Request(f"http://127.0.0.1:{port}/v1/chat/completions", json.dumps(body).encode(),
                                 {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=1800) as r:
        out = json.load(r)
    print(f"answered in {time.time() - t1:.0f} s", flush=True)
    t = out.get("timings", {})
    print("timings:", {k: t.get(k) for k in ("prompt_n", "prompt_ms", "predicted_n", "predicted_per_second")})
    print("\n" + out["choices"][0]["message"]["content"])
finally:
    srv.terminate()
    try:
        srv.wait(15)
    except subprocess.TimeoutExpired:
        srv.kill()
    print("server stopped", flush=True)
