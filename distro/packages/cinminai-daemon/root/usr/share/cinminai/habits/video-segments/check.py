#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""video-segments' check: segments in time order inside the video's length, none empty, and the speech reaching most of
the video (a transcript that stops early is said: whisper can lose the rest of a long file)."""

import json
import sys


def main() -> int:
    with open(sys.argv[1], encoding="utf-8") as f:
        data = json.load(f)
    found, bad = [], False
    segs, length = data.get("segments") or [], float(data.get("duration") or 0)
    starts = [float(s.get("start", 0)) for s in segs]
    if starts != sorted(starts):
        found.append("the segments aren't in time order")
        bad = True
    if length and any(t > length + 1 for t in starts):
        found.append("a segment starts after the video ends")
        bad = True
    if any(not str(s.get("text", "")).strip() for s in segs):
        found.append("an empty segment")
        bad = True
    if not segs:
        found.append("no speech found (no sound track, or nothing said)")
    elif length > 120 and starts[-1] < 0.5 * length:
        found.append(f"the speech stops at {int(starts[-1])} s of {int(length)} s: check the end was heard")
    found.append(f"{len(segs)} segments over {int(length)} s")
    print(json.dumps(found))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
