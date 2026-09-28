# SPDX-License-Identifier: GPL-3.0-or-later
"""What the model can run on, read at load time (SPEC §4.2, §9): graphics cards and their drivers, free
graphics memory, the desktop's memory reserve, processor cores. Read-only: /sys, /proc, nvidia-smi.
Never decides from a card's name alone.
"""

from __future__ import annotations

import dataclasses
import glob
import os
import re
import subprocess

VENDORS = {"0x10de": "nvidia", "0x1002": "amd", "0x8086": "intel"}


@dataclasses.dataclass
class Gpu:
    vendor: str            # nvidia | amd | intel | other
    driver: str            # the kernel driver in use: nvidia, nouveau, amdgpu, radeon, i915, xe, "" (none)
    name: str = ""
    vram_total_mib: int | None = None
    vram_free_mib: int | None = None


def _read(path: str) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read().strip()
    except OSError:
        return ""


def _run(argv: list[str], timeout: float = 5) -> str:
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=True).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def gpus(sysfs: str = "/sys") -> list[Gpu]:
    out, seen = [], set()
    for card in sorted(glob.glob(f"{sysfs}/class/drm/card[0-9]*")):
        if "-" in os.path.basename(card):
            continue  # connectors (card0-HDMI-A-1) are listed next to the cards
        dev = os.path.realpath(os.path.join(card, "device"))
        if dev in seen:
            continue
        seen.add(dev)
        vendor = VENDORS.get(_read(os.path.join(dev, "vendor")), "other")
        drv = os.path.basename(os.path.realpath(os.path.join(dev, "driver"))) if os.path.exists(os.path.join(dev, "driver")) else ""
        g = Gpu(vendor, drv)
        if drv == "amdgpu":
            total, used = _read(os.path.join(dev, "mem_info_vram_total")), _read(os.path.join(dev, "mem_info_vram_used"))
            if total.isdigit() and used.isdigit():
                g.vram_total_mib, g.vram_free_mib = int(total) >> 20, (int(total) - int(used)) >> 20
        out.append(g)
    nv = [g for g in out if g.driver == "nvidia"]
    if nv:
        rows = [r.split(", ") for r in _run(["nvidia-smi", "--query-gpu=name,memory.total,memory.free",
                                             "--format=csv,noheader,nounits"]).splitlines() if r.strip()]
        for g, row in zip(nv, rows):  # both in PCI order
            if len(row) == 3 and row[1].strip().isdigit():
                g.name, g.vram_total_mib, g.vram_free_mib = row[0], int(row[1]), int(row[2])
    return out


def nvidia_free_mib() -> int | None:
    rows = _run(["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"]).split()
    return int(rows[0]) if rows and rows[0].isdigit() else None


def desktop_reserve_mib(sysfs: str = "/sys") -> int:
    """Graphics memory to leave free for the desktop (SPEC §4.2): 1.5 GB at 4K or with more than one
    screen, 0.8 GB otherwise. Read from the connected screens' preferred modes."""
    screens, pixels = 0, 0
    for conn in glob.glob(f"{sysfs}/class/drm/card[0-9]*-*"):
        if _read(os.path.join(conn, "status")) != "connected":
            continue
        screens += 1
        mode = (_read(os.path.join(conn, "modes")).splitlines() or [""])[0]
        m = re.match(r"(\d+)x(\d+)", mode)
        if m:
            pixels = max(pixels, int(m.group(1)) * int(m.group(2)))
    return 1536 if screens > 1 or pixels > 2560 * 1600 else 820


def physical_cores() -> int:
    """Cores, not hardware threads (llama.cpp runs best with one thread per core)."""
    cores = set()
    phys = core = None
    for line in _read("/proc/cpuinfo").splitlines():
        if line.startswith("physical id"):
            phys = line.split(":")[1].strip()
        elif line.startswith("core id"):
            core = line.split(":")[1].strip()
            cores.add((phys, core))
    return len(cores) or max(1, (os.cpu_count() or 2) // 2)


def ram_mib() -> int:
    m = re.search(r"MemTotal:\s+(\d+)", _read("/proc/meminfo"))
    return int(m.group(1)) >> 10 if m else 0
