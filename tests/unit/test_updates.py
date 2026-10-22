# SPDX-License-Identifier: GPL-3.0-or-later
"""The Updates window (PLAN D29, SPEC §3.7.1): the list is apt's own plan (phased updates wait), the root steps run in
order and a failed check stops everything after it, only the waiting versions can be asked for, and every word is in
the six languages.

    python3 -m unittest tests.unit.test_updates -v        (from the repo root)
"""

import hashlib
import json
import os
import shutil
import string
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))

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
        p = window.plan(SIMULATION)
        self.assertEqual([(i["name"], i["old"], i["version"], i["security"]) for i in p["updates"]],
                         [("libssl3t64", "3.0.13-0ubuntu3.5", "3.0.13-0ubuntu3.6", True),
                          ("tzdata", "2024a-3ubuntu1.1", "2025b-0ubuntu0.24.04", False)])
        self.assertEqual([i["name"] for i in p["new"]], ["linux-image-6.8.0-90-generic"])  # comes with an update
        self.assertEqual(p["remove"], ["oldthing"])
        self.assertEqual(p["phased"], 3)  # Ubuntu releases these gradually: they wait, as in Update Manager

    def test_the_request_is_the_exact_versions(self):
        p = window.plan(SIMULATION)
        self.assertEqual(window.request(p["updates"]),
                         ["libssl3t64=3.0.13-0ubuntu3.6", "tzdata=2025b-0ubuntu0.24.04"])

    def test_root_reads_the_same_lines(self):
        # the mechanism's plan (for the fingerprints) and the window's list come from one format
        self.assertEqual([p["name"] for p in root.planned(SIMULATION)],
                         ["libssl3t64", "linux-image-6.8.0-90-generic", "tzdata"])
        self.assertEqual(root.INST_RE.pattern, window.INST_RE.pattern)

    def test_headline(self):
        p = window.plan(SIMULATION)
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

    def test_a_restart_needed_is_said(self):
        open(self.reboot, "w").close()
        self.assertTrue(self.install()["restart"])
        self.assertTrue(self.details["after"]["restart"])
        self.assertIn("Restart", window.step_text("after", "ok", self.details["after"], "en")[1])


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


if __name__ == "__main__":
    unittest.main()
