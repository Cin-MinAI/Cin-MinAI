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
WRITE_ROOT = "/etc/"
PROTECTED_PATHS = (
    "/etc/sudoers", "/etc/sudoers.d", "/etc/shadow", "/etc/gshadow", "/etc/passwd",
    "/etc/group", "/etc/polkit-1", "/etc/pam.d", "/etc/security", "/etc/dbus-1",
    "/etc/systemd", "/etc/apt", "/etc/cinminai", "/etc/ld.so", "/etc/profile",
    "/etc/environment", "/etc/crontab", "/etc/cron.", "/etc/fstab", "/etc/default/grub",
    "/etc/grub.d", "/etc/modprobe.d", "/etc/udev",
)
MAX_WRITE = 1 << 20
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
    if not path.startswith(WRITE_ROOT) or os.path.normpath(path) != path:
        raise Reject(f"only normalized absolute paths under {WRITE_ROOT} can be written")
    if any(path == p or path.startswith(p if p.endswith(".") else p + "/") or path.startswith(p + ".")
           for p in PROTECTED_PATHS):
        raise Reject(f"{path} is protected")
    parent = os.path.dirname(path)
    if not os.path.isdir(parent) or os.path.realpath(parent) != parent:
        raise Reject(f"{parent} is unresolved or goes through a symlink")
    if os.path.islink(path):
        raise Reject(f"{path} is a symlink")
    if os.path.exists(path) and not stat.S_ISREG(os.lstat(path).st_mode):
        raise Reject(f"{path} is not a regular file")
    if len(content) > MAX_WRITE:
        raise Reject(f"content too large ({len(content)} bytes)")
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
        raise Reject(f"{path} is boot-critical")
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
