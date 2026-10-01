# SPDX-License-Identifier: GPL-3.0-or-later
"""Fault rules (SPEC §20.3): evidence in, codes out. A code is set by a rule, never by a model.

Each fault: {"code", "status", "node", "cause", "facts", "evidence", "boots"}.
  status  active  — true now (this boot)
          seen    — in recent boots, not in this one
          cleared — its cause is gone (e.g. the kernel it followed was removed); kept so the history shows
  cause   which branch of the code's tree the evidence picked (trees.json)
  facts   the values the tree's words and commands are filled in with
"""

from __future__ import annotations


def _link_boots(boots: list[dict]) -> list[dict]:
    return [b for b in boots if any(l["exceptions"] for l in b["links"].values())]


def _fs_boots(boots: list[dict]) -> list[dict]:
    return [b for b in boots if b["data_loss"] or b["aborted_journal"] or b["remount_ro"] or b["fs_errors"]
            or any(k.endswith("write") for k in b["io_errors"])]


def _bad(b: dict) -> bool:
    return bool(_link_boots([b]) or _fs_boots([b]) or b["zstd_fail"])


def _short(b: dict) -> dict:
    return {"offset": b["offset"], "started": b["first"], "kernel": b["kernel"]}


def _disk_of(ev: dict, port: str, boots: list[dict]) -> tuple[str, str]:
    """ata2 -> ("sda", "KINGSTON SV300S37A120G"): the port's model from the kernel log, matched to a disk."""
    model = next((b["ata_models"][port] for b in reversed(boots) if port in b["ata_models"]), "")
    for name, d in ev["disks"].items():
        if d["model"] and model.startswith(d["model"].strip()):
            return name, model
    return "", model


def g101(ev: dict) -> dict | None:
    """The graphics driver is installed but not loaded for the running kernel."""
    drv = ev["packages"]["nvidia_driver"]
    if not drv or ev["nvidia_module_loaded"]:
        return None
    now = ev["boots"][-1] if ev["boots"] else {}
    k = ev["kernel"]
    d = ev["dkms"].get(k)
    facts = {"driver": drv, "kernel": k, "module": d["module"] if d else drv.replace("nvidia-driver-", "nvidia/")}
    if now.get("secure_boot") and now.get("sig_fail"):
        cause = "unsigned"
    elif not d or d["state"] != "installed":
        cause = "not_built"
    elif now.get("zstd_fail") or (d.get("warning") and "Diff" in d["warning"]):
        cause = "file_damaged"
    elif now.get("nvrm_errors"):
        cause = "driver_refused"
    else:
        cause = "unknown"
    ev_lines = [l for l in now.get("evidence", []) if "ZSTD" in l or "NVRM" in l or "verification" in l]
    if d and d.get("warning"):
        ev_lines.append(f"dkms status: {d['module']}, {k}: {d['state']} ({d['warning']})")
    return {"code": "G101", "status": "active", "node": "3.1", "cause": cause, "facts": facts,
            "evidence": ev_lines[:8], "boots": [_short(now)] if now else []}


def s301(ev: dict) -> dict | None:
    """An installed kernel isn't covered by the graphics driver."""
    if not ev["packages"]["nvidia_driver"]:
        return None
    missing = [k for k in ev["kernels_installed"]
               if k not in ev["dkms"] or ev["dkms"][k]["state"] != "installed"]
    if not missing:
        return None
    return {"code": "S301", "status": "active" if ev["kernel"] in missing else "seen", "node": "6.4",
            "cause": "not_built", "facts": {"kernels": ", ".join(missing), "kernel": missing[0]},
            "evidence": [f"dkms status has no installed module for {k}" for k in missing], "boots": []}


def i301(ev: dict) -> dict | None:
    """A disk's link reports errors: commands failing, link resets (2.3)."""
    boots = _link_boots(ev["boots"])
    if not boots:
        return None
    port = max((p for b in boots for p in b["links"]), key=lambda p: sum(b["links"].get(p, {}).get("exceptions", 0) for b in boots))
    disk, model = _disk_of(ev, port, ev["boots"])
    agg = {"exceptions": 0, "serror": set(), "drive_errors": set(), "failed": {}, "largest": 0, "limited": None}
    for b in boots:
        l = b["links"].get(port)
        if not l:
            continue
        agg["exceptions"] += l["exceptions"]
        agg["serror"] |= set(l["serror"])
        agg["drive_errors"] |= set(l["drive_errors"])
        for k, n in l["failed"].items():
            agg["failed"][k] = agg["failed"].get(k, 0) + n
        agg["largest"] = max(agg["largest"], l["largest_failed_bytes"])
        agg["limited"] = l["limited_to"] or agg["limited"]
    kernels_bad = sorted({b["kernel"] for b in boots if b["kernel"]})
    kernels_clean = sorted({b["kernel"] for b in ev["boots"] if b["kernel"] and b not in boots} - set(kernels_bad))
    cause = "one_kernel" if kernels_clean else "every_kernel"
    if "ICRC" in agg["drive_errors"] or {"Handshk", "UnrecovData"} & agg["serror"]:
        signal = "the cable link (checksum errors on the wire)"
    else:
        signal = "the disk or its link"
    main = bool(disk) and ev["root"].get("device", "").startswith(f"/dev/{disk}")
    if not disk:
        disk_words = f"a disk ({model or 'unknown model'})"
    else:  # "sda" alone was read as the USB stick from the question (2026-09-30 guide test)
        disk_words = f"your main disk ({disk}, {model})" if main else f"the disk {disk} ({model})"
    facts = {"port": port, "disk": disk or "the disk", "model": model or "unknown model", "disk_words": disk_words,
             "exceptions": agg["exceptions"], "failed": ", ".join(f"{n} {k}" for k, n in sorted(agg["failed"].items())),
             "largest_failed_kib": agg["largest"] // 1024, "limited_to": agg["limited"] or "",
             "max_sectors_kb": (ev["disks"].get(disk) or {}).get("max_sectors_kb") or "",
             "kernels_bad": ", ".join(kernels_bad), "kernels_clean": ", ".join(kernels_clean), "signal": signal}
    ev_lines = [l for b in boots for l in b["evidence"] if port in l][:8]
    status = "active" if boots[-1]["offset"] == 0 else "seen"
    return {"code": "I301", "status": status, "node": "2.3", "cause": cause, "facts": facts,
            "evidence": ev_lines, "boots": [_short(b) for b in boots]}


def i302(ev: dict) -> dict | None:
    """Writes to a filesystem failed: data may be lost, the filesystem may go read-only (2.3)."""
    boots = _fs_boots(ev["boots"])
    root_ro = ev["root"].get("read_only")
    if not boots and not root_ro:
        return None
    lost = sum(b["data_loss"] for b in boots)
    cause = "read_only_now" if root_ro else "write_errors"
    ev_lines = [l for b in boots for l in b["evidence"] if "EXT4" in l or "I/O error" in l][:8]
    status = "active" if root_ro or (boots and boots[-1]["offset"] == 0) else "seen"
    aborted = any(b["aborted_journal"] for b in boots)
    words = (f" ({lost} times with \"potential data loss\")" if lost else "") + \
            (", and the disk's journal was stopped to protect it" if aborted else "")
    return {"code": "I302", "status": status, "node": "2.3", "cause": cause,
            "facts": {"device": ev["root"].get("device", ""), "data_loss": lost, "aborted": aborted,
                      "aborted_words": words},
            "evidence": ev_lines, "boots": [_short(b) for b in boots]}


def s401(ev: dict) -> dict | None:
    """Faults follow one kernel: on boots with kernel K, not on boots with another (6.4, the change lens)."""
    by_kernel: dict[str, list[dict]] = {}
    for b in ev["boots"]:
        if b["kernel"]:
            by_kernel.setdefault(b["kernel"], []).append(b)
    bad = sorted(k for k, bs in by_kernel.items() if any(_bad(b) for b in bs))
    good = sorted(k for k, bs in by_kernel.items() if not any(_bad(b) for b in bs))
    if not bad or not good:
        return None  # faults on every kernel (or none): not a kernel question
    k = bad[-1]
    if ev["kernel"] == k:
        status = "active"
    elif k in ev["kernels_installed"]:
        status = "seen"  # still installed: the next start may pick it
    else:
        status = "cleared"
    good_installed = [g for g in good if g in ev["kernels_installed"]] or good
    bad_boots = [b for b in by_kernel[k] if _bad(b)]
    return {"code": "S401", "status": status, "node": "6.4", "cause": "kernel_regression",
            "facts": {"kernel": k, "good_kernel": good_installed[-1], "good_kernels": ", ".join(good),
                      "bad_boots": len(bad_boots), "boots_on_kernel": len(by_kernel[k]),
                      "meta": ", ".join(ev["packages"]["kernel_meta"]) or "none"},
            "evidence": [f"kernel {k}: problems in {len(bad_boots)} of {len(by_kernel[k])} boots; "
                         f"{', '.join(good)}: none"],
            "boots": [_short(b) for b in bad_boots]}


def h401(ev: dict) -> dict | None:
    """The previous session ended without a clean shutdown (10.4)."""
    prev = next((b for b in reversed(ev["boots"]) if b["offset"] == -1), None)
    if not prev or prev.get("clean_end", True):
        return None
    return {"code": "H401", "status": "active", "node": "10.4", "cause": "unclean",
            "facts": {"ended": prev["last"]}, "evidence": [f"boot {prev['id'][:8]} ({prev['first']}) has no shutdown at its end"],
            "boots": [_short(prev)]}


# failures known to be harmless, with the reason (recorded, not hidden: §20.1.8)
KNOWN_UNITS = {"casper-md5check.service": "a check of the live USB's files, which also runs on installed "
                                          "systems and fails there with nothing to check (Mint's own; harmless)"}


def i101(ev: dict) -> dict | None:
    """A system service failed (2.1)."""
    units = ev["failed_units"]
    if not units:
        return None
    unknown = [u for u in units if u not in KNOWN_UNITS]
    facts = {"units": ", ".join(unknown or units),
             "known": "; ".join(f"{u}: {KNOWN_UNITS[u]}" for u in units if u in KNOWN_UNITS)}
    return {"code": "I101", "status": "active" if unknown else "seen", "node": "2.1",
            "cause": "failed_unit" if unknown else "known", "facts": facts, "evidence": units[:8], "boots": []}


def s101(ev: dict) -> dict | None:
    """The package database has unfinished work (an update interrupted) (6.1)."""
    if not ev["dpkg_audit"]:
        return None
    return {"code": "S101", "status": "active", "node": "6.1", "cause": "interrupted", "facts": {},
            "evidence": ev["dpkg_audit"].splitlines()[:8], "boots": []}


# --- kernel-log events (probes.EVENTS), researched 2026-09-30 ---------------------------------------------

def _event(ev: dict, name: str) -> tuple[list[dict], dict]:
    """The boots that logged an event, and the event merged over them."""
    boots = [b for b in ev["boots"] if b.get("events", {}).get(name)]
    merged = {"count": 0, "details": [], "lines": []}
    for b in boots:
        e = b["events"][name]
        merged["count"] += e["count"]
        merged["details"] += [d for d in e["details"] if d not in merged["details"]]
        merged["lines"] += e["lines"]
    return boots, merged


def _event_fault(ev: dict, code: str, node: str, name: str, cause: str, facts: dict | None = None) -> dict | None:
    boots, e = _event(ev, name)
    if not boots:
        return None
    return {"code": code, "status": "active" if boots[-1]["offset"] == 0 else "seen", "node": node, "cause": cause,
            "facts": {"count": e["count"], "details": ", ".join(e["details"]), "boots_n": len(boots), **(facts or {})},
            "evidence": e["lines"][:6], "boots": [_short(b) for b in boots]}


def p101(ev: dict) -> dict | None:
    """The processor got too hot and slowed itself down (0.1)."""
    return _event_fault(ev, "P101", "0.1", "thermal", "throttled")


def p301(ev: dict) -> dict | None:
    """The processor reported a hardware error (machine check) (0.3)."""
    return _event_fault(ev, "P301", "0.3", "mce", "hardware_error")


def p302(ev: dict) -> dict | None:
    """Memory ran out and the kernel closed a program (0.3)."""
    return _event_fault(ev, "P302", "0.3", "oom", "out_of_memory")


# NVIDIA Xid numbers that mean the card itself stopped (NVIDIA's Xid catalog): 79 off the bus; 8, 109 timeouts;
# 61, 62, 119, 120 its internal processor. Others (e.g. 32 at driver unload, 13/31/43/45 from a program's own
# error) are the driver reporting, usually harmless once — recorded as such, not as a hung card (2026-09-30:
# 35 x Xid 32 from modprobe in the second before a shutdown).
XID_SERIOUS = {"8", "61", "62", "109", "119", "120"}


def g102(ev: dict) -> dict | None:
    """The graphics card hung, or dropped off the PCIe bus (3.1)."""
    xid_boots, xid = _event(ev, "nvidia_xid")
    hang_boots, hang = _event(ev, "gpu_hang")
    if not xid_boots and not hang_boots:
        return None
    fell = "79" in xid["details"] or any("fallen off the bus" in l for l in hang["lines"] + xid["lines"])
    serious = fell or hang_boots or set(xid["details"]) & XID_SERIOUS
    cause = "fell_off_bus" if fell else "hang" if serious else "driver_message"
    boots = sorted({b["offset"]: b for b in xid_boots + hang_boots}.values(), key=lambda b: b["offset"])
    return {"code": "G102", "status": "active" if boots[-1]["offset"] == 0 else "seen", "node": "3.1",
            "cause": cause,
            "facts": {"xids": ", ".join(xid["details"]) or "none", "count": xid["count"] + hang["count"]},
            "evidence": (xid["lines"] + hang["lines"])[:6], "boots": [_short(b) for b in boots]}


def b301(ev: dict) -> dict | None:
    """The kernel hit an internal error (an oops, a BUG, a panic) (1.3)."""
    return _event_fault(ev, "B301", "1.3", "oops", "kernel_error")


ASSISTANT_PROCS = {"llama-server"}


def a101(ev: dict) -> dict | None:
    """A program crashed (8.1). The assistant's own server is X101."""
    boots, e = _event(ev, "app_crash")
    names = [n for n in e["details"] if n not in ASSISTANT_PROCS]
    if not names:
        return None
    lines = [l for l in e["lines"] if not any(p + "[" in l for p in ASSISTANT_PROCS)]
    boots = [b for b in boots if any(n in b["events"]["app_crash"]["details"] for n in names)]
    return {"code": "A101", "status": "active" if boots[-1]["offset"] == 0 else "seen", "node": "8.1",
            "cause": "crashed", "facts": {"programs": ", ".join(names), "boots_n": len(boots)},
            "evidence": lines[:6], "boots": [_short(b) for b in boots]}


def x101(ev: dict) -> dict | None:
    """The assistant's model server crashed (9.1). On 2026-09-30 it did in the 7.0 boots, where files read
    back with zeros: a damaged read of the model file fits."""
    boots = [b for b in ev["boots"] if ASSISTANT_PROCS & set(b.get("events", {}).get("app_crash", {}).get("details", []))]
    if not boots:
        return None
    disk = [b for b in boots if _bad(b)]
    lines = [l for b in boots for l in b["events"]["app_crash"]["lines"] if any(p + "[" in l for p in ASSISTANT_PROCS)]
    return {"code": "X101", "status": "active" if boots[-1]["offset"] == 0 else "seen", "node": "9.1",
            "cause": "with_disk_errors" if disk else "crashed",
            "facts": {"boots_n": len(boots), "kernels": ", ".join(sorted({b["kernel"] for b in boots if b["kernel"]}))},
            "evidence": lines[:6], "boots": [_short(b) for b in boots]}


def n101(ev: dict) -> dict | None:
    """Wi-Fi is switched off (5.1)."""
    sw = ev.get("wifi", {}).get("switches", [])
    if not any(s["soft"] or s["hard"] for s in sw):
        return None
    hard = any(s["hard"] for s in sw)
    return {"code": "N101", "status": "active", "node": "5.1", "cause": "hard" if hard else "soft",
            "facts": {"names": ", ".join(s["name"] for s in sw if s["soft"] or s["hard"])},
            "evidence": [f"rfkill {s['name']}: soft={'on' if s['soft'] else 'off'} hard={'on' if s['hard'] else 'off'}"
                         for s in sw], "boots": []}


def n102(ev: dict) -> dict | None:
    """There's Wi-Fi hardware but no Wi-Fi device: no driver, or its firmware is missing (5.1)."""
    w = ev.get("wifi", {})
    if not w.get("hardware") or w.get("devices"):
        return None
    now = ev["boots"][-1] if ev["boots"] else {}
    fw = now.get("events", {}).get("firmware_missing", {})
    return {"code": "N102", "status": "active", "node": "5.1", "cause": "firmware" if fw else "driver",
            "facts": {"hardware": ", ".join(w["hardware"]), "firmware": ", ".join(fw.get("details", []))},
            "evidence": fw.get("lines", [])[:4] + [f"network hardware: {h}" for h in w["hardware"]], "boots": []}


def d301(ev: dict) -> dict | None:
    """A Windows (NTFS) drive won't open for writing: it was left "dirty", usually by Windows' Fast Startup (7.3)."""
    f = _event_fault(ev, "D301", "7.3", "ntfs_dirty", "windows_fast_startup")
    if f:
        f["facts"]["device"] = f["facts"]["details"].split(", ")[0] or "the Windows drive"
    return f


def d302(ev: dict) -> dict | None:
    """A USB device keeps failing to connect (7.3)."""
    return _event_fault(ev, "D302", "7.3", "usb_error", "wire_errors")


def i303(ev: dict) -> dict | None:
    """A disk is (nearly) full (2.3)."""
    low = []
    for s in ev.get("space", []):
        boot = s["mount"] == "/boot"
        if (boot and s["free_gb"] < 0.15) or (not boot and s["size_gb"] > 3 and (s["free_gb"] < 2 or s["free_pct"] < 5)):
            low.append(s)
    if not low:
        return None
    s = min(low, key=lambda s: s["free_gb"])
    cause = "boot_full" if s["mount"] == "/boot" else "full" if s["free_gb"] < 0.5 else "nearly_full"
    return {"code": "I303", "status": "active", "node": "2.3", "cause": cause,
            "facts": {"mount": s["mount"], "free_gb": s["free_gb"], "free_pct": s["free_pct"], "size_gb": s["size_gb"]},
            "evidence": [f"{x['mount']} ({x['device']}): {x['free_gb']} GB free of {x['size_gb']} GB ({x['free_pct']} %)"
                         for x in low], "boots": []}


def s102(ev: dict) -> dict | None:
    """Packages with broken dependencies: installs and updates stop until it's fixed (6.1)."""
    out = ev.get("apt_check", "")
    if not ("E:" in out or "Unmet dependencies" in out or "broken" in out.lower()):
        return None
    return {"code": "S102", "status": "active", "node": "6.1", "cause": "broken_dependencies", "facts": {},
            "evidence": out.splitlines()[:6], "boots": []}


def u201(ev: dict) -> dict | None:
    """A service in the user's own session failed (4.2)."""
    units = ev.get("user_failed_units", [])
    if not units:
        return None
    return {"code": "U201", "status": "active", "node": "4.2", "cause": "failed_unit",
            "facts": {"units": ", ".join(units)}, "evidence": units[:8], "boots": []}


def s601(ev: dict) -> dict | None:
    """No automatic system snapshots (Timeshift): advice, offered, never a fault (D30) (6.6)."""
    t = ev.get("timeshift", {})
    if t.get("configured") is None or (t.get("configured") and t.get("schedule")):
        return None  # unknown (couldn't read it, or not recorded), or set up with a schedule
    return {"code": "S601", "status": "advice", "node": "6.6",
            "cause": "not_set_up" if not t.get("configured") else "no_schedule", "facts": {},
            "evidence": ["/etc/timeshift/timeshift.json: " + ("no backup disk chosen" if not t.get("configured")
                                                              else "no schedule turned on")], "boots": []}


RULES = [g101, s301, i301, i302, s401, h401, i101, s101,
         p101, p301, p302, g102, b301, a101, x101, n101, n102, d301, d302, i303, s102, u201, s601]
ORDER = {"active": 0, "seen": 1, "cleared": 2, "advice": 3}
# causes before their symptoms: a kernel that doesn't suit the machine (S401) explains the disk link (I301),
# which explains failed writes (I302), which explain a damaged driver file (G101). A full disk (I303) breaks
# updates and logins; hardware errors (P301) and heat (P101) explain hangs (G102) and kernel errors (B301).
# A reader that shows only the first findings must get the one with the real fix.
DEPTH = {"S401": 0, "P301": 1, "I301": 2, "I303": 3, "P101": 4, "I302": 5, "S102": 6, "S101": 7, "G102": 8,
         "G101": 9, "S301": 10, "B301": 11, "P302": 12, "N101": 13, "N102": 14, "D301": 15, "D302": 16,
         "H401": 17, "X101": 18, "A101": 19, "U201": 20, "I101": 21, "S601": 22}


def evaluate(ev: dict) -> list[dict]:
    faults = [f for f in (rule(ev) for rule in RULES) if f]
    return sorted(faults, key=lambda f: (ORDER[f["status"]], DEPTH.get(f["code"], 9)))
