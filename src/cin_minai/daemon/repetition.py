# SPDX-License-Identifier: GPL-3.0-or-later
"""Detect and repair a reply that has fallen into a short generation loop."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Callable, Iterable


@dataclass(frozen=True)
class Repeat:
    piece: str
    starts: tuple[int, ...]  # offsets in the original, unnormalised reply


def _flat(text: str, names: Iterable[str]) -> tuple[str, list[int]]:
    """Collapse whitespace and names while retaining a map back to ``text``."""
    chars: list[str] = []
    offsets: list[int] = []
    for match in re.finditer(r"\S+|\s+", text):
        token = match.group()
        if token.isspace():
            if chars and chars[-1] != " ":
                chars.append(" ")
                offsets.append(match.start())
        else:
            chars.extend(token)
            offsets.extend(range(match.start(), match.end()))
    flat = "".join(chars)
    for name in sorted((n for n in names if n and len(n) >= 4), key=len, reverse=True):
        start = 0
        while (at := flat.find(name, start)) >= 0:
            flat = flat[:at] + "§" + flat[at + len(name):]
            offsets[at:at + len(name)] = [offsets[at]]
            start = at + 1
    return flat, offsets


def find_repeat(text: str, length: int = 24, times: int = 3, names: Iterable[str] = ()) -> Repeat | None:
    """Return the first fixed-length stretch repeated non-overlapping ``times`` times.

    This deliberately has the evaluator's old threshold and ordering.  Product and
    benchmark therefore agree on what constitutes a loop.
    """
    flat, offsets = _flat(text, names)
    for i in range(0, max(0, len(flat) - length * times + 1)):
        piece = flat[i:i + length]
        if not piece.strip():
            continue
        found = [i]
        after = i + length
        while len(found) < times:
            at = flat.find(piece, after)
            if at < 0:
                break
            found.append(at)
            after = at + length
        if len(found) == times:
            return Repeat(piece, tuple(offsets[p] for p in found))
    return None


def trim_repeat(text: str, repeat: Repeat) -> str:
    """Keep the complete reply through the sentence before its first duplication."""
    cutoff = repeat.starts[1]
    prefix = text[:cutoff]
    # A list marker such as ``3.`` is not a complete sentence.
    ends = list(re.finditer(r"(?<!\d)[.!?。！？](?:[\"'’”»）\]]*)", prefix))
    if ends:
        return prefix[:ends[-1].end()].rstrip()
    return prefix.rstrip(" \t\r\n,;:、，；：-")


def repair(text: str, names: Iterable[str] = ()) -> tuple[str, Repeat | None]:
    repeat = find_repeat(text, names=names)
    return (trim_repeat(text, repeat), repeat) if repeat else (text, None)


class LoopDetected(Exception):
    def __init__(self, reply: str, repeat: Repeat) -> None:
        super().__init__(f"reply repeated {repeat.piece!r}")
        self.reply, self.repeat = reply, repeat


class PointCap:
    """Stops a numbered list after `limit` points (the news briefing, D91: asked for three to five, the 4B wrote twenty).
    The stream is cut as the next point begins; what was shown is replaced by the points kept."""

    START = re.compile(r"(?:^|\n)\s*(?:\*\*)?(\d{1,2})[.)．]")

    def __init__(self, emit: Callable[[str], None], limit: int = 5,
                 replace: Callable[[str], None] | None = None) -> None:
        self.emit, self.limit, self.text, self.replace = emit, limit, "", replace

    def feed(self, piece: str) -> None:
        self.text += piece
        over = next((m for m in self.START.finditer(self.text) if int(m.group(1)) > self.limit), None)
        if over is None:
            self.emit(piece)
            return
        kept = self.text[:over.start()].rstrip()
        if self.replace is not None:
            self.replace(kept)
        raise LoopDetected(kept, Repeat(f"point {over.group(1)}", (over.start(),)))


class ReplyGuard:
    """A streaming callback which aborts generation once a loop is established."""

    def __init__(self, emit: Callable[[str], None], names: Iterable[str] = ()) -> None:
        self.emit, self.names, self.text = emit, tuple(names), ""
        self.next_check = 72  # the earliest possible 24-character x3 match

    def feed(self, piece: str) -> None:
        self.text += piece
        self.emit(piece)
        if len(self.text) < self.next_check:
            return
        self.next_check = len(self.text) + 24
        self._check()

    def finish(self) -> None:
        """Check the final sub-24-character tail after a backend completes normally."""
        self._check()

    def _check(self) -> None:
        fixed, repeat = repair(self.text, self.names)
        if repeat is not None:
            replace = getattr(self.emit, "replace", None)
            if replace is not None:
                replace(fixed)
            raise LoopDetected(fixed, repeat)
