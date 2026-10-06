# SPDX-License-Identifier: GPL-3.0-or-later
"""Negative tests for the cinminai-admin validation boundary."""

import json
import os
import stat
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

from cin_minai.admin import policy
from cin_minai.admin.mechanism import append_audit
from cin_minai import sandbox


class AdminPolicyTests(unittest.TestCase):
    def test_privilege_tools_and_shells_are_not_run_argv_programs(self):
        for program in ("/usr/bin/sudo", "/usr/bin/su", "/usr/bin/pkexec", "/bin/sh", "/bin/bash", "/usr/bin/python3"):
            with self.subTest(program=program), self.assertRaises(policy.Reject):
                policy.check_run_argv([program, "/dev/sdb"], protected=set())

    def test_broad_globs_are_rejected(self):
        with self.assertRaises(policy.Reject):
            policy.check_run_argv(["/usr/sbin/wipefs", "--all", "/dev/sd*"])
        with self.assertRaises(policy.Reject):
            policy.check_write("/etc/*.conf", b"x", 0o644)

    def test_unresolved_path_is_rejected(self):
        with self.assertRaises(policy.Reject):
            policy.check_write("/etc/cinminai-parent-that-does-not-exist/x.conf", b"x", 0o644)
        with self.assertRaisesRegex(policy.Reject, "unresolved"):
            policy.check_run_argv(["/usr/sbin/wipefs", "--all", "/dev/cinminai-missing"], protected=set())

    def test_protected_system_files_are_rejected(self):
        for path in ("/etc/sudoers", "/etc/shadow", "/etc/systemd/system/x.service", "/etc/apt/sources.list",
                     # code run as root that a denylist missed
                     "/etc/NetworkManager/dispatcher.d/99-x", "/etc/kernel/postinst.d/x", "/etc/logrotate.d/x",
                     "/etc/bash.bashrc", "/etc/rc.local", "/etc/default/grub", "/etc/udev/rules.d/99-x.rules",
                     # the right directories, but not the assistant's own file
                     "/etc/modprobe.d/blacklist.conf", "/etc/sysctl.d/99-sysctl.conf",
                     "/etc/modprobe.d/cinminai-x.conf/../alsa-base.conf", "/etc/modprobe.d/cinminai-X.conf"):
            with self.subTest(path=path), self.assertRaises(policy.Reject):
                policy.check_write(path, b"x", 0o600)

    def test_write_content_is_checked_line_by_line(self):
        ok = {
            "/etc/modprobe.d/cinminai-nouveau.conf": b"# Cin-MinAI: G101\nblacklist nouveau\noptions nouveau modeset=0\n",
            "/etc/modprobe.d/cinminai-nvidia.conf": b"options nvidia NVreg_PreserveVideoMemoryAllocations=1\n",
            "/etc/sysctl.d/cinminai-watches.conf": b"fs.inotify.max_user_watches = 524288\nvm.swappiness=10\n",
        }
        bad = {
            "/etc/modprobe.d/cinminai-a.conf": (
                b"install nouveau /bin/sh -c 'id > /tmp/x'\n",  # modprobe runs 'install' lines as root
                b"remove nvidia /bin/true\n",
                b"softdep nvidia pre: evil\n",
                b"options nvidia x=1 ; rm\n",
                b"options nvidia x=1 \\\n y=2\n",
                b"blacklist nvme\n",  # unbootable
                b"blacklist usbhid\n",
                b"options nvidia x=1\r\ninstall y /bin/sh\n",
                b"\xff\xfe",
            ),
            "/etc/sysctl.d/cinminai-a.conf": (
                b"kernel.core_pattern = |/tmp/x\n",  # runs a program as root on any crash
                b"kernel.modprobe = /tmp/x\n",
                b"vm.swappiness = 900\n",
                b"vm.swappiness = -1\n",
                b"-vm.swappiness = 10\n",
            ),
        }
        with mock.patch.object(policy.os.path, "isdir", return_value=True), \
             mock.patch.object(policy.os.path, "realpath", side_effect=lambda p: p), \
             mock.patch.object(policy.os.path, "exists", return_value=False):
            for path, content in ok.items():
                with self.subTest(path=path):
                    self.assertEqual(policy.check_write(path, content, 0o644), path)
            for path, contents in bad.items():
                for content in contents:
                    with self.subTest(content=content), self.assertRaises(policy.Reject):
                        policy.check_write(path, content, 0o644)

    def test_boot_critical_block_target_is_rejected(self):
        fake_block = SimpleNamespace(st_mode=stat.S_IFBLK)
        with mock.patch.object(policy.os.path, "exists", return_value=True), \
             mock.patch.object(policy.os.path, "realpath", side_effect=lambda p: p), \
             mock.patch.object(policy.os, "stat", return_value=fake_block):
            with self.assertRaisesRegex(policy.Reject, "boot-critical"):
                policy.check_run_argv(["/usr/sbin/wipefs", "--all", "/dev/nvme0n1"], protected={"/dev/nvme0n1"})

    def test_one_explicit_nonboot_block_target_is_normalized(self):
        fake_block = SimpleNamespace(st_mode=stat.S_IFBLK)
        with mock.patch.object(policy.os.path, "exists", return_value=True), \
             mock.patch.object(policy.os.path, "realpath", side_effect=lambda p: p), \
             mock.patch.object(policy.os, "stat", return_value=fake_block):
            self.assertEqual(
                policy.check_run_argv(["/usr/sbin/wipefs", "--all", "/dev/sdb"], protected={"/dev/nvme0n1"}),
                ["/usr/sbin/wipefs", "--all", "/dev/sdb"],
            )

    def test_allowlisted_program_options_are_still_narrow(self):
        fake_block = SimpleNamespace(st_mode=stat.S_IFBLK)
        with mock.patch.object(policy.os.path, "exists", return_value=True), \
             mock.patch.object(policy.os.path, "realpath", side_effect=lambda p: p), \
             mock.patch.object(policy.os, "stat", return_value=fake_block):
            for argv in (
                ["/usr/sbin/mkfs.ext4", "-d", "/home/mint", "/dev/sdb"],
                ["/usr/sbin/mkfs.vfat", "--invariant", "/dev/sdb"],
                ["/usr/sbin/wipefs", "--output", "/etc/shadow", "/dev/sdb"],
            ):
                with self.subTest(argv=argv), self.assertRaises(policy.Reject):
                    policy.check_run_argv(argv, protected=set())

    def test_protected_service_package_and_modules_are_rejected(self):
        for unit in ("dbus.service", "polkit.service", "cinminai-admin.service"):
            with self.assertRaises(policy.Reject):
                policy.check_unit(unit)
        for package in ("sudo", "systemd", "linux-image-generic", "linux-modules-extra-6.8.0", "grub-efi-amd64", "cinminai-daemon"):
            with self.assertRaises(policy.Reject):
                policy.check_package(package, removing=True)
        for package in ("coreutils-", "systemd-", "nano-"):
            with self.subTest(package=package), self.assertRaises(policy.Reject):
                policy.check_package(package)
        with self.assertRaises(policy.Reject):
            policy.check_package("nano+", removing=True)
        self.assertEqual(policy.check_package("g++"), "g++")
        for module in ("ext4", "nvme", "nvidia", "usbhid"):
            with self.assertRaises(policy.Reject):
                policy.check_module(module, unloading=True, resolver=lambda name: name)

    def test_module_name_cannot_be_an_option_or_path(self):
        for module in ("-r", "../../x", "x y", "x*"):
            with self.assertRaises(policy.Reject):
                policy.check_module(module, resolver=lambda name: name)


class AuditTests(unittest.TestCase):
    def test_records_are_append_only_and_hash_chained(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "admin.log")
            append_audit(path, {"event": "request", "request": "a"})
            append_audit(path, {"event": "rejected", "request": "a"})
            with open(path, encoding="utf-8") as stream:
                rows = [json.loads(line) for line in stream]
            self.assertEqual([row["seq"] for row in rows], [1, 2])
            self.assertEqual(rows[0]["prev"], "0" * 64)
            self.assertEqual(rows[1]["prev"], rows[0]["hash"])

    def test_invalid_tail_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "admin.log")
            with open(path, "w", encoding="utf-8") as stream:
                stream.write("not json\n")
            with self.assertRaises(RuntimeError):
                append_audit(path, {"event": "request"})

    def test_tampered_earlier_record_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "admin.log")
            append_audit(path, {"event": "request", "request": "a"})
            append_audit(path, {"event": "rejected", "request": "a"})
            with open(path, encoding="utf-8") as stream:
                text = stream.read().replace('"event":"request"', '"event":"approved"')
            with open(path, "w", encoding="utf-8") as stream:
                stream.write(text)
            with self.assertRaises(RuntimeError):
                append_audit(path, {"event": "request", "request": "b"})


class PackagePolicyTests(unittest.TestCase):
    def test_every_verb_uses_fresh_auth_admin(self):
        root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        path = os.path.join(root, "distro", "packages", "cinminai-admin", "root", "usr", "share", "polkit-1", "actions", "org.cinminai.admin.policy")
        with open(path, encoding="utf-8") as stream:
            text = stream.read()
        self.assertEqual(text.count('<action id="org.cinminai.admin.'), 8)
        self.assertEqual(text.count("<allow_active>auth_admin</allow_active>"), 8)
        self.assertNotIn("auth_admin_keep", text)

    def test_production_sandbox_never_falls_back_to_host_network(self):
        with mock.patch.object(sandbox.shutil, "which", return_value=None):
            self.assertEqual(sandbox.best_net(), "none")


if __name__ == "__main__":
    unittest.main()
