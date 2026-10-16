# SPDX-License-Identifier: GPL-3.0-or-later
"""Where Cin-MinAI is reaching right now: the LOCAL / WEB / CLOUD indicator's source (PLAN D35: "a CLOUD state in the
LOCAL/WEB indicator"; D28: what this computer sent).

Every request out of the daemon or AICUI goes through Python's opener; install() wraps it, so each one is marked while
it's out (and for a few seconds after, so a person can see it): to a cloud model's API it's CLOUD, anything else on
the internet is WEB. The models on this computer talk over local sockets and never count. The few ways out that don't
use the opener (our own search's process, git to GitHub) mark themselves with out(). Marks are small files in the
user's runtime folder (gone at logout), read by the panel icon; each one is also a line in the local record of what
was sent where (~/.local/state/cinminai/sent.jsonl) — never what was in it.
"""

from __future__ import annotations

import contextlib
import itertools
import json
import os
import time
import urllib.parse
import urllib.request

HOLD_S = 8.0       # a mark stays this long after the request ends, so it's seen
OPEN_S = 600.0     # a request still out is marked this long at most (a process that died leaves no lasting mark)
CLOUD_HOSTS = {"api.anthropic.com": "Anthropic", "api.openai.com": "OpenAI"}
_n = itertools.count(1)
_installed: list = []


def folder() -> str:
    base = os.environ.get("XDG_RUNTIME_DIR") or f"/tmp/cinminai-{os.getuid()}"
    return os.path.join(base, "cinminai", "reach")


def record_path() -> str:
    base = os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state")
    return os.path.join(base, "cinminai", "sent.jsonl")


def kind_of(url: str) -> tuple[str, str]:
    """("cloud", "OpenAI") for a cloud model's API, else ("web", the host)."""
    host = (urllib.parse.urlsplit(url).hostname or "").lower()
    return ("cloud", CLOUD_HOSTS[host]) if host in CLOUD_HOSTS else ("web", host or url[:60])


def _write(path: str, data: dict) -> None:
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path + ".tmp", "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(path + ".tmp", path)
    except OSError:
        pass


def begin(kind: str, to: str) -> tuple[str, dict]:
    """A mark for a request going out now (and its line in the record); end() it when the answer's read."""
    path = os.path.join(folder(), f"{os.getpid()}-{next(_n)}.json")
    mark = {"kind": kind, "to": to, "since": time.time()}
    _write(path, {**mark, "until": mark["since"] + OPEN_S})
    try:
        rec = record_path()
        os.makedirs(os.path.dirname(rec), exist_ok=True)
        with open(rec, "a", encoding="utf-8") as f:
            f.write(json.dumps({"time": time.strftime("%Y-%m-%dT%H:%M:%S"), "kind": kind, "to": to}) + "\n")
    except OSError:
        pass
    return path, mark


def end(path: str, mark: dict) -> None:
    _write(path, {**mark, "until": time.time() + HOLD_S})
    tidy()


@contextlib.contextmanager
def out(kind: str, to: str):
    """Marked while the block runs, and HOLD_S after; one line in the record of what was sent where."""
    path, mark = begin(kind, to)
    try:
        yield
    finally:
        end(path, mark)


def active(now: float | None = None) -> list[dict]:
    """The marks in force: [{"kind", "to", ...}], cloud first."""
    now = now or time.time()
    got = []
    try:
        names = os.listdir(folder())
    except OSError:
        return []
    for name in names:
        if not name.endswith(".json"):
            continue
        try:
            with open(os.path.join(folder(), name), encoding="utf-8") as f:
                m = json.load(f)
        except (OSError, ValueError):
            continue
        if float(m.get("until", 0)) > now:
            got.append(m)
    return sorted(got, key=lambda m: m.get("kind") != "cloud")


def tidy(now: float | None = None) -> None:
    """Marks long past go (the folder stays small)."""
    now = now or time.time()
    try:
        for name in os.listdir(folder()):
            p = os.path.join(folder(), name)
            try:
                with open(p, encoding="utf-8") as f:
                    until = float(json.load(f).get("until", 0))
            except (OSError, ValueError):
                until = 0
            if until < now - 60:
                os.remove(p)
    except OSError:
        pass


def install() -> None:
    """Every request through Python's opener (urlopen, and the openers passed around as it) is marked."""
    if _installed:
        return
    opener = urllib.request.build_opener()
    plain = opener.open

    def marked(url, data=None, timeout=None, **kw):
        full = url if isinstance(url, str) else url.full_url
        path, mark = begin(*kind_of(full))
        try:
            r = plain(url, data, **kw) if timeout is None else plain(url, data, timeout, **kw)
        except BaseException:
            end(path, mark)
            raise
        close, read, done = r.close, r.read, []

        def finish():
            if not done:
                done.append(1)
                end(path, mark)

        def closed():  # the mark lasts until the answer is read and closed (a model download takes minutes)
            try:
                close()
            finally:
                finish()

        def reading(*a, **k):  # read() to the end (or an empty read) ends it too, closed or not
            data = read(*a, **k)
            if not (a or k) or not data:
                finish()
            return data
        r.close, r.read = closed, reading
        return r
    opener.open = marked
    urllib.request.install_opener(opener)
    _installed.append(opener)
