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
| `cinminai-llama` | user (systemd `--user`, started by the daemon) | Pinned llama.cpp build (`llama-server`; CUDA 12, Vulkan, CPU backends) and its service |
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
button. Approval authorizes that one action once. No "always allow" in v1.

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
