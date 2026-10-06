# SPDX-License-Identifier: GPL-3.0-or-later
"""Fail-closed argument validation for the root admin mechanism.

These functions contain no D-Bus or polkit code so the rejection boundary can be
unit-tested without installing or starting the mechanism.
"""

from __future__ import annotations

import os
import re
import stat
import subprocess
from collections.abc import Callable, Iterable, Sequence


class Reject(ValueError):
    """The request is outside the mechanism's deliberately small vocabulary."""


UNIT_RE = re.compile(r"^[A-Za-z0-9@_.:\-]{1,200}\.(service|socket|timer|path|target)$")
PROTECTED_UNITS = re.compile(
    r"^(dbus|dbus-broker|polkit|systemd-.*|user@.*|user-runtime-dir@.*|getty@.*|"
    r"lightdm|gdm3?|sddm|display-manager|cinminai-admin)\.")
PKG_RE = re.compile(r"^[a-z0-9][a-z0-9+.\-]{0,99}$")
PROTECTED_PKGS = re.compile(
    r"^(apt|dpkg|bash|coreutils|dbus.*|libc6|linux-.*|grub.*|shim.*|initramfs-tools.*|cryptsetup.*|"
    r"lvm2|mdadm|mount|util-linux|login|passwd|polkitd|pkexec|sudo|systemd.*|udev|kmod|python3.*|"
    r"libglib2\.0-0.*|cinnamon.*|mint-.*|lightdm|cinminai-.*|base-files|init|ubuntu-.*keyring)$")
MODULE_RE = re.compile(r"^[A-Za-z0-9_]{1,64}$")
PROTECTED_MODULES = re.compile(
    r"^(ext[234]|btrfs|xfs|vfat|fat|fuse|overlay|loop|dm_.*|md_mod|nvme.*|ahci|ata.*|sd_mod|"
    r"usb_storage|uas|i8042|usbhid|hid.*|evdev|serio|drm.*|nvidia.*|amdgpu|i915|nouveau|"
    r"bridge|bonding|cfg80211|mac80211|rfkill)$")
# write_file is an allowlist, not a denylist: much of /etc is code run as root
# (dispatcher scripts, kernel hooks, logrotate, anything shell-sourced), and a
# person approving a password dialog can't tell which.  The assistant writes only
# its own drop-in files (cinminai-<name>.conf, so undo = write it back empty) in
# directories whose every line is checked here.  New places need a checker.
OWN_FILE_RE = re.compile(r"^cinminai-[a-z0-9][a-z0-9-]{0,40}\.conf$")
MODPROBE_LINE_RE = re.compile(
    r"^(options [A-Za-z0-9_-]{1,64}( [A-Za-z0-9_]{1,64}=[A-Za-z0-9_.,:-]{1,128}){1,16}"
    r"|blacklist [A-Za-z0-9_-]{1,64})$")
# Blacklisting these would leave the machine unbootable or without a keyboard;
# display drivers (nouveau, amdgpu, i915) can be blacklisted: the firmware
# framebuffer still draws the screen, and blacklisting nouveau is a common fix.
BLACKLIST_PROTECTED = re.compile(
    r"^(ext[234]|btrfs|xfs|vfat|fat|fuse|overlay|loop|dm_.*|md_mod|nvme.*|ahci|ata.*|sd_mod|"
    r"usb_storage|uas|i8042|usbhid|hid.*|evdev|serio|xhci.*|ehci.*)$")
SYSCTL_LINE_RE = re.compile(r"^([a-z0-9_.]+) ?= ?([0-9]{1,10})$")
SYSCTL_KEYS = {  # key: (lowest, highest)
    "vm.swappiness": (0, 200),
    "vm.vfs_cache_pressure": (1, 1000),
    "vm.max_map_count": (65530, 2147483642),
    "fs.inotify.max_user_watches": (8192, 4194304),
    "fs.inotify.max_user_instances": (128, 8192),
}


def _modprobe_line(line: str) -> None:
    if not MODPROBE_LINE_RE.fullmatch(line):
        raise Reject(f"modprobe.d accepts only 'options' and 'blacklist' lines: {line[:80]!r}")
    word, module = line.split()[:2]
    if word == "blacklist" and BLACKLIST_PROTECTED.fullmatch(module.replace("-", "_")):
        raise Reject(f"{module} is needed to boot or type; it can't be blacklisted")


def _sysctl_line(line: str) -> None:
    match = SYSCTL_LINE_RE.fullmatch(line)
    if not match or match.group(1) not in SYSCTL_KEYS:
        raise Reject(f"sysctl.d accepts only {', '.join(sorted(SYSCTL_KEYS))}: {line[:80]!r}")
    low, high = SYSCTL_KEYS[match.group(1)]
    if not low <= int(match.group(2)) <= high:
        raise Reject(f"{match.group(1)} must be between {low} and {high}")


WRITE_DIRS = {"/etc/modprobe.d": _modprobe_line, "/etc/sysctl.d": _sysctl_line}
MAX_WRITE = 64 << 10
GLOB_CHARS = "*?["

# run_argv is not an arbitrary root shell.  It is the typed escape hatch for the
# destructive-operation dialog and currently permits only explicit block-device
# maintenance programs.  New programs need their own validator here.
BLOCK_COMMANDS = {
    "/usr/sbin/wipefs", "/usr/sbin/blkdiscard", "/usr/sbin/mkfs.ext4",
    "/usr/sbin/mkfs.vfat",
}
LABEL_RE = re.compile(r"^[A-Za-z0-9 _.-]{1,32}$")


def check_unit(unit: str) -> str:
    if not UNIT_RE.fullmatch(unit):
        raise Reject(f"not a unit name: {unit!r}")
    if PROTECTED_UNITS.match(unit):
        raise Reject(f"{unit} is protected")
    return unit


def check_package(package: str, removing: bool = False) -> str:
    if not PKG_RE.fullmatch(package):
        raise Reject(f"not a package name: {package!r}")
    # apt-get reads a trailing '-' on install as "remove" and a trailing '+' on
    # remove as "install" (apt 2.8: `install coreutils-` removes coreutils), so
    # the dialog would name the opposite of what runs.
    if package.endswith("-" if not removing else "+"):
        raise Reject(f"{package!r} would make apt do the opposite action")
    if removing and PROTECTED_PKGS.match(package):
        raise Reject(f"{package} is protected")
    return package


def check_write(path: str, content: bytes, mode: int) -> str:
    if not isinstance(path, str) or "\0" in path or any(c in path for c in GLOB_CHARS):
        raise Reject("path contains an invalid character")
    parent, name = os.path.split(path)
    if os.path.normpath(path) != path or parent not in WRITE_DIRS or not OWN_FILE_RE.fullmatch(name):
        raise Reject(f"only cinminai-<name>.conf in {' or '.join(sorted(WRITE_DIRS))} can be written")
    if len(content) > MAX_WRITE:
        raise Reject(f"content too large ({len(content)} bytes)")
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise Reject("content is not UTF-8 text") from exc
    if "\r" in text or "\\\n" in text:
        raise Reject("content has carriage returns or line continuations")
    for line in text.split("\n"):
        line = line.strip()
        if line and not line.startswith("#"):
            WRITE_DIRS[parent](line)
    if not os.path.isdir(parent) or os.path.realpath(parent) != parent:
        raise Reject(f"{parent} is unresolved or goes through a symlink")
    if os.path.islink(path):
        raise Reject(f"{path} is a symlink")
    if os.path.exists(path) and not stat.S_ISREG(os.lstat(path).st_mode):
        raise Reject(f"{path} is not a regular file")
    if mode not in (0o644, 0o640, 0o600):
        raise Reject(f"mode {oct(mode)} not allowed")
    return path


def installed_module_name(module: str) -> str:
    """Resolve an installed module/alias to exactly one canonical module name."""
    if not MODULE_RE.fullmatch(module):
        raise Reject(f"not a module name: {module!r}")
    try:
        result = subprocess.run(
            ["/sbin/modinfo", "-F", "name", "--", module], check=False,
            capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Reject(f"could not resolve module {module!r}") from exc
    names = {line.strip() for line in result.stdout.splitlines() if line.strip()}
    if result.returncode or len(names) != 1:
        raise Reject(f"module {module!r} does not resolve to one installed module")
    name = names.pop().replace("-", "_")
    if not MODULE_RE.fullmatch(name):
        raise Reject("resolved module name is invalid")
    return name


def check_module(module: str, *, unloading: bool = False,
                 resolver: Callable[[str], str] = installed_module_name) -> str:
    if not MODULE_RE.fullmatch(module):
        raise Reject(f"not a module name: {module!r}")
    name = resolver(module)
    if unloading and PROTECTED_MODULES.fullmatch(name):
        raise Reject(f"{name} is boot-, storage-, display-, input-, or network-critical")
    return name


def boot_devices() -> set[str]:
    """Return root/boot devices, their ancestors, and every sibling on those disks,
    plus every disk with anything mounted or used as swap."""
    protected: set[str] = set()
    sources: list[str] = []
    for mountpoint in ("/", "/boot", "/boot/efi"):
        try:
            mount = subprocess.run(
                ["/usr/bin/findmnt", "-nro", "SOURCE", "--target", mountpoint],
                check=False, capture_output=True, text=True, timeout=5,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise Reject("cannot determine boot-critical devices") from exc
        source = mount.stdout.strip().split("[", 1)[0]
        if mount.returncode == 0 and source.startswith("/dev/"):
            sources.append(os.path.realpath(source))
    if not sources:
        raise Reject("cannot determine the root device; refusing block operation")
    # A disk in use anywhere (a separate /home, a mounted USB drive, swap) is
    # protected too: the ancestors loop below covers the whole disk under it.
    try:
        mounted = subprocess.run(
            ["/usr/bin/findmnt", "-nro", "SOURCE"], check=False,
            capture_output=True, text=True, timeout=5,
        )
        swaps = subprocess.run(
            ["/usr/sbin/swapon", "--show=NAME", "--noheadings", "--raw"], check=False,
            capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Reject("cannot determine mounted devices") from exc
    if mounted.returncode or swaps.returncode:
        raise Reject("cannot determine mounted devices")
    in_use = [line.strip().split("[", 1)[0] for line in (mounted.stdout + swaps.stdout).splitlines()]
    in_use = [os.path.realpath(device) for device in in_use if device.startswith("/dev/")]
    for source in in_use:
        try:
            chain = subprocess.run(
                ["/usr/bin/lsblk", "-snrpo", "PATH", source], check=False,
                capture_output=True, text=True, timeout=5,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise Reject("cannot resolve mounted-device ancestry") from exc
        if chain.returncode:
            raise Reject("cannot resolve mounted-device ancestry")
        protected.update(os.path.realpath(line.strip()) for line in chain.stdout.splitlines() if line.strip())
        protected.add(source)
    for source in sources:
        try:
            chain = subprocess.run(
                ["/usr/bin/lsblk", "-snrpo", "PATH", source], check=False,
                capture_output=True, text=True, timeout=5,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise Reject("cannot resolve boot-device ancestry") from exc
        if chain.returncode:
            raise Reject("cannot resolve boot-device ancestry")
        protected.update(os.path.realpath(line.strip()) for line in chain.stdout.splitlines() if line.strip())
        protected.add(os.path.realpath(source))
    # If root is on one partition, every sibling partition on that physical
    # disk is still boot-critical: formatting one may destroy EFI or recovery.
    for device in list(protected):
        try:
            tree = subprocess.run(
                ["/usr/bin/lsblk", "-nrpo", "PATH", device], check=False,
                capture_output=True, text=True, timeout=5,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise Reject("cannot resolve boot-device descendants") from exc
        if tree.returncode:
            raise Reject("cannot resolve boot-device descendants")
        protected.update(os.path.realpath(line.strip()) for line in tree.stdout.splitlines() if line.strip())
    return protected


def check_block_target(path: str, protected: Iterable[str]) -> str:
    if not isinstance(path, str) or any(c in path for c in GLOB_CHARS) or "\0" in path:
        raise Reject("block target must be one explicit path")
    if not path.startswith("/dev/") or os.path.normpath(path) != path or not os.path.exists(path):
        raise Reject(f"unresolved block target: {path!r}")
    resolved = os.path.realpath(path)
    try:
        is_block = stat.S_ISBLK(os.stat(resolved).st_mode)
    except OSError as exc:
        raise Reject(f"unresolved block target: {path!r}") from exc
    if not is_block:
        raise Reject(f"not a block device: {path!r}")
    if resolved in {os.path.realpath(p) for p in protected}:
        raise Reject(f"{path} is the system disk or in use (mounted or swap); unmount it first")
    return resolved


def check_run_argv(argv: Sequence[str], *, protected: Iterable[str] | None = None) -> list[str]:
    if not isinstance(argv, (list, tuple)) or not (2 <= len(argv) <= 32):
        raise Reject("argv must contain a program and explicit target")
    if any(not isinstance(a, str) or not a or len(a) > 4096 or "\0" in a for a in argv):
        raise Reject("argv contains an invalid argument")
    if any(any(c in a for c in GLOB_CHARS) for a in argv):
        raise Reject("globs are not accepted")
    program = argv[0]
    if program not in BLOCK_COMMANDS:
        raise Reject(f"program is not allowlisted: {program!r}")
    # Every allowed command operates on exactly one explicit final device.  A
    # leading '-' target would be parsed as an option, so it is rejected too.
    target = argv[-1]
    if target.startswith("-"):
        raise Reject("missing explicit block target")
    options = list(argv[1:-1])
    if program == "/usr/sbin/wipefs":
        if any(option not in ("-a", "--all", "-f", "--force") for option in options):
            raise Reject("wipefs accepts only --all and --force")
        if not any(option in ("-a", "--all") for option in options):
            raise Reject("wipefs must explicitly request --all")
    elif program == "/usr/sbin/blkdiscard":
        if any(option not in ("-f", "--force") for option in options):
            raise Reject("blkdiscard accepts only --force")
    else:
        allowed_switch = "-F" if program.endswith("mkfs.ext4") else "-I"
        allowed_label = "-L" if program.endswith("mkfs.ext4") else "-n"
        index = 0
        while index < len(options):
            if options[index] == allowed_switch:
                index += 1
            elif options[index] == allowed_label and index + 1 < len(options) and LABEL_RE.fullmatch(options[index + 1]):
                index += 2
            else:
                raise Reject("mkfs accepts only its force switch and a simple volume label")
    safe_target = check_block_target(target, boot_devices() if protected is None else protected)
    return [*argv[:-1], safe_target]
