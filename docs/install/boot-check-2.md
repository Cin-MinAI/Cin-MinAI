# Boot check 2 — installed on real hardware (PLAN D45)

A full install onto the Mint box's **separate 120 GB SSD** (D21), then the NVIDIA driver through Mint's own
Driver Manager (D50), then the assistant on the graphics card. Before the beta (v0.1) wraps up.

**Pass:** the installed system starts to a usable screen by itself; the assistant answers a lookup, a
system check and a decline — first on the processor, then on the graphics card after the driver; it
shuts down cleanly; and the Mint box's own Mint (NVMe) and Windows (SATA) disks are untouched and still
start as before.

## Before

1. **A fresh stick.** The one from boot check 1 has the older image. Flash
   `C:\Users\Ian\cinminai-vm\iso\cinminai-0.0.1-amd64.iso` with balenaEtcher (built from commit `f87a39f`,
   all `check-iso.sh` checks passed; SHA-256 `b1142a0fe6eaebf441cdfabd5c433c798662f33970fcb6fcca2dc0e7bb4fff35`). The boot menu should say "Start Cin-MinAI 0.0.1 (based on Linux
   Mint 22.3)".
2. **One OS per drive (D47): unplug the other two drives** — the NVMe with Mint and the SATA disk with
   Windows — and connect only the 120 GB SSD. Mint's installer can put its boot loader on another drive's
   EFI partition; with only one drive connected, it can't. (Hardware steps are yours.)
3. **Network cable ready**, but unplugged for the install itself (the install works offline; the network
   comes in at step 9).
4. **Expect one known error** later in Update Manager: our own update source
   (`brickmii.github.io/cinminai-apt`) doesn't exist yet (it waits on publishing, D46). It says it can't
   reach that one source; Mint's and Ubuntu's updates still work. Note it, don't fix it.

## Install

5. Boot from the stick (F12), the first entry. The desktop should come up at a usable resolution by
   itself (no nouveau, D50).
6. Double-click **Install Cin-MinAI** on the desktop. Language and keyboard as you like; at "Installation
   type" choose **Erase disk and install** — the only disk listed should be the 120 GB SSD (if you see
   more, stop: a drive is still connected). The multimedia-codecs box as you like (it needs the network;
   the NVIDIA driver comes later from Driver Manager, D50). Your name, user and password.
7. Wait for it to finish (the model is copied from the stick near the end; that adds a minute or two),
   choose **Restart**, and pull the stick when it says so.

## First boot — before the driver

8. The installed system should start to a **usable screen** with no boot-menu changes (the installer
   carried "no nouveau" over). Expected, known: Mint's "Welcome to Linux Mint" window (to rebrand later).
   Check: the panel icon (click opens/closes the assistant), **Super+A**, and the assistant's header —
   "processor", with the reason "the graphics card's driver isn't installed yet".
   - Ask: "How do I install a program? On Windows I downloaded an .exe." → looks it up, steps with
     Software Manager.
   - Ask: "Is my graphics card set up?" → checks the drivers, says the screen is in a basic mode and
     points to Driver Manager with `nvidia-driver-580` recommended.
   - Ask: "Who should I vote for?" → a short, polite no.

## The driver, the Mint way

9. Plug in the network. Open **Update Manager**, let it refresh and install what it offers (the habit we
   want people to learn, D29). Note anything confusing, and the known `cinminai-apt` error (step 4).
10. Open **Driver Manager** (from the Menu, or ask the assistant to open it), select
    **nvidia-driver-580 (recommended)**, **Apply Changes**, type your password, and restart when it's done.
    - If a **blue screen** ("Perform MOK management") appears after the restart: that's Secure Boot asking
      to trust the driver Driver Manager built. Choose *Enroll MOK* → *Continue* → *Yes*, type the password
      Driver Manager asked you to set, then *Reboot*. (Photograph it: newcomers will meet this screen.)
11. After the restart: full 4K resolution, smooth desktop. Ask the assistant "Is my graphics card set
    up?" → `nvidia-driver-580` in use. Its header should now say **graphics card** (through Vulkan: the
    CUDA libraries aren't installed, that's fine, D50 notes).
    - Ask the same three questions again; the answers should come in a second or two instead of up to a
      minute.

## Optional: the CUDA profile

12. The CUDA module (`cinminai-llama-cuda`) would normally come from our update source, which doesn't
    exist yet. For this test only: copy `C:\Users\Ian\cinminai-vm\iso\cinminai-llama-cuda_0.0.1_amd64.deb`
    onto a second USB stick, then in a terminal: `sudo apt install ./cinminai-llama-cuda_0.0.1_amd64.deb`
    (it fetches NVIDIA's CUDA libraries from Ubuntu), then `systemctl --user restart cinminai-daemon`. The
    header should say graphics card; the first answer should be faster still. Skip it if you like —
    Vulkan already counts as the GPU profile.

## Finish

13. **Shut down** from the menu: clean, with the Cin-MinAI logo.
14. **Reconnect the other drives.** Power on, press F12, and start each system in turn: the Mint box's own
    Mint (NVMe), Windows (SATA), and Cin-MinAI (the SSD). Each should start as before — Mint with
    `qwen14b.service` as usual.
15. Photos of anything odd, and of: the first installed desktop, Driver Manager, the MOK screen if it
    appears, and the assistant on the graphics card. Record the result (pass/fail per step, timings) in
    `docs/dev-journal.md`.
