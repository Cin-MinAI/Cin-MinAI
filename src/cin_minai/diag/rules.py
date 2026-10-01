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


RULES = [g101, s301, i301, i302, s401, h401, i101, s101]
ORDER = {"active": 0, "seen": 1, "cleared": 2}
# causes before their symptoms: a kernel that doesn't suit the machine (S401) explains the disk link (I301),
# which explains failed writes (I302), which explain a damaged driver file (G101). A reader that shows only
# the first findings must get the one with the real fix.
DEPTH = {"S401": 0, "I301": 1, "I302": 2, "S101": 3, "G101": 4, "S301": 5, "H401": 6, "I101": 7}


def evaluate(ev: dict) -> list[dict]:
    faults = [f for f in (rule(ev) for rule in RULES) if f]
    return sorted(faults, key=lambda f: (ORDER[f["status"]], DEPTH.get(f["code"], 9)))
