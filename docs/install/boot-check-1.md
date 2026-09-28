# Boot check 1 — the Alpha on real hardware (PLAN D45)

The live USB boots on the Mint box; the desktop works; the assistant opens from the panel icon and Super+A
and answers a lookup, a system check and a decline correctly; nothing on the machine's own disks is touched.

## Before

1. The image: `C:\Users\Ian\cinminai-vm\iso\cinminai-0.0.1-amd64.iso` (5.9 GB; SHA-256 in the `.sha256`
   file next to it). A USB stick of **8 GB or more** — everything on it is erased.
2. Flash with balenaEtcher: *Flash from file* → the ISO → the stick → *Flash!* (it verifies after writing).
3. The Mint box's disks, for comparison afterwards (read 2026-09-28): `nvme0n1` (Mint: EFI + ext4 root),
   `sda` (233 GB: vfat, a small partition, NTFS). No swap partition (Mint uses `/swapfile`), so the live
   system has nothing on these disks to switch on.

## Boot

4. Shut the Mint box down (this stops everything on it, including `qwen14b.service`), plug the stick in,
   power on and open the firmware's boot menu (on this Gigabyte Z97X board: **F12**); pick the USB stick
   (the UEFI entry).
5. At the Cin-MinAI boot menu, the first entry. Wait for the desktop (Cin-MinAI wallpaper, mark A).
   **Don't open the internal drives in Files** during the test (that would mount them).

## The checks

6. Panel: the assistant icon (right side). Hover: "Assistant: …". Click: the sidebar opens; click again:
   it closes. Super+A: opens it with the cursor in the Ask box.
7. The first question loads the model from the stick onto the processor (the live session has no NVIDIA
   driver): expect about a minute for the first answer, and the header to say "processor" and why.
   - **Lookup:** "How do I install a program? On Windows I downloaded an .exe." → *Looked it up in the
     built-in help*; steps naming Software Manager.
   - **System check:** "How much space is left on my disk?" or "Is my Wi-Fi working?" → *Checked …
     (changes nothing)*; real numbers (the live session's, not the internal disks').
   - **Decline:** "Who should I vote for?" → a short, polite no, and what it can help with.
8. Nothing touched: open a terminal (Ctrl+Alt+T) and run `lsblk -o NAME,MOUNTPOINTS` — nothing should
   be listed as mounted under `sda…` or `nvme0n1…` (only the stick and `loop` devices).
9. Optional: a photo of the screen with the sidebar answering, for the journal.

## After

10. Shut down, remove the stick, boot the Mint box normally. Its own system and services come back as
    they were.

Record the result (pass/fail per step, timings, anything odd) in `docs/dev-journal.md`.
