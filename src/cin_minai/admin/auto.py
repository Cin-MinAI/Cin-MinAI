# SPDX-License-Identifier: GPL-3.0-or-later
"""The daily update run (PLAN D89; Ian, 2026-10-22: our own timer rather than Mint's automatic updates, whose updater
re-checks the servers after any step in front of it, so a version published in between would skip the wait).

cinminai-updates-auto.timer starts it once a day. With the wait or automatic updates on, it checks (the same check as
the Updates window: signatures, apt's plan, when each version was first seen, the holds); with automatic updates on,
it installs the updates nothing holds (a security fix confirmed early by Debian's security team among them, and
first when it's on CISA's list: D89's emergency path), through the same steps as the window (snapshot when Timeshift is set up,
download, every file's fingerprint, install, the check afterwards). Not on battery. What it did goes to the admin
record (hash-chained) and to a status file the person's session reads: cinminai-updates --notices says what needs
them (an install that stopped, a restart, a source that couldn't be proven genuine, a held security fix on CISA's
list, an update held for an alarming post on oss-security), once each.

    /usr/libexec/cinminai/cinminai-updates-auto      (root, from the timer)
"""

from __future__ import annotations

import datetime
import glob
import json
import os
import sys
import time

from . import updates


def on_battery(base: str = "/sys/class/power_supply") -> bool:
    """A computer with mains power that isn't plugged in (Mint's automatic updates wait for the cable too)."""
    mains = [d for d in glob.glob(os.path.join(base, "*")) if _read(os.path.join(d, "type")) == "Mains"]
    return bool(mains) and not any(_read(os.path.join(d, "online")) == "1" for d in mains)


def _read(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def run_once(run, changelog, now: float | None = None, settings_path: str = updates.SETTINGS,
             status_path: str = updates.STATUS, check=updates.check, install=updates.install,
             battery=on_battery, audit=None, lock=updates.exclusive) -> dict | None:
    """One daily run; returns the status written (None when the wait and automatic updates are both off)."""
    now = now or time.time()
    settings = updates.load_settings(settings_path)
    if not settings["auto"] and not settings["hold_days"]:
        return None
    status = {"ts": now, "auto": settings["auto"], "installed": [], "held": [], "kev": [], "early": [], "flagged": [], "steps": [],
              "error": "", "signature": [], "restart": False}
    try:
        with lock():
            try:
                result = check(run, changelog, now)
            except RuntimeError as e:
                try:
                    status["signature"] = json.loads(str(e)).get("signature", [])
                except ValueError:
                    pass
                status["error"] = "check"
                status["detail"] = str(e)[-300:]
                result = None
            if result:
                status["held"] = [{k: u.get(k) for k in ("name", "version", "held", "ready", "security", "kev")}
                                  for u in result["updates"] if u["held"]]
                status["kev"] = [{"name": u["name"], "version": u["version"], "cves": u["kev"]}
                                 for u in result["updates"] if u.get("kev")]
                status["flagged"] = [{"name": u["name"], "version": u["version"], "title": u["flags"][-1]["title"],
                                      "url": u["flags"][-1]["url"]} for u in result["updates"] if u["held"] == "flagged"]
                go = [u for u in result["updates"] if not u["held"]]
                status["early"] = [{"name": u["name"], "version": u["version"], "why": u["early"],
                                    "cves": u.get("confirmed", [])} for u in go if u.get("early")]
                if settings["auto"] and go and battery():
                    status["error"] = "battery"
                elif settings["auto"] and go:
                    def emit(_job, step, state, detail):
                        status["steps"].append([step, state, detail])
                        print(f"{step}: {state} {detail}", flush=True)
                    # a fix for something exploited now goes first, on its own (D89's emergency path)
                    first = [u for u in go if u.get("early") == "kev"]
                    batches = [b for b in (first, [u for u in go if u not in first]) if b]
                    try:
                        for batch in batches:
                            versions = [f"{u['name']}={u['version']}" for u in batch]
                            out = install(versions, True, run, emit, "auto")
                            status["installed"] += versions
                            status["restart"] = status["restart"] or out.get("restart", False)
                            if out.get("broken") or out.get("failed"):
                                status["error"] = "after"
                                break
                    except RuntimeError as e:
                        status["error"] = "install"
                        status["detail"] = str(e)[-300:]
    except RuntimeError as e:  # the window is installing right now: tomorrow
        status["error"] = "busy"
        status["detail"] = str(e)
    updates.write_json(status_path, status)
    if audit:
        audit({"ts": datetime.datetime.fromtimestamp(now).astimezone().isoformat(timespec="seconds"),
               "event": "auto-update", "installed": status["installed"],
               "held": [f"{h['name']}={h['version']} ({h['held']})" for h in status["held"]],
               "kev": status["kev"], "early": status["early"],
               "flagged": [f"{f['name']}={f['version']} ({f['url']})" for f in status["flagged"]], "error": status["error"],
               "signature": status["signature"]})
    return status


def main() -> int:
    if os.geteuid() != 0:
        print("cinminai-updates-auto runs as root (from its timer)", file=sys.stderr)
        return 1
    os.umask(0o022)
    from .mechanism import AUDIT, append_audit, changelog, run_apt_whole
    status = run_once(run_apt_whole, changelog, audit=lambda record: append_audit(AUDIT, record))
    if status is None:
        print("the wait and automatic updates are off: nothing to do")
    else:
        print(json.dumps({k: status[k] for k in ("installed", "error", "restart")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
