# SPDX-License-Identifier: GPL-3.0-or-later
"""Seeing, the same way for any target (PLAN §1b "the look closure"; D64 screenshots, D86, D96). Ian, 2026-10-09:
"When a tool call for a screenshot is called, this is the process. So it doesn't matter if it's a UI, or trying to
get stuff off the web, or just seeing where the screen is at."

1. **Allowed** by the target: the program being built (the AI's own output, run locally in its sandbox: no question);
   a web page (the address leaves the computer: asked, D86); the person's screen (always asked, and shown to them
   before anything reads it).
2. **Capture, by code:** the picture and every fact code can read without a model — the screen and its scaling, the
   windows with their names, sizes and places, whether the program is still running and what it printed.
3. **Structure:** the facts as JSON beside the picture under `.cinminai/looks/` — kept, like sources.
4. **Check, by code:** a window that doesn't fit the screen, one far smaller than the screen, a blank picture, a
   program that stopped.
5. **Use:** the facts and the picture model's answer to one question, never "describe the picture".
6. **Record:** every look stays in the project; the person can open it.

Structure first, pixels second: facts read by code are complete and exact; a picture is where a model guesses.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import time

LOOKS = os.path.join(".cinminai", "looks")
WAIT_S = 4          # how long a program runs before its picture is taken
APART_S = 0.5      # the second picture, to see whether anything moves (code, not a model's guess)
SMALL = 0.4         # a window under this share of the screen's width is "small on this screen"
WINDOW = re.compile(r'^\s+0x[0-9a-f]+ "(?P<name>[^"]*)":.*?\s(?P<w>\d+)x(?P<h>\d+)\+-?\d+\+-?\d+\s+\+(?P<x>-?\d+)\+(?P<y>-?\d+)')


def screen_of(env: dict | None = None) -> tuple[int, int, int]:
    """The person's screen as AICUI read it (CINMINAI_SCREEN "WxH@SCALE"), else a common one."""
    m = re.fullmatch(r"(\d+)x(\d+)@(\d+)", (env or os.environ).get("CINMINAI_SCREEN", ""))
    return (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else (1920, 1080, 1)


def next_name(root: str) -> str:
    os.makedirs(os.path.join(root, LOOKS), exist_ok=True)
    return os.path.join(LOOKS, time.strftime("%Y%m%d-%H%M%S"))


def windows(tree_text: str, screen: tuple[int, int, int]) -> list[dict]:
    """The top-level windows from `xwininfo -root -tree`: name, size, place; the root and tiny helpers left out."""
    found = []
    for line in tree_text.splitlines():
        m = WINDOW.match(line)
        if m:
            found.append((len(line) - len(line.lstrip()), m))
    top = min((indent for indent, _ in found), default=0)  # the root's own children: the least indented
    out = []
    for indent, m in found:
        w, h = int(m.group("w")), int(m.group("h"))
        name = m.group("name")  # a fullscreen window is screen-sized too (2026-10-09: "opened no window")
        if indent != top or ((w, h) == screen[:2] and not name) or w < 40 or h < 40:
            continue
        out.append({"name": m.group("name"), "width": w, "height": h, "x": int(m.group("x")), "y": int(m.group("y"))})
    return out


def picture_facts(path: str) -> dict:
    """What code can say about a picture: its size, and whether anything is drawn (how many colours)."""
    try:
        from PIL import Image
        with Image.open(path) as im:
            small = im.convert("RGB").resize((64, 36))
            colours = len(set(small.getdata()))
            return {"width": im.width, "height": im.height, "colours": colours}
    except Exception:
        return {}


def motion(first: str, second: str) -> dict:
    """Two pictures APART_S apart: did anything change, and where (2026-10-09: the picture model said "the ball isn't
    visible", then "visible and moving", with no change in between — code can tell)."""
    try:
        from PIL import Image, ImageChops
        with Image.open(first) as a, Image.open(second) as b:
            box = ImageChops.difference(a.convert("RGB"), b.convert("RGB")).getbbox()
    except Exception:
        return {}
    if not box:
        return {"moved": False}
    return {"moved": True, "where": {"x": box[0], "y": box[1], "width": box[2] - box[0], "height": box[3] - box[1]}}


def checks(facts: dict) -> list[str]:
    """The problems code can name from the facts — before any model looks."""
    found = []
    sw, sh, scale = facts["screen"]["width"], facts["screen"]["height"], facts["screen"]["scale"]
    for w in facts.get("windows", []):
        name = w["name"] or "a window"
        if w["x"] < 0 or w["y"] < 0 or w["x"] + w["width"] > sw or w["y"] + w["height"] > sh:
            found.append(f"{name} ({w['width']}x{w['height']} at {w['x']},{w['y']}) runs off the {sw}x{sh} screen")
        share = w["width"] / sw
        if share < SMALL:
            found.append(f"{name} is {w['width']}x{w['height']}: {share:.0%} of the screen's width"
                         + (f" (at {scale}x scaling other windows are drawn {scale}x larger)" if scale > 1 else ""))
    if facts.get("program") and not facts.get("windows") and facts.get("running"):
        found.append("the program runs but opened no window")
    if facts.get("program") and not facts.get("running"):
        found.append("the program had stopped before the picture was taken: " + (facts.get("output") or "")[-300:])
    pic = facts.get("picture") or {}
    if pic and pic.get("colours", 99) <= 2:
        found.append("the picture is blank (one colour): nothing was drawn")
    return found


def program_script(entry: str, venv: str, screen: tuple[int, int, int], base: str) -> str:
    """Run the project's entry point in a virtual display the size of the person's screen, at their scaling, and
    take the picture and the window list — all inside the AI's sandbox (no network, only the project)."""
    w, h, k = screen
    start = f"bash {shlex.quote(entry)}" if entry.endswith(".sh") else \
        f"{shlex.quote(os.path.join(venv, 'bin', 'python') if venv else 'python3')} {shlex.quote(entry)}"
    b = shlex.quote(base)
    # in the sandbox: its /tmp starts empty and Xvfb won't make the socket folder unless it's root; and its OpenGL
    # extension goes through the NVIDIA driver, which crashes without the card's devices (measured 2026-10-09) —
    # a picture of a window needs neither
    return (f"mkdir -p -m 1777 /tmp/.X11-unix; Xvfb :77 -screen 0 {w}x{h}x24 -nolisten tcp -extension GLX "
            f">/dev/null 2>&1 & XV=$!; sleep 1; "
            f"export DISPLAY=:77 SDL_VIDEODRIVER=x11 GDK_SCALE={k} QT_SCALE_FACTOR={k}; "
            f"( {start} ) > {b}.out 2>&1 & P=$!; sleep {WAIT_S}; "
            f"if kill -0 $P 2>/dev/null; then echo running=yes; else echo running=no; fi; "
            f"xwininfo -root -tree > {b}.windows 2>&1; "
            f"ffmpeg -loglevel error -f x11grab -video_size {w}x{h} -i :77 -frames:v 1 -y {b}.png; "
            f"sleep {APART_S}; ffmpeg -loglevel error -f x11grab -video_size {w}x{h} -i :77 -frames:v 1 -y {b}-2.png; "
            f"cp {b}.out {b}.seen 2>/dev/null; "  # what it printed by the picture, not its complaints at the shutdown
            f"kill $P 2>/dev/null; kill $XV 2>/dev/null; wait 2>/dev/null; true")


def page_command(url: str, path: str, screen: tuple[int, int, int], profile: str) -> list[str]:
    """Firefox, headless, in a fresh profile of its own, at the person's screen size."""
    w, h, k = screen
    return ["firefox", "--headless", "--no-remote", "--profile", profile, "--window-size", f"{w // k},{h // k}",
            "--screenshot", path, url]


def screen_command(path: str, screen: tuple[int, int, int], display: str) -> list[str]:
    w, h, _ = screen
    return ["ffmpeg", "-loglevel", "error", "-f", "x11grab", "-video_size", f"{w}x{h}", "-i", display,
            "-frames:v", "1", "-y", path]


def save(root: str, base: str, facts: dict) -> str:
    with open(os.path.join(root, base + ".json"), "w", encoding="utf-8") as f:
        json.dump(facts, f, ensure_ascii=False, indent=1)
    return base + ".json"


def report(facts: dict, problems: list[str], answer: str) -> str:
    """What the coder reads: the facts, the problems code found, and the picture model's answer to the question."""
    s = facts["screen"]
    lines = [f"Looked at {facts['target']} ({facts['picture_path']}; facts in {facts['facts_path']})",
             f"screen {s['width']}x{s['height']} at {s['scale']}x scaling"]
    for w in facts.get("windows", []):
        lines.append(f"window \"{w['name']}\": {w['width']}x{w['height']} at {w['x']},{w['y']}")
    if facts.get("program"):  # the state first, in words (2026-10-09: build output in the middle read as "compiling")
        state = ("UP: running, its window open" if facts.get("running") and facts.get("windows") else
                 "running, with no window" if facts.get("running") else "STOPPED")
        lines.append(f"the program after {WAIT_S} s: {state}" + (
            f". What it printed while starting (its build included; finished): {facts['output'][-400:]}"
            if facts.get("output") else ""))
    if "moved" in facts.get("motion", {}):
        m = facts["motion"]
        lines.append(f"between two pictures {APART_S} s apart: " + (
            "something moved, in {width}x{height} at {x},{y}".format(**m["where"]) if m["moved"] else "nothing moved"))
    lines.append("problems code found: " + ("; ".join(problems) if problems else "none"))
    lines.append(f"the picture model, asked \"{facts['question']}\": {answer}" if answer else
                 "no picture model answered (none here can read pictures, or it wasn't asked)")
    return "\n".join(lines)
