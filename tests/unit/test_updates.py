# SPDX-License-Identifier: GPL-3.0-or-later
"""The Updates window (PLAN D29, SPEC §3.7.1): the list is apt's own plan (phased updates wait), the root steps run in
order and a failed check stops everything after it, only the waiting versions can be asked for, and every word is in
the six languages.

    python3 -m unittest tests.unit.test_updates -v        (from the repo root)
"""

import contextlib
import hashlib
import json
import os
import shutil
import string
import sys
import tempfile
import time
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))

from cin_minai.admin import auto  # noqa: E402
from cin_minai.admin import updates as root  # noqa: E402
from cin_minai.admin.policy import Reject  # noqa: E402
from cin_minai.daemon import updates as window  # noqa: E402

SIMULATION = """Reading package lists...
Building dependency tree...
Calculating upgrade...
The following upgrades have been deferred due to phasing:
  gir1.2-glib-2.0 libglib2.0-0t64
  xserver-common
The following packages will be upgraded:
  libssl3t64 tzdata
Inst libssl3t64 [3.0.13-0ubuntu3.5] (3.0.13-0ubuntu3.6 Ubuntu:24.04/noble-updates, Ubuntu:24.04/noble-security [amd64])
Inst linux-image-6.8.0-90-generic (6.8.0-90.91 Ubuntu:24.04/noble-updates [amd64])
Inst tzdata [2024a-3ubuntu1.1] (2025b-0ubuntu0.24.04 Ubuntu:24.04/noble-updates [all])
Remv oldthing [1.0]
Conf libssl3t64 (3.0.13-0ubuntu3.6 Ubuntu:24.04/noble-updates [amd64])
"""


class ThePlan(unittest.TestCase):
    def test_what_apt_would_do(self):
        p = root.plan(SIMULATION)
        self.assertEqual([(i["name"], i["old"], i["version"], i["security"]) for i in p["updates"]],
                         [("libssl3t64", "3.0.13-0ubuntu3.5", "3.0.13-0ubuntu3.6", True),
                          ("tzdata", "2024a-3ubuntu1.1", "2025b-0ubuntu0.24.04", False)])
        self.assertEqual([i["name"] for i in p["new"]], ["linux-image-6.8.0-90-generic"])  # comes with an update
        self.assertEqual(p["remove"], ["oldthing"])
        self.assertEqual(p["phased"], 3)  # Ubuntu releases these gradually: they wait, as in Update Manager

    def test_the_request_is_the_exact_versions(self):
        p = root.plan(SIMULATION)
        self.assertEqual(window.request(p["updates"]),
                         ["libssl3t64=3.0.13-0ubuntu3.6", "tzdata=2025b-0ubuntu0.24.04"])

    def test_the_install_reads_the_same_lines(self):
        # the install's plan (for the fingerprints) and the window's list come from one format
        self.assertEqual([p["name"] for p in root.planned(SIMULATION)],
                         ["libssl3t64", "linux-image-6.8.0-90-generic", "tzdata"])

    def test_headline(self):
        p = root.plan(SIMULATION)
        self.assertEqual(window.headline(p, "en"), "2 updates waiting (1 security)")
        self.assertEqual(window.headline({"updates": []}, "en"), "This computer is up to date.")


class OnlyWaitingUpdates(unittest.TestCase):
    CANDIDATES = {"libssl3t64": ("3.0.13-0ubuntu3.5", "3.0.13-0ubuntu3.6"), "bash": ("5.2.21-2ubuntu4", "5.2.21-2ubuntu4")}

    def check(self, versions):
        return root.check_versions(versions, self.CANDIDATES.get)

    def test_a_waiting_update_passes(self):
        self.assertEqual(self.check(["libssl3t64=3.0.13-0ubuntu3.6"]), ["libssl3t64=3.0.13-0ubuntu3.6"])

    def test_anything_else_is_refused(self):
        for bad in (["libssl3t64=3.0.13-0ubuntu3.4"],   # not the candidate (an older one)
                    ["bash=5.2.21-2ubuntu4"],           # already installed: nothing to update
                    ["notinstalled=1.0"],               # not on this computer: installing isn't updating
                    ["libssl3t64"],                     # no version
                    ["-o=Dpkg::Pre-Invoke=x"],          # an option smuggled in
                    ["libssl3t64=1.0;rm"],              # not a version
                    []):
            with self.subTest(bad=bad), self.assertRaises(Reject):
                self.check(bad)

    def test_too_many_at_once(self):
        with self.assertRaises(Reject):
            self.check(["libssl3t64=3.0.13-0ubuntu3.6"] * (root.MAX_UPDATES + 1))


class Signatures(unittest.TestCase):
    def test_a_signature_problem_is_a_failed_check(self):
        out = ("Hit:1 http://packages.linuxmint.com zena InRelease\n"
               "W: GPG error: http://example.org stable InRelease: The following signatures couldn't be verified "
               "because the public key is not available: NO_PUBKEY 0123456789ABCDEF\n")
        with self.assertRaises(RuntimeError) as e:
            root.refresh(lambda argv: out)
        self.assertTrue(json.loads(str(e.exception))["signature"])
        self.assertTrue(window.not_genuine("GDBus.Error:org.cinminai.Admin1.Error.Failed: " + str(e.exception)))

    def test_the_sources_apt_checked(self):
        out = ("Hit:1 http://packages.linuxmint.com zena InRelease\nGet:2 http://archive.ubuntu.com/ubuntu noble "
               "InRelease [256 kB]\nHit:3 http://archive.ubuntu.com/ubuntu noble-updates InRelease\n"
               "Hit:4 https://cin-minai.github.io/apt stable InRelease\nReading package lists...\n")
        self.assertEqual(root.refresh(lambda argv: out)["sources"],
                         ["packages.linuxmint.com", "archive.ubuntu.com", "cin-minai.github.io"])

    def test_a_network_failure_is_not_called_ungenuine(self):
        def fail(argv):
            raise RuntimeError("apt-get exited 100: E: Failed to fetch http://archive.ubuntu.com  Temporary failure")
        with self.assertRaises(RuntimeError) as e:
            root.refresh(fail)
        self.assertFalse(window.not_genuine("GDBus.Error:org.cinminai.Admin1.Error.Failed: " + str(e.exception)))


class TheSteps(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.archives = os.path.join(self.dir, "archives")
        os.makedirs(self.archives)
        self.ran, self.steps, self.details, self.hashes = [], [], {}, {}
        for name, version, arch in (("libssl3t64", "3.0.13-0ubuntu3.6", "amd64"), ("tzdata", "2025b-0ubuntu0.24.04", "all")):
            data = f"{name} {version}".encode()
            with open(os.path.join(self.archives, root.deb_name(name, version, arch)), "wb") as f:
                f.write(data)
            self.hashes[(name, version, arch)] = hashlib.sha256(data).hexdigest()
        self.timeshift = os.path.join(self.dir, "timeshift.json")
        self.reboot = os.path.join(self.dir, "reboot-required")

    def emit(self, job, step, state, detail):
        self.steps.append((step, state))
        self.details[step] = json.loads(detail)

    def run_apt(self, argv):
        self.ran.append(argv)
        if "-s" in argv:
            return SIMULATION.replace("Inst linux-image-6.8.0-90-generic (6.8.0-90.91 Ubuntu:24.04/noble-updates "
                                      "[amd64])\n", "")
        return ""

    def install(self, snapshot=True, **kw):
        return root.install(["libssl3t64=3.0.13-0ubuntu3.6", "tzdata=2025b-0ubuntu0.24.04"], snapshot, self.run_apt,
                            self.emit, "job1", expected=lambda *k: self.hashes.get(k, ""),
                            archives=self.archives, timeshift_conf=self.timeshift, reboot=self.reboot, **kw)

    def test_every_step_in_order(self):
        with open(self.timeshift, "w") as f:
            json.dump({"backup_device_uuid": "abc"}, f)
        out = self.install()
        self.assertEqual([s for s, st in self.steps if st != "running"],
                         ["snapshot", "download", "fingerprints", "install", "after"])
        self.assertTrue(all(st in ("running", "ok") for _, st in self.steps))
        self.assertEqual(out["installed"], 2)
        self.assertEqual(self.ran[0][:2], ["/usr/bin/timeshift", "--create"])
        install = [a for a in self.ran if a[:2] == ["/usr/bin/apt-get", "install"] and "-s" not in a
                   and "--download-only" not in a][0]
        self.assertIn("--no-remove", install)  # an update that would remove a package stops instead
        self.assertIn("--only-upgrade", install)

    def test_no_timeshift_no_pretend_snapshot(self):
        self.install()
        self.assertIn(("snapshot", "skipped"), self.steps)
        self.assertFalse(any(a[0] == "/usr/bin/timeshift" for a in self.ran))

    def test_a_file_that_doesnt_match_stops_before_the_install(self):
        with open(os.path.join(self.archives, root.deb_name("tzdata", "2025b-0ubuntu0.24.04", "all")), "wb") as f:
            f.write(b"something else")
        with self.assertRaises(RuntimeError):
            self.install()
        self.assertIn(("fingerprints", "failed"), self.steps)
        self.assertNotIn("install", [s for s, _ in self.steps])
        self.assertFalse(any(a[:2] == ["/usr/bin/apt-get", "install"] and "-s" not in a and "--download-only" not in a
                             for a in self.ran))

    def test_a_missing_file_stops_too(self):
        os.remove(os.path.join(self.archives, root.deb_name("libssl3t64", "3.0.13-0ubuntu3.6", "amd64")))
        with self.assertRaises(RuntimeError):
            self.install()
        self.assertIn(("fingerprints", "failed"), self.steps)

    def test_a_second_architectures_file_is_found_by_apts_name(self):
        # NVMe 2026-10-23: "zlib1g:i386" looked for zlib1g:i386_…; apt saves zlib1g_1%3a…_i386.deb
        self.assertEqual(root.deb_name("zlib1g:i386", "1:1.3.dfsg-3.1ubuntu2.3", "i386"),
                         "zlib1g_1%3a1.3.dfsg-3.1ubuntu2.3_i386.deb")
        data = b"zlib1g i386"
        with open(os.path.join(self.archives, "zlib1g_1%3a1.3.dfsg-3.1ubuntu2.3_i386.deb"), "wb") as f:
            f.write(data)
        plan = [{"name": "zlib1g:i386", "version": "1:1.3.dfsg-3.1ubuntu2.3", "arch": "i386"}]
        good, bad = root.fingerprints(plan, lambda *k: hashlib.sha256(data).hexdigest(), self.archives)
        self.assertEqual((good, bad), (1, []))

    def test_a_restart_needed_is_said(self):
        open(self.reboot, "w").close()
        self.assertTrue(self.install()["restart"])
        self.assertTrue(self.details["after"]["restart"])
        self.assertIn("Restart", window.step_text("after", "ok", self.details["after"], "en")[1])


NOW = 1_800_000_000.0
DAY = 86400
UPDATE_OUT = "Hit:1 http://archive.ubuntu.com/ubuntu noble InRelease\nReading package lists...\n"
CHANGELOG = """openssl (3.0.13-0ubuntu3.6) noble-security; urgency=medium

  * SECURITY UPDATE: something
    - CVE-2026-1111
  * SECURITY UPDATE: another, CVE-2026-2222 and CVE-2026-1111 again

 -- Someone <x@example.org>  Mon, 19 Oct 2026 10:00:00 +0000

openssl (3.0.13-0ubuntu3.5) noble-security; urgency=medium

  * SECURITY UPDATE: already installed
    - CVE-2025-9999
"""


def compare(a, b):
    return (a > b) - (a < b)  # good enough for these versions


class Settings(unittest.TestCase):
    def test_the_defaults_hold_nothing(self):
        self.assertEqual(root.check_settings({}), {"hold_days": 0, "auto": False, "own": [], "looked": []})

    def test_what_the_person_sets(self):
        got = root.check_settings({"hold_days": 2, "auto": True, "own": [
            {"name": "firefox", "version": ""}, {"name": "libssl3t64", "version": "3.0.13-0ubuntu3.6"},
            {"name": "firefox", "version": ""}]})
        self.assertEqual(got["own"], [{"name": "firefox", "version": ""},
                                      {"name": "libssl3t64", "version": "3.0.13-0ubuntu3.6"}])  # once each

    def test_anything_else_is_refused(self):
        for bad in ({"hold_days": -1}, {"hold_days": 61}, {"hold_days": True}, {"hold_days": "2"},
                    {"auto": "yes"}, {"own": [{"name": "-o=x", "version": ""}]},
                    {"own": [{"name": "bash", "version": "1;rm"}]}, {"own": [{"name": "bash", "extra": 1}]},
                    {"own": "bash"}, {"other": 1}, [], "x", {"looked": ["bash"]}, {"looked": ["-o=x=1"]},
                    {"looked": [3]}, {"looked": "bash=1"},
                    {"own": [{"name": "p%d" % i, "version": ""} for i in range(root.MAX_OWN + 1)]}):
            with self.subTest(bad=str(bad)[:60]), self.assertRaises(Reject):
                root.check_settings(bad)

    def test_a_damaged_file_means_the_defaults(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "updates.json")
            with open(path, "w") as f:
                f.write('{"hold_days": 9999')
            self.assertEqual(root.load_settings(path), root.DEFAULTS)
            root.write_json(path, {"hold_days": 2, "auto": False, "own": []})
            self.assertEqual(root.load_settings(path)["hold_days"], 2)


class Holds(unittest.TestCase):
    def items(self):
        return [{"name": "firefox", "version": "140.0", "old": "139.0", "security": False},
                {"name": "libssl3t64", "version": "3.0.13-0ubuntu3.6", "old": "3.0.13-0ubuntu3.5", "security": True},
                {"name": "tzdata", "version": "2025b", "old": "2025a", "security": False},
                {"name": "libc6:i386", "version": "2.39-0ubuntu8.7", "old": "2.39-0ubuntu8.6", "security": False}]

    def test_first_seen_is_kept(self):
        seen = root.record_seen({"tzdata": "2025b"}, {}, NOW)
        self.assertEqual(seen, {"tzdata=2025b": NOW})
        later = root.record_seen({"tzdata": "2025b", "firefox": "140.0"}, seen, NOW + DAY)
        self.assertEqual(later, {"tzdata=2025b": NOW, "firefox=140.0": NOW + DAY})
        # gone from the list: kept 90 days, then dropped
        self.assertIn("tzdata=2025b", root.record_seen({}, later, NOW + 89 * DAY))
        self.assertNotIn("tzdata=2025b", root.record_seen({}, later, NOW + 91 * DAY))

    def test_off_by_default_nothing_is_held(self):
        items = self.items()
        root.apply_holds(items, root.DEFAULTS, {}, NOW)
        self.assertEqual([i["held"] for i in items], ["", "", "", ""])

    def test_the_wait_and_the_persons_own(self):
        items = self.items()
        seen = {"firefox=140.0": NOW - 3 * DAY, "libssl3t64=3.0.13-0ubuntu3.6": NOW - DAY, "tzdata=2025b": NOW - DAY,
                "libc6:i386=2.39-0ubuntu8.7": NOW - 3 * DAY}
        settings = {"hold_days": 2, "auto": True, "own": [{"name": "tzdata", "version": "2025b"},
                                                          {"name": "libc6", "version": ""}]}
        root.apply_holds(items, settings, seen, NOW)
        self.assertEqual([i["held"] for i in items], ["", "waiting", "update", "program"])
        self.assertEqual(items[1]["ready"], NOW + DAY)  # security fixes wait too (D89); slice 3 confirms them early
        # the window shows the same holds, also before a change is saved
        for item in items:
            self.assertEqual(window.held(item, settings, NOW), item["held"], item["name"])

    def test_a_new_version_of_a_held_update_is_not_held(self):
        items = self.items()
        root.apply_holds(items, {"hold_days": 0, "own": [{"name": "firefox", "version": "139.5"}]}, {}, NOW)
        self.assertEqual(items[0]["held"], "")

    def test_the_window_adds_and_releases_holds(self):
        item = self.items()[0]
        s = window.hold(root.DEFAULTS, item, "program")
        self.assertEqual(s["own"], [{"name": "firefox", "version": ""}])
        s = window.hold(s, item, "update")
        self.assertEqual(s["own"], [{"name": "firefox", "version": "140.0"}])
        self.assertEqual(window.hold(s, item, "")["own"], [])
        self.assertEqual(root.check_settings(window.hold(s, self.items()[3], "program"))["own"][-1],
                         {"name": "libc6", "version": ""})


class Cisa(unittest.TestCase):
    def test_the_cves_an_update_fixes(self):
        self.assertEqual(root.changelog_cves(CHANGELOG, "3.0.13-0ubuntu3.5", compare),
                         ["CVE-2026-1111", "CVE-2026-2222"])  # not the ones already installed

    def test_kev_fetched_once_a_day_and_a_week_old_copy_serves(self):
        with tempfile.TemporaryDirectory() as d:
            cache = os.path.join(d, "kev.json")
            fetched = []

            def fetch():
                fetched.append(1)
                return json.dumps({"vulnerabilities": [{"cveID": "CVE-2026-2222"}]}).encode()
            self.assertEqual(root.kev_ids(fetch, cache, time.time()), {"CVE-2026-2222"})
            self.assertEqual(root.kev_ids(fetch, cache, time.time() + 3600), {"CVE-2026-2222"})
            self.assertEqual(len(fetched), 1)

            def broken():
                raise OSError("offline")
            self.assertEqual(root.kev_ids(broken, cache, time.time() + 3 * DAY), {"CVE-2026-2222"})
            self.assertIsNone(root.kev_ids(broken, cache, time.time() + 8 * DAY))

    def test_only_held_security_updates_are_looked_up(self):
        items = Holds().items()
        items[1]["held"], items[0]["held"] = "waiting", "update"
        asked = []

        def changelog(item):
            asked.append(item["name"])
            return CHANGELOG
        self.assertTrue(root.mark_kev(items, changelog, compare, lambda: {"CVE-2026-2222"}))
        self.assertEqual(asked, ["libssl3t64"])
        self.assertEqual(items[1]["kev"], ["CVE-2026-2222"])
        self.assertIsNone(root.mark_kev([dict(items[1], held="")], changelog, compare, lambda: set()))
        self.assertFalse(root.mark_kev(items, changelog, compare, lambda: None))  # couldn't read it: said


class Confirmations(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.cache = os.path.join(self.dir, "confirmations.json")
        self.asked = []

    def osv(self, record):
        def fetch(vuln):
            self.asked.append(vuln)
            if isinstance(record, Exception):
                raise record
            return record
        return fetch

    def test_debians_record_names_the_program(self):
        record = {"id": "DEBIAN-CVE-2026-1111", "affected": [{"package": {"name": "openssl", "ecosystem": "Debian:13"}},
                                                             {"package": {"name": "openssl", "ecosystem": "Debian:14"}}]}
        self.assertEqual(root.confirm_cve("CVE-2026-1111", self.osv(record), self.cache, NOW), ["openssl"])
        self.assertEqual(self.asked, ["DEBIAN-CVE-2026-1111"])  # only the CVE number goes out
        root.confirm_cve("CVE-2026-1111", self.osv(record), self.cache, NOW + 20 * DAY)
        self.assertEqual(len(self.asked), 1)  # a confirmation is kept 30 days

    def test_none_and_unreachable_are_different(self):
        self.assertEqual(root.confirm_cve("CVE-2026-3", self.osv(None), self.cache, NOW), [])
        root.confirm_cve("CVE-2026-3", self.osv(None), self.cache, NOW + 2 * DAY)
        self.assertEqual(len(self.asked), 2)  # "none" is asked again the next day
        self.assertIsNone(root.confirm_cve("CVE-2026-4", self.osv(OSError("offline")), self.cache, NOW))

    def item(self, **kw):
        return dict({"name": "libssl3t64", "version": "2", "old": "1", "security": True, "held": "waiting",
                     "cves": ["CVE-1", "CVE-2"], "kev": []}, **kw)

    def early(self, items, answers):
        root.confirm_early(items, lambda name: "openssl", lambda cve: answers.get(cve, []))
        return items

    def test_every_cve_must_be_confirmed_for_the_same_program(self):
        ok, = self.early([self.item()], {"CVE-1": ["openssl"], "CVE-2": ["openssl", "openssl1.1"]})
        self.assertEqual((ok["held"], ok["early"]), ("", "confirmed"))
        half, = self.early([self.item()], {"CVE-1": ["openssl"]})
        self.assertEqual((half["held"], half.get("unconfirmed")), ("waiting", True))
        other, = self.early([self.item()], {"CVE-1": ["gnutls28"], "CVE-2": ["gnutls28"]})
        self.assertEqual(other["held"], "waiting")  # a real CVE, but not this program's
        none, = self.early([self.item(cves=[])], {})
        self.assertEqual((none["held"], none.get("unconfirmed")), ("waiting", True))
        self.assertIn("names no CVE", window.reason(none, "waiting", {"hold_days": 2}, "en"))
        unreached, = self.early([self.item()], {"CVE-1": None, "CVE-2": ["openssl"]})
        self.assertTrue(unreached["osv_unreached"])

    def test_the_program_without_its_version(self):
        # php2shell, 2026-10-22: Ubuntu 24.04 ships php8.3, Debian php8.2 and php8.4
        php = self.item(name="php8.3-cli")
        answers = {"CVE-1": ["php8.2", "php8.4"], "CVE-2": ["php8.4"]}
        root.confirm_early([php], lambda name: "php8.3", answers.get)
        self.assertEqual(php["held"], "")
        for a, b in (("php8.3", "php"), ("glib2.0", "glib"), ("python3.12", "python"), ("gnutls28", "gnutls"),
                     ("openssl", "openssl"), ("nss", "nss"), ("x264", "x264"), ("libxml2", "libxml")):
            self.assertEqual(root.family(a), b, a)

    def test_the_changelog_inside_the_package(self):
        import gzip
        import io as _io
        import tarfile
        buf = _io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as tar:
            data = gzip.compress(CHANGELOG.encode())
            info = tarfile.TarInfo("./usr/share/doc/libssl3t64/changelog.Debian.gz")
            info.size = len(data)
            tar.addfile(info, _io.BytesIO(data))
            link = tarfile.TarInfo("./usr/share/doc/ghostscript/changelog.Debian.gz")
            link.type, link.linkname = tarfile.SYMTYPE, "../libgs10/changelog.Debian.gz"
            tar.addfile(link)
        buf.seek(0)
        with tarfile.open(fileobj=buf) as tar:
            self.assertIn("CVE-2026-2222", root.changelog_in_deb(tar, "libssl3t64")[0])
            self.assertEqual(root.changelog_in_deb(tar, "ghostscript"), ("", "libgs10"))  # follow it to libgs10
            self.assertEqual(root.changelog_in_deb(tar, "nothing"), ("", ""))  # none: ask the server

    def test_ubuntus_kernel_names(self):
        for name in ("linux", "linux-signed", "linux-meta", "linux-hwe-6.11", "linux-signed-hwe-6.11",
                     "linux-meta-hwe-6.11", "linux-oem-6.8"):
            self.assertEqual(root.program(name), "linux", name)
        for name in ("linux-firmware", "linux-atm", "openssl", "glib2.0"):
            self.assertEqual(root.program(name), name, name)

    def test_the_persons_own_holds_stand(self):
        mine, plain = self.early([self.item(held="update"), self.item(security=False)],
                                 {"CVE-1": ["openssl"], "CVE-2": ["openssl"]})
        self.assertEqual((mine["held"], plain["held"]), ("update", "waiting"))
        self.assertNotIn("early", mine)


class TheCheck(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.settings = os.path.join(self.dir, "updates.json")
        self.seen = os.path.join(self.dir, "seen.json")

    def run_apt(self, argv):
        return SIMULATION if "-s" in argv else UPDATE_OUT

    def check(self, now, **kw):
        return root.check(self.run_apt, lambda item: CHANGELOG, now, compare=compare,
                          upgradable=lambda: {"libssl3t64": "3.0.13-0ubuntu3.6", "tzdata": "2025b-0ubuntu0.24.04"},
                          kev=lambda: {"CVE-2026-1111"}, settings_path=self.settings, seen_path=self.seen,
                          sources=lambda name: {"libssl3t64": "openssl"}.get(name, name),
                          confirm=kw.pop("confirm", lambda cve: []),
                          posts=kw.pop("posts", lambda days: {d: [] for d in days}), **kw)

    def test_the_wait_counts_from_the_first_check(self):
        root.write_json(self.settings, {"hold_days": 2, "auto": False, "own": []})
        first = self.check(NOW)
        self.assertEqual([u["held"] for u in first["updates"]], ["waiting", "waiting"])
        self.assertEqual(first["updates"][0]["kev"], ["CVE-2026-1111"])  # held security fix on CISA's list: said
        self.assertTrue(first["kev_checked"])
        self.assertEqual(first["settings"]["hold_days"], 2)
        later = self.check(NOW + 2 * DAY + 1)
        self.assertEqual([u["held"] for u in later["updates"]], ["", ""])
        self.assertIsNone(later["kev_checked"])  # nothing held, nothing looked up

    def test_a_confirmed_fix_does_not_wait_and_one_on_cisas_list_goes_first(self):
        root.write_json(self.settings, {"hold_days": 2, "auto": False, "own": []})
        got = self.check(NOW, confirm=lambda cve: ["openssl"])
        ssl, tz = got["updates"]
        self.assertEqual((ssl["held"], ssl["early"], ssl["confirmed"]), ("", "kev", ["CVE-2026-1111", "CVE-2026-2222"]))
        self.assertEqual(tz["held"], "waiting")  # not a security fix: it waits
        self.assertEqual(window.held(ssl, got["settings"], NOW), "")  # the window agrees
        self.assertIn("CVE-2026-1111", window.reason(ssl, "", got["settings"], "en"))

    def test_a_signature_problem_still_stops_the_check(self):
        def bad(argv):
            return "W: GPG error: http://example.org stable InRelease: NO_PUBKEY 0123456789ABCDEF\n"
        with self.assertRaises(RuntimeError):
            root.check(bad, lambda n: "", NOW, compare=compare, upgradable=dict, kev=set,
                       settings_path=self.settings, seen_path=self.seen)
        self.assertFalse(os.path.exists(self.seen))


class TheDailyRun(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.settings = os.path.join(self.dir, "updates.json")
        self.status = os.path.join(self.dir, "status.json")
        self.installed, self.audits = [], []

    def plan(self, held):
        ups = [{"name": "libssl3t64", "version": "3.0.13-0ubuntu3.6", "old": "x", "security": True,
                "held": held, "ready": 0, "kev": ["CVE-2026-1111"] if held else []},
               {"name": "tzdata", "version": "2025b", "old": "y", "security": False, "held": "", "ready": 0}]
        return lambda run, changelog, now: {"sources": [], "updates": ups, "new": [], "remove": [], "phased": 0}

    def install(self, versions, snapshot, run, emit, job):
        self.installed.append(versions)
        emit(job, "install", "ok", "{}")
        return {"installed": len(versions), "restart": True, "broken": False, "failed": []}

    def daily(self, settings, check, battery=lambda: False):
        if settings is not None:
            root.write_json(self.settings, settings)
        return auto.run_once(None, None, NOW, self.settings, self.status, check, self.install, battery,
                             self.audits.append, lock=contextlib.nullcontext)

    def test_off_does_nothing(self):
        self.assertIsNone(self.daily(None, self.plan("")))
        self.assertFalse(os.path.exists(self.status))

    def test_installs_what_nothing_holds(self):
        st = self.daily({"hold_days": 2, "auto": True, "own": []}, self.plan("waiting"))
        self.assertEqual(self.installed, [["tzdata=2025b"]])
        self.assertTrue(st["restart"])
        self.assertEqual(st["held"][0]["name"], "libssl3t64")
        self.assertEqual(st["kev"], [{"name": "libssl3t64", "version": "3.0.13-0ubuntu3.6", "cves": ["CVE-2026-1111"]}])
        self.assertEqual(self.audits[0]["event"], "auto-update")
        self.assertEqual(root.read_json(self.status, {})["installed"], ["tzdata=2025b"])

    def test_the_wait_alone_only_checks(self):
        st = self.daily({"hold_days": 2, "auto": False, "own": []}, self.plan(""))
        self.assertEqual(self.installed, [])
        self.assertEqual(st["error"], "")

    def test_a_fix_for_something_exploited_now_goes_first(self):
        def check(run, changelog, now):
            ups = [{"name": "tzdata", "version": "2025b", "old": "y", "security": False, "held": "", "ready": 0},
                   {"name": "libssl3t64", "version": "3.0.13-0ubuntu3.6", "old": "x", "security": True, "held": "",
                    "ready": 0, "early": "kev", "confirmed": ["CVE-2026-1111"], "kev": ["CVE-2026-1111"]}]
            return {"sources": [], "updates": ups, "new": [], "remove": [], "phased": 0}
        st = self.daily({"hold_days": 2, "auto": True, "own": []}, check)
        self.assertEqual(self.installed, [["libssl3t64=3.0.13-0ubuntu3.6"], ["tzdata=2025b"]])
        self.assertEqual(st["early"], [{"name": "libssl3t64", "version": "3.0.13-0ubuntu3.6", "why": "kev",
                                        "cves": ["CVE-2026-1111"]}])
        self.assertEqual(self.audits[0]["early"], st["early"])  # the record says it came early and why
        texts, _ = window.notices(st, {}, "en")
        self.assertTrue(any("installed early" in t for t in texts))

    def test_not_on_battery(self):
        st = self.daily({"hold_days": 0, "auto": True, "own": []}, self.plan(""), battery=lambda: True)
        self.assertEqual((self.installed, st["error"]), ([], "battery"))

    def test_a_signature_problem_is_recorded(self):
        def bad(run, changelog, now):
            raise RuntimeError(json.dumps({"signature": ["W: GPG error: x NO_PUBKEY 1"], "error": ""}))
        st = self.daily({"hold_days": 0, "auto": True, "own": []}, bad)
        self.assertEqual((self.installed, st["error"]), ([], "check"))
        self.assertTrue(st["signature"])

    def test_battery_reading(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertFalse(auto.on_battery(d))  # a desktop: no power supply listed
            os.makedirs(os.path.join(d, "AC"))
            for name, value in (("type", "Mains"), ("online", "0")):
                with open(os.path.join(d, "AC", name), "w") as f:
                    f.write(value + "\n")
            self.assertTrue(auto.on_battery(d))


class Alarms(unittest.TestCase):
    # oss-security, 2024-03-29: the xz backdoor's first report and its replies (titles as the archive lists them)
    XZ = [[3, "CVE-2024-28219: Pillow buffer overflow"],
          [4, "backdoor in upstream xz/liblzma leading to ssh server compromise"],
          [5, "Re: backdoor in upstream xz/liblzma leading to ssh server compromise"],
          [6, "Re: eMudhra Intermediates Compromise"]]
    TODAY = time.strftime("%Y/%m/%d", time.gmtime(NOW))
    BEFORE = time.strftime("%Y/%m/%d", time.gmtime(NOW - 5 * DAY))

    def item(self, **kw):
        return dict({"name": "liblzma5", "version": "5.6.1-1", "old": "5.4.5-0.3", "security": False,
                     "held": "waiting", "ready": NOW + DAY, "seen": NOW - DAY}, **kw)

    def mark(self, items, settings=None, posts=None):
        settings = settings or {"hold_days": 2, "auto": False, "own": [], "looked": []}
        found = posts or {self.TODAY: self.XZ}
        self.days = []

        def fetch(days):
            self.days.append(days)
            return {d: found.get(d, []) for d in days}
        self.result = root.mark_alarms(items, settings, lambda name: "xz-utils" if "lzma" in name or "xz" in name
                                       else name, fetch, NOW)
        return items

    def test_the_title_must_name_the_program_and_raise_an_alarm(self):
        xz = root.alarm_names("liblzma5", "xz-utils")
        self.assertEqual({"xz", "liblzma"} <= xz, True)
        self.assertEqual([n for n, _ in root.alarms(xz, self.XZ)], [4, 5])
        self.assertEqual(root.alarms(root.alarm_names("openssh-server", "openssh"), self.XZ), [])  # "ssh" isn't it
        self.assertEqual(root.alarms(root.alarm_names("python3-pil", "pillow"), self.XZ), [])  # no alarm word
        self.assertIn("libssl", root.alarm_names("libssl3t64", "openssl"))
        tiff = root.alarm_names("libtiff6", "tiff")
        for title, alarm in (("libtiff: a malicious TIFF file can crash tiffinfo", False),  # an attacker's input
                             ("tiff: session hijack via crafted tag", False),
                             ("Malicious code in libtiff 4.7.1 release tarball", True),
                             ("libtiff upstream repository compromised", True),
                             ("Compromise of the tiff maintainer's account", True)):
            self.assertEqual(bool(root.alarms(tiff, [[1, title]])), alarm, title)

    def test_held_until_the_person_has_looked(self):
        lzma, plain = self.mark([self.item(), self.item(name="tzdata", version="2025b")])
        self.assertTrue(self.days[0][-1] == self.TODAY)
        self.assertEqual((lzma["held"], lzma["ready"]), ("flagged", 0))
        self.assertEqual(lzma["flags"][-1]["url"], root.OSS_URL.format(self.TODAY) + "5")
        self.assertEqual(plain["held"], "waiting")
        settings = {"hold_days": 2, "auto": False, "own": [], "looked": []}
        self.assertEqual(window.held(lzma, settings, NOW), "flagged")  # the window agrees
        self.assertIn("backdoor in upstream xz", window.reason(lzma, "flagged", settings, "en"))
        looked = window.look(settings, lzma)
        self.assertEqual(root.check_settings(looked)["looked"], ["liblzma5=5.6.1-1"])
        self.assertEqual(window.held(lzma, looked, NOW), "waiting")  # looked: it waits like the rest
        again, = self.mark([self.item()], looked)
        self.assertEqual(again["held"], "waiting")
        self.assertIn("oss-security", window.reason(again, "waiting", looked, "en"))  # still said

    def test_only_posts_since_it_was_first_seen(self):
        old, = self.mark([self.item()], posts={self.BEFORE: self.XZ})
        self.assertEqual(old["held"], "waiting")
        self.assertNotIn("flags", old)

    def test_the_persons_holds_and_the_emergency_path_stand(self):
        mine, early = self.mark([self.item(held="program"), self.item(held="", early="confirmed")])
        self.assertEqual((mine["held"], early["held"]), ("program", ""))
        self.assertNotIn("flags", mine)
        self.assertTrue(early["flags"])  # it goes, and the post is shown
        self.assertIn("oss-security", window.reason(early, "", {"hold_days": 2}, "en"))

    def test_off_with_the_wait(self):
        item = self.item(held="")
        self.mark([item], {"hold_days": 0, "own": []})
        self.assertIsNone(self.result)
        self.assertEqual(self.days, [])  # nothing read

    def test_the_archive_page(self):
        page = ('<ul>\n<li><a href="4">backdoor in upstream xz/liblzma leading to ssh\nserver compromise</a> (A &lt;a&#64;b&gt;)'
                '\n<li><a href="7">Re: CVE-2026-1: a &amp; b</a> (C)\n</ul>')
        import html
        got = [[int(n), " ".join(html.unescape(t).split())] for n, t in root.POST_RE.findall(page)]
        self.assertEqual(got, [[4, "backdoor in upstream xz/liblzma leading to ssh server compromise"],
                               [7, "Re: CVE-2026-1: a & b"]])

    def test_days_read_once_they_are_over(self):
        with tempfile.TemporaryDirectory() as d:
            cache, asked = os.path.join(d, "oss.json"), []

            def fetch(day):
                asked.append(day)
                return [[1, day]]
            days = [self.BEFORE, self.TODAY]
            self.assertEqual(root.oss_posts(days, fetch, cache, NOW)[self.BEFORE], [[1, self.BEFORE]])
            root.oss_posts(days, fetch, cache, NOW + 3600)
            self.assertEqual(len(asked), 2)  # within six hours: nothing read again
            root.oss_posts(days, fetch, cache, NOW + 7 * 3600)
            self.assertEqual(asked[2:], [self.TODAY])  # a finished day isn't read again; today is

            def broken(day):
                raise OSError("offline")
            got = root.oss_posts(days + ["2000/01/01"], broken, cache, NOW + 20 * 3600)
            self.assertEqual((got[self.TODAY], got["2000/01/01"]), ([[1, self.TODAY]], None))

    def test_the_daily_run_says_it_once(self):
        def check(run, changelog, now):
            ups = [dict(self.item(), held="flagged", flags=[{"day": self.TODAY, "number": 4, "title": self.XZ[1][1],
                                                              "url": "https://x/4"}])]
            return {"sources": [], "updates": ups, "new": [], "remove": [], "phased": 0}
        run = TheDailyRun()
        run.setUp()
        try:
            st = run.daily({"hold_days": 2, "auto": True, "own": []}, check)
        finally:
            run.doCleanups()
        self.assertEqual(run.installed, [])
        self.assertEqual(st["flagged"][0]["url"], "https://x/4")
        self.assertIn("https://x/4", run.audits[0]["flagged"][0])
        texts, told = window.notices(st, {}, "en")
        self.assertTrue(any("backdoor in upstream xz" in t for t in texts))
        self.assertFalse(any("backdoor" in t for t in window.notices(dict(st, ts=NOW + DAY), told, "en")[0]))


class Notices(unittest.TestCase):
    STATUS = {"ts": NOW, "installed": ["tzdata=2025b"], "held": [{}], "restart": True, "error": "", "signature": [],
              "kev": [{"name": "libssl3t64", "version": "3.0.13-0ubuntu3.6", "cves": ["CVE-2026-1111"]}]}

    def test_each_said_once(self):
        texts, told = window.notices(self.STATUS, {}, "en")
        self.assertEqual(len(texts), 2)  # the restart, the CISA warning
        self.assertIn("CVE-2026-1111", texts[1])
        again, told = window.notices(self.STATUS, told, "en")
        self.assertEqual(again, [])
        # the next day's run: the restart again, the same held fix not again
        texts, _ = window.notices(dict(self.STATUS, ts=NOW + DAY), told, "en")
        self.assertEqual(len(texts), 1)

    def test_a_failed_check_is_said(self):
        texts, _ = window.notices({"ts": NOW, "signature": ["x"], "error": "check"}, {}, "en")
        self.assertEqual(texts, [window.words("n_genuine", "en")])
        self.assertEqual(window.notices({"ts": NOW, "error": "check"}, {}, "en")[0], [])  # offline: quiet

    def test_the_last_run_in_a_line(self):
        self.assertEqual(window.last_auto({}, "en"), "")
        self.assertIn("1 installed, 1 held", window.last_auto(self.STATUS, "en"))
        self.assertIn("power cable", window.last_auto({"ts": NOW, "error": "battery"}, "en"))


class Words(unittest.TestCase):
    LANGS = ["en", "es", "pt", "fr", "de", "ja"]

    @staticmethod
    def fields(text):
        return {f for _, f, _, _ in string.Formatter().parse(text) if f}

    def test_every_language_has_every_phrase_with_the_same_blanks(self):
        for lang in self.LANGS:
            self.assertEqual(set(window.WORDS[lang]), set(window.WORDS["en"]), lang)
            for key, text in window.WORDS["en"].items():
                self.assertEqual(self.fields(window.WORDS[lang][key]), self.fields(text), (lang, key))

    def test_every_step_reads_in_every_language(self):
        details = {"sources": ["archive.ubuntu.com"], "files": 3, "count": 3, "good": 3, "bad": ["x.deb"],
                   "failed": ["cups.service"], "restart": True, "error": "boom"}
        for lang in self.LANGS:
            for step in window.STEPS:
                for st in ("running", "ok", "failed"):
                    what, how = window.step_text(step, st, details, lang)
                    self.assertTrue(what, (lang, step, st))
            self.assertEqual(window.failure("GDBus.Error:org.cinminai.Admin1.Error.Dismissed: not authorized", lang),
                             window.words("cancelled", lang))


class NoTimeout(unittest.TestCase):
    def test_the_window_waits_for_the_mechanism(self):
        """2026-10-25: D-Bus's default 25 s ran out while the password and the download took longer; the window said
        "Timeout was reached" and stopped at Downloading while the install went on."""
        import inspect
        src = inspect.getsource(window)
        self.assertNotIn("flags, -1, None", src)
        self.assertIn("flags, NO_TIMEOUT, None", src)
        self.assertEqual(window.NO_TIMEOUT, 0x7fffffff)


if __name__ == "__main__":
    unittest.main()


class MonthlyReminder(unittest.TestCase):
    """D29's honest monthly reminder: online, updates not installing by themselves, a month since apt installed
    anything, and updates waiting — once a month at most."""

    def test_when_it_comes(self):
        now, day = 1_800_000_000.0, 86400
        pending = lambda: 3  # noqa: E731
        self.assertEqual(window.monthly(now, now - 31 * day, {}, {}, False, pending), 3)
        self.assertEqual(window.monthly(now, now - 10 * day, {}, {}, False, pending), 0)  # updated lately
        self.assertEqual(window.monthly(now, now - 31 * day, {"auto": True}, {}, False, pending), 0)  # they install
        self.assertEqual(window.monthly(now, now - 31 * day, {}, {}, True, pending), 0)  # offline has its own
        self.assertEqual(window.monthly(now, now - 31 * day, {}, {"month": now - 5 * day}, False, pending), 0)
        self.assertEqual(window.monthly(now, now - 31 * day, {}, {}, False, lambda: 0), 0)  # nothing waits
        self.assertEqual(window.monthly(now, 0, {}, {}, False, pending), 0)  # can't tell: no guess

    def test_last_install_from_the_logs(self):
        import gzip
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        cur, old = os.path.join(d, "history.log"), os.path.join(d, "history.log.1.gz")
        with open(cur, "w") as f:
            f.write("\nStart-Date: 2026-10-01  09:00:00\nCommandline: apt-get install x\n")
        with gzip.open(old, "wt") as f:
            f.write("\nStart-Date: 2026-09-01  09:00:00\n")
        self.assertEqual(time.strftime("%Y-%m-%d", time.localtime(window.last_install([cur, old]))), "2026-10-01")
        self.assertEqual(window.last_install([os.path.join(d, "none")]), 0)

    def test_counting_what_waits(self):
        class Out:
            stdout = SIMULATION
        self.assertEqual(window.waiting(lambda *a, **k: Out()), 3)
        self.assertIn("3", window.words("n_month", "de", n=3))
