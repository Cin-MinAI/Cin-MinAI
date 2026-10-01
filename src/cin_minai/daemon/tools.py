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

from .config import live_session

# which diagnostic codes (cinminai-diag, SPEC §20) belong with which inspect_system topic
DIAG_TOPICS = {"overview": None, "drivers": {"G101", "G102", "S301", "S401"}, "display": {"G101", "G102", "S401"},
               "storage": {"I301", "I302", "I303", "D301", "D302", "S401"},
               "updates": {"S101", "S102", "S301", "S401", "I303"}, "network": {"N101", "N102"},
               "sound": {"U201"}, "battery": {"P101"}}
DIAG_TTL = 60  # seconds a reading is reused: the checks read ten boots' kernel logs (~2 s)

HOME = os.path.expanduser("~")
# the firmware's framebuffer, not a graphics card's driver (boot test 2, 2026-09-29: the check said
# "simple-framebuffer (open source)" — true, and meaningless to a newcomer)
BASIC_DISPLAY = {"simple-framebuffer", "simpledrm", "efi-framebuffer", "vesa-framebuffer", "efifb", "vesafb"}
DRIVER_WORDS = {"i915": "Intel graphics driver i915", "xe": "Intel graphics driver xe",
                "amdgpu": "AMD graphics driver amdgpu", "radeon": "AMD graphics driver radeon",
                "nouveau": "nouveau, the open-source NVIDIA driver"}


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
        self._diag: tuple[float, dict] | None = None

    def label(self, key: str) -> str:
        row = self.labels.get(key, {})
        return row.get(self.lang) or row.get("en", key)

    # --- inspect_system ---------------------------------------------------------------------------
    def inspect(self, topic: str) -> dict:
        fn = getattr(self, "_" + topic, None)
        if fn is None:
            return {"error": f"unknown topic {topic}"}
        try:
            out = fn()
        except Exception as e:  # a broken probe must not take the answer down
            return {"error": f"couldn't read {topic}: {type(e).__name__}"}
        problems = self.problems(topic)
        if problems:
            # the guide explains these like any other fact (trained: "what it means + offer the action");
            # the sidebar shows each command as a card with Copy (D53)
            out["problems_found"] = problems
            if len(problems) > 1:
                out["problems_note"] = "The first problem causes the others: start with its fix."
            out["commands_note"] = "Give only the commands listed here, exactly as written."
        return out

    def diagnose(self) -> dict:
        """The diagnostics' short view (cinminai-diag, D51), reused for DIAG_TTL seconds. CINMINAI_DIAG_FIXTURE
        reads a recorded case instead of this machine (tests, the boot test)."""
        import time
        if self._diag and time.monotonic() - self._diag[0] < DIAG_TTL:
            return self._diag[1]
        from cin_minai.diag import probes, report, rules
        from cin_minai.diag.source import FixtureSource, LiveSource
        fixture = os.environ.get("CINMINAI_DIAG_FIXTURE")
        ev = probes.collect(FixtureSource(fixture) if fixture else LiveSource())
        view = report.guide_view(report.build(ev, rules.evaluate(ev)), limit=None)  # filtered per topic below
        self._diag = (time.monotonic(), view)
        return view

    def problems(self, topic: str) -> list[dict]:
        if topic not in DIAG_TOPICS or live_session():
            return []  # the live USB has no history to read (D42 reads the installed system's)
        try:
            faults = self.diagnose()["faults"]
        except Exception:  # diagnostics must never take an answer down
            return []
        want = DIAG_TOPICS[topic]
        return [f for f in faults if f["now"] and (want is None or f["code"] in want)][:2]

    def _overview(self) -> dict:
        rel = read("/etc/cinminai-release")
        osname = re.search(r'PRETTY_NAME="?([^"\n]+)', rel or read("/etc/os-release"))
        cpu = re.search(r"model name\s*:\s*(.+)", read("/proc/cpuinfo"))
        st = os.statvfs("/")
        g = self._gpu_names()
        return {"open_with": self.label("system_info"), "os": osname.group(1) if osname else "Linux",
                "cpu": re.sub(r"\s+", " ", cpu.group(1)) if cpu else "unknown",
                "ram_gb": math.ceil(hardware.ram_mib() / 1024),  # the kernel keeps some: 31.3 -> 32
                "gpu": ", ".join(g) or "none found",
                "disk_gb": round(st.f_blocks * st.f_frsize / 1e9)}

    LIVE_NOTE = ("Running from the USB stick (the live session): files are kept in memory and are lost at "
                 "shutdown. This computer's own disks are not used or changed. Install Cin-MinAI to keep files.")

    def _storage(self) -> dict:
        st = os.statvfs(HOME)
        size, free = st.f_blocks * st.f_frsize, st.f_bavail * st.f_frsize
        if live_session():
            # the "disk" here is the live session's memory, not a drive: saying "your hard drive is 17 GB
            # and empty" (boot check 1, 2026-09-28) was true and misleading
            return {"live_session": True, "note": self.LIVE_NOTE,
                    "memory_space_free_gb": round(free / 1e9), "open_with": self.label("files")}
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
        in_use, basic = [], False
        for g in hardware.gpus():
            if g.driver in BASIC_DISPLAY:
                basic = True  # the firmware's framebuffer, not a card's driver (D50: the live USB's default)
            elif g.driver == "nvidia":
                v = re.search(r"Kernel Module\s+(?:for x86_64\s+)?(\d+)\.", read("/proc/driver/nvidia/version"))
                in_use.append(f"nvidia-driver-{v.group(1)}" if v else "nvidia")
            elif g.driver:
                in_use.append(f"{DRIVER_WORDS.get(g.driver, g.driver)} (open source)")
            elif g.vendor == "nvidia":
                in_use.append("NVIDIA card: no driver yet")
        rec = run(["ubuntu-drivers", "list", "--recommended"], timeout=30).split()
        rec = [r.split(",")[0] for r in rec if r.startswith("nvidia-driver")]
        recommended = rec[0] if rec else "none needed"
        if any(recommended.startswith(u.split(" ")[0]) for u in in_use):
            recommended = "none needed"
        out = {"gpu": ", ".join(names) or "none found", "driver_in_use": ", ".join(in_use) or "none",
               "recommended": recommended, "open_with": self.label("driver_manager")}
        if basic:
            out["note"] = ("The screen is drawn in a basic mode, without a graphics driver. Installing the "
                           "recommended driver in Driver Manager makes the screen and the assistant faster.")
        return out

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

    def make_spreadsheet(self, args: dict) -> dict:
        """A new spreadsheet in Documents, opened in Calc (SPEC §7.9, D53). Our code writes every formula;
        it never overwrites a file. Filling it in needs the user to share it (D20): the result says how."""
        from . import sheets
        folder = os.path.join(HOME, "Documents")
        try:
            made = sheets.make(folder, str(args.get("title") or "Spreadsheet"), list(args.get("columns") or []),
                               [list(map(str, r)) for r in (args.get("rows") or []) if isinstance(r, list)],
                               str(args.get("total") or "none"))
        except OSError as e:
            return {"created": None, "error": f"couldn't create the file: {e.strerror or e}"}
        opened = False
        try:
            from gi.repository import Gio
            opened = Gio.AppInfo.launch_default_for_uri(Gio.File.new_for_path(made["file"]).get_uri(), None)
        except Exception:
            pass
        return {"created": "~/Documents/" + os.path.basename(made["file"]), "opened_in": self.label("calc") if opened else None,
                "columns": made["columns"], "sheets": made["sheets"],
                "totals": {"sum": "a total of the amount column, beside the list",
                           "by_month": "a total for each month on the sheet \"Totals by month\"",
                           "none": "none"}[made["total"]],
                "next": "To let the assistant fill it in, choose Assistant, then Share this document with the "
                        "assistant, in LibreOffice's menu."}

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
