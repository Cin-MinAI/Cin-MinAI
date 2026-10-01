# SPDX-License-Identifier: GPL-3.0-or-later
"""cinminai-diag rules on recorded cases (SPEC §20.7): every real case is a fixture, every rule is tested on it.

    python3 -m unittest tests.unit.test_diag -v        (from the repo root)
"""

import copy
import json
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))

from cin_minai.diag import probes, report, rules  # noqa: E402
from cin_minai.diag.source import FixtureSource  # noqa: E402

FIX = os.path.join(ROOT, "tests", "fixtures", "diag")


def case(name: str) -> dict:
    return probes.collect(FixtureSource(os.path.join(FIX, name)))


def codes(ev: dict) -> dict:
    return {f["code"]: f for f in rules.evaluate(ev)}


class During70(unittest.TestCase):
    """2026-09-30, the boot of 20:01 on kernel 7.0: link errors, failed writes, driver not loaded."""

    @classmethod
    def setUpClass(cls):
        cls.ev = case("2026-09-30-v300-during-7.0.json")
        cls.f = codes(cls.ev)

    def test_all_four_active(self):
        for c in ("S401", "I301", "I302", "G101"):
            self.assertEqual(self.f[c]["status"], "active", c)

    def test_kernel_is_the_lead(self):
        self.assertEqual(rules.evaluate(self.ev)[0]["code"], "S401")
        s = self.f["S401"]["facts"]
        self.assertEqual(s["kernel"], "7.0.0-34-generic")
        self.assertEqual(s["good_kernel"], "6.14.0-37-generic")

    def test_link_errors_point_at_one_kernel_and_the_wire(self):
        i = self.f["I301"]
        self.assertEqual(i["cause"], "one_kernel")
        self.assertEqual((i["facts"]["disk"], i["facts"]["port"]), ("sda", "ata2"))
        self.assertIn("KINGSTON SV300", i["facts"]["model"])
        self.assertEqual(i["facts"]["largest_failed_kib"], 4096)
        self.assertIn("cable", i["facts"]["signal"])

    def test_driver_file_damaged_not_signature(self):
        g = self.f["G101"]
        self.assertEqual(g["cause"], "file_damaged")  # 2026-09-29's "signature" guess, ruled out by evidence
        self.assertEqual(g["facts"]["module"], "nvidia/580.178.04")

    def test_casper_check_known_harmless(self):
        self.assertEqual((self.f["I101"]["status"], self.f["I101"]["cause"]), ("seen", "known"))

    def test_guide_view_leads_with_the_fix_that_works(self):
        rep = report.build(self.ev, rules.evaluate(self.ev), now="2026-09-30T20:05:00-04:00")
        g = report.guide_view(rep)
        self.assertEqual(g["faults"][0]["code"], "S401")
        self.assertIn("Update Manager", " ".join(g["faults"][0]["steps"]))
        cmd = next(f for f in g["faults"] if f["code"] == "I301")["command"]
        self.assertEqual(cmd, "echo 1280 | sudo tee /sys/block/sda/queue/max_sectors_kb")

    def test_every_command_says_what_it_does_and_how_to_undo(self):
        rep = report.build(self.ev, rules.evaluate(self.ev), now="x")
        for f in rep["findings"]:
            for fx in f["fixes"]:
                if fx.get("command"):
                    self.assertTrue(fx.get("explain") and fx.get("undo"), (f["code"], fx))
                    self.assertNotIn("{", fx["command"], (f["code"], fx["command"]))  # every blank filled


class After68(unittest.TestCase):
    """The same machine on kernel 6.8, 7.0 removed: history, nothing active."""

    @classmethod
    def setUpClass(cls):
        cls.ev = case("2026-09-30-v300-after-6.8.json")
        cls.f = codes(cls.ev)

    def test_kernel_cleared_after_removal(self):
        self.assertEqual(self.f["S401"]["status"], "cleared")
        self.assertNotIn("G101", self.f)

    def test_disk_history_kept(self):
        self.assertEqual(self.f["I301"]["status"], "seen")
        self.assertEqual(self.f["I302"]["status"], "seen")

    def test_driver_loaded_on_68(self):
        self.assertEqual(self.ev["kernel"], "6.8.0-146-generic")
        self.assertEqual(self.ev["nvidia_version_loaded"], "580.178.04")

    def test_guide_view_has_no_active_fault(self):
        rep = report.build(self.ev, rules.evaluate(self.ev), now="x")
        self.assertFalse(any(f["now"] for f in report.guide_view(rep)["faults"]))

    def test_markdown_has_reading_guide_and_table(self):
        md = report.markdown(report.build(self.ev, rules.evaluate(self.ev), now="x"))
        self.assertIn("How to read this", md)
        self.assertIn("| start | kernel |", md)


class Branches(unittest.TestCase):
    """The tree's other branches, on the recorded case with one fact changed."""

    @classmethod
    def setUpClass(cls):
        cls.base = case("2026-09-30-v300-during-7.0.json")

    def ev(self):
        return copy.deepcopy(self.base)

    def test_not_built(self):
        e = self.ev()
        del e["dkms"]["7.0.0-34-generic"]
        f = codes(e)
        self.assertEqual(f["G101"]["cause"], "not_built")
        self.assertEqual(f["S301"]["status"], "active")

    def test_unsigned_with_secure_boot(self):
        e = self.ev()
        e["boots"][-1].update(secure_boot=True, sig_fail=1, zstd_fail=0)
        e["dkms"]["7.0.0-34-generic"]["warning"] = None
        self.assertEqual(codes(e)["G101"]["cause"], "unsigned")

    def test_loaded_driver_no_g101(self):
        e = self.ev()
        e["nvidia_module_loaded"] = True
        self.assertNotIn("G101", codes(e))

    def test_errors_on_every_kernel_mean_hardware(self):
        e = self.ev()
        for b in e["boots"]:
            b["links"] = copy.deepcopy(e["boots"][-1]["links"])
        f = codes(e)
        self.assertEqual(f["I301"]["cause"], "every_kernel")

    def test_root_read_only_now(self):
        e = self.ev()
        e["root"]["read_only"] = True
        self.assertEqual(codes(e)["I302"]["cause"], "read_only_now")

    def test_unclean_previous_boot(self):
        e = self.ev()
        e["boots"][-2]["clean_end"] = False
        self.assertIn("H401", codes(e))

    def test_interrupted_update(self):
        e = self.ev()
        e["dpkg_audit"] = "The following packages are only half configured"
        self.assertEqual(codes(e)["S101"]["status"], "active")


class Researched(unittest.TestCase):
    """Codes from the 2026-09-30 research: real-format kernel lines put into the recorded 7.0 boot, so the
    whole path runs (the recorder's filter, probes, rules, trees)."""

    T = "2026-09-30T20:02:00-04:00 HOST kernel: "
    LINES = {
        "P101": "CPU3: Package temperature above threshold, cpu clock throttled (total events = 12)",
        "P301": "mce: [Hardware Error]: Machine check events logged",
        "P302": "Out of memory: Killed process 4242 (firefox) total-vm:9000000kB, anon-rss:4000000kB",
        "B301": "BUG: kernel NULL pointer dereference, address: 0000000000000008",
        "A101": "traps: firefox[3000] general protection fault ip:7f00 sp:7ffd error:0 in libxul.so[7f00+1000]",
        "D301": 'ntfs3(sdb1): volume is dirty and "force" flag is not set!',
        "D302": "usb 1-4: device descriptor read/64, error -71",
    }

    @classmethod
    def setUpClass(cls):
        with open(os.path.join(FIX, "2026-09-30-v300-during-7.0.json"), encoding="utf-8") as f:
            cls.raw = json.load(f)
        cls.now_key = next(k for k in cls.raw["cmd"] if k.startswith("journalctl -b 725a44f9") and " -k " in k)

    def with_lines(self, *lines: str) -> dict:
        raw = copy.deepcopy(self.raw)
        raw["cmd"][self.now_key] += "".join(self.T + l + "\n" for l in lines)
        return probes.collect(FixtureSource(raw))

    def test_each_kernel_event_sets_its_code_active(self):
        for code, line in self.LINES.items():
            f = codes(self.with_lines(line))
            self.assertIn(code, f, code)
            self.assertEqual(f[code]["status"], "active", code)
            self.assertTrue(probes.keep_line(self.T + line), code)  # a recorded case would keep it

    def test_program_crash_is_not_a_kernel_error(self):
        f = codes(self.with_lines(self.LINES["A101"], "gimp[3100]: segfault at 0 ip 0 sp 0 error 4 in libgimp.so"))
        self.assertNotIn("B301", f)
        self.assertEqual(f["A101"]["facts"]["programs"], "firefox, gimp")

    def test_oom_names_the_program(self):
        self.assertEqual(codes(self.with_lines(self.LINES["P302"]))["P302"]["facts"]["details"], "firefox")

    def test_ntfs_device_both_message_forms(self):
        for line, dev in ((self.LINES["D301"], "sdb1"), ("ntfs3: sdc2: volume is dirty and \"force\" flag is not set!", "sdc2")):
            self.assertEqual(codes(self.with_lines(line))["D301"]["facts"]["device"], dev)

    def test_xid_79_fell_off_and_shutdown_xid_is_minor(self):
        fell = codes(self.with_lines("NVRM: Xid (PCI:0000:01:00): 79, pid=0, name=Xorg, GPU has fallen off the bus."))
        self.assertEqual(fell["G102"]["cause"], "fell_off_bus")
        self.assertEqual(fell["G102"]["status"], "active")
        # the real case: 35 x Xid 32 from modprobe in the second before a shutdown — a driver message, not a hang
        self.assertEqual(codes(case("2026-09-30-v300-after-6.8.json"))["G102"]["cause"], "driver_message")

    def test_amd_ring_timeout_is_a_hang(self):
        f = codes(self.with_lines("amdgpu 0000:03:00.0: [drm:amdgpu_job_timedout [amdgpu]] *ERROR* ring gfx timeout, signaled seq=1"))
        self.assertEqual(f["G102"]["cause"], "hang")

    def test_assistant_server_crash_with_disk_errors(self):
        x = codes(case("2026-09-30-v300-after-6.8.json"))["X101"]  # real: llama-server crashed in two 7.0 boots
        self.assertEqual((x["status"], x["cause"]), ("seen", "with_disk_errors"))
        self.assertIn("7.0.0-34-generic", x["facts"]["kernels"])

    def test_wifi(self):
        e = self.with_lines("iwlwifi 0000:02:00.0: Direct firmware load for iwlwifi-so-a0-hr-b0-83.ucode failed with error -2")
        e["wifi"] = {"hardware": ["Wi-Fi 6 AX201"], "devices": [], "switches": []}
        f = codes(e)["N102"]
        self.assertEqual(f["cause"], "firmware")
        self.assertIn("iwlwifi-so-a0-hr-b0-83.ucode", f["facts"]["firmware"])
        e["wifi"] = {"hardware": ["x"], "devices": ["wlp2s0"], "switches": [{"name": "phy0", "soft": True, "hard": False}]}
        f = codes(e)
        self.assertNotIn("N102", f)
        self.assertEqual(f["N101"]["cause"], "soft")
        e["wifi"]["switches"][0]["hard"] = True
        self.assertEqual(codes(e)["N101"]["cause"], "hard")

    def test_disk_full(self):
        e = copy.deepcopy(case("2026-09-30-v300-during-7.0.json"))
        e["space"] = [{"mount": "/", "device": "/dev/sda2", "size_gb": 118.0, "free_gb": 1.2, "free_pct": 1}]
        self.assertEqual(codes(e)["I303"]["cause"], "nearly_full")
        e["space"][0]["free_gb"] = 0.2
        self.assertEqual(codes(e)["I303"]["cause"], "full")
        e["space"] = [{"mount": "/boot", "device": "/dev/sda1", "size_gb": 1.0, "free_gb": 0.05, "free_pct": 5}]
        self.assertEqual(codes(e)["I303"]["cause"], "boot_full")
        e["space"] = [{"mount": "/", "device": "/dev/sda2", "size_gb": 118.0, "free_gb": 40.0, "free_pct": 34}]
        self.assertNotIn("I303", codes(e))

    def test_broken_packages_and_user_units(self):
        e = copy.deepcopy(case("2026-09-30-v300-during-7.0.json"))
        e["apt_check"] = "E: Unmet dependencies. Try 'apt --fix-broken install' with no packages"
        e["user_failed_units"] = ["pipewire.service"]
        f = codes(e)
        self.assertEqual(f["S102"]["status"], "active")
        self.assertEqual(f["U201"]["facts"]["units"], "pipewire.service")

    def test_snapshots_advice_only_when_known(self):
        e = copy.deepcopy(case("2026-09-30-v300-during-7.0.json"))
        self.assertEqual(codes(e)["S601"]["status"], "advice")  # the real SSD install: Timeshift not set up
        e["timeshift"] = {"configured": None}
        self.assertNotIn("S601", codes(e))  # couldn't read it: say nothing
        e["timeshift"] = {"configured": True, "schedule": ["daily", "boot"]}
        self.assertNotIn("S601", codes(e))

    def test_advice_never_rides_along_with_answers(self):
        rep = report.build(case("2026-09-30-v300-after-6.8.json"), rules.evaluate(case("2026-09-30-v300-after-6.8.json")), now="x")
        self.assertFalse(any(f["now"] for f in report.guide_view(rep)["faults"]))


class Trees(unittest.TestCase):
    def test_every_cause_has_words_and_fixes_entry(self):
        with open(report.TREES, encoding="utf-8") as f:
            trees = json.load(f)["codes"]
        for rule in rules.RULES:
            code = rule.__name__.upper()
            self.assertIn(code, trees, code)
        for code, t in trees.items():
            for cause in t["causes"]:
                self.assertIn(cause, t["fixes"], (code, cause))
            for fixes in t["fixes"].values():
                for fx in fixes:
                    self.assertIn(fx.get("needs"), ("none", "user", "admin"), (code, fx))


if __name__ == "__main__":
    unittest.main()
