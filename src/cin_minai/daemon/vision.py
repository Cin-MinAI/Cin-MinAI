# SPDX-License-Identifier: GPL-3.0-or-later
"""The assistant reads pictures (D64, D78): a photo, a screenshot, a scanned letter — from the lab's scripts
(spikes/vision/, measured 2026-10-03 on the 1080 Ti) made a part of the daemon.

The best model the person has reads it: the 27B when it's downloaded (recommended), otherwise the built-in guide
(it works; quality not guaranteed — its projector is the untuned base model's). Each needs its projector, fetched
like any model (pinned, checksummed: matcher.PROJECTORS). The model is loaded with the projector for the picture
and unloaded after, so the guide comes back; the projector runs on the processor, so the model keeps the card.
"""

from __future__ import annotations

import base64
import io
import mimetypes
import os
import re

# the person's request, then these (the lab's round 2: they stopped guessed numbers and invented letters)
# 2026-10-04: the 27B read a 640x480 letter's gas emergency number wrong and added "Confidence: 100%"; three readings
# of the same photo gave six different phone numbers. Numbers from a picture are never presented as certain.
RULES = ("Answer the request first, in plain words, in the language of the request. Phone numbers, amounts, dates, "
         "account numbers and web addresses read from a picture: copy them as you see them and put (check the "
         "original) after each one — small digits in a photo are easy to misread. Never give a confidence "
         "percentage and never say you're sure of numbers. Never guess text, numbers, barcodes or brands you can't "
         "actually read: say what you can't see. If you count things, give the number and how sure you are. If it's "
         "a document (a letter, a bill, a form), say what it is, what it says, and what the reader has to do and by "
         "when.")
SAMPLING = {"temperature": 0, "repeat_penalty": 1.05, "dry_multiplier": 0.8, "dry_base": 1.75,
            "dry_allowed_length": 3, "dry_penalty_last_n": 1024}  # the lab: both models looped at temperature 0
LONG_SIDE = 1600  # bigger photos are scaled down: the lab's 27B read a letter at this size; more costs minutes
IMAGES = (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tif", ".tiff")


def picture(path: str) -> tuple[str, str]:
    """(mime type, base64) of the picture as a viewer shows it: phone photos are often stored sideways with a
    rotation tag that llama.cpp ignores (the lab got a letter turned 90°), and big photos are scaled down. With
    GdkPixbuf, which Mint ships."""
    try:
        import gi
        gi.require_version("GdkPixbuf", "2.0")
        from gi.repository import GdkPixbuf
        pb = GdkPixbuf.Pixbuf.new_from_file(path).apply_embedded_orientation()
        w, h = pb.get_width(), pb.get_height()
        if max(w, h) > LONG_SIDE:
            f = LONG_SIDE / max(w, h)
            pb = pb.scale_simple(max(1, round(w * f)), max(1, round(h * f)), GdkPixbuf.InterpType.HYPER)
        if pb.get_has_alpha():  # JPEG has no transparency: flatten onto white
            flat = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, False, 8, pb.get_width(), pb.get_height())
            flat.fill(0xFFFFFFFF)
            pb.composite(flat, 0, 0, pb.get_width(), pb.get_height(), 0, 0, 1, 1, GdkPixbuf.InterpType.NEAREST, 255)
            pb = flat
        ok, data = pb.save_to_bufferv("jpeg", ["quality"], ["92"])
        return "image/jpeg", base64.b64encode(data).decode()
    except Exception:  # no GdkPixbuf, or a format it can't read: send the file as it is
        with open(path, "rb") as f:
            return mimetypes.guess_type(path)[0] or "image/jpeg", base64.b64encode(f.read()).decode()


def choose(store, inference_cfg: dict) -> dict:
    """Which model reads pictures here, and what's missing. {"model", "file", "path", "plan", "projector": Model,
    "projector_ready": bool, "recommended": bool} — the 27B if it's downloaded and runs here, else the guide."""
    from cin_minai.inference import matcher
    machine = matcher.read_machine(models_dir=store.root)
    # the desktop's share of the card as measured here (200 MiB when it's drawn by the board's graphics), as AICUI
    # passes it — without it the backend kept its 1.5 GB default and put the 27B on the processor (2026-10-04: 9 min)
    reserve = matcher.margin_mib(machine.cards[0]) if machine.cards else 0
    for m in matcher.CATALOG["coding"]:
        if m.file in matcher.PROJECTORS and store.has(m.file):
            plan = matcher.vision_plan(m, machine)
            if plan:
                plan = dict(plan, reserve_mib=reserve)
                proj = matcher.PROJECTORS[m.file]
                return {"model": m.name, "file": m.file, "path": store.path(m.file), "plan": plan, "projector": proj,
                        "projector_ready": store.has(proj.file), "recommended": True}
    guide = matcher.CATALOG["help"][0]
    proj = matcher.PROJECTORS[guide.file]
    return {"model": "the built-in guide", "file": guide.file, "path": inference_cfg.get("model", ""),
            "plan": dict(matcher.vision_plan(guide, machine) or {}, reserve_mib=reserve), "projector": proj,
            "projector_ready": store.has(proj.file), "recommended": False}


def backend_settings(choice: dict, store, inference_cfg: dict) -> dict:
    """LlamaCppBackend settings: the chosen model with its projector (on the processor), at the vision context."""
    from cin_minai.inference import matcher
    from .models import backend_cfg
    plan = dict(choice["plan"] or {}, context=matcher.VISION_CONTEXT)
    cfg = backend_cfg(inference_cfg, plan, choice["path"])
    cfg["extra_args"] = list(cfg.get("extra_args", [])) + ["--mmproj", store.path(choice["projector"].file),
                                                          "--no-mmproj-offload"]
    cfg["socket_name"] = "llama-vision.sock"
    cfg["model_name"] = choice["model"]
    return cfg


# "find the … in this picture" (Ian, 2026-10-04: "a Ctrl+F for images"), in the six languages (D25)
FIND = re.compile(r"\b(find|where|where's|locate|spot|search|dónde|donde|encuentra|busca|onde|encontre|procure|ache|"
                  r"où|trouve|cherche|wo|finde|suche)\b|どこ|探", re.I)
PLACES = 4
CLOSE_UP = 448  # a place is shown at least this big, so a small figure in a crowd has pixels to be read from


def places(path: str, request: str) -> list[dict]:
    """For "find the man in the red and white shirt": the places in the picture where those colours meet, found in
    a tenth of a second (colorfind, the practical part of Ian's Color Frame), each as a close-up the model can look
    at: [{"where": "bottom right", "box": (…), "mime", "data"}]. None when the request isn't a search by colour,
    or Pillow can't read the picture."""
    from . import colorfind
    names = colorfind.colours_in(request)
    if not names or not FIND.search(request):
        return []
    try:
        from PIL import Image, ImageOps
        with Image.open(path) as raw:
            img = ImageOps.exif_transpose(raw).convert("RGB")
    except Exception:
        return []
    out = []
    for c in colorfind.candidates(img, names, top=PLACES):
        crop = img.crop(c["box"])
        if max(crop.size) < CLOSE_UP:
            f = CLOSE_UP / max(crop.size)
            crop = crop.resize((round(crop.width * f), round(crop.height * f)), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        crop.save(buf, "JPEG", quality=92)
        out.append({"where": colorfind.where(c["box"], img.size), "box": c["box"], "mime": "image/jpeg",
                    "data": base64.b64encode(buf.getvalue()).decode()})
    return out


def messages(path: str, request: str, close_ups: list[dict] | None = None) -> list[dict]:
    mime, data = picture(path)
    content = [{"type": "image_url", "image_url": {"url": f"data:{mime};base64,{data}"}}]
    text = request.strip() or "What is in this picture?"
    if close_ups:
        for c in close_ups:
            content.append({"type": "image_url", "image_url": {"url": f"data:{c['mime']};base64,{c['data']}"}})
        text += ("\n\nAfter the whole picture come close-ups of the places where the colours asked for meet, in "
                 "order: " + "; ".join(f"place {i} ({c['where']})" for i, c in enumerate(close_ups, 1)) + ". Look "
                 "at each and say which one shows what was asked for and where it is in the whole picture, or that "
                 "none of them does — then look in the whole picture yourself.")
    content.append({"type": "text", "text": f"{text}\n\n{RULES}"})
    return [{"role": "user", "content": content}]
