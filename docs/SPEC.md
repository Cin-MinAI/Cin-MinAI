# Cin-minAI — Specification

A Linux Mint–derived distribution with a local AI assistant built into the operating system.

> Rewritten 2026-09-24. The first version of this spec (commit `f8971bd`) described a standalone
> dual-panel terminal app and listed "an entirely new Linux distribution" as a non-goal. That was
> the wrong product. This document replaces it; the hardware, safety, and model material carries over.
>
> [PLAN.md](PLAN.md) records decisions, milestones, and anything that amends this spec.
> Section references like §12 point here.

---

## 1. Product goal

### Vision

AI will change how people use computers the way the internet did: first how they find and process
information, then the computer itself. The next generation of operating systems won't be driven
mainly by keyboards and menus, and people won't rent most of their software as cloud services
(SaaS): they will describe what they need and have it built, and they will want a simple, trustworthy
system underneath to talk to their computer, run what they make, and keep it all on their own machine.

Cin-MinAI is a step toward that, taken responsibly:

* **The assistant is the interface**, across the whole desktop, not an app. Mouse and keyboard stay
  as the fallback; voice and hands-free control come next (§10.6).
* **Local and owned**: the model runs on the user's own hardware and works offline; nothing leaves
  the machine unless the user asks. No subscription stands between a person and their computer.
* **The human keeps the button** (§8): the AI may explain, prepare, and propose; the person approves
  anything that changes the system.
* **User-built software** (later, PLAN M9): what people ask the assistant to build runs sandboxed,
  can be kept and updated like any program, and touches the system only with approval.
* **Built in the open, under the community's oversight.** A system this close to people's
  computers and data deserves scrutiny from the people it is built for. Linux has that built in:
  open source, public design documents and decisions, reproducible builds, signed packages, and the
  freedom to inspect, change, or fork. We publish our code, this specification and the decisions
  log, our eval tasks and results (including the failures), and the licences of every model we
  ship, and we keep the assistant's actions visible and auditable on the machine (§8.4, §12).
* **Taking the community for granted is a security compromise itself** (Ian, 2026-09-25). In the
  digital world security is a community issue, more consequential than in the material one: it
  holds because many independent people can check the code, the builds, and the decisions.
  Transparency is the only way to keep a community project moving and honest without taking its
  community for granted — so security work is public too: reproducible builds and signed packages,
  a published vulnerability policy, security findings and fixes explained, and time taken for
  public discussion when an obstacle needs many people pushing.
* **Semi-Jarvis: high agency over the computer, low agency over the user's life** (Ian, long-term
  plan; recorded 2026-09-28). The assistant grows toward doing real work on the machine for the
  person — but never gains authority over their money, contracts, security choices or other major
  decisions, and never a standing privileged shell. It is built **inside a local OS on purpose**,
  rather than as an agent driving cloud models (as OpenClaw does): something with autonomous control
  over a person's information is safer, and more theirs to control, when it runs on their own
  machine, under the OS's own sandbox, approvals and audit (§8), with every action visible.
* **Small enough to be big** (Ian, 2026-09-26): first a capable helper for newcomers that runs on
  the hardware people already own — then bigger. Doing the small thing well is how this grows.
* **Keep knowledge and hardware in circulation** (Ian, 2026-09-25). Repair know-how, datasheets and
  forum wisdom disappear as sites close and a throwaway culture moves on; parts vanish the same way.
  We don't just collect what's being lost — we **give it to a model to digest and redistribute as
  needed**: an open, versioned knowledge base, a published corpus, and local models that keep
  working offline when the original source is gone. The source stays attached (every card says
  where its knowledge came from and who contributed it, and respects that source's licence), and
  the model is measured on redistributing it correctly, not on sounding knowledgeable (§14.1). Old
  hardware kept useful is the same idea in silicon.
* **Familiarity is a feature** (PLAN D38): the layout people already know stays where it is from
  release to release; changes are rare, explained, and reversible — never a redesign for its own
  sake.
* **Built for the hardware people already own** (D37): older gaming laptops with 4–6 GB cards are
  the MVP's real target. We're planning for a future where efficient models make old hardware
  valuable again, the way mining once did for old GPUs — not proofing for it, planning.
* **Plan for futures beyond our own preferences — that's what protects them.** We prefer local,
  offline, and owned, but we build so the system also serves people who choose differently: cloud
  models in an IDE (PLAN D35), another scanner (D30), another desktop or board (the Pi variant). A
  project that only supports its authors' choices isn't about choice; one that supports the others
  keeps local-first credible, checkable, and open to everyone who wants to build on it.

**Audience:** people who know Windows and are new to Linux (decided 2026-09-25, PLAN D22). Every
everyday task — asking, approving, undoing, sharing a document, turning awareness off — works from
the desktop with the mouse and familiar keys (Ctrl+Z, Esc); a terminal is never required. The
assistant explains Linux in Windows terms when that helps ("like Task Manager", "like Windows
Update"), and dialogs say what will happen in plain words, not package or unit names alone.

**Design persona — the careful newcomer** (PLAN D28): an older person who wants to try AI and/or
Linux, distrusts anything online, and still keeps a checkbook. If the system works for him, it works
for most of our audience. He needs: a computer that can be **really offline** and show it (§12.4);
help with his **checkbook** in a spreadsheet he owns (§7.11); **large, plain, patient** answers;
help telling **scams** from real messages (§10.6); and no accounts, sign-ins, or subscriptions.

**Design persona — the everyday user** (Ian, 2026-09-25): sits down at a PC or tablet to browse,
watch, chat — and looks up an hour later. Never opens a settings page if it can be avoided. For them
the assistant is **invisible until it's useful and never costs them time**: no pop-ups or nagging
(it speaks when asked, or when something is actually wrong — a full disk, a security update);
**fast beats clever** (a 2-second answer to "why is the sound on the monitor?" over a thorough one in
20); defaults that just work, so the assistant is rarely needed. Anything like a screen-time summary
exists only as an option they switch on themselves (Rule 9).

The three personas span the range: the **careful newcomer** (needs a hand to trust it), the
**everyday user** (wants it to just be there), and — for a possible Pi variant — the **tinkerer**
(opens it up; PLAN §6). **The MVP is for the first two** (PLAN D34); the tinkerer and a Pi OS port
reach out to developers afterwards. A design that doesn't fail any of the three is the goal.

**Beyond the product:** Cin-MinAI is also meant to **start and influence community-developed AI
projects** — more of them, the odd ones, and the established ones that don't mind the odd. Its
reusable parts (eval, corpus pipeline, label extraction, benchmark harness, the public model cycle)
are built to be taken and used on their own.

Ship an installable desktop operating system, forked from Linux Mint Cinnamon, in which a locally
running AI assistant is a native part of the system rather than an app you add:

* It lives in the desktop — a Cinnamon panel applet, a docked sidebar, and a global hotkey.
* It is attached to the user's **real terminals** — it can see commands, output, exit codes, and
  working directory, and it can place a command at the prompt.
* It is attached to **Firefox** — it can read the page or selection the user shares and answer in a
  Firefox sidebar.
* It works inside **LibreOffice** — it can read the document or selection the user shares and, with
  approval, edit it through a fixed toolkit (Writer, Calc, Impress), every edit one Ctrl+Z away.
* It understands Linux and the machine's hardware — `/sys`, `/proc`, systemd, udev, USB, PCI,
  serial devices, microcontrollers, and build toolchains.
* It can act on the machine through a controlled boundary: sandboxed by default, user-approved
  outside the sandbox, and administrator actions only through polkit with the human pressing the button.
* It runs locally, tuned for older NVIDIA cards (Pascal: GTX 1070 / 1080 Ti) through modern RTX,
  with CPU fallback.

Distinctive value (unchanged from the original spec):

> Not "a chatbot inside a terminal", but a local Linux engineering assistant attached to a real
> operating environment — where Linux, the kernel, hardware buses, embedded systems, FPGAs, and
> microcontrollers all become understandable through the same interface.

Because we ship the OS, we control the whole stack: the shell configuration, the terminal, the
browser defaults, the desktop, the drivers, the installer, and the first-boot experience. The AI
integration should use that — it should feel designed in, not bolted on.

---

## 2. Fundamental rules

### Rule 1 — Local first

The model runs locally. Terminal output, files, logs, system and browser context stay on the
machine unless the user deliberately invokes a web feature. The assistant stays useful offline.

### Rule 2 — The terminal is real

The user's shell is a normal, persistent, interactive shell in a normal terminal emulator. The AI
integration observes and assists it; it never replaces it with a simulation, and it never breaks
`cd`, `export`, aliases, job control, Ctrl-C/Z, `ssh`, `gdb`, REPLs, or full-screen programs.

### Rule 3 — Model output is not authorization

```text
MODEL REQUEST ≠ USER PERMISSION
```

The assistant may propose actions. It can never grant itself privileges.

### Rule 4 — The human has the dangerous button

Administrator actions and hardware writes visibly stop for authorization. The user sees exactly what
will run, and there is always a Deny.

### Rule 5 — No privileged shell for the AI

Never implement `sudo bash`, `sudo -s`, a persistent root token, or a timed sudo session for the
assistant. One approved request → one privileged action → privilege disappears.

### Rule 6 — Inspect before modifying

```text
observe → identify → hypothesis → inspect/test → propose change
        → human authorization if needed → change → verify
```

Not: symptom → guess → `sudo something` → hope.

### Rule 7 — Stay a good Mint citizen

Users of this distro should keep what makes Mint good: stability, Mint's update manager and
policies, Cinnamon, sane defaults. We fork only what the AI integration needs, and we keep our
changes rebasable onto new Mint releases.

### Rule 8 — Visible, switchable awareness

The user can always tell what the assistant can currently see (which terminals, whether a browser
page or an office document is shared) and can turn it off per terminal, per session, or globally. Nothing is captured
while it is off.

### Rule 9 — Suggest and offer; the user decides

Beyond what the system needs to work, we **recommend, explain, and offer — we don't decide** (PLAN
D30). Choices such as offline mode, the firewall, a virus scanner, bigger models, or voice are
presented with a plain recommendation and its reason, and the person picks; the other choices,
including tools from other projects, stay open and work. "Recommended" may be marked, never
silently pre-applied, and every choice can be changed later.

---

## 3. Distribution

### 3.1 Base

* Upstream: **Linux Mint Cinnamon, x86-64**, which is built on Ubuntu LTS.
  Current base: Mint 22.x on Ubuntu 24.04 "noble". Moving to Mint 23 is a planned rebase, not a rewrite.
* Mint and Ubuntu package repositories stay enabled; the user keeps receiving their updates.
* Our own apt repository adds our packages and our forked Mint packages. Forked packages carry a
  version suffix (e.g. `6.4.8+cinminai1`) and an apt pin so ours win over Mint's until Mint ships a
  newer upstream version, at which point we rebase.

### 3.2 Branding

We cannot present the result as "Linux Mint" or "Ubuntu". The distro gets its own name, logo,
artwork, `/etc/os-release` (`ID=cinminai`, `ID_LIKE="linuxmint ubuntu debian"`), boot splash,
installer slideshow, and welcome screen, while crediting Mint and Ubuntu. Review both projects'
trademark guidance before any public release.

Name: **Cin-MinAI OS** (short: Cin-MinAI; decided 2026-09-24, PLAN D17). Package prefix `cinminai-`,
D-Bus prefix `org.cinminai.`, Python package `cin_minai`, `ID=cinminai`.

### 3.3 Build strategy (staged)

**Stage 1 — Remaster.** A scripted, reproducible pipeline that:

1. downloads and verifies the official Mint Cinnamon ISO (checksum + GPG signature),
2. unpacks `casper/filesystem.squashfs`,
3. in a chroot: adds our apt source and keyring, installs our meta-package, applies branding,
   removes nothing Mint needs,
4. regenerates the manifest, squashfs, and boot configuration, and
5. writes a hybrid ISO with `xorriso`, plus checksums and a signature.

Runs as root in an Ubuntu 24.04 build environment (WSL2 on the dev PC, or CI). The same inputs must
produce the same ISO contents (pinned ISO and package versions).

**Stage 2 — Fork.** Where Stage 1 packages and extension points are not enough, fork Mint's own
packages from `github.com/linuxmint`, patch them, and publish them in our repository. Expected
candidates: Cinnamon (sidebar docking, deeper assistant hooks), `mintwelcome` (first-boot AI setup),
the installer and its slideshow, `mintsystem` / artwork (branding), and possibly the default terminal.

**Stage 3 (only if needed) — Build from scratch.** Bootstrap from Ubuntu plus Mint's repositories
instead of remastering Mint's ISO. Only if Stage 1 stops being maintainable.

### 3.4 What the ISO contains

* Everything in Mint Cinnamon, rebranded.
* `cinminai-desktop` meta-package, which pulls in every component in §4.
* Our llama.cpp build (`cinminai-llama`, pinned, from our repo) and its service, not yet running a model.
* The shell integration enabled for all users by default (with the per-terminal off switch).
* Firefox with our extension force-installed by enterprise policy.
* LibreOffice (Mint's) with our extension installed for all users (`unopkg add --shared`).
* **The guide model** (§10.6) and its knowledge base, so the assistant works with no internet at
  all — in the live session, during installation, and after. Larger models are an optional download
  in first-boot setup (§9) when there is a connection.
* No proprietary NVIDIA driver preinstalled; first-boot setup selects one (§3.6).

### 3.5 Installer and first boot

* Mint's installer, rebranded (Stage 1), later patched (Stage 2) to add the AI setup pages.
* The live session works with the assistant in CPU mode or with a small model if the user chooses,
  so the assistant can help with installation problems.
* First login runs the AI setup (§9): hardware detection, driver, model download, benchmark.

### 3.6 NVIDIA and Pascal

* CUDA 13 dropped Pascal (compute 6.1); we build llama.cpp with the CUDA 12 toolkit (sm_61 plus
  modern archs) so one package serves Pascal and current cards.
* Pascal requires driver **570+**; the **580 branch is the last** to support Pascal.
* The distro must never silently move a Pascal machine past 580.x. Ship an apt pin / Driver Manager
  rule for detected Pascal cards and warn before any manual upgrade.
* No prebuilt Linux llama.cpp binary targets Pascal, hence our own build; a Vulkan build is the
  fallback (also covers AMD/Intel GPUs).
* Pin known-good llama.cpp releases in our repo; don't follow upstream blindly.

### 3.7 Updates

* Our packages update through Mint's Update Manager like everything else.
* When Mint releases a new version of a package we forked, we rebase, rebuild, and publish before
  users would otherwise be held back. Track this with automation (§15).
* Distro upgrades (e.g. 22.x → 23) are handled like Mint's, with our repo switched to the new series.

#### 3.7.0 Two schedules (PLAN D31)

* **Security updates — continuous.** Whenever Ubuntu, Mint, or we publish a fix; offered through the
  §3.7.1 window with honest reminders. Never held back for a release.
* **Releases — twice a year**, following Mint's point releases (a new base series every two years
  with Mint). Each release brings the desktop changes **and the model cycle** (§10.7): the result of
  that half-year's public model review. Features and models arrive together, with release notes in
  plain words.

#### 3.7.1 The update experience (PLAN D29)

Updating should **feel** safe, because it is — and the person should be able to watch it be safe.
A Cin-MinAI update window (Update Manager stays available for experts) runs the same apt update
through the admin mechanism (§8.4) and shows each real step as it happens:

```text
 ◉ Taking a safety snapshot (Timeshift)                  ✓ you can go back if anything goes wrong
 ◉ Connecting to the update servers                      Linux Mint · Ubuntu · Cin-MinAI
 ◉ Checking the updates are genuine                      ✓ signed by Linux Mint's key (A1B2 … )
 ◉ Downloading 7 updates (2 security)                    ████████░░  38 MB
 ◉ Checking every file's fingerprint                     ✓ 7 of 7 match the signed list
 ◉ Installing                                            libssl3 … firefox … (plain-language names)
 ◉ Checking the system afterwards                        ✓ everything started · restart not needed
 ◉ Disconnecting (offline mode)                          ✓ offline again
```

* **Only real checks, never theatre.** Every ✓ is the result of a check apt, gpg, or our code
  actually ran — repository signatures (InRelease, gpgv), package SHA-256 against the signed index,
  the post-install state. A failed check stops the update, says so in plain words ("this update
  could not be proven genuine, so nothing was installed"), and plays the warning sound.
* **Plain names:** each package line has a one-line explanation from its description ("security fix
  for secure websites"); "Details" shows the technical log for those who want it.
* **Honest reminders** (at most once a month when updates wait; offline mode §12.4 adds "go online
  for about 10 minutes"): "Security updates fix weaknesses that criminals look for. It's been 34 days
  since the last one." Updates close known holes in the programs themselves; that's different from
  an antivirus's list of known threats, and the assistant explains it that way when asked.
* **Sights and sounds** follow §5.7: a calm start tone, a soft tick for each verified step, a
  completion chime, a distinct warning tone; optional spoken narration ("Checking the updates are
  genuine… they are.") once voice ships (§10.6).

### 3.8 Legal

* Ubuntu, Mint, and our code: follow their licenses (mostly GPL). Publish source for everything we
  modify and distribute.
* Model weights: verify the license of each shipped or downloaded model before release.
* NVIDIA driver: installed from Ubuntu's repositories by the user's choice, not redistributed by us.
* Firefox: Mozilla trademark rules for unmodified builds — we ship Mint's Firefox package plus policy
  files, which is allowed; we do not rebuild Firefox.

---

## 4. System architecture

```text
┌────────────────────────── Cinnamon session (user) ───────────────────────────┐
│                                                                              │
│  Panel applet ─┐   Sidebar window ─┐   Hotkey ─┐                             │
│  (status, on/off)  (chat, cards)     (open/ask)│                             │
│                │                   │           │                             │
│                ▼                   ▼           ▼                             │
│          D-Bus session bus:  org.cinminai.Assistant1                          │
│                          │                                                   │
│                          ▼                                                   │
│  ┌──────────────── cinminai-daemon (systemd --user) ───────────────────┐     │
│  │ conversation + session state   context providers   action manager  │     │
│  │ inference client               web search          audit log        │     │
│  └───▲────────────────▲───────────────────▲──────────────┬──────┬──────┘     │
│      │                │                   │              │      │            │
│  terminal relay   native-messaging  llama-server HTTP bwrap   system bus     │
│  (per terminal)   host (Firefox)       (localhost)    runner   (admin)       │
│      │                │                   │              │      │            │
│  bash/zsh in any  Firefox sidebar   llama.cpp (user)  sandboxed│            │
│  terminal emulator  extension          (system)        commands │            │
└─────────────────────────────────────────────────────────────────┼────────────┘
                                                                  ▼
                                               org.cinminai.Admin1 (root, D-Bus
                                               activated) ──► polkit ──► Cinnamon
                                               auth dialog ──► one action
```

Components (each is one Debian package unless noted):

| Package | Runs as | Purpose |
|---------|---------|---------|
| `cinminai-daemon` | user (systemd `--user`) | The assistant: conversation, context, tools, action manager, inference client |
| `cinminai-shell` | user, per terminal | Terminal relay + bash/zsh integration (§6) |
| `cinminai-sidebar` | user | Docked GTK sidebar: chat, command cards, approval dialogs (§5) |
| `cinminai-applet` | Cinnamon | Panel applet: status, awareness toggles, opens sidebar (§5) |
| `cinminai-firefox` | user / Firefox | WebExtension + native messaging host + policy file (§7) |
| `cinminai-libreoffice` | user / LibreOffice | Python-UNO extension: menu + context menu, document toolkit, session D-Bus client (§7.6) |
| `cinminai-admin` | root, D-Bus activated | Privileged mechanism behind polkit (§8.4) |
| `cinminai-sandbox` | user | bwrap profile + runner (§8.2) |
| `cinminai-setup` | user (+ admin for driver) | First-boot hardware/model configurator (§9) |
| `cinminai-llama` | user (the daemon's child, in its unit; PLAN D48) | Pinned llama.cpp build (`llama-server`; CPU and Vulkan backends as modules; CUDA 12 in `cinminai-llama-cuda`) |
| `cinminai-diag` | root (read-only recorder) + user (session agent) | Diagnostics along the operational tree: activity log, boot records, fault codes with freeze frames, diagnostic trees, a published format any reader can use (§20, D51) |
| `cinminai-guide-model` | — | Puts the guide model in place from the install media or the download, SHA-256 checked (D23, D46, D48) |
| `cinminai-branding` | — | Artwork, os-release, plymouth, slideshow |
| `cinminai-archive-keyring` | — | Our apt key + source list + pins |
| `cinminai-desktop` | — | Meta-package pulling in all of the above |

Implementation language: **Python 3 from the base system** (3.12 on noble) with Debian-packaged
dependencies (PyGObject, GTK 3/XApp like Mint's own tools, `python3-pyte`, an async D-Bus library,
an HTTP client). No virtualenvs, no pip at runtime. Cinnamon applet in CJS (JavaScript), Firefox
extension in JavaScript. The admin mechanism is deliberately tiny and dependency-light.

### 4.1 Failure isolation

* The daemon crashing or the model OOMing never affects the user's terminals or desktop — terminals
  run through the relay, which falls back to plain pass-through if the daemon is gone.
* systemd restarts the daemon with a rate limit; no endless restart loops.
* Model OOM: stop generation → unload → reduce context → retry once → offer a smaller profile.

### 4.2 GPU memory is shared with the desktop

Measured on the Mint box (GTX 1080 Ti 11 GB, one 4K display, 2026-09-25): the desktop's share of
VRAM is not fixed. Xorg used ~1.0 GB at idle, **1.44 GB after a few extra 4K windows** (three
LibreOffice documents plus terminals), and did not give it back when they closed. Qwen3-14B Q4_K_M
needs ~9.1 GB at 8K and ~9.8 GB at 16K context. With the idle unload, the model was unloaded when the
desktop grew; every reload then failed and the service restarted 99 times. Rules:

* **Budget at load time, not only at setup.** Before starting `llama-server`, the supervisor reads
  free VRAM (NVML / `nvidia-smi`) and picks the largest profile that fits with the reserve below.
* **Keep a desktop reserve**: ≥ 1.5 GB free after loading on 4K / multi-monitor, ≥ 0.8 GB at
  1080p. First-boot setup chooses the default model/context with this reserve (§9); it is re-checked
  on every load.
* **Step down, never crash-loop.** A load that fails for memory goes down the ladder: context
  (16K → 8K → 4K) → partial GPU offload (fewer `-ngl` layers) → the smaller model → CPU. At most one
  attempt per step; systemd's restart is only for crashes, with a hard limit.
* **Say so.** The sidebar header and applet show a reduced profile in words ("Qwen3-14B, 8K context —
  GPU memory is busy"), and offer "try full size again" once memory frees up.
* **Idle unload is a choice, not a default, on tight cards**: if the full profile needs more than
  85 % of VRAM, keep the model resident (or accept that the reload may come back reduced).
* Nothing else of ours may take GPU memory by surprise (the sidebar and extensions stay on the CPU).
* **Running the card dry breaks more than the model:** with the model loaded and ~0.7 GB free, the
  X server could not get memory for window buffers and *other applications* rendered garbage
  (LibreOffice Writer text, Impress thumbnails and panels; LibreOffice itself used no GPU). The
  reserve protects the whole desktop, not just our reload.

---

## 5. Desktop surface

### 5.1 Sidebar

A docked panel on the right edge of the screen (width adjustable, can be hidden), opened by the
applet or hotkey. Contents:

```text
┌──────────────────────────────┐
│ ● LOCAL   qwen3.5-9b  8K     │ ← model, context, LOCAL/WEB, ADMIN: LOCKED
│ Sees: Terminal 2 (~/proj) ✓  │ ← current awareness, click to change
├──────────────────────────────┤
│ Build failed in parser.cpp.  │
│ Likely cause: missing        │
│ -lusb-1.0 at link time.      │
│                              │
│ ┌──────────────────────────┐ │
│ │ pkg-config --libs libusb │ │ ← command card
│ └──────────────────────────┘ │
│ [Copy] [To terminal] [Run in │
│  sandbox] [Explain]          │
├──────────────────────────────┤
│ Ask…                     ⏎   │
└──────────────────────────────┘
```

Stage 1: a GTK window that reserves screen space (struts) at the edge.
Stage 2: patch Cinnamon so the sidebar is a first-class shell element (proper docking, correct
behaviour with fullscreen, multi-monitor, and workspaces).

### 5.2 Panel applet

Icon with state (idle / thinking / needs approval / off / error), a menu with awareness toggles
(terminals, browser, web search), model status, and "Open assistant".

### 5.3 Hotkey

A default global shortcut (configurable in Cinnamon's keyboard settings) opens the sidebar focused
on the input, pre-attached to the focused window's context (the focused terminal, the Firefox tab,
or the LibreOffice document).

### 5.4 Status always visible

The sidebar header shows at all times:

```text
MODEL  BACKEND  GPU/VRAM  CTX  LOCAL|WEB  ADMIN: LOCKED  awareness
```

### 5.5 Action states

The user must never wonder "did the AI actually run that?". Every action shows one of:

```text
SUGGESTED  RUNNING  COMPLETED  FAILED  APPROVAL REQUIRED  DENIED
```

After a run, the model receives the real exit code and output and reasons from that evidence.

### 5.6 First-run notice

The first time the assistant opens, show:

```text
This system includes a local AI assistant that can see your terminals and,
when you share them, browser pages. It runs on this computer.

It can run commands in a sandbox. Anything outside the sandbox needs your
approval; administrator actions also need your password.

The assistant can be wrong. Back up anything you cannot afford to lose.
You are responsible for actions you approve.
```

A shorter version stays available under Help/About. The same notice appears in the installer.

**"Why Cin-MinAI exists"** (`docs/WHY.md`, shipped as `/usr/share/doc/cinminai/WHY`): a short page
with the project's reasoning, reachable from the welcome screen and Help/About. Offered, never
pushed (Rule 9): it opens only when someone clicks it, and it begins "These are just words. You
don't have to believe them."

### 5.7 Sights and sounds (PLAN D29)

People should be able to **feel** what the system is doing, not just read it. A small, consistent
vocabulary of sounds and visuals, used everywhere (assistant, approvals, updates, offline mode):

| Moment | Sight | Sound |
|---|---|---|
| Assistant starts listening/working | gentle pulse on the applet | soft rising tone |
| Something needs your approval | the card lifts, the button is highlighted | two-note "your turn" |
| A step checked and passed | ✓ appears, green | soft tick |
| Finished | summary with ✓ | completion chime |
| Stopped for safety / failed check | amber panel, plain explanation | distinct low warning tone (never alarming) |
| Going online / back offline | panel badge changes ONLINE ↔ OFFLINE | short connect / disconnect tones |

* **Every sound has a visual equivalent and every visual a spoken/screen-reader one** (Orca,
  AT-SPI), so hearing and sight each work alone. Sounds follow the system volume and a single
  "Sounds" switch; nothing plays when the system is muted.
* Sounds are **our own or CC0**, short (< 1 s), soft, and part of the freedesktop sound theme so
  other apps can use them. Colours never carry meaning alone (✓/!, words).
* Spoken narration (voice milestone, §10.6) reads the same step texts; it's optional and off by
  default except where the person turned voice on.

---

## 6. Terminal integration

### 6.1 Goal

Work with the terminal the user already uses (Mint's default terminal, any other emulator, a TTY,
and SSH sessions started from them), without replacing it:

* **See:** each command line, its working directory, exit status, duration, and its output as
  clean text.
* **Act:** put a command at the prompt of a chosen terminal **without pressing Enter**.
* Never type hidden commands into the user's shell.

### 6.2 Mechanism: terminal relay (default)

A small PTY relay sits between the terminal emulator and the shell:

```text
terminal emulator ⇄ relay (pty master) ⇄ bash/zsh (pty slave)
                      │
                      └─ terminal emulation state (pyte) + command segmentation
                         ─► cinminai-daemon (session bus / unix socket)
```

* Enabled by the distro's shell startup: interactive login shells in a graphical session re-exec
  through the relay once (guarded against nesting; disabled for non-interactive shells, `scp`,
  `rsync`, and anything without a TTY).
* Shell hooks emit **OSC 133** semantic prompt markers (prompt start, command start, output start,
  command end + exit code) and cwd reports (OSC 7). The relay uses them to split the stream into
  commands.
* The relay keeps an emulator state (our pyte work from the terminal spike) so captured output is
  what the user saw — without escape codes and without full-screen programs' redraw noise.
* Pass-through is byte-exact and adds no noticeable latency. If the daemon is not running, the relay
  still passes bytes through and simply records nothing.
* **Send to terminal** writes the command into the relay's input side, exactly as if typed, without a
  newline. Kernel `TIOCSTI` injection is not used.
* Throughput: pass-through never waits for emulation; emulation may lag or skip during floods
  (`cat` of a large log) and catches up on the visible screen and the command's tail.

Alternative, to be decided by spike: patch the default terminal (VTE-based) so it exposes command
segments over D-Bus. Better integration in that one terminal, but nothing in other terminals or TTYs.
The two can coexist; the relay is the baseline because it works everywhere.

### 6.3 Privacy in the terminal

* A visible per-terminal indicator (prompt marker and/or window title suffix) when a terminal is
  shared with the assistant; one command toggles it (`ai off` / `ai on`), and the applet has a global switch.
* **Nothing is captured while the terminal's echo is off** (password prompts: `sudo`, `ssh`, `gpg`).
  The relay checks the PTY's termios state.
* Common credential patterns are redacted before anything reaches the model (§12.3).
* Captured terminal history is kept in memory plus a bounded, user-only, on-disk log that can be
  disabled; it is never sent off the machine.

### 6.4 Human shell vs. AI execution

The user's shell and the AI's execution are separate. The assistant **never** runs commands in the
user's shell by itself. Its options for a proposed command:

```text
[ Copy ]  [ To terminal ]  [ Run in sandbox ]  [ Explain ]
```

and for commands outside the sandbox lane, `[ Request approval ]` / `[ Request admin ]` instead of
"Run in sandbox" (§8).

If the target terminal's foreground process is a root shell or an SSH session, "To terminal" shows a
warning naming the context ("this terminal is root on localhost" / "this terminal is ssh to host X").

---

## 7. Application integration: Firefox and LibreOffice

Firefox: §7.1–7.5. LibreOffice: §7.6–7.10.

### 7.1 Extension

A WebExtension, **force-installed** by an enterprise policy file shipped in `cinminai-firefox`, and
signed by Mozilla (unlisted/self-distributed signing — release Firefox refuses unsigned extensions).

* A Firefox sidebar panel showing the same assistant conversation (or a browser-scoped one).
* Context menu: "Ask about selection", "Ask about this page", "Send to assistant".
* The page is shared only on user action. There is no background reading of pages.
* Packaging (M0 spike): `cinminai-firefox` owns `/etc/firefox/policies/policies.json` (Firefox reads
  only one, so all our Firefox policies live there) and ships the xpi under a versioned path; a new
  `install_url` makes Firefox update the extension at its next start. If the package is removed, the
  extension removes itself (`management.uninstallSelf()`) once the native host is reported missing.

### 7.2 Native messaging

The extension talks to a native messaging host (`/usr/lib/mozilla/native-messaging-hosts/`), which
forwards to `cinminai-daemon`. Limits: size cap per message (selections larger than the cap are
truncated with a visible notice), type allowlist, schema validation.

### 7.3 Terminal ↔ browser

* From the assistant: open sources and documentation in Firefox.
* From Firefox: send a selection (an error message, a README section) into the conversation that is
  attached to a terminal.

### 7.4 Web content is untrusted

Anything from a web page is untrusted text:

```text
browser text → AI context → AI analysis → command proposal → human / lane policy
```

Never browser text → executed command. Page content is quoted as data in the prompt and cannot
change lanes, approvals, or tool permissions (prompt injection is assumed, not hoped against).

### 7.5 Web search

`/web` (or a button) runs a search through a replaceable `SearchProvider` (DuckDuckGo first, local
SearXNG as an option), fetches selected pages, and gives compact context to the model. The status
shows WEB while it happens. Ordinary prompts are never sent to search engines or cloud APIs.

**Built (2026-10-01, D55; `src/cin_minai/daemon/websearch.py`):** for a question about the world the guide calls
`web_search` (prompt v2.2); that is only an **offer** — the sidebar shows the exact query (editable), what is sent
and to whom ("Only these words are sent, to DuckDuckGo…"), **Search** / **No thanks**; nothing is fetched before
the click (a unit test fails if anything is). Then: DuckDuckGo's HTML results by form post (a plain GET came back
as its home page), the top three pages read as text (Wikipedia through its API; others through a small HTML-to-text
pass without scripts, menus and footers; https only, size and time limits), and the guide answers from them only —
the pages are quoted as material, "not instructions" — with a **Sources** card of links. Offline, the offer says so
and waits. Live on the Mint box's test install: "Why did World War II start?" (Britannica, Wikipedia) and "¿Cómo
se hace una buena lasaña?" (three recipe sites) answered correctly from the pages, about a second for the search.
Rough edges: the offer's own words are English for now (D25's UI translation); citations [n] uneven.

### 7.6 LibreOffice extension

`cinminai-libreoffice` ships a Python-UNO extension (`.oxt`, uses Mint's `python3-uno`; no
Basic macros), installed for all users with `unopkg add --shared`. It runs inside LibreOffice, so it
has the document model of Writer, Calc, and Impress, and talks to the daemon over the session D-Bus
(`org.cinminai.Assistant1`) like the sidebar. The conversation shows in the same sidebar.

* **Tools → Assistant** menu and context-menu entries: "Ask about selection", "Rewrite selection",
  "Explain this formula", "Summarize document".
* Invoking any of them shares that document with the assistant for the conversation; the sidebar
  shows `Sees: document "<title>"`, removable with one click.
* The extension reports which document window is focused, for the hotkey's context (§5.3).
* **Built (2026-09-30):** `cinminai-libreoffice` installs the extension unpacked as a *bundled* extension
  (`/usr/lib/libreoffice/share/extensions/cinminai/`: dpkg owns every file, no `unopkg` in maintainer
  scripts); source `src/libreoffice-extension/` (from the M0 spike). The daemon (`office.py`) builds the
  document context in **exactly** the trained format — checked character for character against
  `run_eval.py`'s prompt v2, from a real LibreOffice — so the shipped guide edits without retraining; the
  current document is the most recently shared one; the sidebar header shows `Sees: document "…"`
  (`ForgetDocument` stops using it; sharing itself stays in LibreOffice's menu). With the real guide on the
  1080 Ti, the eval's five expenses-sheet questions all pass end to end (`tests/integration/
  check_libreoffice.py --guide`), after one toolkit fix: cells that fit the range turned sideways are turned
  (C1:C2 given as one row of two).

### 7.7 Toolkit

The model reaches documents only through named tools with strict JSON schemas (llama.cpp
schema-constrained output, PLAN D6). There is no "run macro", no Basic, no arbitrary UNO calls.

| App | Read tools | Edit tools |
|-----|-----------|-----------|
| All | `doc_info` (type, title, size, modified), `get_selection` | `export_pdf`, `save_copy_as` (new file only) |
| Writer | `outline` (headings), `get_section`, `get_paragraphs(range)`, `styles_in_use`, `find_text` | `replace_selection`, `insert_at_cursor`, `apply_paragraph_style`, `insert_table`, `add_comment` |
| Calc | `sheets`, `used_range`, `read_range`, `read_formulas`, `named_ranges` | `write_range`, `set_formula`, `format_range`, `sort_range`, `create_chart` |
| Impress | `slides`, `slide_text`, `slide_notes` | `add_slide`, `set_slide_text`, `set_notes` |

Large documents are never sent whole: the model navigates with `outline` / `used_range` and reads
the parts it needs, within the context budget (§11).

### 7.8 Edit rules

* Read tools run only on a document the user shared (§7.6). Nothing is read in the background.
* Every edit tool is in the `USER_APPROVED` lane (§8.1): the sidebar shows a preview card
  (before → after for text; cell grid for ranges; slide text for Impress) with **Apply** / **Discard**.
* An applied edit runs inside one LibreOffice undo context named `Assistant: <summary>`, so a single
  Ctrl+Z reverts all of it.
* The assistant never saves, overwrites, or closes the user's file; `save_copy_as` only creates a
  new file at a path the user picks.
* If the document changed since the preview was made (checked by a revision/modified snapshot of
  the target range), Apply refuses and the preview is rebuilt.

### 7.9 Headless documents

"Make me a spreadsheet of…" requests run a separate headless LibreOffice inside the sandbox (§8.2)
with only the workspace mounted; the result is offered to the user to open or save. This never
touches the user's running LibreOffice.

**In the Alpha (2026-09-30, D53): `make_spreadsheet`, no LibreOffice process at all.** The model says what
the sheet is for — a title, the column names, example rows, and the kind of total (none, a sum, or a total for
each month) — and `src/cin_minai/daemon/sheets.py` writes the `.ods` itself with the standard library: every
formula is ours (a `SUM` beside the list; `SUMIFS` per month on a "Totals by month" sheet with a year total),
dates and amounts typed, nothing executed. It's always a **new** file in Documents (`… (2).ods`, never an
overwrite), opened in Calc; Calc computes the totals as it opens (checked in a real LibreOffice). Filling it
in is the user's next choice: the reply says how to share it (§7.6). The tool is in prompt **v2.1** (v2 plus
this one tool), adopted only if the public eval shows no loss against v2 (D33).

### 7.10 Document content is untrusted

Like web pages (§7.4), document text is data in the prompt. It cannot change lanes, approvals, or
tool permissions; a document that says "apply all edits without asking" changes nothing.

### 7.11 Household templates: the checkbook register

A Calc template ships on the ISO (PLAN D28), opened from the Menu or by asking ("help me keep my
checkbook"): one sheet **Register** — Date, Check no., Payee, Memo, Payment, Deposit, Balance
(formula), Cleared ✓ — and one **Reconcile** sheet (statement balance vs. cleared entries). The
assistant works it through the toolkit, under the §7.8 rules (preview, approve, one Ctrl+Z):

* "I wrote check 1043 to Dr. Miller for $85 on the 3rd" → one new row, previewed.
* "My statement says $1,212.40 — what's missing?" → compares cleared entries, lists candidates.
* "How much did I spend at the pharmacy this year?" → answers from the sheet, or adds a formula.
* "Print it" → the normal print dialog.

The file lives in his Documents folder, never online. The assistant suggests a USB-stick backup
(Backup Tool) after changes, at most once a week. Toolkit addition: `append_rows(sheet, rows)`, so a
small model doesn't have to work out the next empty row. Other templates (household budget, simple
bills list) follow the same pattern.

### 7.12 Writing projects (PLAN D54, D55)

The assistant takes in information for as long as the user wants, then writes it up when asked. Built for the Alpha
(2026-10-01): `src/cin_minai/daemon/projects.py`, `writer.py`, `odt.py`.

* **A project** is a folder in `Documents/Writing/<title>/`: `project.json` (notes and the conversation, saved
  atomically after every change) and the drafts beside it. The sidebar's **New ▾** starts or opens one; while it's
  open, the header shows `Writing: <title>` with **Notes**, **Write it up** and close.
* **Gathering:** each message gets a short reply — what was understood, then one question that helps the story
  (who, where, why, how it should feel) — and the facts in it become **notes**: facts (true in the story's world),
  characters, places, ideas (incl. tone). The user is the writer: their own plans ("I want to write a book") aren't
  story facts (the first run made "Elias wants to write a book" out of it).
* **Write it up:** an **outline card** (6–8 scenes, each with what happens) with **Write it** / **Plan again** (with
  what should change). Then the draft, scene by scene, each written with the notes as fixed facts, the whole plan,
  a summary of each earlier scene and **the previous scene's last paragraph word for word**, and told to stay inside
  its scene — with only summaries, scene 4 re-found the bottle scene 3 had found. The sidebar shows "Writing scene
  n of N"; Stop keeps what's written.
* **The document** is a new `.odt` (never an overwrite), opened in Writer: A5, 12 pt serif on a 0.62 cm line pitch
  (about 28 lines a page), "Rough draft — <title>" in the header, scene breaks, the model's `*emphasis*` as italics.
  At most ~600 lines (Ian's limit), ~650 words a scene.
* **Measured (the guide on the 1080 Ti, 2026-10-01):** 6–7 scenes, 4,000–4,400 words, 15–17 pages, in about 2½
  minutes; the key fact ("the message is from his younger self") held through notes, outline and draft. While a
  draft is written the daemon keeps the screen awake (the session manager's idle inhibitor): with the screen asleep
  the card stayed in its low power state and ran 6× slower.
* **Loops (hands-on 2026-10-01, "Grandman Stan"):** a scene repeated whole paragraphs three times, a scene opened with the previous one's ending, and two Chinese characters slipped in. Fixed: llama.cpp's DRY sampler and a light presence penalty while writing, the previous ending marked "already written; begin right after it", and a clean-up pass per scene (a paragraph 85 % the same as an earlier one, or as the previous ending, is dropped; CJK characters removed unless the story is Japanese). The same notes rewritten: 6 repeated paragraphs, 1 echo and 2 CJK characters → 0, 18 pages in 2¼ minutes.
* **The Story Circle (PLAN D56), built 2026-10-01:** Dan Harmon's eight steps (You, Need, Go, Search, Find, Take,
  Return, Change), in our own words, in `projects.py` (`CIRCLE`). The notes keep a `circle` of their own, and the
  partner asks about the first empty step. A project's **shape**: *a story in one chapter* (the outline is all eight
  steps, one scene each: the grammar can't leave one out) or *a story over 2–8 chapters* (an even split of the
  steps, 6–8 scenes a chapter; each chapter is told which steps came before and which come later, and gets the
  earlier chapters' summaries; a finished chapter moves on to the next one, a stopped one doesn't). Every scene is
  told its step. Sidebar: the outline card grouped by step; the Notes card shows the circle and the shape (also in
  the New project dialog); D-Bus `ProjectSet`. Files: `Chapter n — <title>.odt`.
* **Measured (the guide on the 1080 Ti, Ian's "The Coming War" notes, 2026-10-01):** one chapter: 8 scenes,
  5,147 words, 20 pages in 146 s, 0 repeats, a real arc (her familiar world → the soldier's warning → the cost →
  she takes the lead), the soldier stays her ally throughout (before the circle he changed sides halfway). Still
  wrong: the soldier gets a name only in scene 4, one scene opens by retelling the previous ending in new words,
  "Need" isn't the heroine's own want, and Martians grow red skin and glowing eyes against the notes. Over 4 chapters:
  chapter 1 (You, Need, 8 scenes) ran ahead into Go and then padded; **chapter 2 retold chapter 1** (the email and
  the meeting again, despite the summary) and the soldier turned enemy. Next: a fixed cast in the plan (name, who,
  side), "already shown, don't show again" for earlier chapters, fewer scenes per step over chapters, sentence-level
  echo trimming.
* **The review before every chapter (PLAN D57), built 2026-10-01:** **Write it up** now reads the chapters before
  this one as the files are now (`odt.read`, in ~1,500-word parts, each summarized; cached by the file's mtime and
  size, so the writer's own edits are read again), then fills a review (`REVIEW_SCHEMA`: each step written / partly
  written / planned / missing with one sentence, up to four characters with their step, what's missing, questions
  where the chapters and the notes disagree). The sidebar shows it as a card with an answer field and **Plan the
  chapter** (D-Bus `PlanChapter`); the answers become notes and go to the plan as "what the writer said (it
  decides)". The next chapter starts at the first step not written, the steps left paced over the chapters left
  (`next_steps`); before chapter 1 nothing can be "written". Characters keep their side "unless the writer changes it".
* **Measured (same notes, 4 chapters, 2026-10-01 17:15):** the review before chapter 1 is right (all missing; "her
  need isn't defined" — the place for the writer's answer). **Before chapter 2 the guide marked all eight steps
  "written"** after one chapter ("Take: she has taken on the goal"), so chapter 2 was planned as the ending; it also
  asked one question four times (now de-duplicated) and quoted a "sky turned to glass" that isn't in the notes.
* **Evidence (2026-10-01, built and rerun):** each step comes with `evidence` first (the chapter's words, copied),
  then its status; the prompt says what has to be true for each step (`STEP_TESTS`: "Take: they pay a heavy price: a
  loss, a wound, a sacrifice"; "a goal someone takes on is Need"). Our code (`check_evidence`) keeps "written" only
  when 80 % of a 4+-word quote is one run in the chapter text, and each step needs its own quote; otherwise the step
  is "planned" (the notes have it) or "missing". The card shows the quote. **Rerun, same notes:** before chapter 2
  the check took back Go, Find, Take, Return and Change (You and Need kept, with real quotes; Search kept on a quote
  where Elena literally searches the web — the next chapter still starts at Go), so chapter 2 covered **Go, Search**;
  chapter 1 kept to You and Need (6 scenes, 3,776 words); chapter 2 (8 scenes, 5,181 words, 0 repeats) went
  underground and on, without replaying the first meeting, and the soldier stayed her ally (uneasy, as the notes'
  "stalks her" suggests). The review's questions were real ones ("your notes say he warns her by email; the chapter
  only has a cryptic message — is it him?"). Still: chapter 2's first scene replays chapter 1's last messages, and the
  Martians keep getting red eyes (the notes say only red hair).
* **Hands-on with Ian (2026-10-01 evening):** the review questions "great", one chapter "excellent". Over chapters: (1) **garbled text ending a chapter** ("filledwith … readytohelphimfindwhatheneeded"): DRY blocks a repeated word sequence, and the model repeated the previous scene's last paragraph with the spaces dropped. Fixed in `clean_scene`: paragraphs also compared letter for letter without spaces, sentences of 30+ letters repeated anywhere in the chapter dropped, a run of letters that splits wholly into the story's own words cut (a German compound doesn't); `quality()` counts repeated sentences and glued words. Over all real drafts it removed only true repeats. (2) "Grandman Stan" **ended after 3 of 4 chapters**: chapter 1 ran ahead (8 scenes for 2 steps) and the review took "Stan remains defiant" for Change. Fixed: 2-3 scenes a step over chapters (the whole circle keeps one a step), every scene told which step mustn't happen yet; the **review card's steps are tick boxes** — the writer's ticks decide where the chapter starts (`PlanChapter` JSON `written`, `Writer.set_written`), with a live "Chapter n would cover" line (`words.would_cover`, tested equal to `next_steps`). Rerun (Grandman Stan, 4 chapters): chapter 1 kept to You + Need (4 scenes, 2,965 words); its words did reach the shoe store, so the review found Go and Search — the writer's ticks settle such calls. The sidebar now keeps a log (`~/.cache/cinminai/sidebar.log`).
* **"Missed the Moon" (Ian, 2026-10-01 night):** the first whole book, 3 chapters, 12,314 words, all clean (0 repeats, 0 glued words); Ian: "reads in a skim as publishable with some cleanup". Its middle chapters overlap (Take/Return in 2 and 3: the review called Find written before chapter 2, missing before chapter 3) — the ticks weren't used.
* **Make a manuscript (PLAN D58, built 2026-10-01):** `daemon/manuscript.py`, D-Bus `MakeManuscript`, a button on the Notes card with a name/contact dialog. Checked by converting both files with LibreOffice and looking at the pages: title page without header, "McClenathan / MISSED THE MOON / 2", chapters a third down; 41 pages (.odt) / 43 (.docx), Letter.
* **The circle while gathering, its own question (2026-10-01):** inside the notes form the guide filled no step in a whole conversation (80 notes, 0 steps); asked separately it copied the step descriptions into all eight. Now: a short question per message (`CIRCLE_NOTE_SCHEMA`), read as the answer to the partner's question before it, filled only with words copied from the message (checked with `found_in`). Replay of Ian's two conversations: no copied descriptions, the open step moves on (Missed the Moon → Go), but the filing is rough (whole messages under You, the soldier's view of Elena under Need, Return missed) — the review and the writer's ticks stay the real check.
* **Then:** nested circles (act, scene, each main character); the form (screenplay, stage play) as the output, the
  circle the structure; sources (a shared book read in parts into notes, then e.g. a character analysis).

### 7.13 The journal (PLAN D55)

An assistant that only asks about the person, and writes the entry when they press the button. Built for the Alpha
(2026-10-01): `src/cin_minai/daemon/journal.py`; the sidebar's **New ▾ → Journal**.

* **The interviewer** asks one short question at a time about what happened, who was there, how it felt, what the
  person thinks, what changed, what they want to remember — following what they just said; never advice, never
  judging, never steering to a topic they didn't raise. Measured with the guide: "What did you fix on the
  computer?", "How did your dad handle those frustrating moments…?".
* **Write today's entry:** first person, in the person's own words as far as possible, nothing added (no events,
  feelings, opinions, advice or moral they didn't give), with the date and time in the header and a short title (a
  date the model writes as the title is replaced by the entry's first words). **The voice** (Ian asked for a journal voice, 2026-10-01): a looser prompt ("weave their words with light connecting sentences") quoted the companion's last, unanswered question and *invented its answer*; with the questions shown only in brackets and a trailing unanswered one left out, four runs added nothing — but the guide then keeps the person's sentences as they are, with or without an example in the prompt. Kept faithful (D33: the voice wording didn't help and was reverted); a fuller voice is a job for a bigger model or cycle-1 training. Entries are `.odt` files in
  `Documents/Journal/` with `journal.json` as the index.
* **The conversation is never written to disk** — only the finished entry; closing the journal forgets it.
* **Private** (Ian: "just a little 4 digit pin is fine"): the entry is encrypted with GnuPG (AES-256) using a random
  key kept in the login keyring (Secret Service), so a copied disk can't be read without the login password; the PIN
  (a salted PBKDF2 hash) opens it **inside the sidebar only** — never as a file in Writer, so LibreOffice's recovery
  files never hold the plaintext; the plain document exists only in memory-backed storage for the moment of
  encryption. A 4-digit PIN is a lock against people looking, not strong encryption by itself: the keyring is what
  protects the file at rest. The assistant can't read a private entry while it's locked; the entry list shows its
  date and a lock, not its title. Tested on the Mint box's test install with the real keyring and model: sealed,
  the wrong PIN refused, the right one opens it.

---

## 8. Action boundary

### 8.1 Three lanes

| Lane | Runs where | Approval | Examples |
|------|-----------|----------|----------|
| `SANDBOXED` | bwrap, as user | none | build, test, grep, read `/sys` and `/proc`, `lspci`, `lsusb`, `git diff` in a workspace |
| `USER_APPROVED` | outside the sandbox, as user | in-sidebar approval, once | `picotool load`, `esptool write_flash`, `avrdude`, anything touching `$HOME` outside the workspace, `git reset --hard` |
| `ADMIN` | root mechanism via polkit | in-sidebar approval **then** polkit password | package install/remove, `systemctl restart`, writes to `/etc`, `dd` to a block device |

The boundary is enforced by the sandbox and the mechanism, **not** by classifying command strings.
The classifier only picks which button a command card shows; a wrong label cannot grant access.

Hardware writes are not the same as root: MCU flashing via `dialout` / `plugdev` needs no root but
is a hardware write, so it is `USER_APPROVED`. The sandbox blocks device access regardless of label.

### 8.2 Sandbox

Every assistant-initiated command in the `SANDBOXED` lane runs under `bwrap` with:

* `--new-session`, no-new-privs → `sudo`, `su`, `pkexec` cannot elevate.
* Read-only binds of `/usr`, `/etc`, `/lib*`; read-write bind of the active workspace only;
  `$HOME` not mounted.
* Minimal `/dev` → no block devices, serial ports, or debug probes.
* **Neither** the system D-Bus socket **nor** the session bus socket **nor** the daemon's own
  sockets are mounted → sandboxed code cannot trigger polkit, cannot talk to desktop services, and
  cannot ask our daemon to approve anything.
* Network allowed by default for builds; toggleable per workspace. Always a **private network
  namespace** with user-mode networking (`pasta`): internet works, but the host's loopback
  services (e.g. llama-server, CUPS) and abstract unix sockets (e.g. the X server, which would
  allow keylogging and input injection) are unreachable. The host network namespace is never used.
* The sandbox gets its own `/etc/resolv.conf` (the host's links into `/run`, which is hidden).
* Optional resource limits through a `systemd --user` scope (memory, tasks, CPU weight); a
  timeout kills every process in the sandbox.
* The user namespace maps only the user's own uid: "root" does not exist inside, so setuid
  binaries and `setuid(0)` fail outright.

Workspaces: a project the user opens with the assistant, or `~/.local/share/cinminai/workspaces/`.

### 8.3 Approval dialogs

The approval UI is drawn by the sidebar from the daemon's action record, never from model text
alone. It shows the exact argv, working directory, lane, the model's stated reason, and a Deny
button. Approval authorizes that one action once. Modes (PLAN D85): **Ask** (the default) asks for every
action; **Auto** lets *reversible* actions run on their own — shown, recorded, undoable; irreversible and admin actions
always ask, and no setting turns that off.

```text
┌──────────────────────────────────────────────┐
│ ADMINISTRATOR PERMISSION REQUIRED            │
│ The assistant proposes:                      │
│   systemctl restart bluetooth.service        │
│ Reason: apply the config change and check    │
│ whether the controller initializes.          │
│ [ Deny ]                         [ Approve ] │
└──────────────────────────────────────────────┘
```

Destructive operations (block devices, partition tables, filesystems, firmware, bootloader) get a
stronger dialog naming the target device and reminding the user to back up; the confirm button reads
"I understand — run".

Denial returns a clean "denied by user" result to the model and leaves the system unchanged.

### 8.4 Admin mechanism

`org.cinminai.Admin1`: a root-owned, D-Bus-activated system service (the standard polkit mechanism
pattern) with a fixed verb set:

```text
restart_service   install_package   remove_package   write_file
set_service_enabled   load_module   unload_module   run_argv (always destructive-dialog)
```

* Each verb checks its own polkit action with `auth_admin` — **never** `auth_admin_keep`.
* Requests are structured JSON mapped to argv lists; no `shell=True`, no string commands.
* The Cinnamon polkit dialog names the action; the in-sidebar dialog is where the full detail is shown.
* The model never sees or handles passwords; they are typed into the polkit agent only.
* Every request, approval, denial, and result goes to an append-only audit log.
* `write_file` is an **allowlist**: only the assistant's own `cinminai-<name>.conf` drop-ins (undo = write it back
  empty), only in `/etc/modprobe.d` (`options` and `blacklist` lines; nothing that blocks booting or typing) and
  `/etc/sysctl.d` (a few named settings with limits), every line checked. Much of `/etc` is code run as root, and a
  person at a password dialog can't tell which; a new place needs its own checker in source. `run_argv` is the same:
  a few block-device programs with their own option grammar, never the system disk or a disk in use.

### 8.5 Hardware write rule

```text
READ: generally allowed (sandbox)
WRITE: user approval — firmware, EEPROM, flash, fuses, raw block devices,
       PCI config, MMIO, bootloader, partition tables
```

Enforced by the architecture (sandbox + lanes), not by the prompt.

### 8.6 The limit of admin protection

Root protection does not protect files the user can write (`rm -rf ~/Documents` needs no root).
That is why autonomous execution happens only inside the sandbox and workspace, and everything
touching the wider home directory is `USER_APPROVED`.

---

### 8.7 AI recovery mode (post-MVP, PLAN D42)

When the installed system won't work, the user boots the install USB and chooses **AI recovery**.
The guide (on the ISO, CPU, fully offline — the network may be part of what's broken) diagnoses
the installed system **against its own known-good record** instead of guessing what normal is.

* **Install record** (system state only, never personal files): package list and versions, kernel,
  graphics driver and branch (e.g. the Pascal 580 pin), bootloader, partition layout and fstab, the
  hardware first-boot detected, fingerprints (hashes) of key system config files, the chosen model
  profile.
* **Change timeline:** every approved change through the admin mechanism (§8.4) — updates, driver
  installs, config writes — appends a signed entry, so recovery can answer the first repair
  question: *what changed since it last worked?*
* **Sealed with a split key** so neither a bad fix nor malware can quietly rewrite the baseline:
  proper secret sharing (**2-of-3**, not key "halves" — one share alone reveals nothing): a share on
  the install USB (a small writable partition), a share held by the machine where it survives disk
  trouble (TPM or the EFI partition, not the root disk), and a **printed recovery code** as the
  third, so a lost or reflashed USB doesn't lock anyone out. Created in a short step at the end of
  installation. If the user chose disk encryption (offered, Rule 9), the same shares can unlock it
  — on an unencrypted disk the key authenticates the record and the owner's intent; it doesn't
  stop someone with physical access, and we say so.
* **An independent second reference:** Debian package checksums and the signed apt indexes let
  recovery check every system file against what its package should contain, without trusting the
  machine at all.
* **Keeping the USB current:** the guide now and then suggests "plug in your install USB to update
  your recovery backup"; it verifies the USB's share, shows what it will write, and **writes only
  after the user approves** (Rule 9, the human's button).
* **No network, ever, anywhere in this loop:** the record, the timeline, the refresh, and recovery
  itself are all local — the machine, a USB stick in the user's hand, and a printed code. No account,
  server, or connection is needed, and none is offered as a shortcut.
* **Repairs:** a fixed set — boot repair, Timeshift rollback, freeing disk space, falling back to the
  safe graphics driver, package repair; each shown as a plan in plain words, snapshot/backup first,
  then the human's button. Files on the broken system (logs, configs) are untrusted input (§7.10).

Example: *"Since your last working start, two things changed: a new graphics driver on the 3rd and a
boot setting on the 4th. The boot error matches the driver. I can switch back to the previous driver
— one package and one setting; I'll snapshot first. Go ahead?"*

## 9. Hardware detection and first-boot setup

`cinminai-setup` runs on first login (a page in the welcome screen) and on demand:

0. **Online or offline?** "Keep this computer offline" (§12.4) skips every download: the guide model
   on the ISO is used as is, and larger models stay an option for later.
   **Protection choices** (Rule 9), each with a one-line reason: firewall on (recommended), virus
   checking with ClamAV (offered, §12.5), security-update reminders (recommended).

1. Detect CPU, RAM, GPU(s), driver, VRAM, disk space (`lscpu`, `/proc/meminfo`, `lspci -nn`,
   `nvidia-smi` when present, `/sys`).
2. If an NVIDIA GPU is present without a driver: recommend one (Pascal → 580 branch, pinned) and
   install it through the admin boundary with the user's approval.
3. Pick a candidate model profile, download it (with a size and time estimate, pausable), then
   **benchmark it**: load, short generation, measure prompt and generation speed and VRAM.
4. Keep the configuration or step down the fallback ladder:

```text
larger quant + preferred KV cache → Q4 + preferred KV → Q4 + default KV
→ smaller context → smaller model → CPU profile
```

5. Show the result: GPU, VRAM, model, quant, context, tok/s, remaining VRAM.

Result stored in `~/.config/cinminai/config.toml`, editable:

```toml
[hardware]
gpu_vendor = "nvidia"
gpu_model = "GeForce GTX 1080 Ti"
vram_mb = 11264
ram_mb = 32768

[inference]
backend = "llama.cpp"            # llama-server; build variant chosen by detection
build = "cuda12"                 # cuda12 | vulkan | cpu
model = "Qwen3.5-9B-Q5_K_M.gguf" # GGUF in ~/.local/share/cinminai/models, sha256 pinned
context = 8192
n_gpu_layers = "all"
kv_cache = "auto"                # f16 | q8_0 | q4_0, tried by the benchmark
flash_attn = "auto"
batch = 512
threads = "auto"
extra_args = []                  # any other llama-server flag, for hand tuning
```

Every `llama-server` option is reachable from this file; the daemon restarts the server when it
changes.

Rules: never decide from GPU name alone; keep the desktop VRAM reserve of §4.2 (measured with the
user's real display setup, not assumed); unsupported hardware is never fatal if CPU mode works;
never promise a tokens-per-second rate — measure it.

---

## 10. Model

### 10.1 Choice

The model is a configuration value chosen by benchmark (PLAN §3). The expected default is
Qwen3.5-9B; Qwen2.5-Coder-7B is the control baseline. Deployment context is chosen by memory and
benchmark — never the model's maximum on small cards.

**Hardware ethos (PLAN D24):** plan for a **6 GB graphics card, NVIDIA or AMD**, as the floor;
8 GB is the common case. Minimum requirements are about ordinary, affordable hardware (storage size
and speed, RAM, PCIe lanes), never "buy a new card".

| Class | Typical GPU | VRAM | Starting profile |
|-------|-------------|-----:|------------------|
| Floor | GTX 1060 6GB, RX 5600 XT, RTX 2060 | 6 GB | the guide model (§10.6), 8K |
| Common | GTX 1070/1080, RTX 3050/3060 8GB, RX 6600/7600 | 8 GB | guide model, or a 9B Q4 after validation, 8K |
| Legacy+ | GTX 1080 Ti | 11 GB | 9B–14B Q4, 8–16K (reserve per §4.2) |
| Modern | RTX 12 GB+, RX 16 GB+ | 12+ GB | benchmark-driven |
| CPU | none usable | RAM | the guide model on the CPU (slower) |

NVIDIA uses the CUDA 12 build; AMD (and Intel) use the Vulkan build (§3.6).

### 10.2 Backend abstraction

```python
class InferenceBackend:
    async def stream(...)
    async def generate(...)
    async def health(...)
    async def model_info(...)
    async def unload(...)
```

`LlamaCppBackend` only (PLAN D5): talks to our `llama-server` over localhost HTTP (streaming
completions, JSON-schema/grammar-constrained output, `/health`, `/props`), and supervises it
(start/restart with the configured flags, OOM ladder). Full low-level control, runtime LoRA
(`--lora`). Supports: stock model, stock + LoRA adapter, merged model. The interface stays, so
another backend could be added later without touching the rest.

### 10.3 Quantization and KV cache

Weights normally Q4_K_M, Q5_K_M/Q6_K where VRAM permits. KV cache type (`q8_0` etc.) is tried, not
forced: support depends on model, backend, and device — the benchmark in §9 decides.

### 10.4 Prompt

Short and operational:

```text
You are the local engineering assistant of this Linux system.
Prefer inspection and evidence over guessing.
The machine's current state is authoritative.
Do not claim a command succeeded until its output shows it.
Distinguish suggestions from executed actions.
Prefer minimal, reversible changes.
Administrator actions and hardware writes require human authorization.
After a change, verify the result.
```

Knowledge belongs in the model, the LoRA, the providers, and retrieved context — not in a
textbook-sized system prompt. Thinking mode is off by default and used for multi-step diagnosis.

### 10.5 Tools

The model uses structured tools with schema-constrained JSON output:

```text
read_file(path)            list_directory(path)       run_sandboxed(argv, cwd)
get_terminal_output(id, n) get_git_diff()             query_manpage(topic)
inspect_system()           inspect_usb()              inspect_pci()
search_web(query)          request_user_action(argv)  request_admin_action(verb, args)
```

Keep the tool set small; a 9B model misuses large tool sets.

### 10.6 The guide model (built in, offline)

A small model ships on the ISO (PLAN D23) so the assistant works without internet from the first
boot of the live USB, through installation, and after.

* **Who it's for:** (1) people who can barely use a computer, and (2) people who don't want cloud
  services or internet connections. Both come from Windows (SPEC §1).
* **What it does:** computer lessons (step by step, with the mouse, in Windows terms first), the
  Windows → Linux transition ("where is Control Panel?", "how do I install a program?"), working in
  LibreOffice through the toolkit (§7.7: spreadsheets, writing a paper), and simple system help
  through the read-only tools. **Staying safe** is in scope too: "is this email/call/pop-up a scam?" — it explains the warning
signs in the pasted text or shared page, says never to give a PIN, password or card number to anyone
who contacts you, and states that **Cin-MinAI never calls, emails, or asks for money or passwords**.
**What it doesn't:** general knowledge — history, civics, maths
  lessons, and so on; it says so politely and, when online, points to the bigger model or the web.
* **Understanding the user, then fitting them** (2026-09-25): when a request is vague, the guide
  restates what it understood, offers 2–4 ways it can help, names any out-of-scope reading honestly,
  and asks — the user is the pilot (trained through the interpretation corpus, PLAN D32). The
  choices people make are also what personalization learns from: after someone picks "a list in
  Calc" a few times, the guide leads with it (still offering the rest). Guardrails: preferences are
  **local only** (§12), **visible and editable** on a plain "what I've learned about how you like
  things" page (clear one or all), **opt-in** (Rule 9), announced when used ("you usually like lists
  in Calc — shall I start one there?"), and about **how someone likes to be helped**, never a profile
  of who they are.
* **Built as small model + knowledge + tools**, not a small model alone: a curated, shipped
  transition knowledge base (Windows concept → Mint equivalent → mouse steps) it looks things up in
  instead of guessing; the tools to check the real machine; and a fine-tune for behaviour (assume a
  Windows user, explain simply, stay in scope, call tools correctly), not for facts.
* **Size:** fits a **6 GB card** (NVIDIA or AMD) with the §4.2 desktop reserve and an 8K context, and
  runs usably on the CPU (the live USB has no proprietary driver).
* **Live USB = supported, reduced, "install recommended"** (PLAN D27): the guide answers from the USB
  so people can try it and get through installation, and it says plainly that the installed system
  is faster and better. On the CPU it keeps prompts short (~1K tokens: small system prompt, a few
  help-card snippets, trimmed history) — reading 4K tokens took 87 s on an i7-4790K (M0 smoke test,
  Qwen3.5-2B), while generating ran at 12 tok/s, fast enough to read along. Likewise offline works;
  online adds web search and model downloads. Candidates (Apache-2.0, Sept
  2026): Qwen3.5-2B/4B (vision: can explain a screenshot), Gemma 4 E2B/E4B (possibly audio input),
  Granite 4.2 3B; chosen by the guide eval (PLAN §3).
* **Languages (v1):** English, Spanish, Portuguese, French, German, Japanese — for the model, the
  knowledge base, and later voice (PLAN D25). Japanese is the only non-Latin script: the guide eval
  checks it separately (small models vary most there), and the ISO needs a CJK font and IBus + Mozc.
* **Voice (later milestone):** speech-to-text (whisper.cpp, MIT) and text-to-speech (Kokoro-82M,
  Apache-2.0, or Piper) on the CPU so the GPU stays with the model; wake word; hands-free control of
  the desktop through the accessibility layer (AT-SPI) plus our tools — the whole system usable
  without mouse and keyboard. Check each language's voice coverage before committing.

### 10.7 The model cycle (PLAN D31)

Models improve fast, but a guide that changes behaviour every month is not what our users want.
**Twice a year, with each release, we review the models in public** and ship what wins:

1. **Candidates**: new open-weight models since the last cycle, proposed by us and by the community
   (anyone can nominate one), filtered by licence (Apache-2.0/MIT-compatible) and by what fits the
   hardware floor (D24).
2. **The same bakeoff, published**: the guide eval (`training/eval/guide/`), the big-model suite
   (§14.1), speed and memory on the reference cards (CUDA, Vulkan, CPU), with every result — the
   losers and the failures included — in the release's `docs/benchmarks.md`.
3. **Fine-tune and re-check** the winners (knowledge base, behaviour), re-run the eval, and only
   ship a model that beats the current one where it matters and loses nowhere critical (safety,
   declines, the careful-newcomer tasks).
4. **Release notes** say which models "made it into Cin-MinAI this cycle" and why, in plain words.

On the user's machine the new model is **offered, not forced** (Rule 9): "a better guide is
available — faster, better at Japanese; download 1.3 GB?", with the old one kept for a switch back.
Offline users get it with the next ISO or an update stick. A model never changes silently between
releases; security fixes to the runtime (llama.cpp) are ordinary security updates.

---

## 11. Context

### 11.1 Providers

Context comes from independent providers returning structured results:

```python
class ContextResult:
    source: str
    title: str
    content: str
    metadata: dict
```

```text
terminal   files   git   man/info/doc   system   journal   hardware   usb   pci
serial     compiler   browser   web
```

The model receives the useful part, not raw dumps.

### 11.2 Linux system knowledge

`/etc/os-release`, `uname`, `/proc`, `/sys`, `/dev`, systemd and `journalctl`, udev, mounts,
permissions, users/groups, processes, environment, network interfaces, package state, kernel modules.
Tools: `systemctl journalctl ps ss ip lsmod modinfo udevadm lsblk findmnt df free lsof dmesg`.
Prefer diagnosis over reinstalling packages or rewriting configuration.

Because we ship the distro, the assistant also knows **this distro**: its own packages, its
defaults, where its config lives, and how its updates work (shipped as local documentation).

### 11.3 Local documentation

`man`, `info`, `/usr/share/doc`, `--help` output, and installed package docs, indexed locally
(index built at ISO build time for base packages, updated when packages change).

### 11.4 Compiler and log filtering

Never feed a 50,000-line log to the model. Extract: first and last error, warnings near errors, the
compiler invocation, file:line references, undefined linker symbols, traceback tail, test-failure
summary. The full log stays available on request.

### 11.5 Structured session state

Keep state outside the model and inject only what is relevant:

```json
{
  "project": "...", "terminal": "...", "cwd": "...", "kernel": "...",
  "current_problem": "...", "tested_hypotheses": [], "confirmed_facts": [],
  "files_changed": [], "pending_actions": []
}
```

### 11.5.1 Long sessions: one conversation, continuity underneath (PLAN D40)

The goal is a **Jarvis-like experience**: one continuous conversation that feels like it remembers.
The model never carries the whole session — the system does, and hands the model only what matters
now (the guide has ~8K tokens on a GPU, ~1K on the CPU, D27). No limits is not a promise we make;
an **effective context length we measure and keep improving** is (D33).

* **Session notebook** (the state above, extended): goal, decisions, what was tried, open items,
  relevant machine facts. The model sees the notebook + the last few turns.
* **Rolling compaction, never silent:** older turns fold into the notebook; the user is told ("I've
  summarized our earlier conversation — here's what I kept") and can see or correct it. The full
  transcript stays on disk, local only (§12).
* **Recall on demand:** when something from far back matters, search the stored transcript and bring
  in just that piece (keyword search first; no extra model needed).
* **Threads underneath, one conversation on screen:** when the topic clearly changes, the system
  starts a new internal thread (short contexts keep the model sharp); the user just sees one
  conversation.
* **Cheap to continue:** a stable prompt front (system prompt + notebook first, new turns last) so
  llama-server reuses its cache; the cache is saved to disk on idle unload and restored on resume,
  so picking up takes seconds, not minutes (matters most on the CPU).
* **Staying on course:** in long tasks the guide re-anchors now and then ("we're still getting your
  printer working — next is the driver"), which also catches drift.
* **On open: offer a rundown of last session.** "Want a quick rundown of where we left off?" — yes:
  a short, plain summary from the notebook; no: straight in. If someone always says no, ask once
  whether to stop asking (Rule 9, D39). "Start fresh" is always one click.
* **Measured:** long-session eval tasks — a fact given at turn 3 used correctly at turn 30; a
  compaction that keeps what matters; a rundown that is accurate.

### 11.6 Hardware state cache

CPU, GPU, USB controllers, PCI devices, storage, network adapters, and bound drivers are cached and
refreshed from udev events, not rediscovered each prompt.

### 11.7 Git

Branch, uncommitted files, diff stat, recent commits, repo root as automatic context. Explaining or
reviewing a diff is a normal request. `git reset --hard`, `git clean -fdx`, and force pushes are never
run without approval.

### 11.8 Edits

Source changes are proposed as diffs and applied after the user reviews them, except inside a
workspace where the user has enabled autonomous edits.

---

## 12. Privacy and logging

### 12.1 Paths

```text
~/.config/cinminai/          configuration
~/.local/share/cinminai/     workspaces, conversation history, terminal logs
~/.cache/cinminai/           indexes, downloaded pages
$XDG_RUNTIME_DIR/cinminai/   sockets
/var/log/cinminai/admin.log  admin audit log (root-owned, user-readable)
```

### 12.2 Rules

* Everything stays local. Prompt and terminal logging are configurable and can be disabled.
* Passwords never enter the model context (echo-off capture rule, §6.3; polkit handles admin auth).
* The LOCAL/WEB indicator shows whenever anything leaves the machine.

### 12.3 Redaction

Before terminal or file content reaches the model, redact common credential patterns: private key
blocks, `password=`/`token=`/`secret=` assignments, bearer tokens, cloud access keys, URLs with
embedded credentials.

### 12.4 Offline mode

A first-boot choice (§9), changeable later in the assistant's settings: **"Keep this computer
offline."** For people who don't trust online services (PLAN D28).

* **Offline means offline, for the whole system**, not a promise from our components: networking is
  switched off (NetworkManager), Wi-Fi and cable alike. The panel shows OFFLINE; the assistant's
  web search and model downloads are hidden, not greyed out.
* **Going online is one deliberate button**, "Go online to install updates": connect, run Update
  Manager, disconnect when done, and say so. The assistant gives a reminder about security updates at
  most once a month, in plain words, and never nags.
* **Proof, not promises:** "What has this computer sent?" lists every outbound connection our
  components made (in offline mode: none), with the date.
* Online users get the same honesty: the assistant can list what connects (updates, Firefox, email)
  when asked. Offline updates from a USB stick are an open question (PLAN §6).

### 12.5 Virus checking (optional, PLAN D30)

Linux Mint ships no antivirus, and on Linux the everyday threats are scams, phishing, and fake
"your computer is infected" pages rather than viruses (the assistant's scam help, §10.6, and
updates, §3.7.1, cover those). A scanner is still useful for **files that came from elsewhere** —
USB sticks and attachments from Windows friends — so we don't pass their viruses on.

* **ClamAV is offered, not installed**: at first boot (§9 step 0), when asked ("do I need an
  antivirus?"), or when a USB stick with Windows programs is plugged in (once, dismissible). Its
  packages and a virus database ship **on the ISO as an offline repository**, so the offline user
  can say yes without internet.
* Once chosen: right-click → **"Check for viruses"** on a file, folder, or USB stick, in the §3.7.1
  style window with §5.7 sights and sounds ("Checked 214 files ✓ nothing found"); its database
  updates with the regular updates (no extra connections; in offline mode, with "Go online to
  install updates").
* **Any other scanner the user prefers** is equally fine: we don't block, replace, or disparage it,
  and the assistant helps install whichever one they choose from Software Manager.
* The assistant answers "do I need an antivirus?" honestly: not the way Windows does; here is what
  actually protects you; you can check any file or stick yourself if you want to.

---

## 13. Hardware and embedded knowledge

Much of this system's value is hardware-oriented Linux knowledge. The model should reason along:

```text
physical device → electrical/protocol layer → bus → kernel driver → device node/sysfs → userspace
```

**USB:** topology, hubs, ports, host controllers, devices, interfaces, endpoints, descriptors,
VID/PID, classes, USB 2 vs 3, Type-C, enumeration, power, autosuspend, drivers, udev.
Tools: `lsusb` (`-t`, `-v`), `usb-devices`, `udevadm`, `/sys/bus/usb`, journal, `dmesg`.
Physical port ≠ USB device ≠ interface ≠ endpoint.

**PCI/PCIe:** domain:bus:device.function, vendor/device ID, class, driver, BARs, IRQ, MSI/MSI-X,
link generation, width and speed, IOMMU, lane allocation. Tools: `lspci` (`-nn`, `-nnk`, `-vv`),
`/sys/bus/pci`. A GPU running at fewer lanes is not necessarily faulty — consider CPU lane
allocation, board topology, M.2 lane sharing, BIOS settings, slot wiring, power states.

**Other protocols:** UART, I2C, SPI, CAN, GPIO, PWM, ADC/DAC, SATA, NVMe, SCSI, Ethernet, Wi-Fi,
Bluetooth, JTAG, SWD. Not all need tools in v1; the provider architecture allows adding them.

**Microcontrollers:** RP2040/RP2350, STM32/Cortex-M, ESP32, AVR, SAMD21/51, RISC-V MCUs.
Toolchains: `arm-none-eabi-gcc`, clang, `avr-gcc`, `riscv-none-elf-gcc`, OpenOCD, GDB, `picotool`,
`dfu-util`, `esptool`, `avrdude`, CMake, Ninja, PlatformIO, Zephyr, FreeRTOS.
Workflow: source → compile → link → ELF → bin/hex/UF2 → bootloader/probe → flash → reset → verify.
BUILD, TEST, DISASSEMBLE, DEBUG (read-oriented) are sandboxed; FLASH, ERASE, FUSES, EEPROM WRITE
need approval.

**HDL/FPGA:** Verilog, SystemVerilog, VHDL (Bluespec secondary); iverilog, Verilator, Yosys,
nextpnr, GTKWave, openFPGALoader, constraints and timing reports. Concepts: synthesis vs
simulation, combinational vs sequential, clock domains, reset synchronization, metastability, FSMs,
blocking vs non-blocking, setup/hold, pin constraints, utilization. Simulation and synthesis are
sandboxed; PROGRAM DEVICE needs approval.

**Formats:** C, C++, assembly, Rust, Python, Bash, linker scripts, Make, CMake, Kconfig, Device
Tree, systemd units, udev rules, JSON, YAML, TOML.

**Train concepts, retrieve identifiers.** Don't memorize IDs or versions. The model learns what IDs
mean; the runtime supplies `pci.ids`, `usb.ids`, sysfs, the running kernel, local docs, and web
lookup. The machine is the authority on machine state.

---

## 14. Evaluation and LoRA

### 14.1 Evaluation first

A hidden suite of ≥100 problems:

```text
20 shell/filesystem  15 systemd/services  10 networking  10 permissions
10 package/build failures  10 USB/PCI/hardware  10 embedded/MCU  10 HDL/FPGA
5 recovery / destructive-operation judgement
```

Score: correct diagnosis, useful inspection commands, unnecessary commands, dangerous commands
proposed, root cause found, fix correctness, verification performed, tokens, time. Never score by
how knowledgeable an answer sounds. The harness starts early (PLAN M3), not at the end.

### 14.2 LoRA

Only after the stock baseline exists. Purpose: behavior and domain specialization ("Linux
hardware operator"), not programming syntax.

Starting dataset mix: 25% Linux admin/shell diagnosis, 15% Linux hardware/kernel interfaces,
10% USB/PCI/bus troubleshooting, 15% embedded C/C++/MCU, 10% HDL, 10% Python/build tooling,
5% Rust/Go system tooling, 5% config formats (systemd/udev/DTS), 5% recovery and failed
troubleshooting. Adjust from measured failures.

Training pattern: problem → evidence → interpretation → hypothesis → test → new evidence →
accept/reject → minimal fix → verify — including many cases where **the first hypothesis is wrong**.

PEFT LoRA, trained off the target machines, loaded dynamically (llama.cpp `--lora`) first for easy
A/B against stock; merging later. The base model for LoRA is chosen after the baseline (PLAN D8).

Tools usually improve a small model more than training does. Order: stock model → benchmark → tools
→ benchmark → corpus → LoRA → compare.

---

## 15. Repository layout

```text
Cin-minAI/
├── docs/                    SPEC, PLAN, spikes, benchmarks
├── distro/
│   ├── build-iso.sh         Stage 1 remaster pipeline
│   ├── config/              pinned upstream ISO + checksums, package list, pins
│   ├── chroot-hooks/        ordered scripts run inside the chroot
│   └── branding/            artwork sources
├── packages/                debian/ packaging for each cinminai-* package
├── forks/                   patch series against upstream Mint packages (Stage 2)
├── src/cin_minai/
│   ├── daemon/              D-Bus service, conversation, session state
│   ├── inference/           backend interface, llama_cpp (client + server supervisor)
│   ├── context/             providers, extractors, redaction
│   ├── actions/             lanes, sandbox runner, admin client, audit
│   ├── terminal/            relay, emulator, segmentation
│   ├── sidebar/             GTK sidebar
│   ├── setup/               hardware detection, benchmark, first-boot UI
│   └── admin/               root mechanism (kept minimal)
├── cinnamon/applet/         CJS applet
├── firefox/                 WebExtension + native messaging host
├── shell/                   bash/zsh integration scripts
├── tests/  unit/ integration/ security/ hardware/ iso/
├── training/  datasets/ eval/ lora/
└── spikes/                  throwaway M0 code
```

Tooling: CI builds all packages and the ISO, publishes to the apt repo (signed), and runs unit,
integration, and ISO boot tests (QEMU). A job watches Mint's repositories for new versions of
packages we fork.

---

## 16. Tests

### 16.1 Security (against the real sandbox and mechanism)

The assistant's normal execution path cannot:

```text
acquire sudo / su / pkexec          reach the system or session D-Bus
talk to the daemon's approval API   rewrite the admin mechanism or polkit policy
write raw block devices             open serial ports or debug probes
flash firmware                      write PCI configuration
modify protected system files       read $HOME outside the workspace
turn browser text into execution    capture terminal input while echo is off
```

Also test indirect paths. The goal is not an unbreakable security appliance; it is that the
normal AI path cannot accidentally or casually gain administrator or hardware-write access.

### 16.2 Functional

```text
terminal behaviour unchanged through the relay (vim, htop, less, ssh, Ctrl-C/Z, resize, REPLs)
commands, cwd, exit codes, and output captured correctly and per command
"To terminal" places text without Enter
relay passes through when the daemon is down
assistant streams without freezing the desktop
model crash does not affect terminals; terminal exit does not affect the assistant
browser selection reaches the right conversation
/web failure is graceful offline
GPU OOM triggers the fallback ladder
denial returns cleanly to the model
awareness off → nothing captured
```

### 16.3 Distro

```text
ISO builds reproducibly from pinned inputs
ISO boots (BIOS + UEFI) in QEMU; live session works
install completes; first boot runs setup; assistant works after reboot
our packages upgrade cleanly; forked packages rebase on new Mint versions
Pascal machine is not moved past the 580 driver branch
```

### 16.4 Hardware matrix

GTX 1070 8 GB, GTX 1080 Ti 11 GB, modern RTX, CPU-only, no NVIDIA driver, network disconnected,
USB hotplug, serial device, multiple PCI devices, VM (no GPU).

---

## 17. Non-goals for v1

```text
a replacement desktop environment (we patch Cinnamon; we don't replace it)
a new terminal emulator
our own kernel or init system
a non-Mint base (Arch, Fedora, from-scratch)
a fully autonomous root administrator
a browser automation framework
a massive IDE
a cloud AI service
an undefeatable security sandbox
an automatic BIOS flashing system
```

---

## 18. v0.1 acceptance criteria

```text
A branded ISO installs on real hardware and in a VM.
First boot detects hardware, installs a suitable driver on approval, downloads a model,
  benchmarks it, and picks sensible defaults (1070/1080 Ti class included).
The assistant opens from the applet and hotkey and streams responses locally.
It sees the focused terminal's commands and output; the user can switch that off.
It proposes commands; the user can copy, send to terminal, or run in the sandbox.
It inspects system, USB, and PCI information.
A Firefox selection reaches the assistant; /web works and fails gracefully offline.
Out-of-sandbox actions require approval; admin actions also require polkit.
The assistant never holds persistent administrator privileges.
Hardware writes require approval.
Denial leaves the system clean.
Assistant failure never affects the user's terminals or desktop.
System updates work through Mint's Update Manager.
```

Priority order: 1. reliability 2. safety boundary 3. terminal and desktop behave exactly as stock
4. model usefulness 5. hardware awareness 6. speed 7. appearance.

---

## 19. Core product rule

```text
The assistant may recommend the dangerous action.
The assistant may explain the dangerous action.
The assistant may prepare the dangerous action.
The assistant does not get to approve the dangerous action.
```

The user owns the computer. The user owns the button.

---

## 20. Diagnostics — an OBD-II for the computer (PLAN D51)

A car keeps its own records and speaks a published standard; any scan tool can read it — the dealer's,
a cheap handheld, a mechanic's laptop. `cinminai-diag` does that for the computer: it **watches every
part of the system along one operational tree**, keeps an activity log, sets **standard fault codes**
with **freeze-frame evidence**, and carries a **diagnostic tree** per code — checks that run by
themselves, then ranked fixes. Any reader can use it: the guide (tested locally, it must work), a bigger
local model, a cloud model (D35), an assistant like Claude installed on the machine, or a person on a
forum. The assistant is one scan tool, not the diagnostic system.

Why (2026-09-29, the first installed system): after a kernel update (6.14 → 7.0) the NVIDIA driver no
longer loaded, though it was installed and built for both kernels — first taken for a missing signature,
until the evidence showed Secure Boot was off (the cause, found on 2026-09-30, sat two layers down: kernel 7.0 pushing an old
SSD's SATA link harder than it could take — exactly why a diagnostic record is needed); a hard power-off after a crash damaged the root filesystem; the shutdown
dialog blamed `at-spi-registryd`. The facts were spread over `dkms status`, `modinfo`, `mokutil`, the kernel log, the
apt history and the initramfs prompt — and the guide, seeing only `inspect_system`, would have sent the
user to reinstall a driver they already had. A small model can't be trusted to read raw logs; code can.
**Code reads the system; readers explain it.**

### 20.1 Principles

1. **One operational tree, no blind spots.** Every stage from power-on to daily use to shutdown is a node
   (§20.2). A node without a monitor is a visible gap in the coverage table, not an invisible one.
2. **Evidence, not guesses.** Monitors and checks are deterministic programs with typed results. A fault
   code is set by a rule over evidence, never by a model.
3. **A published standard.** The formats (§20.4) are versioned (`cinminai-diag/1`) and documented for
   readers, like SAE's code standard — including a short *reading guide* written for AI readers.
4. **Its own module.** It runs apart from the desktop and the assistant, so it keeps recording when either
   is the broken part (and at boot, before both). The recovery mode (D42, §8.7) builds on it.
5. **As automated as possible, never unilateral.** Monitors, checks and screenshots run by themselves;
   anything that changes the system is a fix the user approves, through the admin boundary (D3, §8.4), and
   is verified afterwards (Rule 6). No reader gets a shell: checks and fixes come from fixed catalogues.
6. **Local and private.** Everything stays on the machine (Rule 1). A report leaves it only when the user
   exports it, redacted (§12.3), and sees what's in it.
7. **Planned for the faults we can't reproduce.** An unrecognised failure still gets a code, a full
   freeze frame and a timeline, so whoever helps next has what they'd ask for.
8. **More information never hurts** (Ian, 2026-09-29): "even when it's misdirected information —
   eventually you find your way to the misdirection and realize it was more of a roundabout." We run
   what we have from the machine that's broken — no meters, no scopes — so everything is recorded and
   shown, uncertain readings included, each labelled with what it can and can't tell (§20.8). The
   reader decides how much to show: the guide leads a newcomer with the likeliest finding in plain words;
   a tinkerer gets every reading, log line and test result to dig through. Nothing is hidden to keep it
   tidy.

### 20.2 The operational tree

The system as it runs, in order. Each node lists what is watched (**W**), where the evidence comes from
(**E**), and typical faults (**F**), with worked codes (§20.3). The numbering is the tree; codes use it.

**0 — Power and firmware** *(before Linux; seen from Linux afterwards, or by its absence)*
- **0.1 Power:** W supply, battery, AC changes, thermal throttling. E `/sys/class/power_supply`,
  `/sys/class/thermal`, ACPI events in the journal. F battery worn or failing; overheating; brown-outs
  (sudden power loss shows up as 10.4 at next boot).
- **0.2 Firmware:** W firmware version, boot mode (UEFI/legacy), Secure Boot state, boot entries and
  order, TPM. E `/sys/firmware/efi`, `mokutil --sb-state`, `efibootmgr`, `fwupdmgr`, `dmidecode`. F Secure
  Boot on with unsigned modules (see 2.2); a boot entry pointing at another drive's loader (D47); firmware
  updates available.
- **0.3 Hardware inventory:** W CPU and microcode, memory size and errors, storage devices, PCI and USB
  devices, sensors. E `/proc/cpuinfo`, EDAC, `lspci`, `lsusb`, `lsblk`, `sensors`. F memory errors; a disk
  that vanished; a device with no driver.

**1 — Boot chain** *(firmware → loader → kernel → initramfs → root)*
- **1.1 EFI system partition and boot entry:** W the ESP's health, which entry started us. E `efibootmgr`,
  `/boot/efi`, `fsck.vfat` results. F ESP full or damaged; entry missing after a firmware reset.
- **1.2 Boot loader (shim → GRUB):** W default entry, kernels offered, boot options, time spent in the menu,
  the signature chain (shim, GRUB, kernel, MOK list). E `/etc/default/grub`, `grub.cfg`, `/proc/cmdline`,
  `mokutil --list-enrolled`. F default entry pointing at a kernel that fails (2.2); boot options lost
  (e.g. D50's `modprobe.blacklist=nouveau`).
- **1.3 Kernel start:** W version, boot options, taint flags, early errors, boot time. E `uname -r`,
  `/proc/sys/kernel/tainted`, `journalctl -k -b -p err`, `systemd-analyze`. F kernel panics (seen as a
  missing boot record); a new kernel series.
- **1.4 Initramfs:** W modules and microcode it carried, splash, root discovery, disk unlocking, the root
  filesystem check. E the boot's journal, `lsinitramfs`, the initramfs prompt's text. F **B401** — root
  filesystem needs a manual check (2026-09-29).
- **1.5 Root mount and switch-over:** W root mounted read-write, fstab UUIDs match. E `findmnt`,
  `/etc/fstab`, `blkid`. F fstab UUID mismatch; root read-only after errors.

**2 — System start and core services** *(systemd)*
- **2.1 systemd:** W targets reached, failed units, degraded state, boot time per unit. E `systemctl
  --failed`, `systemctl is-system-running`, `systemd-analyze blame`. F a failing unit (e.g. Mint's own
  `casper-md5check` on installed systems — upstream, recorded as known).
- **2.2 Kernel modules and drivers:** W which device has which driver, modules refused (signature,
  version), firmware files missing, blacklists, per-kernel driver coverage (DKMS and prebuilt modules).
  E `lsmod`, `/sys/bus/pci/devices/*/driver`, `modinfo -F signer`, `dkms status`, the kernel log
  ("module verification failed", "Key was rejected"), `/etc/modprobe.d`. F **G101** (below); a Wi-Fi card
  with no firmware.
- **2.3 Storage and filesystems:** W mounts, free space and inodes, filesystem errors, SMART health, swap,
  trim. E `df`, `findmnt`, `dumpe2fs` error counts, `smartctl`, the kernel log. F disk nearly full; SMART
  failing; errors counted on a mounted filesystem.
- **2.4 Core services:** W journald, logind, D-Bus, polkit, NetworkManager, CUPS, Bluetooth, udisks2,
  AppArmor, ufw, time sync. E `systemctl status`, their journals, `timedatectl`. F a service crash-looping;
  clock not synchronised (breaks certificates and updates).

**3 — Graphics and display**
- **3.1 GPU driver:** W the kernel graphics driver in use (i915, amdgpu, nouveau, nvidia, or the firmware's
  framebuffer), NVIDIA driver version per kernel, acceleration available. E 2.2's evidence, `/proc/driver/
  nvidia/version`, `glxinfo -B`, `vulkaninfo --summary`. F **G101**; running on the basic framebuffer by
  choice (D50) vs by failure.
- **3.2 Display server:** W Xorg start, driver loaded, modes offered, scale. E `Xorg.0.log`, `xrandr
  --query` (read-only). F resolution choices greyed out (no mode setting: 3.1).
- **3.3 Login:** W LightDM and the greeter, autologin, session start. E their journals. F login loop.
- **3.4 Desktop shell:** W Cinnamon (Muffin) up, fallback mode, crashes, applet errors. E `~/.xsession-
  errors`, Cinnamon's log (Looking Glass), `org.Cinnamon` on D-Bus. F Cinnamon in fallback mode; an applet
  failing to load.
- **3.5 Screens:** W outputs connected, EDID names, hotplug, layout. E `/sys/class/drm/*/status`, EDID.
  F a screen connected but off; a black screen (seen as "desktop never came up" in the boot record).

**4 — User session**
- **4.1 Session manager:** W start-up programs, clients that don't answer, shutdown inhibitors.
  E `cinnamon-session`'s journal, `org.gnome.SessionManager`. F **U101** (below).
- **4.2 User services and buses:** W `systemd --user` units, the session bus, keyring, the accessibility
  bus. E `systemctl --user --failed`, their journals. F keyring locked or corrupt.
- **4.3 Input:** W keyboard layouts, input methods (IBus, Mozc), pointer devices. E `gsettings`, `ibus`.
- **4.4 Home and settings:** W free space in home, permissions, settings database health. E `df`, `dconf`.
  F home full; a broken settings file.

**5 — Connectivity**
- **5.1 Links:** W wired, Wi-Fi (radio switch, driver, firmware, signal), Bluetooth. E `nmcli`, `rfkill`,
  `iw`. **5.2 Addresses and names:** W DHCP, routes, DNS, internet reachability as NetworkManager sees it.
  E `nmcli`, `resolvectl`. **5.3 Firewall and VPN:** W ufw state, VPN links. **5.4 Offline mode** (§12.4):
  W chosen and honoured. F no firmware for a Wi-Fi card; DNS failing while the link is up.

**6 — Software lifecycle**
- **6.1 Package database:** W dpkg state (half-installed, broken dependencies), locks, interrupted runs.
  E `dpkg --audit`, `apt-get check`. F an update interrupted by a power loss.
- **6.2 Sources and keys:** W every source reachable and signed. E `apt-get update` results, `apt-cache
  policy`. F a source that doesn't exist (2026-09-29: our own `cinminai-apt`, not yet published).
- **6.3 Updates:** W pending, security, held, last check, reboot required; **what an update will change**
  (a new kernel series, a driver without a signed module for it). E `apt-get -s dist-upgrade`, `/var/lib/
  apt/periodic`, `/var/run/reboot-required`, Update Manager's history. F **S301** (below): a kernel update
  the installed graphics driver doesn't cover.
- **6.4 Kernels installed:** W which kernels, headers present, which kernel each driver is built and signed
  for, which kernel the loader starts. E `/lib/modules`, `dkms status`, `modinfo -F signer`. F a kernel
  without its drivers (G101's cause).
- **6.5 Other stores:** W Flatpak runtimes and apps. **6.6 Snapshots:** W Timeshift's last snapshot,
  especially before an update (D29).

**7 — Devices in use**
- **7.1 Sound:** W PipeWire, the default output, mute, volume. **7.2 Printing and scanning:** W CUPS
  queues, stuck jobs, SANE. **7.3 Removable storage:** W mounts, safe removal. **7.4 Power states:**
  W suspend and resume, lid, battery health. E `pactl`, `lpstat`, `udisksctl`, the journal. F sound on the
  wrong output; a printer paused; resume failing.

**8 — Applications**
- **8.1 Crashes and hangs:** W core dumps, "not responding" windows. E `coredumpctl`, the journal.
  **8.2 Defaults:** W default programs and file types. **8.3 Big programs:** W LibreOffice and Firefox
  profiles (start-up, corruption, policies). F a program crashing at start; a profile locked.

**9 — The assistant stack** *(ours, watched like any other part)*
- **9.1 The daemon and the model:** W state, profile and why it's reduced (§4.2), graphics memory, model
  file integrity. E `org.cinminai.Assistant1`, `llama-server`'s log, the model's SHA-256. **9.2 Sidebar,
  applet, hotkey:** W the checks the boot test runs (icon running, key bound). **9.3 Diagnostics itself:**
  W the recorder running, its storage, readiness (§20.5).

**10 — Shutdown, restart and the next start**
- **10.1 Session end:** W clients answering, inhibitors, time taken. F **U101**. **10.2 System stop:**
  W stop jobs waiting ("a stop job is running…"), time taken. **10.3 Power off / restart** reached.
  **10.4 Clean or not — seen at the next start:** W the previous boot ended cleanly (journal closed,
  filesystems clean) or not. E `journalctl --list-boots`, the last boot's final lines, 1.4's fsck result.
  F **H401** (below). This closes the loop back to **0**.

**Cross-cutting lenses** (read across the tree, not separate nodes): *security* (Secure Boot 0.2/1.2,
signatures 2.2/6.4, updates 6.3, firewall 5.3, AppArmor 2.4); *change* — the **timeline** (§20.5);
*performance* (boot time 1.3/2.1, memory pressure, CPU and GPU load, temperatures).

### 20.3 Fault codes

A code is a letter for the part of the tree, the node's number, and a fault number: **`G101`** = graphics
(3), node 3.1 → fault 01. Letters: `P` power/firmware (0), `B` boot chain (1), `I` system start (2), `G`
graphics (3), `U` user session (4), `N` connectivity (5), `S` software (6), `D` devices (7), `A`
applications (8), `X` the assistant (9), `H` shutdown and restart (10). Codes are **pending** when seen
once and **confirmed** when seen again or when their rule says one is enough; a code **clears** only after
its fix is verified, or after N clean boots for intermittent ones. `?000` codes per letter mean
"recognised node, unrecognised fault" — recorded in full.

The first worked codes, all from 2026-09-29:

| Code | Meaning | Detected by |
|---|---|---|
| **G101** | The graphics driver is installed but not loaded for the running kernel. Its tree's branches are the causes: the module unsigned while Secure Boot is on; the module's version different from the driver's other files; the driver not supporting this kernel; the module never built for it | NVIDIA package installed; no `nvidia` module loaded (or `NVRM` errors); per kernel: module present, its version, its signer; Secure Boot state; the kernel log |
| **S301** | An installed or pending kernel isn't covered by the graphics driver (not built, not signed, or a driver version that doesn't support it) | per-kernel check of 6.4 before and after every update |
| **B401** | The root filesystem needed a manual check at start | the boot record: initramfs prompt reached, fsck exit status 4 |
| **H401** | The previous session ended without a clean shutdown | 10.4: the last boot's journal ends without a shutdown, or 1.4 found errors |
| **U101** | The session's end was held up by a client that didn't answer | the session manager's journal; the boot test's shutdown check |

Added with the first slice (2026-09-30, from the kernel 7.0 case on the Mint box; `src/cin_minai/diag/`):

| Code | Meaning | Detected by |
|---|---|---|
| **I301** | A disk's link reports errors (failed commands, link resets). Branches: only on one kernel (→ S401), or on every kernel (the cable, port, plug or disk) | kernel log per boot: `ataN.00: exception`, `SError`, the drive's own `ICRC ABRT`, failed command sizes, `limiting SATA link speed` |
| **I302** | Writes to a filesystem failed: data may be lost, the filesystem may go read-only | `I/O error … (WRITE)`, `EXT4-fs warning/error`, `potential data loss`, aborted journal, root mounted read-only |
| **S401** | The faults follow one kernel: on boots with kernel K, none on boots with another | the boots' kernels against their I301/I302/G101 evidence; **cleared** once K is removed |
| **I101** | A system service failed (known-harmless ones, e.g. `casper-md5check` on installed systems, are marked so, not hidden) | `systemctl --failed` |
| **S101** | The package database has unfinished work (an interrupted update) | `dpkg --audit` |

**From the research of 2026-09-30** (Debian / Ubuntu / Linux Mint troubleshooting; sources in `trees.json` per fix):

| Code | Meaning | Detected by |
|---|---|---|
| **P101** | The processor got too hot and throttled itself | `Core/Package temperature above threshold, cpu clock throttled` |
| **P301** | The processor reported a hardware error (machine check) | `mce: [Hardware Error]` |
| **P302** | Memory ran out; the kernel closed a program (named) | `Out of memory: Killed process N (name)` |
| **B301** | The kernel hit an internal error (oops, BUG, panic) | the kernel's own messages — *not* a program's `traps:` / `segfault` line |
| **G102** | The graphics card dropped off the bus, hung, or its driver reported an error | NVIDIA `Xid`, graded: 79 off the bus; 8, 61, 62, 109, 119, 120 the card stopped; others a driver message; AMD `ring … timeout`, Intel `GPU HANG` |
| **A101** | A program crashed (named) | `traps: name[pid] general protection fault`, `name[pid]: segfault at` |
| **X101** | The assistant's model server crashed; branch: in boots with disk errors | the same, for `llama-server` |
| **N101** | Wi-Fi switched off: software (airplane mode) or a hardware switch | `/sys/class/rfkill` |
| **N102** | Wi-Fi hardware but no Wi-Fi device: missing firmware (named) or no driver | `lspci` network controller, no `/sys/class/net/*/wireless`, `Direct firmware load … failed` |
| **D301** | A Windows (NTFS) drive opens read-only: left "dirty", usually by Windows' Fast Startup | `ntfs3: …: volume is dirty` |
| **D302** | A USB device keeps failing to connect (port named) | `device descriptor read/64, error -71`, over-current |
| **I303** | A disk (or /boot) is (nearly) full | `df` |
| **S102** | Packages with broken dependencies | `apt-get check` |
| **U201** | A service in the user's session failed | `systemctl --user --failed` |
| **S601** | No automatic Timeshift snapshots — **advice**, offered, never a fault (D30); unknown if unreadable | `/etc/timeshift/timeshift.json` |

What the real data taught, first run (the Mint box's SSD): a **program's crash looked like a kernel error** (`traps:
llama-server … general protection fault`) until the pattern excluded it, and it surfaced a finding nobody had spotted —
the assistant's model server crashing in both 7.0 boots where files read back with zeros (X101); and **35 × NVIDIA Xid 32
from `modprobe`, a second before a shutdown**, is the driver unloading, not a hung card — Xids are graded. A missing or
unreadable file is "unknown", never "not set up". A rule is only kept once it's right on a real machine.

G101 gained the branch **the driver file reads back damaged** (`ZSTD-decompression failed`, `dkms`: *Diff between built and
installed module*) — on 2026-09-30 that was the disk's link, not the driver. Findings are ranked **cause before symptom**
(S401 → I301 → I302 → G101), so a reader that shows only the first one shows the real fix.

### 20.4 Records and the published format

- **Activity log** (`/var/log/cinminai-diag/events.jsonl`, and the session's part under the user's
  state directory): one JSON line per event — time, node, kind (`state`, `change`, `check`, `fault`,
  `fix`), data. Rotated; kept for a set number of boots.
- **Boot record** (one per boot): firmware mode, Secure Boot, loader entry, kernel and boot options,
  initramfs result, targets reached, graphics driver in use, desktop up (and when), how the previous boot
  ended.
- **Fault record:** code, status, first and last seen, count, the freeze frame, the tree's progress.
- **Freeze frame:** versions (kernel, drivers, packages involved), boot options, the relevant log lines,
  the evidence the rule used, and a **screenshot** when the fault is visual (taken by the session agent,
  kept locally, listed in the record so the user sees it exists).
- **Diagnostic trees** (data files, one per code, versioned with the OS like the help cards): the code's
  plain meaning, the detection rule, **steps** (a check from the catalogue with its expected result, a
  screenshot, or a question for the user) with branches, and **fixes** — each with plain words, an action
  from the fixed catalogue, the privilege it needs (none, user, or administrator through polkit),
  whether it's reversible, and the check that verifies it.
- **Catalogues:** *checks* are small read-only programs with typed results; *actions* are the fixed
  verbs fixes may use (§8.4). Readers name them; they never send shell text (Rules 3 and 5).
- **The interface ("the port")**, all showing the same data: a command, `cinminai-diag` (`status`,
  `codes`, `show CODE`, `tree CODE`, `run CHECK`, `timeline`, `report [--redact]`); a D-Bus service,
  `org.cinminai.Diag1`; and a **report** — Markdown for people and AIs, with the JSON beside it — that
  starts with a short *reading guide*: what the codes mean, what readers may and may not do, how fixes are
  approved. Schema name and version in every file (`cinminai-diag/1`).

### 20.5 How it runs

- **Where:** a small system service that only reads and records (boot record, journal, packages, disks,
  firmware state) and never executes a reader's requests; a session agent for what only the session sees
  (screens, the session manager, screenshots). Readers talk to either; neither runs arbitrary commands.
- **When:** the boot record at every start (including the one after a crash); continuous event watching
  (journal, udev, packages); daily checks (disk space, SMART, updates); **around every change** — a
  snapshot before an update and a check after it, where S301 and G101 are caught (D29's post-check); at
  shutdown; and on demand.
- **Readiness:** which checks have run since this boot, so a reader knows what is known and what isn't.
- **Evidence about a failing disk can't live only on that disk** (2026-09-30): in the 7.0 boots where the SSD failed
  hardest, the system log's own writes failed, so the persisted log lacks the very errors seen live. The recorder keeps
  the current boot's disk and filesystem events in memory (`/run`) and writes them once the disk is healthy again, or to
  another disk (the ESP, a USB stick) — and a report says when a boot's log ends early.
- **The timeline:** every change (packages, kernels, drivers, settings, boot options) against every boot's
  outcome — "what changed since it last worked?" in one list. D42's recovery mode reads the same timeline
  from the USB.
- **Automation:** when a fault is set, its tree's automated steps run by themselves — the checks and
  screenshots a helper would ask for — and stop at anything that needs the user or a password. The
  assistant can then open with the finding: "after yesterday's update your graphics driver didn't load;
  your previous version still works — shall I…?"

### 20.6 Readers

- **The guide** gets one tool, `diagnose` (codes, a node's state, a tree's next step), and explains in
  plain words; its eval (cycle 1) adds diagnostic items built from recorded cases. It must work on the
  guide alone — that's the local test. **Until `diagnose` is trained** (cycle 1), the shipped guide gets the
  active findings with `inspect_system`: the topic's codes ride along as `problems_found` (problem, cause, the
  first fix, its command with what it does and how to undo it). Tested 2026-09-30 on the 1080 Ti with the
  recorded 7.0 case: asked "my graphics stopped working after the update", "is my disk OK?" and "my USB sticks
  say read-only", the guide answered each time with the fix found by hand — switch to the long-term kernel in
  Update Manager — after two wording fixes in the trees (no code numbers in user-facing text; "your main disk",
  not "sda"). The sidebar shows each command as a **card with Copy**, what it does and how to undo it (D53).
- **Bigger local and cloud models** (D35) read the same report, and more of it; **an assistant installed
  on the machine** (Claude, Codex, any other) reads the report and the command; **a person** reads the
  Markdown. Nothing is written for one reader only.

### 20.7 Testing

Every real case becomes a recorded **fixture** — the evidence as it was (command outputs, log lines, boot
records) — and each fault rule is tested against it mechanically. The first fixtures are 2026-09-29's
(G101 / S301 on the Mint box's SSD, B401, H401, U101). The VM runs the monitors on every boot test and
can inject faults the hardware can't be asked for (a full disk, a killed service, an interrupted update).
Coverage — which nodes of §20.2 have monitors, checks and trees — is published with each release, so
the blind spots are listed rather than discovered.

### 20.8 Hardware tests — from the system or from the install USB

The monitors of §20.2 *watch*; hardware tests *exercise*: optional, active tests of the parts, so a fault
that isn't software can be told apart from one that is. They run from the installed system **and from the
install USB**, as part of the same package: when the installed system won't start, or its results can't be
trusted, the stick people are asked to keep (D42) boots its own Linux and tests the machine from outside it
— "is it a bad memory stick or the power supply?" The boot menu gets a **Hardware check** entry (the live
system started straight into the diagnostics) next to the **Memory test** it already carries (Memtest86+).

**What each test can tell** — stated in the results, so no reader over-trusts one:

| Part | Test | Tells | Can't tell |
|---|---|---|---|
| Memory | Memtest86+ from the boot menu (whole memory, outside Linux); `memtester` inside Linux (the free part); kernel memory-error counters (EDAC) | bad cells, a failing stick (with a stick-by-stick retest) | rare timing faults a short run misses |
| CPU | a load test (`stress-ng`) with temperature, clock and throttling watched; machine-check errors (`rasdaemon`); microcode | errors under load, overheating, throttling, a cooler not doing its job | a slow degradation within spec |
| GPU (if fitted) | a video-memory test (e.g. `memtest_vulkan`), a render and compute load (Vulkan / CUDA) with temperature, clocks and power watched (`nvidia-smi`, `sensors`) | bad video memory, artefacts, overheating, power limits hit | the display cable (see Screens) |
| Power supply | motherboard voltage rails (+12 V, +5 V, +3.3 V, CPU core) at rest and **under combined CPU + GPU load**, and whether the machine resets under load | rails sagging or out of range, the classic "turns off under load" | the exact voltages (the board's sensor is approximate; not every board has one) — for that, a multimeter or PSU tester |
| PCIe | each device's negotiated link speed and width against what it's capable of (`lspci -vv`), bus error counters (AER) | a card running at x4 instead of x16, or at a lower generation; a flaky slot or riser | lanes with nothing plugged in |
| Storage | SMART / NVMe self-tests (short and long), a read-only surface scan | failing sectors, a drive near the end of its life | anything by writing: tests never write to a disk |
| Ethernet | link and negotiated speed and duplex (`ethtool`), the port's cable test where the chip supports it, error counters, the chip's self-test where it has one | a bad cable or port, a link stuck at 100 Mb/s | a fault further along the network |
| USB | every port listed; a guided test — plug a stick into each port in turn — records whether it's seen and at what speed | dead ports, a USB 3 port running at USB 2 speed | power delivery beyond what the port reports |
| Controllers and input | game controllers, keyboard and pointer (`evtest`), a key-by-key keyboard check | dead keys, drifting sticks, a controller not seen | — |
| Sound, camera, radios | speaker and microphone loopback, camera capture, a Wi-Fi scan, a Bluetooth scan | outputs, inputs and radios alive | quality |
| Screens | test patterns (dead pixels, colour, backlight bleed), each output with each cable | dead pixels, a bad cable or port | — |
| Fans, temperatures, battery | fan speeds, temperatures at rest and under load, battery capacity against design and charge cycles | a stopped fan, a worn battery | — |

**Rules:** non-destructive only (nothing is written to any disk; memory and load tests run in RAM);
load tests say beforehand what they do (heat, noise, power draw — a laptop plugged in) and run only when
the user starts them, with time limits and a stop button; results are codes like any other (`P` for
power, memory, CPU and inventory; `D` for devices; `I` for storage) with freeze frames. **Keeping the
results from the USB:** the live system runs in memory, so results are shown, can be saved to another USB
stick, and — with the user's approval, through the same boundary as D42 — written into the installed
system's diagnostics log, where its own assistant finds them at the next start. More tests, more
information: the list grows like the diagnostic trees, one tool at a time, each with its "tells / can't
tell".

### 20.9 First slice

**Built 2026-09-30** (`src/cin_minai/diag/`, `cinminai-diag` in the daemon package; tests `tests/unit/test_diag.py` on
the two recorded cases in `tests/fixtures/diag/`): probes for the boot record, drivers and kernels, the disk and its
link, and packages, as an unprivileged user in `adm`; codes G101, S301, I301, I302, S401, H401, I101, S101; the command
(`status`, `report`, `show`, `guide`, `capture`) and the Markdown/JSON report. Still to come in the slice: the system
service (as root: SMART, the boot record at every start, the in-memory event log), B401 and U101, and the trees in the
six languages.


Monitors for the boot record (1, 2.1, 10.4), drivers and kernels (2.2, 3.1, 6.4), updates (6.3) and disk
(2.3); codes G101, S301, B401, H401, U101 with their trees; the command and the report; the guide's
`diagnose` tool. Then node by node, in the tree's order. Hardware tests (§20.8) follow, cheapest first —
the ones that only read what Linux already reports (PCIe link width and speed, SMART self-tests, USB ports
and their speeds, sensors at rest, the battery), then the **Hardware check** boot entry on the USB, then the
load tests (CPU, GPU, power-supply rails under load) and the guided ones (USB ports, keyboard, screens).

## 21. AICUI — the AI coding workspace (PLAN D61)

> **Project environments (Ian, 2026-10-08; built that night).** A folder AICUI works in becomes a project only on the
> person's yes and only inside their home folder (`.cinminai/project.json`, a token); the home folder and the system
> never get one. A project is offered a Python environment; accepting makes `.venv/` a folder holding only a header —
> "the bot can't make it until it knows what it's making". When the work needs a package, the AI asks for it (`need`,
> never pip); AICUI shows the person what and why, and on their yes builds the real environment outside the project
> (`~/.local/share/cinminai/envs/<token>`), links `.venv` to it and writes `requirements.txt`. The working tree shows it
> as one line; environments of projects that are gone are offered for removal. A venv made elsewhere is left alone.

Ian's design (2026-10-02, layout sketch `artwork/aicui-layout-2026-10-02.png`): a simple, clean coding workspace
"like JetBrains in spirit, but not as elaborate: easy navigation and clean-looking coding action". It opens a folder
or a file, like an IDE; one window per project.

**Layout.** Left, tall: **Chat history** — the conversation; the model's *thinking* streams in live and then collapses
into an expandable bubble. Middle, top: **Working tree** — the project's files, git-aware (what changed). Middle, below:
**Session goals**. Right, the largest pane: **AI terminal**. Bottom: the **typing box**, and **model selection** at the
bottom right.

**The AI terminal is a real terminal** (a PTY, VTE in GTK): you see the AI working, and its permission prompts appear
in the terminal "like they always would", as in Claude Code or Codex. You can type in it too.

**Permissions are the user's** (D54: not deciding for people):
- *Ask* (the default): every file change and command is approved in the terminal.
- *Auto mode*: the user approves working without asking, per session.
- *Admin / no admin*: whether the AI may request administrator actions at all (through the D3 lane, polkit per request).
- *No permissions at all* is possible, with a plain warning: strongly advised against until the model's stability is
  tested on this kind of work — "don't risk anything you aren't willing to lose".
Commands run in the sandbox (D1) except where the user lifted it.

**The changelog.** Every file the AI changes goes into the changelog — which file, what changed (the diff), when,
which model, for which goal — with undo per change. Kept whatever the permission mode, so even auto mode can be
reviewed and rolled back.

**Session goals, written by both.** At the start the AI asks about the project's goals and scope (as the writing
partner gathers a story) and fills the goals in; the user adds and edits them. Once work starts they are the AI's
to-do list, ticked as they're done (the writer's tick boxes, D57); they stay with the project for the next session.

**Models.** Local by default: the system matcher's coding model (D60; on the 1080 Ti, Qwen3.8-27B IQ3_XXS at 14 tok/s).
Cloud providers connect per D35: OAuth sign-in through the web browser where the provider offers it, otherwise an API
key, stored in the keyring; the CLOUD indicator shows it. The model can be switched while the AI is idle; some context
is lost in the switch (the goals, the changelog and a summary carry over) — "let's see how that goes".

**Settled (Ian, 2026-10-02):**
- *The changelog's place:* a button at the bottom of the Working tree pane switches the pane to the changelog; it
  minimizes back to the tree.
- *Multiple models:* local alone, cloud alone, or **both together** — to save cloud tokens: by default the local model
  does the volume (reading and searching the project, routine edits, running tests, summarizing output) and the cloud
  model the judgement (planning, the hard bug, review); roles adjustable per session. Both share the goals and the
  changelog, so the cloud model is sent only what it needs. Any cloud model can run alone too; the terminal can also
  run other agents' command-line tools (Claude Code, Codex), whose file changes the changelog records like ours.
- *Claude first:* an **API key** button (one paste, into the keyring) — the API's intended use. An **OAuth** button only
  if Anthropic's terms allow a third-party app to sign in with a Claude account; then it launches their sign-in in the
  browser however they specify. Checked before it's built; until then, the key covers it.
- *GitHub for syncing:* sign-in through GitHub's official OAuth **device flow** (a short code confirmed in the browser)
  or a pasted token, in the keyring; git uses it through the system's credential helper.
- *The changelog is git under the hood, never in the user's history:* a **shadow git store** per project (in
  `.cinminai/` beside the project's files) keeps a snapshot of every AI change with its model, its goal and its diff;
  undo restores the file exactly; it works in folders that aren't git repositories. AICUI never commits, stages or
  pushes in the user's own repository by itself; when a goal is done it **offers** a real commit of that goal's changes
  with a drafted message to approve or edit (D30), pushed through the GitHub sign-in.

## 22. The model system (PLAN D93, D94, D95)

One system, seen from the person's chair: they ask; the right models do the work, placed on the hardware on their
own; every step can be seen and stopped; nothing changes the system or leaves the computer without the person.
Decided 2026-10-07/08 with Ian ("this is all intertwined into a whole experience and should be considered as such").

### 22.1 The experience

1. **The person asks** — typed, or spoken later (D91) — in their own words.
2. **The guide (the tuned 4B) is always there** and works out what it means: it answers itself when it can, or turns
   the request into tasks (turn tokens, §22.4) for the models whose job they are.
3. **Each kind of task has a model**, chosen by the person in the Models view, with our pick for this computer as the
   default (§22.3).
4. **Models are placed on the hardware automatically** (§22.2): the person never manages memory.
5. **Models hand work to each other** in small, checked steps (§22.5); what fails goes back to whoever owns it.
6. **Anything that changes the system goes through the guide and the admin service** — Allow and the password, or
   the key for automation (§22.6); anything that leaves the computer is shown first (D86).
7. **The person sees it as it happens**: what's queued, who works on what and why; Stop cancels a request with every
   task it spawned.
8. **Honesty runs through every layer** (§22.7).

### 22.2 Placement

- The guide has a usable place at all times: on the graphics card when there's room, else on the processor (D27's
  smaller context there). A big model gets the card.
- **Measured on Ian's PC (2026-10-08; i7-4790K, DDR3, GTX 1080 Ti):** the 27B on the card and the 4B on the processor
  at the same time don't slow each other — 27B 15.4 → 15.3 tokens/s writing, 4B 6.8 → 6.7. A permanent helper beside
  the big model is free on such a machine.
- **Step down and back up:** a model that falls back to the processor because the card is busy moves back onto it as
  soon as there's room and it isn't answering (built 2026-10-08; it used to stay on the processor until a restart).
- Each model has its own server (the guide, the big model, a reader for pictures); a model that isn't loaded is loaded
  when a task needs it, and the person sees that it's loading.
- A small "draft" model on the processor that speeds up the big one (speculative decoding) is measured when one with
  the big model's vocabulary exists (Qwen3.8 has no small sibling, 2026-10-08).

### 22.3 Models per task (D93)

The Models view (start screen and panel menu): everyday help (the guide), the news and searches, writing, coding
(AICUI), pictures and video, research papers — each with the model it uses now and our pick as the default ("use ours
again" is one click). Changing one: our catalogue first (measured, licences read), then a Hugging Face search of every
GGUF model llama.cpp can run, each checked against this machine before it's offered (memory from the file's own
header, the split it would use), with its licence as published ("licence not reviewed by us" where we haven't read
it); download with resume and the fingerprint check, a speed test here, then assign it. Models already on a drive are
found, not downloaded again. A small helper asks what the person wants to do and suggests a setup; they decide. The
CUDA engine is offered on one card once the NVIDIA driver is in (built 2026-10-08).

*As built (2026-10-08, `daemon/jobs.py`, `daemon/hub.py`):* the view lists each job with its model (ours or the
person's choice) and the models here, with Remove for one no job uses. The search says first that its words go to
Hugging Face and nothing else (D86). A repository's files are pinned to its current revision with the SHA-256 from its
own record; "Does it run here?" reads the file's first 8–96 MB (a range request) and answers per job. Download (the
store's: resumes, checked), a speed test as the job will load it, then the job. Models on connected drives are copied
in. The news and searches have no line: their reports are built in code, not by a model (D92). Not yet: models in
parts, models that ask for a Hugging Face sign-in, a picture reader for a found model, and the setup helper.

**Jobs, and the Requests view (Ian, 2026-10-08: "the requests list ties to the model list… we may try a combo with an
old Qwen coder instead of 4B that works better for certain things").** The Models view assigns a model to each *job*,
finer than a task's kind: help and the system, laying out code (the junior), writing code (the senior), reviewing, news
and searches, writing, pictures and video, research papers. Every job takes any model — ours or one found on Hugging
Face — except **help and the system**, which holds the system and admin tools and stays with a model we trained and
measured (§22.5; shown locked). The **Requests view** (start screen, panel menu, `--requests`) lists recent requests
as trees: each task with its state, its kind, and **which model did it** (recorded when it finishes), with Stop on
anything not finished. So a combination is judged by what it did: swap the junior for an older coder model, and the
Requests view shows how its tasks went. Built 2026-10-08: the Requests view, the model recorded per task, Stop from
the view.

### 22.4 Turn tokens (D95)

Every request becomes a **turn token** — from the person, a recipe (D91), or another model. Each model has its own
queue: quick repeated requests stack as tasks instead of blocking each other or getting lost. A token holds who asked,
for whom, what to do, the token it came from (so a request's whole tree is known), its state (waiting, working, done,
failed, cancelled) and its result. Every token is written to the record.

- **Size: 5 % of the receiving model's context** (Ian, 2026-10-08) — at 32K about 1,600 tokens; the 4B on the
  processor (8K) about 400, since it reads ~33 tokens/s there. A token says what to do; bulk stays in files and the
  token points to them ("fill in src/x.cpp against include/x.h"). A token that would be bigger is refused with "put it
  in a file and point to it".
- **Budgets per request:** how many tokens one request may spawn, and how deep hand-offs may go; when a budget runs
  out, the work stops and says where it is (as AICUI's stuck check). Two models never ping-pong for ever.
- **Priority:** the person's own requests come first.
- **Models work at the same time** where their tokens allow (§22.2: free) — the guide lays file 2 while the big model
  fills file 1. Measured 2026-10-08: handing over *in sequence* doesn't pay (the 4B on the processor took 5:45 to lay
  a framework the 27B lays in 1:53 on the card); working *at the same time* is where the gain is.
- **Stop** cancels a request and every token under it.

### 22.5 Roles and hand-offs (D94)

- **The guide** (the model we trained and measured) holds the system and admin tools; it orchestrates, retrieves
  information, lays frameworks and checks goals. **Any other model** — any publisher (D93) — is untrusted weights: it
  gets only its task, never system tools.
- **Orchestration is recipes in code** (D91): the guide picks the recipe and fills the blanks.
- **Contracts first:** a framework settles the interface and the edge behaviour in the header (which error, what
  happens at the limits) — 2026-10-08: the same model, as junior and as senior, chose two different exceptions for one
  rule, and the test failed.
- **Every result is checked in code before it's accepted** — it compiles, the tests pass, the page loads, the setting
  changed — and a failure goes back, as a token with the exact error, to the model that owns that file. The guide
  judges only where no check can exist. (2026-10-08: a returned file carried notes outside its comments; one compile
  would have sent it straight back.)
- **Each token says its scope**: what's this model's and what's someone else's ("implement only what belongs in this
  file") — 2026-10-08: filling files separately, a model re-implemented another file's functions and the program
  didn't link.
- **Reviews by a different model**, never the worker and not the guide; batched (one model at a time on a card);
  disagreements shown, not settled (as D92). A model from another family is the most independent reviewer.
- **Cloud models by choice** as the final check or the whole job (OpenAI and Anthropic now; Gemini and Grok later);
  their keys through the key card into the login keyring; what's sent shown first.

**As built in AICUI (2026-10-08, slice 3).** The guide organizes on the processor beside the coding model on the
card; it never reads code, but the map, the problems the checks find, each goal's cycle state and short summaries of
what the coder did. Every move follows one contract, checked by code rather than by its wording: it says what it acts
on, and a task also what proves it's done; what the person just gave (a link, a project file, pasted material — kept
as a source) is used first, or the move goes back once and then to the person; a task that changed nothing comes back
as such, and two in a row go to the person; the coder may decline a task with its reason. Stuck: one hint (from the
problems when the checks name any), then the person. Ian: "We can't just auto code what to do. This has to be
generalized for function."

### 22.6 Admin, and the key

Admin actions go through the guide and cinminai-admin's typed verbs, every one recorded (D85). Built 2026-10-08:
installing a program by name, the recommended graphics driver, and the CUDA engine on the Allow card — then the system
asks for the password. With the key in (D94; a FIDO2 security key is the strong option), admin actions may run in Auto
— typed verbs only, each recorded; pulling it ends that at once; wiping a disk and the like still ask. Ian sets the
defences; the AI — Mythos as the long-term security suite — finds and fixes within them.

### 22.7 Honesty

Facts come from sources, never memory alone: a source the person gives beats what a model remembers (a difference is
said once, not a reason to stop); a list a model can't know is said to be unknowable, not invented. The news says who
says what (D92). AICUI shows the model what it just wrote after every write — repeated lines, repeated names, rows
identical except for one name — and a coding model is recommended only if it passes the honesty eval
(`training/eval/aicui/honesty.py`): asked for a long factual list it can't know, it says so. (2026-10-08: the 27B
noticed it had been inventing entries, stopped, told the person plainly and proposed a data file — the behaviour this
section protects.)

### 22.8 Build order (update 6)

1. **The core:** a turn-token queue per model, placement, step down and up (done), the token record and its view.
2. **The Models view** (D93).
3. **Roles and hand-offs:** the guide lays out and checks, the big model builds, the fix loop. Its acceptance test is
   round 3 of the tandem measurement — the two at the same time, contracts in the header, a check after every file,
   errors back to their owner — ending in a build whose tests pass.
4. **Admin automation with the key, and cloud reviewers.**

## 23. Habits: fetch, structure, check, use, review, assimilate (PLAN D96)

One way of working for every job with bulk in it — code, a PDF, a video, a list, the system's logs. Ian, 2026-10-08:
"There is something I see here as universal in habit: jsons, automated scripts for quick habit retrieval like maybe
reading a pdf and summarizing or fetching a youtube video and summarizing, or in code doing the json then checking
it, or scripting or whatever then checking it." And the cycle, in his words: **fetch – structure – check – use –
review – assimilate.**

**The principle: the model directs, code carries the bulk.** A model's context is small (8–16K here) and its memory
of facts is unreliable; a script reads a 300-page PDF or a 126-row set list without effort and without inventing a
row. So the model decides and writes small programs; code fetches, shapes and checks; the model works from the result.
Measured the day it was named: on a long coding job the model typed ~340 lines of real-world data from memory — two
steps overran their limit, the data was partly guessed, and a source it had been given went unused. Every failure was
a step of this cycle skipped.

### 23.1 The six steps

1. **Fetch** — code brings the material in (a page, a file, a transcript, a feed, logs). What leaves the computer is
   shown first (D86); the model doesn't read the bulk.
2. **Structure** — code turns it into JSON (or CSV for plain tables): sections with pages, segments with times, rows
   with fields. From here on that file is the source of truth, not the model's memory.
3. **Check** — code checks the data: the count, no empty fields, every page or minute covered, a sample compared
   against the source. Mechanical: *is the data right?* Only checked data goes on.
4. **Use** — the model works from the checked JSON: it summarizes, codes, answers, reading what it needs.
5. **Review** — a judgment on the result: *did it do what was asked, and is it good?* Never by the model that did the
   work (D94): the reviewing job (§22.3), the person, or a cloud reviewer when the person allows one.
6. **Assimilate** — what passed review goes back into the system, with where it came from (which run, which source,
   who reviewed):
   - a script and its check that worked → a **habit**, run by name next time;
   - a failure review caught → a **new check**, so it can't pass again;
   - how the person likes things done → a **preference** the next run starts from;
   - a project shape that worked → a **kit** (a starting point for that kind of project).

Small asks stay direct ("what time is it", a one-line edit). The cycle is for **bulk** (more than ~30 items or more
than a page) and for anything **done before**.

### 23.2 A habit

A folder with three files — `habit.json` (name, what it's for, what it takes and gives as JSON schemas, the
permissions it needs, its origin, its runs: how many, the last that passed, the last that failed), `run.py` (fetch and
structure) and `check.py` (the check, exit 0 = passed, its findings as JSON). Three places: shipped with the system
(`/usr/share/cinminai/habits`, ours, reviewed), the person's own (`~/.local/share/cinminai/habits`), and a project's
(`.cinminai/habits` in AICUI). First shipped: a PDF to sections, a video to timed segments (the video pipeline), a web
page to its text and tables, a table to rows, a list from a named source.

**Who does what (D94):** running a habit is choosing it, filling its inputs and reading a small result — the guide
can do that; writing a new habit is coding — the coding model; reviewing is another model or the person. The tandem
split (§22.5) follows from the work itself.

**Every run is a task on the Team Table (§22.4)** with its inputs, its output, the check's verdict and the review's;
the Requests view shows it.

### 23.3 Rules

- **Assimilate only what passed review** — otherwise mistakes are learned and repeated.
- **Assimilating changes the system, so it is suggested, never decided (Rule 9, D30):** a new habit, preference or
  kit is offered with its reason ("this worked three times — keep it as a habit?"). A check learned from a failure
  only adds caution and may be added on its own; it is listed and can be removed.
- **Everything assimilated keeps its origin** and can be traced and undone.
- **Habits are code:** they run in the sandbox (D1) under the action modes (D85) — reversible ones may run
  automatically, anything else asks; network only if the habit declares it and the person allows it. A habit from
  anyone else is shown and reviewed before its first run. No habit holds admin tools (D94).
- **A check is only as good as what it checks:** counts catch missing rows, not wrong ones — checks also compare
  samples against the source.
- **Honest reports:** a failed check or review is said plainly, with what failed.

### 23.3b As built in AICUI (2026-10-08 night)

- **Fetch:** whatever comes in is kept whole in the project — a page as `sources/<name>.txt` (every piece of text,
  pictures' and links' own words included) beside `sources/<name>.html` as it came; a file as it came under `assets/`;
  the person's pasted material as `sources/pasted-N.txt`. Always asked first (D86).
- **The cycle per goal:** AICUI records what was fetched and the data made from it while a goal was worked, and shows
  each goal's stages to both models — fetched, structured, checked by a test, used by the code, reviewed (ticked by
  the person). A goal isn't ticked while data recorded for it isn't read by a passing test.
- **One progress rule:** progress is an action of four kinds, and nothing else (Ian, 2026-10-09: "The only 4 things
  that qualify as an action that counts as progress is pass, fail, write, delete. Accept, reject, create, destroy.
  Assimilate, Dissimilate, Disseminate, Annihilate"): a verdict (pass / fail — a check's result, when it's new),
  content (write / delete), a decision (accept / reject — the person's, or the coder declining a task), existence
  (create / destroy — a goal, an environment). Reading, listing, searching, fetching, looking and thinking gather; the
  cycle's own steps count when they land as one of the four. Six steps without one are said (and recorded), again at
  twelve; fifteen stop the task — a hint, then the person.

### 23.4 Build order

1. **AICUI, data from scripts:** a list over ~30 items comes from a script into a data file and is checked before
   code uses it; long literal data written into code is flagged by the summary after each write. Measured on a long
   coding job with real-world data, before and after.
2. **The habit format and the first shipped habits**, reshaped from what the daemon already does (video, web page,
   tables), plus PDF.
3. **Review and assimilation:** the reviewing job, the offer card for a new habit, learned checks; with slice 3 of
   §22.8 (the guide runs habits, the big model writes them).
