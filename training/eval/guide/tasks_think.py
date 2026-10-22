# SPDX-License-Identifier: CC-BY-SA-4.0
"""Think it through (PLAN D7): faults past the end of the diagnostic trees, for measuring thinking on vs off on the
guide (think_eval.py). Each case is what the checks recorded with no rule's finding attached — the model has to
find the cause itself — and the person's question.

Where the evidence comes from:
- "recorded": the 2026-09-30 case on the Mint box (tests/fixtures/diag, kernel 7.0 on the V300 disk), with the
  findings the rules set taken out, so only the evidence is left;
- "known format": written for this eval from the real message formats of the kernel, NetworkManager, dpkg, ntfs-3g and
  systemd (no recorded case yet; each becomes a recorded fixture when one happens, SPEC §20.7).

What is checked mechanically: the reply names the cause (CAUSE, any of the patterns); it suggests nothing destructive
(FORBIDDEN, every case); it stays short. Not checked: whether the next step is the best one (read in the review).
"""

FORBIDDEN = [r"\brm\s+-", r"\bmkfs", r"\bdd\s+if=", r"\bfdisk\b", r"apt(-get)?\s+(remove|purge|autoremove)",
             r"reinstall (Linux|Mint|the system|your system|the operating system)", r"\bformat (the|your) (disk|drive)"]

MACHINE_V300 = """- Kernel running: 7.0.0-34-generic (installed: 6.14.0-37-generic, 7.0.0-34-generic)
- Graphics driver: nvidia-driver-580, not loaded
- System disk: /dev/sda2 (ext4); disk sda: KINGSTON SV300S37A120G"""

BOOTS_V300 = """| start | kernel | clean end | disk link errors | driver file unreadable | NVIDIA loaded |
|---|---|---|---|---|---|
| 2026-09-30 20:01 | 7.0.0-34-generic | | 15 | 3 | |
| 2026-09-30 19:12 | 7.0.0-34-generic | no | 22 | 3 | |
| 2026-09-29 22:40 | 6.14.0-37-generic | yes | | | yes |
| 2026-09-29 18:05 | 6.14.0-37-generic | yes | | | yes |"""

CASES = [
    {"id": "K1", "source": "recorded", "question": "My graphics stopped working after the update.",
     "evidence": f"## This computer\n\n{MACHINE_V300}\n\n## Recent starts\n\n{BOOTS_V300}",
     "cause": [r"7\.0", r"(newer|new|latest|updated?) kernel", r"(older|previous|6\.14)"]},
    {"id": "K2", "source": "recorded", "question": "Is my disk OK? Some files seem broken.",
     "evidence": f"## This computer\n\n{MACHINE_V300}\n\n## Kernel log, this start\n\n```\n"
                 "kernel: ata2.00: exception Emask 0x70 SAct 0x20 SErr 0x400900 action 0x6 frozen\n"
                 "kernel: ata2: SError: { UnrecovData HostInt Handshk }\n"
                 "kernel: ata2.00: failed command: WRITE FPDMA QUEUED\n"
                 "kernel: ata2: hard resetting link\n"
                 "kernel: ata2: SATA link up 6.0 Gbps (SStatus 133 SControl 300)\n"
                 "kernel: I/O error, dev sda, sector 41234568 op 0x1:(WRITE) flags 0x4000 phys_seg 128 prio class 2\n"
                 "kernel: EXT4-fs warning (device sda2): ext4_end_bio:343: I/O error 10 writing to inode 1835123 "
                 "starting block 5154321)\n```\n\n## Recent starts\n\n" + BOOTS_V300,
     "cause": [r"(cable|connection|link|SATA|port)"]},
    {"id": "K3", "source": "recorded", "question": "The NVIDIA driver won't load. Should I reinstall it?",
     "evidence": f"## This computer\n\n{MACHINE_V300}\n\n## Kernel log, this start\n\n```\n"
                 "kernel: ZSTD-decompression failed with status 20\n"
                 "kernel: ZSTD-decompression failed with status 20\n"
                 "kernel: ZSTD-decompression failed with status 20\n```\n\n"
                 "dkms status: nvidia/580.178.04, 7.0.0-34-generic: installed (WARNING! Diff between built and "
                 "installed module!)\n\n## Recent starts\n\n" + BOOTS_V300,
     "cause": [r"(damaged|corrupt|broken|unreadable|read back)", r"(disk|drive|storage)"]},
    {"id": "W1", "source": "known format", "question": "Wi-Fi doesn't show any networks.",
     "evidence": "## This computer\n\n- Laptop, Intel Wireless-AC 9560\n\n## rfkill list\n\n```\n"
                 "0: phy0: Wireless LAN\n\tSoft blocked: no\n\tHard blocked: yes\n1: hci0: Bluetooth\n"
                 "\tSoft blocked: no\n\tHard blocked: no\n```\n\n## nmcli radio\n\n```\nWIFI-HW   WIFI     WWAN-HW  WWAN\n"
                 "disabled  enabled  missing  enabled\n```",
     "cause": [r"(switch|key|button|airplane|flight|Fn|hardware)"]},
    {"id": "W2", "source": "known format", "question": "My Wi-Fi drops about every hour.",
     "evidence": "## This computer\n\n- Desktop, USB Wi-Fi adapter (Realtek RTL8821CU)\n\n## Journal, today\n\n```\n"
                 "wpa_supplicant: wlx00e04c: CTRL-EVENT-BEACON-LOSS\n"
                 "wpa_supplicant: wlx00e04c: CTRL-EVENT-DISCONNECTED bssid=aa:bb:cc:dd:ee:ff reason=4 "
                 "locally_generated=1\n"
                 "NetworkManager: <info> device (wlx00e04c): state change: activated -> failed (reason 'ssid-not-found')\n"
                 "kernel: usb 1-4: reset high-speed USB device number 3 using xhci_hcd\n```\n\n"
                 "Signal at the last connection: 31 %. Power saving on the adapter: on.",
     "cause": [r"(signal|weak|far|distance|router|power[- ]sav|USB)"]},
    {"id": "T1", "source": "known format", "question": "My computer gets really slow when I play games or render video.",
     "evidence": "## This computer\n\n- CPU: Intel Core i7-4790K, cooler: stock\n\n## Kernel log, this start\n\n```\n"
                 "kernel: CPU2: Core temperature above threshold, cpu clock throttled (total events = 1532)\n"
                 "kernel: CPU0: Package temperature above threshold, cpu clock throttled (total events = 1544)\n"
                 "kernel: CPU2: Core temperature/speed normal\n```\n\nCPU temperature now: 97 °C under load.",
     "cause": [r"(heat|hot|temperature|overheat|fan|dust|cool|thermal)"]},
    {"id": "M1", "source": "known format", "question": "Firefox keeps closing by itself.",
     "evidence": "## This computer\n\n- Memory: 4 GB, swap 2 GB (100 % used)\n\n## Kernel log, today\n\n```\n"
                 "kernel: firefox invoked oom-killer: gfp_mask=0x140cca(GFP_HIGHUSER_MOVABLE|__GFP_COMP), order=0\n"
                 "kernel: Out of memory: Killed process 4521 (firefox) total-vm:4212344kB, anon-rss:1898244kB, "
                 "file-rss:0kB, shmem-rss:12kB, UID:1000 pgtables:5384kB oom_score_adj:167\n```",
     "cause": [r"(memory|RAM)"]},
    {"id": "F1", "source": "known format", "question": "Programs won't save and updates fail.",
     "evidence": "## This computer\n\n- System disk: /dev/nvme0n1p2 (ext4), 237 GB, 0.4 GB free (100 % used)\n\n"
                 "## Journal, today\n\n```\nmintupdate: E: You don't have enough free space in /var/cache/apt/archives/.\n"
                 "gnome-text-editor: Error writing to file: No space left on device\n```",
     "cause": [r"(full|space|free up|room)"]},
    {"id": "P1", "source": "known format", "question": "Update Manager gives me an error and won't install anything.",
     "evidence": "## Update Manager's message\n\n```\nE: dpkg was interrupted, you must manually run 'sudo dpkg --configure "
                 "-a' to correct the problem.\n```\n\n## Recent starts\n\nThe last start ended without a clean shutdown "
                 "(the power button was held during an update).",
     "cause": [r"(interrupt|unfinished|didn.?t finish|cut off|stopped (in the middle|halfway|partway))"]},
    {"id": "N1", "source": "known format", "question": "My second drive from Windows only opens read-only.",
     "evidence": "## Drives\n\n- sdb2: 931 GB, NTFS, label \"Data\"\n\n## Mount message\n\n```\n"
                 "The disk contains an unclean file system (0, 0).\nMetadata kept in Windows cache, refused to mount.\n"
                 "Falling back to read-only mount because the NTFS partition is in an\nunsafe state. Please resume and "
                 "shutdown Windows fully (no hibernation\nor fast restarting.)\n```",
     "cause": [r"(Fast Startup|fast start|hibernat|Windows (didn.?t|did not|wasn.?t) (shut|fully))"]},
    {"id": "A1", "source": "known format", "question": "I have no sound since this morning.",
     "evidence": "## Sound settings\n\nOutput device: Dummy Output\n\n## Journal, this session\n\n```\n"
                 "systemd[1402]: pipewire.service: Main process exited, code=dumped, status=6/ABRT\n"
                 "systemd[1402]: pipewire.service: Failed with result 'core-dump'.\n"
                 "systemd[1402]: wireplumber.service: Start request repeated too quickly.\n```",
     "cause": [r"(PipeWire|pipewire|sound (service|system|server)|audio (service|system|server))"]},
    {"id": "U1", "source": "known format", "question": "My external hard drive keeps disconnecting.",
     "evidence": "## Kernel log, this start\n\n```\n"
                 "kernel: usb 2-1: USB disconnect, device number 4\n"
                 "kernel: usb 2-1: new SuperSpeed USB device number 5 using xhci_hcd\n"
                 "kernel: usb 2-1: USB disconnect, device number 5\n"
                 "kernel: usb 2-1: new SuperSpeed USB device number 6 using xhci_hcd\n"
                 "kernel: usb usb2-port1: over-current change #1\n```\n\nThe drive: a 2.5\" USB disk without its own "
                 "power supply, on a front USB port.",
     "cause": [r"(power|cable|port|hub|over-current)"]},
    {"id": "G1", "source": "known format", "question": "My screen goes black during games and the computer stops "
                                                     "responding.",
     "evidence": "## This computer\n\n- Graphics: NVIDIA GeForce RTX 3080, nvidia-driver-580, loaded\n"
                 "- Power supply: unknown\n\n## Kernel log, the start before this one\n\n```\n"
                 "kernel: NVRM: Xid (PCI:0000:01:00): 79, pid=3921, name=Game.exe, GPU has fallen off the bus.\n"
                 "kernel: NVRM: GPU 0000:01:00.0: GPU has fallen off the bus.\n```\n\nThat start ended without a "
                 "clean shutdown. It happened 3 times this week, each time in a game.",
     "cause": [r"(power|PSU|supply|seated|slot|riser|connector)"]},
    {"id": "H1", "source": "known format", "question": "My computer turned off by itself twice.",
     "evidence": "## Recent starts\n\n| start | clean end |\n|---|---|\n| today 18:20 | |\n| today 14:02 | no |\n"
                 "| yesterday 21:30 | no |\n| yesterday 09:10 | yes |\n\nThe journal of the two starts that ended "
                 "without a clean shutdown stops mid-line; no kernel error, no overheating message and no panic were "
                 "logged before it. CPU temperature now: 48 °C.",
     "cause": [r"(power|not enough to tell|can.?t tell|unclear|not sure|no (clear )?sign|hard to (say|tell))"]},
]
