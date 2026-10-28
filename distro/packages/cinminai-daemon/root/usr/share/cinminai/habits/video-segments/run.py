#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""video-segments: a video's speech as timed segments, through the assistant's own pipeline (ffmpeg, then whisper with
the speech model the Models view downloads)."""

import json
import sys

from cin_minai.daemon import video
from cin_minai.daemon.models import ModelStore


def main() -> int:
    with open(sys.argv[1], encoding="utf-8") as f:
        path = json.load(f).get("path", "")
    store = ModelStore()
    if not store.has(video.WHISPER.file):
        print("the speech model (whisper small) isn't on this computer yet: download it in the Models view")
        return 1
    length = video.duration(path)
    work = video.workdir()
    try:
        lines = video.transcript(path, work, store.path(video.WHISPER.file))
    finally:
        video.cleanup(work)
    segments = [{"start": round(t, 2), "text": text} for t, text in lines]
    with open(sys.argv[2], "w", encoding="utf-8") as f:
        json.dump({"source": path, "duration": round(length, 2), "segments": segments}, f, ensure_ascii=False,
                  indent=1)
    print(f"{len(segments)} segments over {video.hms(length)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
