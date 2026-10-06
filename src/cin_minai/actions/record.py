# SPDX-License-Identifier: GPL-3.0-or-later
"""The record (PLAN D67 R, SPEC §8.4): every action the assistant proposes, every answer, every result and undo, in
order, append-only. Each line carries a link — the hash of the previous link and this line — so the record checks
as whole and untampered. A torn last line (a crash mid-write) is set aside in `<record>.torn`, never dropped.

What it keeps is what happened, not the person's content: action names, paths, sizes, hashes, short summaries. The
journal's sealed entries, passwords and document text never go in.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time

GENESIS = "0" * 24


def default_path() -> str:
    base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return os.path.join(base, "cinminai", "record", "actions.jsonl")


def _link(prev: str, payload: str) -> str:
    return hashlib.blake2b((prev + payload).encode(), digest_size=12).hexdigest()


def _payload(entry: dict) -> str:
    return json.dumps(entry, separators=(",", ":"), sort_keys=True, ensure_ascii=False)


class RecordError(ValueError):
    pass


class Record:
    def __init__(self, path: str | None = None):
        self.path = path or default_path()
        self.last_link = GENESIS
        self.seq = 0
        self.torn: str | None = None
        self._lock = threading.Lock()
        os.makedirs(os.path.dirname(self.path), mode=0o700, exist_ok=True)
        self.entries: list[dict] = self._load()

    def _load(self) -> list[dict]:
        if not os.path.exists(self.path):
            return []
        with open(self.path, "rb") as f:
            data = f.read()
        lines = data.split(b"\n")
        tail = lines.pop()
        out = []
        prev = GENESIS
        for n, raw in enumerate(lines, 1):
            entry = json.loads(raw)
            link = entry.pop("link")
            if _link(prev, _payload(entry)) != link:
                raise RecordError(f"the record was changed at line {n}")
            prev = link
            out.append(entry)
        if tail:
            self.torn = tail.decode(errors="replace")
            with open(self.path + ".torn", "ab") as t:
                t.write(tail + b"\n")
            with open(self.path, "r+b") as f:
                f.truncate(len(data) - len(tail))
        self.last_link = prev
        self.seq = out[-1]["seq"] if out else 0
        return out

    def add(self, event: str, **fields) -> dict:
        with self._lock:
            self.seq += 1
            entry = {"seq": self.seq, "t": round(time.time(), 3), "event": event, **fields}
            payload = _payload(entry)
            self.last_link = _link(self.last_link, payload)
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(payload[:-1] + f',"link":"{self.last_link}"}}\n')
                f.flush()
                os.fsync(f.fileno())
            self.entries.append(entry)
            return entry

    def verify(self) -> int:
        """Re-check the whole record on disk; returns the number of entries."""
        return len(Record(self.path).entries)

    def of(self, action_id: str) -> list[dict]:
        return [e for e in self.entries if e.get("id") == action_id]

    def recent(self, n: int = 50) -> list[dict]:
        return self.entries[-n:]
