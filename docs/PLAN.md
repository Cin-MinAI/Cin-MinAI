# Cin-minAI — Implementation Plan

Living plan for the Cin-minAI distribution. The design is in [SPEC.md](SPEC.md); section references
like §6.2 point there. This document records decisions and milestones and **overrides the spec where
they differ**.

Last updated: 2026-09-25 (vision + community oversight, D26; M9 user-built software)

---

## 1. Decisions log

| # | Decision | Status |
|---|----------|--------|
| D1 | The safety boundary is enforced by an OS sandbox (bubblewrap), not by classifying command strings. The classifier only picks which button a command card shows. | kept (SPEC §8.2) |
| D2 | Three action lanes: `SANDBOXED`, `USER_APPROVED`, `ADMIN`. | kept (SPEC §8.1) |
| D3 | Polkit uses `auth_admin` only — never `auth_admin_keep`. | kept (SPEC §8.4) |
| D4 | The model is a config value chosen by benchmark. Expected default Qwen3.5-9B; Qwen2.5-Coder-7B is the control baseline. | kept |
| D5 | **llama.cpp (`llama-server`) is the only inference backend** — built and packaged by us (CUDA 12 incl. Pascal sm_61, Vulkan, CPU), so every knob (quant, GPU layers, context, KV-cache type, flash attention, batch, threads, LoRA) is ours to tune. No Ollama. | changed 2026-09-24 |
| D6 | Tool calls use schema-constrained JSON output (llama.cpp JSON schema / GBNF grammar), not free-form function calling. | kept |
| D7 | Thinking mode off by default; opt-in for multi-step diagnosis. | kept |
| D8 | LoRA base model is not decided until after the baseline benchmark. | kept |
| D9 | Private GitHub repo. Develop on the Windows PC (WSL2 for builds, Hyper-V VM for ISO tests); validate hardware on the Mint box. | amended |
| D10 | **The product is a Linux Mint Cinnamon–derived distribution**, not an app. Base: Mint 22.x / Ubuntu 24.04. Supersedes the original spec's app scope. | new |
| D11 | Build in stages: (1) scripted remaster of the official Mint ISO plus our apt repo; (2) fork Mint packages where extension points aren't enough; (3) from-scratch build only if (1) stops being maintainable. | new |
| D12 | The AI surface is OS-wide: a `systemd --user` daemon, a Cinnamon applet, a docked sidebar, and a global hotkey. No standalone terminal app. | new |
| D13 | Terminal attach via a PTY relay + OSC 133 shell hooks (works with any terminal, TTYs, SSH). A patch to the default VTE terminal is evaluated in M0 as a complement, not a replacement. | new, pending spike |
| D14 | Firefox integration via a Mozilla-signed WebExtension, force-installed by enterprise policy, talking to the daemon through native messaging. Replaces the original bookmarklet / `qwen://` scheme. | new; confirmed by the M0 spike 2026-09-25 |
| D15 | IPC: session D-Bus (`org.cinminai.Assistant1`) for desktop clients; a D-Bus-activated system service (`org.cinminai.Admin1`) with polkit checks for admin actions, replacing a `pkexec` helper. The sandbox mounts neither bus nor the daemon's sockets. | new |
| D16 | Python 3 from the base system with Debian-packaged dependencies. No venv/pip at runtime. GTK 3 / XApp for UI, matching Mint's own tools. | new |
| D17 | The distro must be rebranded; it can't ship as "Linux Mint". Name: **Cin-MinAI OS** (short: Cin-MinAI), decided 2026-09-24. Technical ids keep the `cinminai` prefix. | decided |
| D18 | Model weights are not on the standard ISO; first-boot setup downloads and benchmarks them. | **superseded by D23** (2026-09-25) |
| D19 | Nothing is captured from a terminal while its echo is off, and every terminal shows whether the assistant can see it. | new (SPEC §6.3) |
| D20 | LibreOffice integration through a Python-UNO extension with a fixed, schema-checked document toolkit; reads only shared documents; every edit previewed, approved, and one Ctrl+Z to undo. | new 2026-09-24 (SPEC §7.6–7.10) |
| D21 | **The product is the installable ISO; the Mint box is only a shared test machine.** It runs other projects: spikes there stay user-level, reversible, and are removed when done; no changes to its services (incl. `qwen14b.service`), drivers, boot setup, or desktop settings. Nothing we build may depend on that machine's state — everything ships as packages. Full-system tests install the ISO onto a dedicated, physically separate 120 GB SATA SSD (third boot drive, chosen in the firmware boot menu); the installer and its bootloader touch only that disk. | new 2026-09-24 |
| D22 | **Audience: Windows users new to Linux.** Everyday use needs no terminal; mouse + familiar keys; plain-language dialogs; the assistant bridges from Windows concepts. Spike tools (e.g. `lo_assist.py`) are for testing only. | new 2026-09-25 (SPEC §1) |
| D23 | **A small "guide" model ships on the ISO** (with its transition knowledge base): the assistant works offline from the live USB through install and after. Larger models are optional downloads. Supersedes D18. | new 2026-09-25 (SPEC §10.6) |
| D24 | **Hardware ethos: plan for a 6 GB GPU floor, NVIDIA and AMD** (CUDA and Vulkan builds); 8 GB is the common case. Minimum requirements are about affordable hardware (storage, RAM, PCIe lanes), never new-card purchases. No 6 GB card on hand: enforce a 6 GB budget in software on the 1080 Ti/4070 for tests. | new 2026-09-25 (SPEC §10.1) |
| D25 | **v1 languages: English, Spanish, Portuguese, French, German, Japanese** — top web languages, leaving out ones under sanctions or that will build their own. Applies to the guide model, knowledge base, UI text, and later voice. Japanese also needs a CJK font and a Japanese input method (IBus + Mozc) on the ISO. | confirmed 2026-09-25 (Japanese added by the user) |
| D26 | **Vision and community oversight** (SPEC §1 Vision): AI becomes the way people use their computer; we build the local, owned, human-approved version of that **in the open** — code, spec, decisions, eval tasks and results, model licences all public, reviewable and forkable by the community it's built for. When the repo goes public is an open question (§6). | new 2026-09-25 |
| D27 | **Works everywhere, best installed and online.** The live USB runs the guide (CPU, or GPU if a free driver can) as a supported but reduced mode, and it recommends installing, as Mint does; no internet needed, but the web makes it better. We don't tune the product for running from USB. On CPU the guide keeps prompts short (~1K tokens: small system prompt, a few help-card snippets, trimmed history): the M0 smoke test took 87 s to read 4K tokens on the i7-4790K. | new 2026-09-25 |
| D28 | **Design persona: the careful newcomer** — an older person trying AI/Linux, distrustful of anything online, still keeps a checkbook (SPEC §1). Requirements: real system-wide offline mode with one "go online for updates" button and a "what has this computer sent?" page (§12.4, M5); a checkbook register template worked by the assistant, local file + USB backup reminder (§7.11, M6, toolkit `append_rows`); scam help and the promise "Cin-MinAI never calls, emails, or asks for money or passwords" (§10.6, guide knowledge base). | new 2026-09-25 |
| D29 | **Updates you can watch; sights and sounds throughout.** A Cin-MinAI update window shows each real step — safety snapshot, signature check, per-file fingerprint check, install, post-check, (re)disconnect — with only genuine checks, plain-language package names, honest monthly reminders ("updates fix weaknesses criminals look for"), and a shared vocabulary of sounds + visuals (SPEC §3.7.1, §5.7), each with an accessible equivalent. | new 2026-09-25 |
| D30 | **Suggest and offer; the user decides** (SPEC Rule 9). Beyond what the system needs to work, choices are recommended with a reason and offered, never silently applied; other projects' tools stay welcome. First application: **virus checking** — no antivirus by default (Mint ships none; threats here are mostly scams); ClamAV **offered** at first boot/when asked, carried on the ISO as an offline repo, with a "Check for viruses" right-click action; any other scanner the user picks is supported. Firewall: offered at first boot as recommended-on. | new 2026-09-25 |
| D31 | **Two update schedules; a public model cycle.** Security updates are continuous; releases come twice a year with Mint's point releases, and each carries **the model cycle**: a public review (community-nominated candidates, licence + hardware filters, the published bakeoff incl. failures, fine-tune, ship only if it beats the current model without losing on safety/declines/persona tasks). New models are offered, never forced; the old one stays for a switch back. The M0 bakeoff is cycle zero. (SPEC §3.7.0, §10.7) | new 2026-09-25 |
| D32 | **The guide's fine-tune is only for the Windows → Linux transition**, with a **published corpus** (`training/datasets/transition/`, generated by local open models, filtered, decontaminated) updated every OS release; anyone can rebuild the guide from it. Declines, scam help, office tools and system checks are handled by the prompt, knowledge base, tools and daemon checks, not by training. End users first at every step: simple, effective tools and easy ways to find them. | new 2026-09-25 |
| D33 | **Ease and reliability are the standard; take cheap, measured gains.** Every optimization is measured on its own (A/B, same inputs), adopted only if it helps, and recorded; nothing is tuned by feel. Backlog below (§3 "Optimization backlog"). | new 2026-09-25 |
| D34 | **MVP = the careful newcomer + the everyday user, on Mint** (SPEC §1). The tinkerer / Pi OS port comes after, as outreach to developers. **Purpose beyond the product: start and influence community-developed AI projects** — we want more of them, the odd ones, and the established ones that don't mind the odd. So our reusable parts are built to stand alone and be adopted separately: the guide eval + held-out method, the corpus pipeline (local teachers, mechanical filters, decontamination), `extract_labels.py`, `bench/run.py`, and the public model cycle (D31). | new 2026-09-25 |
| D35 | **Cloud models: opt-in backends, starting with IDEs (post-v0.1).** llama.cpp stays the only built-in backend and the default (amends D5: "only" → "only built-in"); cloud providers are connected per provider by the user, with one-button OAuth sign-in where the provider offers it, otherwise a key pasted once; credentials in the system keyring; a CLOUD state in the LOCAL/WEB indicator; same sandbox, approvals and rules as local models. | new 2026-09-25 |
| D36 | **Concerns we can't address ourselves are published as requests for help** (`docs/HELP-WANTED.md`): what we have, what's missing, and what a useful contribution looks like — AMD/Vulkan, everyday laptops with integrated graphics, ARM, native-speaker review of the six languages, an outside security review before release, real Windows-switcher questions, board-repair know-how. Kept current like the decisions log. | new 2026-09-25 |

### D1 — Sandbox details

Every assistant command in the `SANDBOXED` lane runs under `bwrap` with `--new-session` and
no-new-privs, read-only system binds, read-write workspace only, `$HOME` not mounted, minimal
`/dev`, and **no** system bus, session bus, or daemon sockets (so `systemctl restart …` cannot
raise a real polkit dialog and sandboxed code cannot ask the daemon for approval). Network on by
default for builds, toggleable per workspace — **always through a private network namespace
(`pasta`, from the `passt` package), never the host's**: the M0 spike showed that with the host
network namespace, sandboxed code can connect to the X server through its abstract socket (Mint
allows any process of the user) and to every service on 127.0.0.1. `cinminai-sandbox` depends on
`bubblewrap` and `passt`, and relies on Mint's `kernel.apparmor_restrict_unprivileged_userns=0`
(stock Ubuntu 24.04 sets 1; if that changes, ship AppArmor profiles for bwrap/pasta). The security
tests (SPEC §16.1) run against this profile (`spikes/sandbox/check.py`).

### D11 — Why remaster first

Every Mint derivative starts by adding packages to an existing base. Stage 1 gives a bootable,
installable, updateable system early, and all of our own packages are needed in every stage anyway.
Stage 2 forks are limited to what the integration needs (expected: Cinnamon for sidebar docking,
`mintwelcome` for first-boot setup, installer slideshow and branding). Each fork is a patch series in
`forks/` so rebasing onto a new Mint version is mechanical.

### D13 — Why a relay

A shell hook alone sees commands and exit codes but not output. Patching the default terminal sees
output but only in that one terminal. A PTY relay between the terminal and the shell sees everything
in every terminal, can place text at the prompt (no `TIOCSTI`, which modern kernels disable), and
reuses the pyte emulation from the terminal spike. Risks to measure in M0: added latency,
throughput, and edge cases (`sudo -i`, `su`, `tmux`, `ssh`, nested shells).

---

## 2. Hardware and environment

| Machine | Role | Specs | Notes |
|---------|------|-------|-------|
| Dev PC (Windows 10 Pro) | development, package + ISO builds, VM tests, "modern" GPU profile | Ryzen 9 3900X, RTX 4070 12 GB, driver 591 | Virtualization enabled 2026-09-24. WSL2 Ubuntu 24.04 for builds (install pending). Hyper-V VMs to boot and install ISOs (no GPU in VM). |
| Mint box (`mint@192.168.5.70`) | **Test machine only** (D21): Pascal live runs, hardware tests, benchmarks | i7-4790K, GTX 1080 Ti 11 GB, 32 GB DDR3, Z97X-UD5H; Mint 22.3, kernel 7.0, driver 580.178 | Shared with other projects; already has 2 boot drives, physically separate. Full install test at MVP: our ISO onto a dedicated 120 GB SATA SSD as a third, separate boot drive (pick it in the firmware boot menu; installer and GRUB go to that SSD only). |

Build environment: Ubuntu 24.04 (matches Mint 22.x's base) with `squashfs-tools`, `xorriso`,
`debootstrap`, `devscripts`, `sbuild`/`pbuilder`, `reprepro` (or `aptly`), `qemu-system-x86`, `ovmf`.

Pascal constraints (Sept 2026): CUDA 13 dropped Pascal. Driver 570+ required, **580 branch is the
last for Pascal** → the distro pins it on Pascal machines. No prebuilt Pascal llama.cpp for Linux,
so we build it: CUDA 12 toolkit with sm_61 plus modern archs, and a Vulkan build as fallback. Pin a
tested llama.cpp release in our repo. DDR3 (~20 GB/s) makes CPU-offloaded MoE models slow on
prompt ingestion.

---

## 3. Model strategy

### Candidates (as of Sept 2026)

| Model | Type | Q4 size | Role |
|-------|------|---------|------|
| **Qwen3-14B** | Dense, standard attention, hybrid thinking | 8.4 GiB | **Incumbent — already running on the Mint box** (see below); the bar every candidate must beat |
| Qwen3.5-9B | Dense, hybrid Gated DeltaNet attention, vision, hybrid thinking | ~5.5 GB | Challenger for default (1080 Ti, 4070): less VRAM, more headroom for the desktop |
| Qwen3.5-4B | same family | ~2.5 GB | Fallback / CPU / 8 GB cards / live session |
| Qwen2.5-Coder-7B | Dense, standard attention | ~4.7 GB | **Control baseline**; safest LoRA path |
| Qwen3.6-35B-A3B | MoE, 3B active | ~20 GB | Experimental "deep think" profile via expert offload to RAM |

Notes: no coder-specific Qwen below 30B in the 3.5/3.6/3.8 generations; Qwen3.5 needs a llama.cpp
build that supports its architecture (pin one we've tested); hybrid attention needs much less KV
cache at long context; Qwen3.5 on Pascal is unmeasured.
Trust our eval, not leaderboards. Verify each model's license before the distro downloads it by default.

### Baseline already on the Mint box (built 2026-08-23 with Codex, found 2026-09-24)

`~/Documents/Codex/2026-08-23/h/work/local-ai-testbed` on the Mint box:

- llama.cpp b10603 (`c060ca9`), built with Ubuntu's `nvidia-cuda-toolkit` **12.0** (no NVIDIA
  repo needed), GCC/G++ 12 as host compiler, `CMAKE_CUDA_ARCHITECTURES=61`, flash attention on.
- Official `Qwen/Qwen3-14B-GGUF` Q4_K_M, all layers on the GPU; `qwen14b.service` (systemd
  `--user`): `-c 16384 --cache-type-k/v q8_0 -np 1 -rea off`, localhost:8080 with an API key,
  `--sleep-idle-seconds 300`.
- Measured: ~25–29 tok/s generation, ~509 tok/s prompt (pp512); wake from idle to first token
  2.5 s. VRAM: 9.9 GiB peak at 4K context; **10.9 of 11.0 GiB used at 16K** incl. the desktop —
  only ~300 MB left for the desktop, Firefox, and the sidebar.
- **2026-09-25, that margin ran out in practice:** during the LibreOffice spike three extra 4K
  windows grew Xorg to 1.44 GB (it stayed there); the idle-unloaded model then failed every reload
  (`failed to allocate compute buffers`) and systemd restarted it 99 times. Recovered by Codex with the
  reversible `QWEN_CONTEXT_SIZE=8192` override: llama-server 9,138 MiB, Xorg 1,120 MiB, 485 MiB free.
  Design rules now in SPEC §4.2 (load-time budget, desktop reserve, step-down ladder, visible status).
- Also there: a GTK chat GUI with context compression (`gui/qwen_gui.py`) and an Aider workflow.

Carry into the product: the CUDA 12.0 + gcc-12 + sm_61 recipe (add `sm_75;86;89` for Turing–Ada,
and `GGML_NATIVE=OFF` + runtime-selected CPU variants for a distributable build — this build is
`GGML_NATIVE=ON`), q8_0 KV cache, idle unload. The VRAM margin at 16K is the main open question
the bakeoff must answer for the 14B vs. the 9B.

### Guide model track (D23–D25)

Two tracks in the bakeoff: the **guide** (small, ships on the ISO, 6 GB floor) and the **big**
model (optional download, 8 GB+). Guide track, in order:

1. **Guide eval first** (~100 tasks, in each v1 language where it applies): Windows → Linux
   transition questions, computer lessons for a beginner, LibreOffice toolkit tasks (reuse the 30
   from the LibreOffice spike), simple system help with read-only tools, and off-topic requests it
   must decline politely (history, civics, maths lessons…).
   **Written 2026-09-25:** `training/eval/guide/` — 75 tasks / 150 items (15 tasks in all six
   languages), mechanical scoring against Mint's own localized names; reference Qwen3-14B 86 %
   (Japanese 67 %). See its README.
2. **Candidates** (Apache-2.0): Qwen3.5-2B and -4B, Gemma 4 E2B and E4B, Granite 4.2 3B; Qwen2.5-1.5B
   as the old baseline. Measured under a **6 GB budget** (enforced in software: total VRAM incl. the
   §4.2 reserve), on the CPU (live-USB case), and on the Vulkan build (AMD path).
3. **Transition knowledge base** (retrieval, shipped on the ISO) — the facts come from here, not
   from the weights.
4. **Fine-tune the winner** (LoRA on the RTX 4070; data drafted with the big model, reviewed), then
   quantize, re-run the eval, and ship. **Cycle 0 (2026-09-25):** Gemma 4 E2B and Qwen3.5-4B both go
   through the fine-tune; plan, phases and the model card in `training/guide/`. Vulkan/AMD is a
   community beta (no AMD hardware here). Replaces "M8 — LoRA later" for the guide.
5. **Voice** (later milestone): whisper.cpp + Kokoro/Piper on the CPU, wake word, AT-SPI control.

### Optimization backlog (D33)

Found while watching the Mint box; each to be measured before it's adopted (and the same knobs feed
the product's llama-server supervisor, SPEC §10.3):

| Idea | Why | Where | Status |
|---|---|---|---|
| Pin compute threads, one per physical core (`--cpu-mask` + `--cpu-strict`, batch too) | the scheduler put two of four workers on core 0 (hottest core) while core 3 idled | `bench/run.py --pin`, teacher, product supervisor | implemented as an option; A/B pending |
| `--poll 0` when layers run on the GPU | main thread busy-waited at 98 % of a core | `bench/run.py --poll`, teacher | option; A/B pending |
| Parallel slots + parallel workers | GPU 36–41 % busy with one request at a time | `generate.py --workers`, teacher `--parallel 2`, evals | implemented; A/B pending |
| Partial CPU offload vs. desktop reserve | 4 CPU layers keep 1.9 GB free but slow every token | teacher; product step-down ladder (SPEC §4.2) | measure cost per offloaded layer |

### Bakeoff matrix (M0)

Run on the 1080 Ti; repeat on the 4070.

| Candidate | Quants | Contexts |
|-----------|--------|----------|
| Qwen3-14B (incumbent) | Q4_K_M | 8K, 16K |
| Qwen3.5-9B | Q4_K_M, Q5_K_M, Q6_K | 8K, 16K, 32K |
| Qwen3.5-4B | Q8_0 | 16K |
| Qwen2.5-Coder-7B | Q5_K_M | 8K, 16K |
| Qwen3.6-35B-A3B (RAM offload) | Q4_K_M | 8K |

Measure: prompt and generation tok/s, peak VRAM and RAM, **free VRAM left for the desktop (SPEC §4.2
reserve: ≥ 1.5 GB at 4K) with a realistic desktop open (browser, office documents, terminals)**, time-to-first-token on a 4K-token build
log, valid JSON tool-call rate over 50 attempts, score on ~20 Linux diagnosis tasks (seed of the
SPEC §14.1 suite). Output: `bench-results/` (git-ignored) plus `docs/benchmarks.md`, which drives the
profiles in first-boot setup.

---

## 4. Milestones

Each milestone has an exit test. Nothing moves forward on a red exit test.

### M0 — Spikes (throwaway code in `spikes/`)

| Spike | Question | Exit |
|-------|----------|------|
| **Terminal emulation** | Can pyte give us clean terminal text in Python? | **Done — GO** (see spikes.md). Now reused inside the relay. |
| **ISO remaster** | Can we script Mint 22.3 ISO → our ISO with one extra package from our own signed apt repo? | ISO boots in a Hyper-V VM (UEFI) and QEMU (BIOS), installs, and the package upgrades from our repo after install. |
| **Terminal relay** | Relay + OSC 133 hooks in Mint's default terminal: latency, throughput, correctness; compare with a VTE patch. | vim/htop/less/ssh/tmux/`sudo -i` behave identically; per-command output captured; send-to-prompt works; echo-off capture suppressed; keystroke latency not noticeable. |
| **Desktop surface** | Cinnamon applet + docked GTK sidebar + global hotkey talking to a stub daemon over session D-Bus. | Sidebar docks with struts, survives workspace/monitor changes; hotkey opens it focused; applet reflects daemon state. |
| **Firefox** | Signed WebExtension (sidebar + context menu) + native messaging host + policy install. | Fresh profile gets the extension automatically; a selection reaches the stub daemon; oversize input is truncated with notice. |
| **Streaming** | `llama-server` tokens (our CUDA 12 build, on the 1080 Ti) into the sidebar while the desktop and terminals are busy. | No visible stutter in terminals or the desktop during generation. |
| **Sandbox** | bwrap profile per D1. | `sudo`, `pkexec`, `su`, D-Bus `systemctl`, writing `/dev/sda`, opening `/dev/ttyUSB0`, reaching the daemon socket — all fail. |
| **Admin mechanism** | D-Bus-activated root service + polkit action on Mint. | Cinnamon auth dialog appears per request; no cached auth; denial is clean. |
| **LibreOffice** | Python-UNO extension ↔ daemon over D-Bus; toolkit per SPEC §7.7. | Installs with `unopkg --shared` (user-level for the spike, removed after); one read + one edit tool each for Writer, Calc, Impress; preview → Apply → a single Ctrl+Z undoes it; Qwen picks the right tool with valid arguments in ≥ 90 % of 30 scripted requests. |
| **Model bakeoff** | §3 above. | `docs/benchmarks.md` written. |

Exit: go/no-go per spike in `docs/spikes.md`. Done (2026-09-24/25): terminal emulation, ISO remaster,
terminal relay, desktop surface, streaming, sandbox, admin, LibreOffice, Firefox. Remaining: model
bakeoff (both tracks, incl. the guide model). Spikes on the Mint
box follow D21 and are cleaned up when M0 closes.

### M1 — Distro skeleton

- Signed apt repository (key generated and stored offline; CI signs with a subkey).
- `cinminai-archive-keyring`, `cinminai-branding`, `cinminai-desktop` (meta) packages.
- `distro/build-iso.sh` from the spike, made reproducible from pinned inputs.
- CI: build packages + ISO, QEMU boot test (BIOS + UEFI), publish.
- Rebranding: os-release, artwork, plymouth, installer slideshow, welcome screen.

Exit: a branded ISO installs in a VM and receives an update from our repository through Mint's Update Manager.

### M2 — Assistant core on the desktop

- `cinminai-daemon`: session D-Bus API, `InferenceBackend` + `LlamaCppBackend`, conversation, session state, supervisor/OOM ladder.
- `cinminai-llama`: pinned llama.cpp build (CUDA 12 / Vulkan / CPU backends) and its service.
- `cinminai-sidebar` (chat, streaming, status header), `cinminai-applet`, hotkey.
- First-run notice (SPEC §5.6).

Exit: in an installed VM (CPU profile) and on the Mint box (GPU), the assistant opens from applet and
hotkey and streams answers; killing the daemon doesn't affect the desktop and it restarts cleanly.

### M3 — Terminal integration + sandboxed execution

- `cinminai-shell`: relay, bash/zsh hooks, awareness indicator and toggles, echo-off rule, redaction.
- Terminal context provider + compiler/log extractor (SPEC §11.4).
- Command cards: Copy, To terminal, Run in sandbox, Explain.
- `cinminai-sandbox` + `ActionManager` (`SANDBOXED` lane), results fed back to the model, visible action states.
- Structured JSON tools (SPEC §10.5); other context providers (files, git, man, system, journal).
- Start the eval harness here.

Exit: the assistant diagnoses a seeded build failure from the user's real terminal and verifies the fix in the sandbox.

### M4 — Action boundary

- `USER_APPROVED` lane and approval dialogs; destructive-operation dialog.
- `cinminai-admin` mechanism + polkit policy; audit log; `ADMIN: LOCKED` indicator.
- `tests/security/` covering SPEC §16.1 against the real sandbox and mechanism.

Exit: all security tests green on the Mint box and in the VM.

### M5 — First-boot setup + hardware

- `cinminai-setup`: hardware detection, driver recommendation and install via the admin lane,
  Pascal 580 pin, model download, benchmark + fallback ladder, config file.
- Hardware providers: USB, PCI, serial, from sysfs + `usb.ids` / `pci.ids`; udev-driven cache.
- MCU flash/erase actions in the `USER_APPROVED` lane.
- Update window (SPEC §3.7.1): apt through the admin mechanism with `APT::Status-Fd`, signature and
  hash results surfaced per step, Timeshift snapshot first, offline-mode connect/disconnect,
  reminders; the §5.7 sound set and visual states (shared with the sidebar and approval cards).

Exit: fresh install onto the test SSD in the Mint box (D21) ends with a working GPU profile chosen by measurement; a fresh VM ends with a working CPU profile; an update in offline mode connects, shows every check passing, and disconnects; a tampered package (test repo) stops the update with the warning shown and heard.

### M6 — Firefox, LibreOffice + web

- `cinminai-firefox`: signed extension, sidebar, context menu, native messaging host, policy.
- `cinminai-libreoffice`: shared extension, full SPEC §7.7 toolkit, preview/Apply cards in the
  sidebar, undo contexts, headless document generation in the sandbox.
- `SearchProvider` (DuckDuckGo, then SearXNG), page fetch, LOCAL/WEB indicator, open sources in Firefox.

Exit: a selection in Firefox lands in the terminal-attached conversation; `/web` works and fails
gracefully offline; in a fresh install, a Calc range can be asked about and an approved edit is
undone with one Ctrl+Z.

### M7 — Deeper fork → v0.1

- Stage 2 forks as needed: Cinnamon (first-class sidebar), `mintwelcome` (setup page), installer
  (AI pages, notice), anything the M2–M6 work showed the extension points can't do.
- Automation that detects new Mint versions of forked packages and rebases.
- Real-hardware install test on the Pascal machine.

Exit: SPEC §18 acceptance criteria all pass → **v0.1**.

### M8 — Eval, then LoRA

- ≥100-problem hidden eval suite with automated scoring (SPEC §14.1); stock baseline per hardware profile.
- Decide LoRA base (D8); confirm training and llama.cpp `--lora` support for that architecture.
- Dataset targeted at measured failures; train off-box; A/B via `LlamaCppBackend`.

### M9 — User-built software (after v0.1)

The vision's next step (SPEC §1): people describe a small program, the assistant builds it, and the
OS runs it safely.
- Build and run in the sandbox (D1); a "keep this" step turns it into a user package with a name,
  icon, and menu entry, updatable and removable like any program.
- Anything it needs outside the sandbox (files, network, devices, admin) is declared and approved
  by the person, per app, and visible afterwards.
- Share and review: an app can be exported with its source so others (and the community) can read
  it before running it.

Exit: a non-programmer builds, keeps, updates, and removes a small app (e.g. a household budget
tracker) without a terminal, and every permission it has was granted on screen.

### M10 — IDEs and cloud backends (after v0.1, D35)

- IDE integration (the assistant in the editor people code in; which IDEs first is open).
- Provider backends behind the same interface as `LlamaCppBackend`: OAuth sign-in (browser or device
  flow) where offered, API key otherwise, stored with libsecret; per-provider connect/disconnect.
- CLOUD indicator state; what's sent is shown on request, like "what has this computer sent?" (§12.4).
- The guide and offline mode are unaffected: cloud never becomes a requirement.

Exit: from a fresh install, connect one cloud provider with one sign-in, use it in an IDE, see the
CLOUD indicator, disconnect, and confirm the local model takes over with nothing left in config files.

---

## 5. Risks

| Risk | Mitigation |
|------|------------|
| Forked Mint packages fall behind upstream | Fork as little as possible; patch series in `forks/`; automated upstream watch; Stage 1 works without forks |
| Remastering breaks on a new Mint ISO | Pinned inputs; CI boot tests; Stage 3 is the fallback |
| Desktop takes the model's VRAM (4K, many windows; seen 2026-09-25) | SPEC §4.2: load-time budget, desktop reserve, step-down ladder instead of restart loops, "reduced" status; bakeoff measures 14B vs 9B with the reserve |
| Relay adds latency or breaks edge cases | M0 spike with explicit edge-case list; pass-through mode; per-terminal off switch; VTE patch as complement |
| Users see terminal capture as spyware | Visible per-terminal indicator, one-command off switch, echo-off rule, local-only storage, first-run notice (D19) |
| Firefox extension signing / policy changes | Unlisted AMO signing; keep the extension small; pin tested Firefox behaviour in ISO tests |
| Prompt injection from web pages or terminal output | Untrusted content is data only; lanes and approvals are enforced outside the model |
| Small model misusing tools | Constrained JSON, few tools, eval-driven prompt tuning |
| Pascal dropped by inference backends or drivers | We build llama.cpp ourselves (CUDA 12 toolkit keeps sm_61); pin the 580 driver branch; Vulkan fallback |
| Qwen3.5 slow on Pascal | Bakeoff includes Qwen2.5-Coder-7B as a standard-attention fallback |
| LoRA tooling immature for hybrid architecture | D8 |
| Sandbox gaps (D-Bus, `/dev`, setuid, user namespaces) | Security tests against the real profile |
| Trademark / licensing | Rebrand (D17); review Mint, Ubuntu, Mozilla, and model licenses before public release |
| Scope creep (FPGA/MCU modes, LSP, own terminal) | Held to after v0.1 (SPEC §17) |

---

## 6. Open questions

- **Base series:** stay on Mint 22.x (Ubuntu 24.04, supported to 2029) for v0.1, or wait for Mint 23
  (Ubuntu 26.04)? Current plan: 22.x, rebase later.
- **Apt repository hosting:** GitHub Pages / releases, a VPS, or object storage. Needed by M1.
- ~~Default terminal~~: keep Mint's default (VTE patch dropped after the M0 relay spike).
- ~~Live-session assistant~~: decided — D23 + D27 (guide runs in the live session, reduced; install recommended).
- **License** for our own code (GPL-compatible, since we patch GPL packages). Decide before M1.
- **Offline updates (D28):** security updates for a computer that never goes online — an update
  bundle on a USB stick made on another computer? Or accept "go online for 10 minutes a month"?
- **Raspberry Pi 5 / ARM (idea, 2026-09-25):** Ian has a Pi 5 16 GB with an NVMe HAT. First a
  measurement spike when a second NVMe is available: llama.cpp CPU build on ARM, guide candidates
  through `bench/run.py --pin` + the guide eval, an ARM column in `docs/benchmarks.md`. A port is
  decided after M1: Cinnamon on Debian arm64 (keeps our desktop code) vs. a native Raspberry Pi OS
  (Wayland/labwc) panel plugin + sidebar; either way the guide needs a Pi knowledge-base/labels
  variant (Mint's tools don't exist there — `extract_labels.py` re-run on the Pi).
  **Leaning (2026-09-25): native Pi OS**, not a Cinnamon swap — keep the Pi's own ecosystem
  (firmware, configuration tools, camera, GPIO support). Our core (daemon, guide, tools, sandbox,
  admin, LibreOffice/Firefox) is desktop-independent; only the surface (panel applet, docked sidebar,
  hotkey) is Cinnamon-specific, so the Pi needs a **second surface** (Pi OS panel plugin + a Wayland
  sidebar via layer-shell) — work that also prepares Mint for a future Cinnamon Wayland session.
  **Different audience:** people getting into AI who already know PCs (maybe cloud AI), not Windows
  migrants. The pitch changes from "use your computer" to **"talk to any piece of hardware"**: with
  SPI/I2C/UART/GPIO on the board, a local model helps read a datasheet, wire a sensor, and get the
  first bytes over the bus (SPEC §13), with hardware writes still behind the human's button (§8.5).
  Needs its own knowledge base and corpus variant ("new to Linux and electronics").
  **Persona — the tinkerer** (from Ian's hardware-modding background): not much money, loves to dig
  in, happy to break a few eggs. Design consequence: **low friction on software, firm guardrails on
  physics** — terminal first-class, free sandboxed experiments, one-click snapshots so software
  mistakes cost nothing; before anything touches pins or buses, checks for what destroys hardware
  (voltage levels, pin conflicts, current limits: "that module is 5 V, use a level shifter"), with
  writes still behind the approval button (§8.5); knowledge of cheap sensor modules and clone boards.
  **Tinkerer version, as Ian sees it** (mechanic by trade): a streamlined, compact image with IDEs
  and a **hardware- and language-specific focus**, organised as **domain packs**. **First pack:
  board-level module repair** — diagnosing failed PCBs such as PCMs and TCMs, where the user finds the
  value: photo of the board → the (vision-capable) guide reads chip markings and finds datasheets →
  known failure points for the module family → guided measurements at test points → **back up the
  EEPROM/serial flash over the Pi's SPI/I2C** (`flashrom` linux_spi, `i2c-tools`) with the console-modding
  scene's NAND discipline (JRunner and friends): **read at least twice, dumps must match bit for bit,
  keep the verified original, then write, then read back and compare again** —
  before any rework → repair → verify against the backup. Instruments: USB logic analyzer (sigrok /
  PulseView), Pi camera or USB microscope. Guardrails: in-circuit reads can back-power the board;
  3.3 V vs 5 V logic; bench supply with a current limit; chip writes only after a verified backup and
  the human's button (§8.5); immobilizer data moved between the owner's own modules is repair work,
  defeating anti-theft on someone else's vehicle is not. **Later pack: a scanner** (SocketCAN, CAN
  HAT or USB adapter, ISO-TP/UDS/OBD-II; DTCs and live data free, clearing/relearn/flashing behind a
  checklist — stable battery voltage, backup, correct module; no emissions-defeat work).
  **Division of labour (Ian's compromise):** the **local model does the hands-on, checkable work** —
  connect, run the tools (flashrom, sigrok, can-utils), read-twice-and-compare dumps, collect
  measurements, package a diagnostic bundle. **Diagnosis and analysis are the human's, or a cloud
  model's if the user connects one (D35)**. Rule: *don't rely on it unless you know you can rely on
  it* — analysis is labelled as advice with its basis shown; hardware writes never follow from
  analysis alone (backup + checklist + human button, §8.5); works offline (collect now, analyse
  later); a bundle sent to the cloud shows its contents, redacts identifiers (VIN, immobilizer data)
  by default, and asks first; trust is measured on a set of known-fault boards per module family.
  Language/tool core for a first release: C, Python, Bash, reading ARM + one ECU assembly family,
  the bus protocols, S19/HEX/BIN, flashrom/sigrok/OpenOCD; further languages come as packs
  (FPGA: Verilog/VHDL + Yosys/nextpnr; retro/learning: BASIC/MMBasic, Forth; …).
- **Going public (D26):** when to open the repository and invite review — at M1 with the licence
  decision, or with the first installable alpha. Needs the licence, a contribution guide, and a
  place for discussion; secrets (AMO key, signing keys) stay out of the repo either way.

---

> The assistant may recommend the dangerous action.
> The assistant may explain the dangerous action.
> The assistant may prepare the dangerous action.
> The assistant does not get to approve the dangerous action.
>
> The user owns the computer. The user owns the button. (SPEC §19)
