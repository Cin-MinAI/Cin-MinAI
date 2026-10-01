# SPDX-License-Identifier: GPL-3.0-or-later
"""The first slice's monitors (SPEC §20.9): boot record (1, 2.1, 10.4), drivers and kernels (2.2, 3.1, 6.4),
storage and its link (2.3), packages (6.1, 6.3). Each reads what an unprivileged user in the `adm` group can
(Mint's first user is): the kernel log of recent boots, /proc, /sys, dpkg and dkms. What needs root (SMART)
is listed as not read, so a reader knows what isn't known (§20.5, readiness).

collect() returns plain data, the same on every machine; rules.py turns it into codes.
"""

from __future__ import annotations

import os
import re

BOOTS_BACK = 10  # how many earlier boots the kernel log is read for (the change lens: what differs between them)

# kernel log lines a probe looks at; a recorded fixture keeps only these
RX = {
    "version": re.compile(r"Linux version (\S+)"),
    "secureboot": re.compile(r"secureboot: Secure boot (enabled|disabled)"),
    "ata_model": re.compile(r"\b(ata\d+)\.\d+: ATA-\d+: (.+?), \S+, max "),
    "ata_exception": re.compile(r"\b(ata\d+)\.\d+: exception Emask"),
    "ata_serror": re.compile(r"\b(ata\d+): SError: \{ ([^}]*) \}"),
    "ata_error": re.compile(r"\b(ata\d+)\.\d+: error: \{ ([^}]*) \}"),
    "ata_failed": re.compile(r"\b(ata\d+)\.\d+: failed command: (\w+)"),
    "ata_cmd_size": re.compile(r"\b(ata\d+)\.\d+: cmd .* dma (\d+) "),
    "ata_limit": re.compile(r"\b(ata\d+): limiting SATA link speed to ([\d.]+ Gbps)"),
    "io_error": re.compile(r"I/O error, dev (\w+), sector \d+ op 0x\d+:\((\w+)\)"),
    "ext4_error": re.compile(r"EXT4-fs (error|warning) \(device (\w+)\)"),
    "data_loss": re.compile(r"EXT4-fs \((\w+)\): .*potential data loss"),
    "aborted_journal": re.compile(r"\((\w+)\): Detected aborted journal|Aborting journal on device (\w+)"),
    "remount_ro": re.compile(r"EXT4-fs \((\w+)\): Remounting filesystem read-only"),
    "zstd_fail": re.compile(r"ZSTD-decompression failed|zstd_decompress.*corrupt", re.I),
    "sig_fail": re.compile(r"module verification failed|Key was rejected by service|Loading of unsigned module"),
    "nvrm_error": re.compile(r"NVRM: (?!loading).*(?:fail|error|mismatch|not supported)", re.I),
    "nvidia_loaded": re.compile(r"NVRM: loading NVIDIA"),
    # the end of a boot's system log: a clean shutdown says so (10.4)
    "shutdown": re.compile(r"systemd-shutdown|Journal stopped|Reached target .*(Power-Off|Reboot|Shutdown)"),
}


def keep_line(line: str) -> bool:
    return any(rx.search(line) for rx in RX.values())


def _kernel_log(src, boot: str) -> list[str]:
    out = src.run(["journalctl", "-b", boot, "-k", "-q", "--no-pager", "-o", "short-iso"])
    return [l for l in out.splitlines() if keep_line(l)]


def boot_list(src) -> list[dict]:
    rows = []
    for line in src.run(["journalctl", "--list-boots", "--no-pager"]).splitlines():
        m = re.match(r"\s*(-?\d+)\s+([0-9a-f]{32})\s+(\w{3} \S+ \S+ \S+)\s+(\w{3} \S+ \S+ \S+)", line)
        if m:
            rows.append({"offset": int(m.group(1)), "id": m.group(2), "first": m.group(3), "last": m.group(4)})
    return sorted(rows, key=lambda r: r["offset"])[-(BOOTS_BACK + 1):]


def read_boot(src, boot: dict) -> dict:
    """One boot as the kernel log tells it: kernel, Secure Boot, disk-link and filesystem errors, driver."""
    lines = _kernel_log(src, boot["id"])
    b = {**boot, "kernel": None, "secure_boot": None, "ata_models": {}, "links": {}, "io_errors": {},
         "fs_errors": {}, "data_loss": 0, "aborted_journal": False, "remount_ro": [], "zstd_fail": 0,
         "sig_fail": 0, "nvrm_errors": [], "nvidia_loaded": False, "evidence": []}

    def link(port: str) -> dict:
        return b["links"].setdefault(port, {"exceptions": 0, "serror": [], "drive_errors": [], "failed": {},
                                            "largest_failed_bytes": 0, "limited_to": None})

    for line in lines:
        if b["kernel"] is None and (m := RX["version"].search(line)):
            b["kernel"] = m.group(1)
        if m := RX["secureboot"].search(line):
            b["secure_boot"] = m.group(1) == "enabled"
        if m := RX["ata_model"].search(line):
            b["ata_models"][m.group(1)] = m.group(2).strip()
        hit = True
        if m := RX["ata_exception"].search(line):
            link(m.group(1))["exceptions"] += 1
        elif m := RX["ata_serror"].search(line):
            l = link(m.group(1))
            l["serror"] = sorted(set(l["serror"]) | set(m.group(2).split()))
        elif m := RX["ata_error"].search(line):
            l = link(m.group(1))
            l["drive_errors"] = sorted(set(l["drive_errors"]) | set(m.group(2).split()))
        elif m := RX["ata_failed"].search(line):
            f = link(m.group(1))["failed"]
            f[m.group(2)] = f.get(m.group(2), 0) + 1
        elif m := RX["ata_cmd_size"].search(line):
            l = link(m.group(1))
            l["largest_failed_bytes"] = max(l["largest_failed_bytes"], int(m.group(2)))
            hit = False  # too many to keep as evidence
        elif m := RX["ata_limit"].search(line):
            link(m.group(1))["limited_to"] = m.group(2)
        elif m := RX["io_error"].search(line):
            key = f"{m.group(1)} {m.group(2).lower()}"
            b["io_errors"][key] = b["io_errors"].get(key, 0) + 1
        elif m := RX["data_loss"].search(line):
            b["data_loss"] += 1
        elif m := RX["aborted_journal"].search(line):  # before ext4_error: the line is an "EXT4-fs error" too
            b["aborted_journal"] = True
        elif m := RX["remount_ro"].search(line):
            b["remount_ro"].append(m.group(1))
        elif m := RX["ext4_error"].search(line):
            b["fs_errors"][m.group(2)] = b["fs_errors"].get(m.group(2), 0) + 1
        elif RX["zstd_fail"].search(line):
            b["zstd_fail"] += 1
        elif RX["sig_fail"].search(line):
            b["sig_fail"] += 1
        elif RX["nvrm_error"].search(line):
            b["nvrm_errors"].append(line.split("kernel: ", 1)[-1][:200])
        elif RX["nvidia_loaded"].search(line):
            b["nvidia_loaded"] = True
        else:
            hit = False
        if hit and len(b["evidence"]) < 12:
            b["evidence"].append(line[:240])
    if boot["offset"] != 0:
        tail = src.run(["journalctl", "-b", boot["id"], "-q", "--no-pager", "-n", "40", "-o", "cat"])
        b["clean_end"] = bool(RX["shutdown"].search(tail))
    return b


def packages(src) -> dict:
    out = src.run(["dpkg-query", "-W", "-f", "${Package} ${Version} ${db:Status-Abbrev}\n",
                   "nvidia-driver-*", "linux-image-*", "linux-generic*", "linux-headers-*"])
    pk = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[2].startswith("ii"):
            pk[parts[0]] = parts[1]
    nvidia = sorted(p for p in pk if re.fullmatch(r"nvidia-driver-\d+(-open|-server)?", p))
    meta = sorted(p for p in pk if p.startswith("linux-generic"))
    return {"nvidia_driver": nvidia[-1] if nvidia else None, "kernel_meta": meta,
            "headers": sorted(p[len("linux-headers-"):] for p in pk if re.match(r"linux-headers-\d", p))}


def dkms(src) -> dict:
    """{kernel: {"module": "nvidia/580.178.04", "state": "installed", "warning": "..."}}"""
    out = {}
    for line in src.run(["dkms", "status"]).splitlines():
        m = re.match(r"(\S+?)/(\S+?), (\S+?), \S+?: (\w+)(?: \((.+)\))?", line)
        if m:
            out[m.group(3)] = {"module": f"{m.group(1)}/{m.group(2)}", "state": m.group(4), "warning": m.group(5)}
    return out


def disks(src) -> dict:
    out = {}
    for d in src.glob("/sys/block/sd*"):
        name = os.path.basename(d)
        out[name] = {"model": src.read(f"{d}/device/model").strip(),
                     "max_sectors_kb": src.read(f"{d}/queue/max_sectors_kb").strip() or None}
    return out


def root_mount(src) -> dict:
    for line in src.read("/proc/mounts").splitlines():
        f = line.split()
        if len(f) >= 4 and f[1] == "/":
            return {"device": f[0], "fstype": f[2], "read_only": f[3].split(",")[0] == "ro"}
    return {}


def collect(src) -> dict:
    boots = [read_boot(src, b) for b in boot_list(src)]
    modules = {l.split()[0] for l in src.read("/proc/modules").splitlines() if l.strip()}
    kernel = src.read("/proc/sys/kernel/osrelease").strip()
    return {
        "kernel": kernel,
        "kernels_installed": sorted(os.path.basename(p)[len("vmlinuz-"):] for p in src.glob("/boot/vmlinuz-*")),
        "packages": packages(src),
        "dkms": dkms(src),
        "nvidia_module_loaded": "nvidia" in modules,
        "nvidia_version_loaded": (re.search(r"Kernel Module\s+(?:for x86_64\s+)?([\d.]+)",
                                            src.read("/proc/driver/nvidia/version")) or [None, None])[1],
        "root": root_mount(src),
        "disks": disks(src),
        "failed_units": [l.split()[0] for l in src.run(["systemctl", "--failed", "--no-legend", "--plain"]).splitlines()
                         if l.strip()],
        "dpkg_audit": src.run(["dpkg", "--audit"]).strip(),
        "reboot_required": bool(src.read("/var/run/reboot-required")),
        "boots": boots,
        "not_read": ["SMART (needs the system service, as root)"],
    }
