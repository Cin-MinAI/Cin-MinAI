#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Derive the "during the failing 7.0 boot" case from the case recorded after the switch to 6.8.

    python3 tests/fixtures/diag/make_7.0_case.py

The kernel logs are the real ones, recorded on 2026-09-30 22:30 (2026-09-30-v300-after-6.8.json). The
boot that started at 20:01:30 becomes "now": the later boots are dropped and the live state is set to what
the session saw then (journal 2026-09-29/30): `dkms status` with the Diff warning, no nvidia module loaded,
kernels 6.14 and 7.0 installed with the HWE kernel line, writes of up to 4096 KiB.
"""

import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
NOW = "Wed 2026-09-30 20:01:30 EDT"

with open(os.path.join(HERE, "2026-09-30-v300-after-6.8.json"), encoding="utf-8") as f:
    case = json.load(f)
cmd, files = case["cmd"], case["file"]

boots = cmd["journalctl --list-boots --no-pager"].splitlines()
rows = [l for l in boots if re.match(r"\s*-?\d+\s+[0-9a-f]{32}", l)]
i = next(n for n, l in enumerate(rows) if NOW in l)
kept = rows[:i + 1]
out_rows = [boots[0]] if not re.match(r"\s*-?\d+\s+[0-9a-f]{32}", boots[0]) else []
for n, l in enumerate(kept):
    off = n - len(kept) + 1
    out_rows.append(re.sub(r"^\s*-?\d+", f"{off:>3}", l))
cmd["journalctl --list-boots --no-pager"] = "\n".join(out_rows) + "\n"
now_id = re.search(r"[0-9a-f]{32}", kept[-1]).group(0)
for k in [k for k in cmd if f"-b {now_id} -q --no-pager -n 40" in k]:
    del cmd[k]  # the current boot has no end yet

cmd["dkms status"] = ("nvidia/580.178.04, 6.14.0-37-generic, x86_64: installed\n"
                      "nvidia/580.178.04, 7.0.0-34-generic, x86_64: installed "
                      "(WARNING! Diff between built and installed module!)\n")
q = [k for k in cmd if k.startswith("dpkg-query")][0]
cmd[q] = ("linux-generic-hwe-24.04 7.0.0-34.34~24.04.1 ii \nlinux-headers-6.14.0-37-generic 6.14.0-37.37~24.04.1 ii \n"
          "linux-headers-7.0.0-34-generic 7.0.0-34.34~24.04.1 ii \nlinux-image-6.14.0-37-generic 6.14.0-37.37~24.04.1 ii \n"
          "linux-image-7.0.0-34-generic 7.0.0-34.34~24.04.1 ii \nnvidia-driver-580 580.178.04-0ubuntu0.24.04.1 ii \n")
files["/proc/sys/kernel/osrelease"] = "7.0.0-34-generic\n"
files["/proc/modules"] = "".join(l + "\n" for l in files.get("/proc/modules", "").splitlines()
                                 if not l.startswith("nvidia"))
files["/proc/driver/nvidia/version"] = ""
for p in [p for p in files if p.startswith("/boot/vmlinuz-")]:
    del files[p]
files["/boot/vmlinuz-6.14.0-37-generic"] = ""
files["/boot/vmlinuz-7.0.0-34-generic"] = ""
files["/sys/block/sda/queue/max_sectors_kb"] = "4096\n"
case["note"] = ("Assembled from real outputs: the 2026-09-30 22:30 recording, with the boot of 20:01:30 (kernel 7.0, "
                "SATA link errors, driver file unreadable) as now; see make_7.0_case.py.")

with open(os.path.join(HERE, "2026-09-30-v300-during-7.0.json"), "w", encoding="utf-8", newline="\n") as f:
    json.dump(case, f, indent=1, ensure_ascii=False)
    f.write("\n")
print("written 2026-09-30-v300-during-7.0.json; now =", now_id[:8])
