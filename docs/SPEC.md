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

Ship an installable desktop operating system, forked from Linux Mint Cinnamon, in which a locally
running AI assistant is a native part of the system rather than an app you add:

* It lives in the desktop — a Cinnamon panel applet, a docked sidebar, and a global hotkey.
* It is attached to the user's **real terminals** — it can see commands, output, exit codes, and
  working directory, and it can place a command at the prompt.
* It is attached to **Firefox** — it can read the page or selection the user shares and answer in a
  Firefox sidebar.
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
page is shared) and can turn it off per terminal, per session, or globally. Nothing is captured
while it is off.

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
* Ollama (pinned version, from our repo) and its system service, not yet running a model.
* The shell integration enabled for all users by default (with the per-terminal off switch).
* Firefox with our extension force-installed by enterprise policy.
* **No model weights** on the standard ISO. They are downloaded during first-boot setup (§9). An
  "offline" ISO variant with a default model bundled can come later.
* No proprietary NVIDIA driver preinstalled; first-boot setup selects one (§3.6).

### 3.5 Installer and first boot

* Mint's installer, rebranded (Stage 1), later patched (Stage 2) to add the AI setup pages.
* The live session works with the assistant in CPU mode or with a small model if the user chooses,
  so the assistant can help with installation problems.
* First login runs the AI setup (§9): hardware detection, driver, model download, benchmark.

### 3.6 NVIDIA and Pascal

* CUDA 13 dropped Pascal (compute 6.1). Ollama still ships a CUDA 12 runner that supports it.
* Pascal requires driver **570+**; the **580 branch is the last** to support Pascal.
* The distro must never silently move a Pascal machine past 580.x. Ship an apt pin / Driver Manager
  rule for detected Pascal cards and warn before any manual upgrade.
* No prebuilt Linux llama.cpp binary targets Pascal: build against CUDA 12 or use Vulkan.
* Pin known-good Ollama versions in our repo; don't follow upstream blindly.

### 3.7 Updates

* Our packages update through Mint's Update Manager like everything else.
* When Mint releases a new version of a package we forked, we rebase, rebuild, and publish before
  users would otherwise be held back. Track this with automation (§15).
* Distro upgrades (e.g. 22.x → 23) are handled like Mint's, with our repo switched to the new series.

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
│  terminal relay   native-messaging     Ollama HTTP    bwrap   system bus     │
│  (per terminal)   host (Firefox)       (localhost)    runner   (admin)       │
│      │                │                   │              │      │            │
│  bash/zsh in any  Firefox sidebar      ollama.service  sandboxed│            │
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
| `cinminai-admin` | root, D-Bus activated | Privileged mechanism behind polkit (§8.4) |
| `cinminai-sandbox` | user | bwrap profile + runner (§8.2) |
| `cinminai-setup` | user (+ admin for driver) | First-boot hardware/model configurator (§9) |
| `cinminai-ollama` | system | Pinned Ollama build and service config |
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
on the input, pre-attached to the focused window's context (the focused terminal, or the Firefox tab).

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

## 7. Firefox integration

### 7.1 Extension

A WebExtension, **force-installed** by an enterprise policy file shipped in `cinminai-firefox`, and
signed by Mozilla (unlisted/self-distributed signing — release Firefox refuses unsigned extensions).

* A Firefox sidebar panel showing the same assistant conversation (or a browser-scoped one).
* Context menu: "Ask about selection", "Ask about this page", "Send to assistant".
* The page is shared only on user action. There is no background reading of pages.

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
* Network allowed by default for builds; toggleable per workspace.

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
backend = "ollama"
model = "qwen3.5:9b"
context = 8192
kv_cache = "auto"
```

Rules: never decide from GPU name alone; unsupported hardware is never fatal if CPU mode works;
never promise a tokens-per-second rate — measure it.

---

## 10. Model

### 10.1 Choice

The model is a configuration value chosen by benchmark (PLAN §3). The expected default is
Qwen3.5-9B; Qwen2.5-Coder-7B is the control baseline. Deployment context is chosen by memory and
benchmark — never the model's maximum on small cards.

| Class | Typical GPU | VRAM | Starting profile |
|-------|-------------|-----:|------------------|
| Legacy | GTX 1070 | 8 GB | small model / 9B Q4 after validation, 4–8K |
| Legacy+ | GTX 1080 Ti | 11 GB | 9B Q4–Q6, 8–16K |
| Modern | RTX, 12 GB+ | 12+ GB | benchmark-driven |
| CPU | none usable | RAM | smallest profile |

### 10.2 Backend abstraction

```python
class InferenceBackend:
    async def stream(...)
    async def generate(...)
    async def health(...)
    async def model_info(...)
    async def unload(...)
```

`OllamaBackend` first (simplest, Pascal-capable CUDA 12 runner). `LlamaCppBackend` second, for
runtime LoRA (`--lora`) and low-level control. Supports: stock model, stock + LoRA adapter, merged model.

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
│   ├── inference/           backend interface, ollama, llama_cpp
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
