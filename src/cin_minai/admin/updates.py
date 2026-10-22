# SPDX-License-Identifier: GPL-3.0-or-later
"""The update window's root steps (PLAN D29, SPEC §3.7.1): only real checks, each one a check apt, sha256 or our code
actually ran.

- refresh: `apt-get update`; apt checks every source's signature (InRelease, gpgv) and refuses an unsigned or
  wrongly signed one. A problem it reports is a failed check, never a warning to skip.
- install: the exact versions the window listed (each an installed package's current candidate), in steps: a safety
  snapshot (Timeshift, only when it is set up), the download, every file's SHA-256 against the signed index, the
  install (`--no-remove`: an update that would remove a package stops instead), and the check afterwards (dpkg's
  audit, services that failed since, a restart needed).

Each step is announced through `emit(job, step, state, detail)`: state is running, ok, skipped or failed; detail is
JSON. No D-Bus here, so the steps can be tested without root."""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Callable, Sequence

from .policy import PKG_RE, Reject

ARCHIVES = "/var/cache/apt/archives"
TIMESHIFT_CONF = "/etc/timeshift/timeshift.json"
REBOOT = "/var/run/reboot-required"
MAX_UPDATES = 3000
APT_OPTS = ["-o", "Dpkg::Options::=--force-confold", "-o", "Dpkg::Options::=--force-confdef"]
VERSION_RE = re.compile(r"^[A-Za-z0-9.+~:\-]{1,120}$")
# what apt says when a source's signature can't be checked (apt 2.8; LANG=C)
SIGNATURE_PROBLEMS = ("NO_PUBKEY", "EXPKEYSIG", "BADSIG", "is not signed", "GPG error", "The following signatures",
                      "Signed-By", "Clearsigned file isn't valid", "repository is not updated")
# `apt-get -s` lines: "Inst name [old] (new origins [arch])" (no [old] for a package new to the computer)
INST_RE = re.compile(r"^Inst (?P<name>\S+) (?:\[(?P<old>[^\]]+)\] )?\((?P<new>\S+) (?P<origins>.*?) ?\[(?P<arch>[^\]]+)\]\)")

Run = Callable[[list[str]], str]
Emit = Callable[[str, str, str, str], None]


def check_versions(versions: Sequence[str], candidates: Callable[[str], tuple[str, str] | None]) -> list[str]:
    """Each `name=version` (or `name:arch=version`) must be an installed package whose candidate is that version:
    an update the window listed, nothing else. `candidates(name)` gives (installed, candidate) or None."""
    if not versions:
        raise Reject("no updates named")
    if len(versions) > MAX_UPDATES:
        raise Reject("too many updates in one request")
    out = []
    for item in versions:
        name, sep, version = str(item).partition("=")
        base = name.split(":", 1)[0]
        if not sep or not PKG_RE.fullmatch(base) or not VERSION_RE.fullmatch(version):
            raise Reject(f"not an update: {item!r}")
        if ":" in name and not re.fullmatch(r"[a-z0-9]+", name.split(":", 1)[1]):
            raise Reject(f"not an architecture: {item!r}")
        found = candidates(name)
        if not found:
            raise Reject(f"{name} isn't installed")
        installed, candidate = found
        if candidate != version or installed == version:
            raise Reject(f"{name} {version} isn't a waiting update")
        out.append(f"{name}={version}")
    return out


def apt_candidates() -> Callable[[str], tuple[str, str] | None]:
    """The real `candidates` for check_versions: apt's own cache, read fresh (once per request)."""
    import apt  # python3-apt, a dependency of Mint's Update Manager
    cache = apt.Cache()

    def candidates(name: str) -> tuple[str, str] | None:
        if name not in cache:
            return None
        pkg = cache[name]
        if not pkg.installed or not pkg.candidate:
            return None
        return pkg.installed.version, pkg.candidate.version
    return candidates


def signature_problems(output: str) -> list[str]:
    return [line.strip() for line in output.splitlines()
            if line.startswith(("W:", "E:", "Err:")) and any(p in line for p in SIGNATURE_PROBLEMS)]


def sources(output: str) -> list[str]:
    """The servers apt read from (Hit/Get lines), in order, once each."""
    seen: list[str] = []
    for line in output.splitlines():
        m = re.match(r"^(?:Hit|Get|Ign):\d+ (?:https?|file|cdrom)://([^/ ]+)", line)
        if m and m.group(1) not in seen:
            seen.append(m.group(1))
    return seen


def refresh(run: Run) -> dict:
    """apt-get update: the lists, their signatures checked by apt. Fails (raises) on any signature problem."""
    try:
        out = run(["/usr/bin/apt-get", "update"])
    except RuntimeError as e:
        problems = signature_problems(str(e))
        raise RuntimeError(json.dumps({"signature": problems or [], "error": str(e)[-400:]})) from None
    problems = signature_problems(out)
    if problems:
        raise RuntimeError(json.dumps({"signature": problems, "error": ""}))
    return {"sources": sources(out)}


def planned(output: str) -> list[dict]:
    """What `apt-get -s` would install: the updates and any package new to the computer they bring."""
    return [{"name": m.group("name"), "old": m.group("old") or "", "version": m.group("new"),
             "arch": m.group("arch"), "origins": m.group("origins")}
            for m in map(INST_RE.match, output.splitlines()) if m]


def deb_name(name: str, version: str, arch: str) -> str:
    """apt's name for the downloaded file (an epoch's ':' written %3a)."""
    return f"{name}_{version.replace(':', '%3a')}_{arch}.deb"


def apt_hashes() -> Callable[[str, str, str], str]:
    """The SHA-256 the signed index gives for a version (python3-apt, one cache read): the real `expected`."""
    import apt
    cache = apt.Cache()

    def expected(name: str, version: str, arch: str) -> str:
        for key in (name, f"{name}:{arch}"):
            if key in cache:
                for v in cache[key].versions:
                    if v.version == version and v.architecture in (arch, "all"):
                        return (v.sha256 or "").lower()
        return ""
    return expected


def fingerprints(plan: list[dict], expected: Callable[[str, str, str], str],
                 archives: str = ARCHIVES) -> tuple[int, list[str]]:
    """Every file to be installed against the SHA-256 in the signed index: (matching, the names that don't)."""
    good, bad = 0, []
    for p in plan:
        f = {"file": deb_name(p["name"], p["version"], p["arch"]), "hash": expected(p["name"], p["version"], p["arch"])}
        if not f["hash"]:
            bad.append(f["file"])
            continue
        h = hashlib.sha256()
        try:
            with open(os.path.join(archives, f["file"]), "rb") as data:
                for chunk in iter(lambda: data.read(1 << 20), b""):
                    h.update(chunk)
        except OSError:
            bad.append(f["file"])
            continue
        if h.hexdigest() == f["hash"]:
            good += 1
        else:
            bad.append(f["file"])
    return good, bad


def timeshift_ready(conf: str = TIMESHIFT_CONF) -> bool:
    """Timeshift set up: its settings name a backup drive."""
    try:
        with open(conf, encoding="utf-8") as f:
            return bool(json.load(f).get("backup_device_uuid"))
    except (OSError, ValueError):
        return False


def failed_units(run: Run) -> set[str]:
    try:
        out = run(["/usr/bin/systemctl", "--failed", "--no-legend", "--plain"])
    except RuntimeError:
        return set()
    return {line.split()[0] for line in out.splitlines() if line.strip()}


def install(versions: list[str], snapshot: bool, run: Run, emit: Emit, job: str, expected=None,
            archives: str = ARCHIVES, timeshift_conf: str = TIMESHIFT_CONF, reboot: str = REBOOT) -> dict:
    """The steps after the password, in order; a failed check stops everything after it."""
    def step(name: str, state: str, **detail) -> None:
        emit(job, name, state, json.dumps(detail))

    result: dict = {"installed": 0, "snapshot": "skipped", "restart": False}
    if snapshot and timeshift_ready(timeshift_conf):
        step("snapshot", "running")
        try:
            run(["/usr/bin/timeshift", "--create", "--scripted", "--comments", "Before updates (Cin-MinAI)"])
        except RuntimeError as e:
            step("snapshot", "failed", error=str(e)[-300:])
            raise RuntimeError("snapshot failed: nothing was installed") from None
        step("snapshot", "ok")
        result["snapshot"] = "ok"
    else:
        step("snapshot", "skipped", reason="not set up" if snapshot else "not asked")

    before = failed_units(run)
    get = ["/usr/bin/apt-get", "install", "--only-upgrade", "--no-remove", "-y", *APT_OPTS]
    step("download", "running", count=len(versions))
    try:
        plan = planned(run([*get, "-s", "--", *versions]))
        run([*get, "--download-only", "--", *versions])
    except RuntimeError as e:
        step("download", "failed", error=str(e)[-300:])
        raise RuntimeError("the download failed: nothing was installed") from None
    step("download", "ok", files=len(plan), new=[p["name"] for p in plan if not p["old"]][:20])

    step("fingerprints", "running", files=len(plan))
    good, bad = fingerprints(plan, expected or apt_hashes(), archives)
    if bad or not plan:
        step("fingerprints", "failed", good=good, bad=bad[:20])
        raise RuntimeError("a downloaded file didn't match the signed list: nothing was installed")
    step("fingerprints", "ok", good=good, files=len(plan))

    step("install", "running", count=len(versions))
    try:
        run([*get, "--", *versions])
    except RuntimeError as e:
        step("install", "failed", error=str(e)[-300:])
        raise RuntimeError("the install stopped part-way") from None
    step("install", "ok", count=len(versions))
    result["installed"] = len(versions)

    step("after", "running")
    try:
        audit = run(["/usr/bin/dpkg", "--audit"]).strip()
    except RuntimeError as e:
        audit = str(e)
    newly_failed = sorted(failed_units(run) - before)
    restart = os.path.exists(reboot)
    result.update(restart=restart, broken=bool(audit), failed=newly_failed)
    step("after", "failed" if audit or newly_failed else "ok", broken=audit[-300:], failed=newly_failed,
         restart=restart)
    return result
