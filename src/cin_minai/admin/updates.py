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
JSON. No D-Bus here, so the steps can be tested without root.

Holds (slice 2, PLAN D89 as Ian set it 2026-10-22): optional and off by default. The settings (root-owned, readable by
all) say how many days a new version waits (0 = no wait), whether updates install by themselves once a day (our own
timer, auto.py: Mint's updater re-checks the servers after any step in front of it, so a version published in between
would skip the wait), and the person's own holds: one update (that version only) or a program (all its updates, until
they release it). When a version was first seen is recorded at every check. A held security update whose fixes are on
CISA's Known Exploited Vulnerabilities list is said, once: it stays held, the person decides."""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
import urllib.request
from collections.abc import Callable, Sequence
from contextlib import contextmanager

from .policy import PKG_RE, Reject

ARCHIVES = "/var/cache/apt/archives"
TIMESHIFT_CONF = "/etc/timeshift/timeshift.json"
REBOOT = "/var/run/reboot-required"
SETTINGS = "/etc/cinminai/updates.json"
SEEN = "/var/lib/cinminai/updates-seen.json"
STATUS = "/var/lib/cinminai/updates-status.json"
KEV_CACHE = "/var/lib/cinminai/kev.json"
KEV_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
LOCK = "/run/lock/cinminai-updates.lock"
DEFAULTS = {"hold_days": 0, "auto": False, "own": []}
MAX_HOLD_DAYS = 60
MAX_OWN = 500
DAY = 86400
MAX_UPDATES = 3000
APT_OPTS = ["-o", "Dpkg::Options::=--force-confold", "-o", "Dpkg::Options::=--force-confdef"]
VERSION_RE = re.compile(r"^[A-Za-z0-9.+~:\-]{1,120}$")
# what apt says when a source's signature can't be checked (apt 2.8; LANG=C)
SIGNATURE_PROBLEMS = ("NO_PUBKEY", "EXPKEYSIG", "BADSIG", "is not signed", "GPG error", "The following signatures",
                      "Signed-By", "Clearsigned file isn't valid", "repository is not updated")
# `apt-get -s` lines: "Inst name [old] (new origins [arch])" (no [old] for a package new to the computer)
INST_RE = re.compile(r"^Inst (?P<name>\S+) (?:\[(?P<old>[^\]]+)\] )?\((?P<new>\S+) (?P<origins>.*?) ?\[(?P<arch>[^\]]+)\]\)")
REMV_RE = re.compile(r"^Remv (?P<name>\S+)")
CVE_RE = re.compile(r"\bCVE-\d{4}-\d{4,7}\b")
# a changelog entry's first line: "name (version) suite; urgency=..."
ENTRY_RE = re.compile(r"^[a-z0-9][a-z0-9.+\-]* \((?P<version>[^)\s]+)\) ")

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


def plan(output: str) -> dict:
    """What an upgrade would do (`apt-get -s dist-upgrade`): the updates (installed packages getting a new version),
    packages it would add (a new kernel), remove, and how many updates Ubuntu holds back for now (phased)."""
    ups, new, gone, phased, in_phased = [], [], [], 0, False
    for line in output.splitlines():
        m = INST_RE.match(line)
        if m:
            item = {"name": m.group("name"), "old": m.group("old") or "", "version": m.group("new"),
                    "arch": m.group("arch"), "security": "-security" in m.group("origins")}
            (ups if item["old"] else new).append(item)
            in_phased = False
            continue
        r = REMV_RE.match(line)
        if r:
            gone.append(r.group("name"))
        if line.startswith("The following upgrades have been deferred due to phasing"):
            in_phased = True
        elif in_phased and line.startswith("  "):
            phased += len(line.split())
        else:
            in_phased = False
    return {"updates": ups, "new": new, "remove": gone, "phased": phased}


def write_json(path: str, data, mode: int = 0o644) -> None:
    """Whole or not at all: a temporary file beside it, then a rename."""
    os.makedirs(os.path.dirname(path), mode=0o755, exist_ok=True)
    tmp = f"{path}.tmp-{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, sort_keys=True)
        f.flush()
        os.fsync(f.fileno())
    os.chmod(tmp, mode)
    os.replace(tmp, path)


def read_json(path: str, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def check_settings(data) -> dict:
    """The settings as the person set them, or Reject: days 0-60, automatic on or off, at most 500 holds of their own,
    each a package name and a version (that update) or "" (the program, every update until released)."""
    if not isinstance(data, dict) or set(data) - set(DEFAULTS):
        raise Reject("not update settings")
    days, auto, own = data.get("hold_days", 0), data.get("auto", False), data.get("own", [])
    if not isinstance(days, int) or isinstance(days, bool) or not 0 <= days <= MAX_HOLD_DAYS:
        raise Reject(f"the wait is 0 to {MAX_HOLD_DAYS} days")
    if not isinstance(auto, bool):
        raise Reject("automatic is on or off")
    if not isinstance(own, list) or len(own) > MAX_OWN:
        raise Reject("too many holds")
    holds, seen = [], set()
    for h in own:
        if not isinstance(h, dict) or set(h) - {"name", "version"}:
            raise Reject("not a hold")
        name, version = h.get("name"), h.get("version", "")
        if not isinstance(name, str) or not PKG_RE.fullmatch(name):
            raise Reject(f"not a package name: {name!r}")
        if not isinstance(version, str) or (version and not VERSION_RE.fullmatch(version)):
            raise Reject(f"not a version: {version!r}")
        if (name, version) not in seen:
            seen.add((name, version))
            holds.append({"name": name, "version": version})
    return {"hold_days": days, "auto": auto, "own": holds}


def load_settings(path: str = SETTINGS) -> dict:
    try:
        return check_settings(read_json(path, dict(DEFAULTS)))
    except Reject:
        return dict(DEFAULTS)  # a damaged file means the defaults (no wait, nothing automatic), never a guess


def record_seen(current: dict[str, str], seen: dict[str, float], now: float) -> dict[str, float]:
    """When each waiting version was first seen. Versions no longer waiting are kept 90 days (one that comes back keeps
    its first time), then dropped."""
    out = {k: t for k, t in seen.items() if isinstance(t, (int, float)) and now - t < 90 * DAY}
    for name, version in current.items():
        out.setdefault(f"{name}={version}", now)
    return out


def apt_upgradable() -> dict[str, str]:
    """Every installed package with a newer candidate, phased ones too (python3-apt, read fresh)."""
    import apt
    cache = apt.Cache()
    return {p.name: p.candidate.version for p in cache if p.is_upgradable}


def base_name(name: str) -> str:
    return name.split(":", 1)[0]


def apply_holds(items: list[dict], settings: dict, seen: dict[str, float], now: float) -> None:
    """Mark each update: held "update" or "program" (the person's own), "waiting" (newer than the wait, with when it's
    ready), or "" (goes). The person's own holds come first."""
    own = {(h["name"], h["version"]) for h in settings.get("own", [])}
    wait = settings.get("hold_days", 0) * DAY
    for item in items:
        name = base_name(item["name"])
        first = seen.get(f"{item['name']}={item['version']}", seen.get(f"{name}={item['version']}", now))
        item["seen"] = first
        item["held"], item["ready"] = "", 0
        if (name, item["version"]) in own:
            item["held"] = "update"
        elif (name, "") in own:
            item["held"] = "program"
        elif wait and now < first + wait:
            item["held"], item["ready"] = "waiting", first + wait


def changelog_cves(text: str, installed: str, compare: Callable[[str, str], int]) -> list[str]:
    """The CVEs named in the changelog entries newer than the installed version, in order, once each."""
    out: list[str] = []
    for line in text.splitlines():
        m = ENTRY_RE.match(line)
        if m and installed and compare(m.group("version"), installed) <= 0:
            break
        for cve in CVE_RE.findall(line):
            if cve not in out:
                out.append(cve)
    return out


def kev_ids(fetch: Callable[[], bytes] | None = None, cache: str = KEV_CACHE, now: float | None = None) -> set[str] | None:
    """CISA's Known Exploited Vulnerabilities (the CVE ids), fetched at most once a day; a copy up to a week old serves
    when the fetch fails; None when there's nothing to go on. The fetch sends nothing about this computer."""
    now = now or time.time()
    try:
        age = now - os.path.getmtime(cache)
    except OSError:
        age = float("inf")
    data = None
    if age > DAY:
        try:
            raw = (fetch or (lambda: urllib.request.urlopen(KEV_URL, timeout=30).read()))()
            data = json.loads(raw)
            write_json(cache, data)
        except (OSError, ValueError):
            data = None
    if data is None and age <= 7 * DAY:
        data = read_json(cache, None)
    try:
        return {v["cveID"] for v in data["vulnerabilities"]}
    except (TypeError, KeyError):
        return None


def mark_kev(items: list[dict], changelog: Callable[[str], str], compare: Callable[[str, str], int],
             kev: Callable[[], set[str] | None] = kev_ids) -> bool | None:
    """For held security updates: the CVEs they fix (their changelog) and which of those CISA lists as exploited now.
    Returns whether CISA's list could be read (None when nothing was held)."""
    held = [i for i in items if i.get("held") and i.get("security")]
    if not held:
        return None
    known = kev()
    for item in held:
        try:
            item["cves"] = changelog_cves(changelog(item["name"]), item["old"], compare)
        except RuntimeError:
            item["cves"] = []
        item["kev"] = [c for c in item["cves"] if known and c in known]
    return known is not None


def apt_compare() -> Callable[[str, str], int]:
    import apt_pkg
    apt_pkg.init_system()
    return apt_pkg.version_compare


def check(run: Run, changelog: Callable[[str], str], now: float | None = None, upgradable=apt_upgradable,
          compare=None, kev=kev_ids, settings_path: str = SETTINGS, seen_path: str = SEEN) -> dict:
    """A check for updates (the window's and the daily timer's): the lists refreshed and their signatures checked, apt's
    plan, when each waiting version was first seen (recorded), and the holds applied."""
    now = now or time.time()
    result = refresh(run)
    result.update(plan(run(["/usr/bin/apt-get", "-s", "-o", "APT::Get::Show-User-Simulation-Note=false",
                            "dist-upgrade"])))
    seen = record_seen(upgradable(), read_json(seen_path, {}), now)
    write_json(seen_path, seen)
    settings = load_settings(settings_path)
    apply_holds(result["updates"], settings, seen, now)
    result["kev_checked"] = mark_kev(result["updates"], changelog, compare or apt_compare(), kev)
    result["settings"] = settings
    return result


@contextmanager
def exclusive(path: str = LOCK):
    """One update at a time, across the window's mechanism and the daily timer."""
    import fcntl
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_CLOEXEC, 0o644)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise RuntimeError("an update is already running") from None
        yield
    finally:
        os.close(fd)


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
