# D84 coverage: what Cin-MinAI 0.0.1 offers, and what the guide can teach

PLAN D84: everything Mint offers, the assistant can teach, on the base model. Coverage is measured, not assumed.
This is the first measurement (2026-10-06): **the list from the ISO, matched against the help cards.** It counts a
thing as covered when a card's subject is that thing. D84's real bar is stricter: a card counts only once the guide's
eval passes on the base 4B model, in all six languages. That eval step comes after the gaps below are filled.

**Source:** the release ISO `cinminai-0.0.1-amd64.iso` (sha256 `ae74be30…`), its `/casper/filesystem.squashfs`:
every `.desktop` file in `/usr/share/applications` that Cinnamon shows (99; another 50 are hidden), and the 30 Cinnamon
settings modules (all 30 also appear among the System Settings entries). **Cards:** `training/kb`, 91 in all (63
Windows-transition, 15 lessons, 13 terminal). **Method:** `training/kb/coverage_inventory.py` and
`coverage_match.py` (match by Mint label key, then by name), then every name-only match read by hand: "Windows",
"Panel" and "Desktop" are in many cards without being their subject.

## Summary

| | Items | Covered | Gaps |
|---|---|---|---|
| Menu apps | 45 | 28 | 17 |
| System Settings entries | 53 (+ "Install Cin-MinAI", live USB only) | 28 | 25 |
| Concepts behind them (list below) | 44 | 17 (+3 partly) | 24 |

## Menu apps

**Covered (28):** Archive Manager, Assistant, Calculator, Celluloid, Character Map, Document Scanner, Document Viewer,
Drawing, Files, Firefox, Image Viewer, Install Multimedia Codecs (in the DVD card), LibreOffice, Calc, Impress, Writer,
Notes, Onboard, Pix, Rhythmbox, Screenshot, System Monitor, Terminal (13 terminal cards), Text Editor, Thunderbird,
Timeshift, Warpinator, Web Apps.

**Gaps (17):**

| App | What it's for | Priority |
|---|---|---|
| **AICUI** | our own coding workspace | **must** (D84: no feature ships without its card) |
| USB Image Writer | make a bootable USB from an ISO | high |
| USB Stick Formatter | wipe and format a USB stick | high |
| Passwords and Keys | the keyring, i.e. why a "keyring password" prompt appears | high |
| Calendar | calendar, can show online accounts' events | high |
| GParted | partitions (advanced) | medium |
| Disk Usage Analyzer | what's filling the disk | medium |
| Boot Repair | fix a computer that won't start | medium |
| Transmission | torrents | medium |
| Hypnotix | internet TV | medium |
| Fonts | look at and install fonts | medium |
| Power Statistics | battery history | low |
| File Renamer | rename many files at once | low |
| LibreOffice Draw | drawings, diagrams, editing PDFs | low (mention in the office card) |
| Library | e-book and PDF shelf | low |
| Virtual keyboard | Cinnamon's own on-screen keyboard (Onboard is covered) | low |
| Vim | terminal editor | low |

## System Settings

**Covered (28):** Accessibility, Account details, Backgrounds, Backup Tool, Bluetooth Manager, Date & Time, Display,
Driver Manager, Firewall Configuration, Font Selection, Input method, Keyboard, Languages, Mouse and Touchpad, Network,
Night Light, Power Management, Preferred Applications, Printers, Screensaver, Software Manager, Sound, Startup
Applications, System Information, System Settings, Themes, Update Manager; Desktop only for "add a desktop icon".

**Gaps (25):**

| Entry | What it's for | Priority |
|---|---|---|
| Users and Groups | add a person to the computer, a child's account | high |
| Software Sources | where software comes from, mirrors, PPAs | high |
| Panel (and Applets) | the taskbar: move it, add or remove things | high |
| Disks | drives, formatting, disk health | high |
| Online Accounts | Google / Microsoft accounts on the desktop | high |
| Login Window | automatic login, the login screen | high |
| Notifications | quiet the pop-ups, do-not-disturb | high |
| Workspaces | several desktops (Windows' Task View) | medium |
| Hot Corners | corner of the screen shows all windows | medium |
| Windows | title-bar buttons, snapping, Alt+Tab style | medium |
| Privacy | recent files, clearing history | medium |
| Fingerprints | fingerprint login | medium |
| Welcome Screen | the first-steps window (only mentioned in the DVD card) | medium |
| Desklets, Extensions, Effects | desktop widgets, add-ons, animations | medium |
| General, Actions, Gestures | scaling options, Nemo actions, touchpad gestures | low |
| Color, Graphics Tablet, Thunderbolt | monitor profiles, drawing tablets, Thunderbolt devices | low |
| Advanced Network Configuration | VPN and manual connections (see VPN below) | medium |
| System Administration | Mint's admin tool | low |

## Concepts (the ideas behind the apps)

**Covered (17):** firewall, drivers, backup, snapshots/restore, file permissions (terminal), administrator/sudo,
updates, Flatpak (terminal), packages, antivirus/malware, codecs, terminal, Wi-Fi, printers, Bluetooth, night light,
screen reader. Partly: phones (photos only), cloud (Microsoft account only), Windows programs (".exe doesn't run").

**Gaps (24):**

| Concept | Priority |
|---|---|
| VPN | high (Ian's example; Network → VPN) |
| software sources / repositories | high |
| hidden files (Ctrl+H) | high |
| user accounts (adding people) | high |
| system specs ("how much RAM / which graphics card") | high |
| power and battery | high |
| live USB, dual boot, Secure Boot / BIOS / UEFI | high (install time) |
| kernel (Update Manager offers kernels) | medium |
| partitions, file systems, formatting | medium |
| desktop environment, workspaces, applets/extensions/desklets | medium |
| passwords / keyring | high (see Passwords and Keys) |
| screen recording (Cinnamon: Ctrl+Shift+Alt+R) | medium |
| swap, encryption, boot loader (GRUB) | low |
| torrents, SSH / remote access, virtual machines | low |
| open source and licences | low |

## Batch 1 (2026-10-06): six cards, measured on the base guide

Cards `vpn`, `keyring`, `hidden_files`, `user_accounts`, `bootable_usb`, `aicui` (`training/kb/transition.py`),
everyday pictures by Ian, every button and menu name checked against the test SSD's own program files. New labels:
Passwords and Keys (no Japanese name on the ISO), USB Image Writer, USB Stick Formatter. Search words in six
languages; 36 natural questions, one per language, all find their card (`test_helpcards`), and the lookup accuracy
floors hold (sessions 90.2 %, held-out 78.7 %).

The base guide (Qwen3.5-4B guide-HO Q4_K_M, llama.cpp v0.5.0, prompt v2.2, `tasks_d84.py`, 9 tasks / 33 items):
- **The right first step:** 32/33 (it looks the card up; open-app where that fits).
- **The steps:** correct and in order in every language read (the facts come from the card).
- **Not yet:** for "how do I…" questions the 4B answers with the steps only and **drops what isn't an action**:
  the hidden-files caution (0/6, even attached to the step), the "why" of the USB erase in French and Japanese
  (the safe action, "save the stick's files first", is there in all six). A first wording, "copy … off the
  stick", came back in French as "copy … onto the stick": rewritten without the ambiguous word.
- **"What is a VPN?"** went to web search instead of the card (prompt v2.2 sends knowledge to the web, D55), and
  "why can't I copy the ISO" lost the image/map picture.
- **Button names in five languages are the model's own translations** and three of them were wrong in German
  ("Bild auswählen" for Abbild auswählen, "Versteckte Dateien anzeigen" for Verborgene Dateien anzeigen, "Kein
  Passwort festgelegt" for Kein Passwort eingestellt). The real ones are in the ISO's catalogues (nemo, mintstick,
  cinnamon, cinnamon-control-center, seahorse).

So these six are **not covered yet** by D84's bar. What would close it (to decide): in-app labels from the
catalogues into `labels.json`, used by cards like app names; a prompt change (concept questions to the help first;
keep a card's caution and picture), A/B-measured on the full eval; or teaching it in guide cycle 1 (D31).

## How the gaps get filled (D84)

1. **The everyday picture first, from Ian** for each concept (credited), then the card: what it is, when you'd want
   it and when not, numbered steps with the names on screen, and an offer to open it.
2. **Every fact checked on a real Mint 22.3 install** (the test SSD), with Mint's own labels in all six languages
   (`labels.json`).
3. **Eval questions in all six languages**; a card counts once the base 4B guide passes it.
4. **Re-run this measurement for every release** (`docs/release-checklist.md`): the "must" row grows with every feature.
