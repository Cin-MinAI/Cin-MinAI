# SPDX-License-Identifier: GPL-3.0-or-later
"""Standing tasks (PLAN D88): things the assistant keeps doing once the person has set them up — first, news watches
(D92: "keep me up to date on Pfizer patents").

* Set up once, by the person, on a card that says what is sent, to whom and how often (D86): that click is the
  consent for every scheduled run. Listed in one place (what, when, last result), paused or deleted there.
* A watch runs the news scan (press, social, official) once a day at its time and reports **only what's new**: an item
  is new when its address hasn't been shown for this watch before. The first run, at setup, shows everything and is
  the starting point.
* Each run is kept with the task (when, what was sent where, how many new, any trouble): the last RUNS of them.
* The file is ~/.local/share/cinminai/standing.json; nothing in it is secret (keys live in the keyring, keys.py).
"""

from __future__ import annotations

import datetime as dt
import json
import os
import tempfile
import threading
import uuid

SEEN = 400   # addresses remembered per watch
RUNS = 30    # runs kept per watch


def path() -> str:
    base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return os.path.join(base, "cinminai", "standing.json")


class Store:
    def __init__(self, file: str | None = None) -> None:
        self.file = file or path()
        self.lock = threading.Lock()
        self.tasks: list[dict] = []
        try:
            with open(self.file, encoding="utf-8") as f:
                self.tasks = json.load(f).get("tasks", [])
        except (OSError, ValueError):
            self.tasks = []

    def save(self) -> None:
        os.makedirs(os.path.dirname(self.file), exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(self.file), prefix=".standing.")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"version": 1, "tasks": self.tasks}, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self.file)

    def add(self, topic: str, at: str, lang: str, now: dt.datetime, only: str = "") -> dict:
        task = {"id": uuid.uuid4().hex[:10], "kind": "news", "topic": topic, "only": only, "every": "day", "at": at,
                "lang": lang,
                "created": now.isoformat(timespec="minutes"), "paused": False, "last_run": "", "last_new": 0,
                "last_report": "", "seen": [], "runs": []}
        with self.lock:
            self.tasks.append(task)
            self.save()
        return task

    def get(self, tid: str) -> dict | None:
        return next((t for t in self.tasks if t["id"] == tid), None)

    def change(self, tid: str, what: str) -> dict | None:
        """pause | resume | delete; returns the task (None when there's no such task)."""
        if what not in ("pause", "resume", "delete"):
            raise ValueError(what)
        with self.lock:
            task = self.get(tid)
            if task is None:
                return None
            if what == "delete":
                self.tasks.remove(task)
            else:
                task["paused"] = what == "pause"
            self.save()
            return task

    def due(self, now: dt.datetime) -> list[dict]:
        """Tasks whose time has come today and that haven't run since. A computer that was off at 8:00 runs the
        watch when it's next on (once, not once per missed day)."""
        out = []
        for t in self.tasks:
            if t["paused"]:
                continue
            h, m = (int(x) for x in t["at"].split(":"))
            slot = now.replace(hour=h, minute=m, second=0, microsecond=0)
            if now < slot:
                slot -= dt.timedelta(days=1)
            last = dt.datetime.fromisoformat(t["last_run"]) if t["last_run"] else None
            if last is None or last < slot:
                out.append(t)
        return out

    def fresh(self, task: dict, items: list[dict]) -> list[dict]:
        """The items this watch hasn't shown before (by address, else by title)."""
        seen = set(task["seen"])
        return [it for it in items if (it.get("url") or it.get("title")) not in seen]

    def ran(self, tid: str, now: dt.datetime, shown: list[dict], sent_to: str, report: str, trouble: str = "") -> None:
        with self.lock:
            task = self.get(tid)
            if task is None:  # deleted while it ran
                return
            task["seen"] = (task["seen"] + [it.get("url") or it.get("title") for it in shown])[-SEEN:]
            task["last_run"] = now.isoformat(timespec="minutes")
            task["last_new"] = len(shown)
            if shown:
                task["last_report"] = report
            task["runs"] = (task["runs"] + [{"at": task["last_run"], "sent_to": sent_to, "new": len(shown),
                                             **({"trouble": trouble} if trouble else {})}])[-RUNS:]
            self.save()

    def listing(self) -> list[dict]:
        """For the list in the sidebar: everything but the remembered addresses."""
        return [{k: v for k, v in t.items() if k != "seen"} for t in self.tasks]
