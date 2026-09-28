# SPDX-License-Identifier: GPL-3.0-or-later
"""The guide's read-only tools for the Alpha (PLAN §4): inspect_system, open_app, and the answer for
request_install (not in the Alpha: it says how to install by hand). lookup_help is helpcards.py.

inspect_system returns the same shapes the guide was trained on (training/datasets/sessions/generate.py
`system_result`): short facts plus "open_with", the name of the settings page or program to fix it, in
the language of the desktop. Everything here reads (/sys, /proc, statvfs, nmcli, pactl, lpstat, apt's
simulation); nothing changes the system and nothing goes on the network.
"""

from __future__ import annotations

import datetime as dt
import glob
import json
import math
import os
import re
import subprocess

from cin_minai.inference import hardware

HOME = os.path.expanduser("~")


def run(argv: list[str], timeout: float = 5) -> str:
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=timeout,
                              env={**os.environ, "LC_ALL": "C.UTF-8"}).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def read(path: str) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read().strip()
    except OSError:
        return ""


def desktop_lang() -> str:
    """The desktop's language, one of the six (PLAN D25); names on screen are in this language."""
    for var in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        v = os.environ.get(var, "")
        if v and v not in ("C", "POSIX") and not v.startswith("C."):
            code = v.split(":")[0][:2].lower()
            return code if code in ("en", "es", "pt", "fr", "de", "ja") else "en"
    return "en"


class Tools:
    def __init__(self, labels: dict, desktop: dict, lang: str | None = None) -> None:
        self.labels, self.desktop = labels, desktop
        self.lang = lang or desktop_lang()

    def label(self, key: str) -> str:
        row = self.labels.get(key, {})
        return row.get(self.lang) or row.get("en", key)

    # --- inspect_system ---------------------------------------------------------------------------
    def inspect(self, topic: str) -> dict:
        fn = getattr(self, "_" + topic, None)
        if fn is None:
            return {"error": f"unknown topic {topic}"}
        try:
            return fn()
        except Exception as e:  # a broken probe must not take the answer down
            return {"error": f"couldn't read {topic}: {type(e).__name__}"}

    def _overview(self) -> dict:
        rel = read("/etc/cinminai-release")
        osname = re.search(r'PRETTY_NAME="?([^"\n]+)', rel or read("/etc/os-release"))
        cpu = re.search(r"model name\s*:\s*(.+)", read("/proc/cpuinfo"))
        st = os.statvfs("/")
        g = self._gpu_names()
        return {"open_with": self.label("system_info"), "os": osname.group(1) if osname else "Linux",
                "cpu": re.sub(r"\s+", " ", cpu.group(1)) if cpu else "unknown",
                "ram_gb": math.ceil(hardware.ram_mib() / 1024),  # the kernel keeps some: 31.3 -> 32 "gpu": ", ".join(g) or "none found",
                "disk_gb": round(st.f_blocks * st.f_frsize / 1e9)}

    def _storage(self) -> dict:
        st = os.statvfs(HOME)
        size, free = st.f_blocks * st.f_frsize, st.f_bavail * st.f_frsize
        folders = []
        for name in ("Videos", "Downloads", "Pictures", "Documents", "Music", "Desktop"):
            path = os.path.join(HOME, name)
            if os.path.isdir(path):
                out = run(["du", "-s", "--block-size=1", path], timeout=4).split()
                if out and out[0].isdigit():
                    folders.append({"path": "~/" + name, "gb": round(int(out[0]) / 1e9, 1)})
        folders = sorted((f for f in folders if f["gb"] > 0), key=lambda f: -f["gb"])[:2]
        return {"disks": [{"name": "Main disk", "size_gb": round(size / 1e9), "free_gb": round(free / 1e9),
                           "used_pct": round(100 * (size - free) / size) if size else 0}],
                "largest_folders": folders, "open_with": self.label("files")}

    def _updates(self) -> dict:
        sim = run(["apt-get", "-s", "-o", "Debug::NoLocking=1", "dist-upgrade"], timeout=30)
        inst = [l for l in sim.splitlines() if l.startswith("Inst ")]
        security = [l for l in inst if "-security" in l]
        stamps = [p for p in ("/var/lib/apt/periodic/update-success-stamp", "/var/cache/apt/pkgcache.bin")
                  if os.path.exists(p)]
        checked = "never"
        if stamps:
            days = (dt.date.today() - dt.date.fromtimestamp(max(os.path.getmtime(p) for p in stamps))).days
            checked = "today" if days <= 0 else "yesterday" if days == 1 else f"{days} days ago"
        return {"updates_available": len(inst), "security_updates": len(security), "last_checked": checked,
                "open_with": self.label("update_manager")}

    def _network(self) -> dict:
        radio = run(["nmcli", "-t", "-f", "WIFI", "general"]).strip()
        wifi: dict = {"enabled": radio == "enabled"}
        for line in run(["nmcli", "-t", "-f", "ACTIVE,SSID,SIGNAL", "device", "wifi", "list", "--rescan", "no"]).splitlines():
            parts = line.split(":")
            if len(parts) >= 3 and parts[0] == "yes":
                wifi.update(network=parts[1], signal_pct=int(parts[2]) if parts[2].isdigit() else None)
        wired = "no cable"
        for line in run(["nmcli", "-t", "-f", "TYPE,STATE", "device"]).splitlines():
            t, _, state = line.partition(":")
            if t == "ethernet" and state.startswith("connected"):
                wired = "connected"
        conn = run(["nmcli", "-t", "-f", "CONNECTIVITY", "general"]).strip()
        out = {"wifi": wifi, "wired": wired, "internet": conn == "full", "open_with": self.label("network")}
        if not conn:
            out["note"] = "network status not available"
        return out

    def _printers(self) -> dict:
        jobs: dict[str, int] = {}
        for line in run(["lpstat", "-o"]).splitlines():
            name = line.split()[0].rsplit("-", 1)[0] if line.strip() else ""  # job id: <printer>-<number>
            jobs[name] = jobs.get(name, 0) + 1
        printers = []
        for line in run(["lpstat", "-p"]).splitlines():
            m = re.match(r"printer (\S+) (?:is )?(idle|now printing|disabled)", line)
            if m:
                state = {"idle": "ready", "now printing": "printing", "disabled": "paused"}[m.group(2)]
                printers.append({"name": m.group(1), "state": state, "jobs_waiting": jobs.get(m.group(1), 0)})
        # Mint has no translation of "Printers" in some languages: then the settings (as in training)
        return {"printers": printers,
                "open_with": self.labels.get("printers", {}).get(self.lang) or self.label("system_settings")}

    def _sound(self) -> dict:
        default = run(["pactl", "get-default-sink"]).strip()
        try:
            sinks = json.loads(run(["pactl", "-f", "json", "list", "sinks"]) or "[]")
        except ValueError:
            sinks = []
        for s in sinks:
            if s.get("name") == default:
                vols = [int(str(v.get("value_percent", "0")).rstrip("%")) for v in (s.get("volume") or {}).values()]
                return {"output": s.get("description", default), "muted": bool(s.get("mute")),
                        "volume_pct": max(vols) if vols else None, "open_with": self.label("sound")}
        return {"output": None, "note": "no sound output found", "open_with": self.label("sound")}

    def _display(self) -> dict:
        monitors = []
        for conn in sorted(glob.glob("/sys/class/drm/card[0-9]*-*")):
            if read(os.path.join(conn, "status")) != "connected":
                continue
            kind = os.path.basename(conn).split("-", 1)[1]
            name = "Built-in display" if kind.startswith(("eDP", "LVDS", "DSI")) else edid_name(conn) or kind
            mode = (read(os.path.join(conn, "modes")).splitlines() or [""])[0]
            m = {"name": name, "connected": True, "resolution": mode or None}
            card = conn.rsplit("-", 1)[0].split("-")[0]  # /sys/class/drm/card1-HDMI-A-1 -> .../card1
            driver = os.path.basename(os.path.realpath(os.path.join(card, "device", "driver")))
            if driver != "nvidia":  # NVIDIA's own driver leaves "enabled" unset: a working screen would read as off
                m["on"] = read(os.path.join(conn, "enabled")) == "enabled"
            monitors.append(m)
        return {"monitors": monitors, "open_with": self.label("display")}

    def _battery(self) -> dict:
        for bat in sorted(glob.glob("/sys/class/power_supply/BAT*")):
            full = read(f"{bat}/energy_full") or read(f"{bat}/charge_full")
            design = read(f"{bat}/energy_full_design") or read(f"{bat}/charge_full_design")
            health = round(100 * int(full) / int(design)) if full.isdigit() and design.isdigit() and int(design) else None
            status = read(f"{bat}/status").lower()
            return {"battery": {"charge_pct": int(read(f"{bat}/capacity") or 0), "health_pct": health,
                                "state": {"not charging": "plugged in, not charging"}.get(status, status)},
                    "open_with": self.label("power")}
        return {"battery": None, "note": "no battery: this computer runs on mains power", "open_with": self.label("power")}

    def _drivers(self) -> dict:
        names = self._gpu_names()
        in_use = []
        for g in hardware.gpus():
            if g.driver == "nvidia":
                v = re.search(r"Kernel Module\s+(?:for x86_64\s+)?(\d+)\.", read("/proc/driver/nvidia/version"))
                in_use.append(f"nvidia-driver-{v.group(1)}" if v else "nvidia")
            elif g.driver:
                in_use.append(f"{g.driver} (open source)")
        rec = run(["ubuntu-drivers", "list", "--recommended"], timeout=30).split()
        rec = [r.split(",")[0] for r in rec if r.startswith("nvidia-driver")]
        recommended = rec[0] if rec else "none needed"
        if any(recommended.startswith(u.split(" ")[0]) for u in in_use):
            recommended = "none needed"
        return {"gpu": ", ".join(names) or "none found", "driver_in_use": ", ".join(in_use) or "none",
                "recommended": recommended, "open_with": self.label("driver_manager")}

    def _gpu_names(self) -> list[str]:
        out = []
        for line in run(["lspci", "-mm"]).splitlines():
            f = re.findall(r'"([^"]*)"', line)
            if len(f) >= 3 and re.search(r"VGA|3D|Display", f[0]):
                out.append(f"{f[1].split(' ')[0].replace('Corporation', '').strip()} {f[2]}".strip())
        return out

    # --- open_app ---------------------------------------------------------------------------------
    def open_app(self, app: str) -> dict:
        desktop = self.desktop.get(app) or ("cinnamon-settings-backgrounds.desktop" if app == "change_background" else None)
        if not desktop:
            return {"opened": None, "error": f"unknown program {app}"}
        from gi.repository import Gio  # the daemon's main loop already has it
        info = Gio.DesktopAppInfo.new(desktop)
        if info is None:
            return {"opened": None, "error": f"{self.label(app)} is not installed"}
        try:
            info.launch([], None)
        except Exception as e:
            return {"opened": None, "error": f"couldn't open {self.label(app)}: {e}"}
        return {"opened": self.label(app)}

    def request_install(self, package: str) -> dict:
        return {"installed": False,
                "note": "Installing through the assistant comes in a later version of Cin-MinAI. The user can "
                        f"install it themselves: open {self.label('software_manager')} from the Menu, search for "
                        "the program, click Install, and type their password.",
                "open_with": self.label("software_manager")}


def edid_name(conn: str) -> str:
    """The monitor's own name from its EDID (descriptor tag 0xFC), e.g. "DELL P2422H"."""
    try:
        with open(os.path.join(conn, "edid"), "rb") as f:
            e = f.read(128)
    except OSError:
        return ""
    for off in (54, 72, 90, 108):
        d = e[off:off + 18]
        if len(d) == 18 and d[:3] == b"\0\0\0" and d[3] == 0xFC:
            return d[5:].split(b"\n")[0].decode("ascii", "replace").strip()
    return ""
