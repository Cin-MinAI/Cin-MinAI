# SPDX-License-Identifier: GPL-3.0-or-later
"""Chains of actions (PLAN D91): "pull up X and do Y" as fixed recipes the daemon runs step by step.

The steps are code, so a chain runs the same way every time; the request is recognized by rules (intent.py) and the
model only ever fills in blanks. Every step is shown (the Action signal) and recorded where it changes something or
sends something out; Cancel stops the chain between steps; a search goes out only after the person's Search click
(D86). This module holds the steps that don't need the daemon's state; the daemon (service.py) strings them together.

Recipe "video review" (first, 2026-10-07): search YouTube for the topic -> list the videos -> open the first in Firefox
-> wait until our extension reports that video -> summarize it (D78's path) if the person asked for a summary.
"""

from __future__ import annotations

import re
import subprocess
import threading
import time
from typing import Callable

WATCH = re.compile(r"^https://(?:www\.|m\.)?youtube\.com/watch\?(?:[^#]*&)?v=([\w-]{11})|^https://youtu\.be/([\w-]{11})")


def video_query(topic: str) -> str:
    return f"{topic} site:youtube.com"


def youtube_videos(results: list[dict]) -> list[dict]:
    """The YouTube videos among search results, in order, once each: [{"id", "title", "url"}]."""
    out, seen = [], set()
    for r in results:
        m = WATCH.match(r.get("url", ""))
        if not m:
            continue  # channels, playlists, shorts pages, other sites
        vid = m.group(1) or m.group(2)
        if vid in seen:
            continue
        seen.add(vid)
        title = re.sub(r"\s*-\s*YouTube\s*$", "", r.get("title", "")).strip() or "a YouTube video"
        out.append({"id": vid, "title": title, "url": f"https://www.youtube.com/watch?v={vid}"})
    return out


def open_in_firefox(url: str) -> None:
    """Our extension lives in Firefox, so the video opens there (not just the default browser)."""
    subprocess.Popen(["firefox", "--new-tab", url], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True)


def wait_for_video(video_id: str, cancel: threading.Event, read: Callable[..., dict], timeout: float = 45,
                   poll: float = 1.5) -> dict | None:
    """Our extension's reading of Firefox's front tab once it is this video and has something to read (transcript or
    storyboard); None if that doesn't happen in time or the person cancels. Firefox may still be starting."""
    end = time.monotonic() + timeout
    while time.monotonic() < end and not cancel.is_set():
        info = read(timeout_ms=3000)
        if info.get("id") == video_id and (info.get("transcript") or info.get("storyboard") or info.get("live")):
            return info
        cancel.wait(poll)
    return None
