# SPDX-License-Identifier: GPL-3.0-or-later
""""Summarize this video" about the YouTube video open in Firefox (D78; Ian, 2026-10-04, with a cooking video full of
ad breaks: "exactly where a user like me would lose the motivation to watch").

The extension reads what the page shows: the transcript panel and the storyboard — YouTube's own preview pictures,
a small frame every few seconds over the whole video. So nothing is downloaded but those pictures, nothing plays,
and the ads aren't in either. Before this, the guide answered such a request with a web search that recommended
online summarizer sites; never again: the assistant does it here, or says plainly why it can't.
"""

from __future__ import annotations

import io
import json
import os
import re
import urllib.parse
import urllib.request

from . import video

# "summarize this video", "what does this video say", "resume este vídeo", "fasse dieses Video zusammen"… — a video
# named with "this/that", or any video with a verb that only means summing up ("what is a video codec?" isn't one)
VIDEO = re.compile(r"\b(videos?|vídeos?|vidéos?|youtube|clips?)\b|動画|ビデオ", re.I)
THIS_VIDEO = re.compile(r"\b(this|that|este|esta|ese|esa|esse|essa|ce|cette|dieses|diesem|dieser|das)\s+(youtube\s+)?"
                        r"(video|vídeo|vidéo|clip)\b|この動画|このビデオ", re.I)
STRONG = re.compile(r"\b(summari[sz]e|summary|sum (it )?up|recap|tl;?dr|watch (it|this) for me|resum[aei]r?|resumen|resumo|résum[eé]r?|"
                    r"zusammen(fassen|fassung)?|fass)\b|要約|まとめ", re.I)
WEAK = re.compile(r"\b(what|watch|tell me|explain|steps|key points|about|dice|diz|dit|sagt|worum|qu[eé]|o que)\b|何", re.I)
FIREFOX = ("org.cinminai.Firefox", "/org/cinminai/Firefox", "org.cinminai.Firefox")
STORYBOARD_HOSTS = (".ytimg.com",)
MAX_SHEETS = 40  # a long video's storyboard: 40 sheets of 9-25 frames is plenty to choose from


def asks_about_video(text: str) -> bool:
    return bool((THIS_VIDEO.search(text) and (STRONG.search(text) or WEAK.search(text)))
                or (VIDEO.search(text) and STRONG.search(text)))


def from_firefox(timeout_ms: int = 30000) -> dict:
    """What Firefox has open: the extension's reading, or {"error": "no_extension"} when Firefox (or the extension)
    isn't running."""
    try:
        import gi
        gi.require_version("Gio", "2.0")
        from gi.repository import Gio, GLib
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        r = bus.call_sync(FIREFOX[0], FIREFOX[1], FIREFOX[2], "CurrentVideo", None, GLib.VariantType("(s)"),
                          Gio.DBusCallFlags.NO_AUTO_START, timeout_ms, None)
        return json.loads(r.unpack()[0])
    except Exception as e:
        return {"error": "no_extension", "detail": str(e)}


def storyboard_sheets(spec: str, length: float) -> tuple[list[dict], float]:
    """The best level of a storyboard spec: [{"url", "cols", "rows", "w", "h", "first"}], seconds per frame. Spec:
    "BASE|w#h#count#cols#rows#interval_ms#name#sigh|…" — one level per part, the last the largest."""
    parts = spec.split("|")
    if len(parts) < 2:
        return [], 0
    base, level = parts[0], len(parts) - 2
    fields = parts[-1].split("#")
    if len(fields) < 8:
        return [], 0
    w, h, count, cols, rows, interval = (int(x) for x in fields[:6])
    name, sigh = fields[6], fields[7]
    if count <= 0 or cols <= 0 or rows <= 0:
        return [], 0
    step = interval / 1000 if interval > 0 else (length / count if length else 0)
    per = cols * rows
    sheets = []
    for m in range(min(MAX_SHEETS, -(-count // per))):
        url = base.replace("$L", str(level)).replace("$N", name).replace("$M", str(m))
        url += ("&" if "?" in url else "?") + "sigh=" + urllib.parse.quote(sigh, safe="")
        sheets.append({"url": url, "cols": cols, "rows": rows, "w": w, "h": h, "first": m * per,
                       "count": min(per, count - m * per)})
    return sheets, step


def allowed(url: str) -> bool:
    host = urllib.parse.urlparse(url).hostname or ""
    return urllib.parse.urlparse(url).scheme == "https" and host.endswith(STORYBOARD_HOSTS)


def cut(sheet_bytes: bytes, sheet: dict) -> list:
    """The frames of one storyboard sheet, in order (Pillow images)."""
    from PIL import Image
    img = Image.open(io.BytesIO(sheet_bytes)).convert("RGB")
    w, h = img.width // sheet["cols"], img.height // sheet["rows"]
    out = []
    for i in range(sheet["count"]):
        r, c = divmod(i, sheet["cols"])
        out.append(img.crop((c * w, r * h, c * w + w, r * h + h)))
    return out


def changes(frames: list[tuple[float, object]], length: float) -> list[tuple[float, object]]:
    """The frames where the picture changes, at least one every few gaps — the same choice ffmpeg's scene filter
    makes for a file (video.key_frames), on the storyboard's small pictures."""
    from PIL import ImageChops, ImageStat
    k = video.SHORT if length < 300 else video.LONG
    kept, last, last_t = [], None, -1e9
    for t, im in frames:
        small = im.convert("L").resize((32, 18))
        diff = ImageStat.Stat(ImageChops.difference(small, last)).mean[0] if last is not None else 255
        if (diff > 18 and t - last_t >= k["gap"]) or t - last_t >= 3 * k["gap"]:
            kept.append((t, im))
            last, last_t = small, t
    if len(kept) > k["max"]:
        keep = sorted({round(i * (len(kept) - 1) / (k["max"] - 1)) for i in range(k["max"])})
        kept = [kept[i] for i in keep]
    return kept


def key_frames(info: dict, work: str, fetch=None) -> list[tuple[float, str]]:
    """[(time, jpeg path)] from the storyboard, like video.key_frames for a file."""
    fetch = fetch or (lambda url: urllib.request.urlopen(urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0"}),
        timeout=30).read())
    length = float(info.get("length") or 0)
    sheets, step = storyboard_sheets(info.get("storyboard", ""), length)
    frames = []
    for sheet in sheets:
        if not allowed(sheet["url"]):
            continue
        try:
            data = fetch(sheet["url"])
        except Exception:
            continue  # a missing sheet: the others still tell the story
        for i, im in enumerate(cut(data, sheet)):
            frames.append(((sheet["first"] + i) * step, im))
    out = []
    os.makedirs(os.path.join(work, "frames"), exist_ok=True)
    for n, (t, im) in enumerate(changes(frames, length)):
        path = os.path.join(work, "frames", f"s{n:04d}.jpg")
        im.save(path, "JPEG", quality=92)
        out.append((t, path))
    return out


def lines(info: dict) -> list[tuple[float, str]]:
    out = []
    for item in info.get("transcript") or []:
        try:
            t, text = float(item[0]), str(item[1]).strip()
        except (TypeError, ValueError, IndexError):
            continue
        if text and not re.fullmatch(r"\[.*\]|\(.*\)", text):
            out.append((t, text))
    return out


def problem(info: dict) -> str | None:
    """Why it can't be done, in plain words — or None."""
    err = info.get("error")
    if err == "no_extension":
        return ("I can summarize a YouTube video that's open in Firefox, but I can't reach Firefox right now. Open the "
                "video in Firefox and ask again. A video file on this computer works too: drop it on me or use the "
                "picture button.")
    if err == "no_video":
        return ("The tab in front in Firefox isn't a YouTube video. Open the video there (or bring its tab to the "
                "front) and ask again. A video file on this computer works too: drop it on me.")
    if err:
        return "I couldn't read the video's page in Firefox. Reload the page and ask again."
    if info.get("live"):
        return "That's a live stream: there's no whole video to summarize yet. Ask again once it has ended."
    if not info.get("transcript") and not info.get("storyboard"):
        return "This video has neither a transcript nor preview pictures I can read, so I can't summarize it here."
    return None
