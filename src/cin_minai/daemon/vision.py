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
import mimetypes
import os

# the person's request, then these (the lab's round 2: they stopped guessed numbers and invented letters)
RULES = ("Answer the request first, in plain words, in the language of the request. Any number, date, phone number, "
         "code or web address you read from the picture: copy it exactly if it's clear; if it's small or blurry, "
         "write it followed by (verify), or say it's too small to read. Never guess text, numbers, barcodes or "
         "brands you can't actually read: say what you can't see. If you count things, give the number and say how "
         "sure you are. If it's a document (a letter, a bill, a form), say what it is, what it says, and what the "
         "reader has to do and by when.")
SAMPLING = {"temperature": 0, "repeat_penalty": 1.05, "dry_multiplier": 0.8, "dry_base": 1.75,
            "dry_allowed_length": 3, "dry_penalty_last_n": 1024}  # the lab: both models looped at temperature 0
LONG_SIDE = 1600  # bigger photos are scaled down: the lab's 27B read a letter at this size; more costs minutes
IMAGES = (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tif", ".tiff")


def picture(path: str) -> tuple[str, str]:
    """(mime type, base64) of the picture as a viewer shows it: phone photos are often stored sideways with a
    rotation tag that llama.cpp ignores (the lab got a letter turned 90°), and big photos are scaled down. With
    GdkPixbuf, which Mint ships (Pillow and ffmpeg aren't on its image)."""
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
    for m in matcher.CATALOG["coding"]:
        if m.file in matcher.PROJECTORS and store.has(m.file):
            plan = matcher.vision_plan(m, machine)
            if plan:
                proj = matcher.PROJECTORS[m.file]
                return {"model": m.name, "file": m.file, "path": store.path(m.file), "plan": plan, "projector": proj,
                        "projector_ready": store.has(proj.file), "recommended": True}
    guide = matcher.CATALOG["help"][0]
    proj = matcher.PROJECTORS[guide.file]
    return {"model": "the built-in guide", "file": guide.file, "path": inference_cfg.get("model", ""),
            "plan": matcher.vision_plan(guide, machine) or {}, "projector": proj,
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


def messages(path: str, request: str) -> list[dict]:
    mime, data = picture(path)
    return [{"role": "user", "content": [
        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{data}"}},
        {"type": "text", "text": f"{request.strip() or 'What is in this picture?'}\n\n{RULES}"}]}]
