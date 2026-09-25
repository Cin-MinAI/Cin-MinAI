# M0 Spike Results

Go/no-go record for each M0 spike in [PLAN.md](PLAN.md#m0--spikes-1-week-throwaway-code-in-spikes).

| Spike | Status | Verdict |
|-------|--------|---------|
| Terminal emulation (pyte) | Done 2026-09-24 | **GO** — pyte reused inside the terminal relay |
| ISO remaster | Done 2026-09-24 | **GO** — remaster + own signed repo works (UEFI + BIOS) |
| Terminal relay (vs. VTE patch) | Done 2026-09-24 | **GO** — relay is the baseline; VTE patch not needed for M1 |
| Desktop surface (applet, sidebar, hotkey) | Done 2026-09-24 | **GO** — dock + struts + Cinnamon keybinding + CJS applet over session D-Bus |
| Firefox (extension + native messaging) | Done 2026-09-25 | **GO** — AMO-signed extension, force-installed by policy from our repo, native host → daemon; upgrades on restart |
| Streaming (llama-server → sidebar) | Done 2026-09-24 | **GO** — no desktop or terminal impact while the 1080 Ti generates |
| Sandbox (bwrap) | Done 2026-09-24 | **GO** — bwrap + pasta private network; host network namespace rejected (X server reachable) |
| Admin mechanism (D-Bus + polkit) | Done 2026-09-24 | **GO** — D-Bus-activated root mechanism, per-request auth_admin, verified with the real Cinnamon dialog |
| LibreOffice (extension + toolkit) | Done 2026-09-25 | **GO** — extension + D-Bus toolkit, one-step undo in all 3 apps, Qwen3-14B 93 % on 30 requests |
| Model bakeoff | Guide track done 2026-09-25; big track + RTX 4070 to run | Guide: **Gemma 4 E2B** and **Qwen3.5-4B** go to fine-tuning (docs/benchmarks.md, cycle 0) |

> 2026-09-24: the project scope changed from a standalone terminal app to a Mint-derived distro
> (PLAN D10). The terminal spike below was run for the old app design. Its findings still apply
> to the emulation layer of the terminal relay (PLAN D13); its "Decision" section is superseded.

---

## Terminal widget

**Code:** `spikes/terminal/` — `pty_session.py` (PTY + child), `terminal_view.py` (Textual
widget over pyte), `app.py` (split app with fake 40 tok/s assistant stream), `check.py`
(headless acceptance harness).

**Environment:** Mint box — Linux Mint 22.3, kernel 7.0, i7-4790K, Python 3.12.3,
Textual 8.2.8, pyte 0.8.2. Run with `python check.py` from a venv (`uv venv`).

### Result: 17/17 checks pass

| Check (old spec §51; now SPEC §16.2) | Result |
|------------------|--------|
| `cd` + `export` persist across commands | PASS |
| Printable keys via real Textual key events | PASS |
| Ctrl-C interrupts foreground job | PASS |
| Ctrl-Z suspends job (`jobs` shows Stopped) | PASS |
| SGR colors / bold rendered | PASS |
| vi: open, insert, `:wq`, file written | PASS |
| Alternate screen restored after editor exits | PASS |
| less: page + quit | PASS |
| top: render + quit | PASS |
| python3 REPL: eval + Ctrl-D | PASS |
| Resize propagates to PTY (`stty size` matches widget) | PASS |
| Assistant stream smooth while idle (max gap 36 ms @ 40 Hz) | PASS |
| Throughput: 100k short lines | 1.1 s, max UI stall 83 ms |
| Throughput: 200k `seq` lines (1.5 MB) | 3.6 s, max UI stall 62 ms |
| Throughput: colored `ls -R` 20k lines (0.5 MB) | 2.3 s, max UI stall 53 ms |
| Shell `exit` leaves app running | PASS |

### Findings

1. **pyte throughput is the limit: ~0.3–0.7 MB/s on the 4790K.** Profiling shows pyte's
   `draw`/`index` and namedtuple `_replace` dominate; Textual rendering is secondary. The UI
   stays responsive (stalls ≤ ~110 ms) because the PTY applies backpressure — the producer
   blocks rather than us buffering. Interactive work, builds, and editors are fine. Dumping
   10+ MB (`journalctl -b --no-pager`, `cat` of a large log) will take tens of seconds to
   catch up. Ctrl-C still works during floods.
2. **pyte bug: private-marker CSI kills the parser.** Sequences like `ESC[>4;1m` (xterm
   modifyOtherKeys, emitted by bash/readline) reach handlers that don't accept `private=`;
   the `TypeError` permanently kills pyte's parser generator. Fixed in `AltScreen` by
   wrapping all non-private-aware CSI handlers to ignore private variants, plus a feed-level
   guard that rebuilds the stream on any exception.
3. **pyte has no alternate screen buffer.** Implemented modes 47/1047/1049 in `AltScreen`
   (~25 lines). Verified with vi.
4. **Textual `Resize.size` includes the border.** Must size the PTY from the widget's content
   size, otherwise lines wrap 2 columns too wide.
5. **Test harness: `Pilot.press` is ~0.9 s per key** because the 30 fps render timer keeps the
   app from going idle. Harness writes text straight to the PTY and uses Pilot only for
   special keys. Not a runtime issue.
6. **Ctrl-Q is taken by the app (quit).** Terminal loses XON; acceptable. Everything else,
   including Tab and Ctrl-C, reaches the shell.

### Not covered by this spike (carry into M1)

- Scrollback (pyte `HistoryScreen`) and mouse reporting.
- Selection / copy of terminal text (needed for "send output to assistant").
- Real interactive feel — keystroke latency by hand on the Mint desktop.
- `textual-terminal` comparison: skipped. Our widget passed everything; the spec's advice to
  keep terminal integration behind our own interface covers future swaps.

### Decision

*(Superseded by PLAN D12/D13 — there is no standalone terminal widget any more. What carries
over: pyte with the `AltScreen` fixes as the relay's emulator, and the throughput plan below.)*

Original decision: **GO: build M1 on our own pyte-based widget** behind the `TerminalSession` / emulator
interfaces. Throughput work in M1, in order of cost:

1. Plain-text fast path — for chunks with no ESC bytes while on the primary screen, only the
   last `rows` lines affect the display; feed just those (the full raw stream still goes to
   the log used for compiler-context extraction, SPEC §11.4).
2. If still too slow: spike **libvterm** (C, used by Neovim; `libvterm0` is in the Ubuntu
   repos) via ctypes as a drop-in emulator.

---

## ISO remaster

Scripts: `spikes/iso-remaster/`: `make-repo.sh VERSION` (signed reprepro repo, spike key),
`build-iso.sh` (Mint 22.3 ISO → our ISO with `cinminai-desktop` baked in), `vm.sh` (QEMU/KVM in WSL).
Built in WSL Ubuntu 24.04. Output `cinminai-spike-22.3-amd64.iso`, sha256 `a4093dc5…6c59`.
Manifest diff vs. upstream: exactly our three packages added.

### Result (2026-09-24): all checks pass

| Check | UEFI (Hyper-V Gen2, Secure Boot, MS UEFI CA template) | BIOS (Hyper-V Gen1) |
|-------|------|------|
| ISO boots to live desktop | pass (upstream signed shim/GRUB unchanged) | pass, with "compatibility mode" (see finding 4) |
| Packages present in live session | pass | pass |
| Installs (ubiquity, erase disk) | pass | pass |
| Installed system has packages + repo source + key | pass (`cinminai-hello 0.1`) | pass |
| Upgrade 0.1 → 0.2 from our repo via `apt upgrade` | pass (signature verified, all 3 upgraded) | pass |

### Findings

1. **Test repo hosting.** A VM on Hyper-V "Default Switch" can't reach WSL; the repo was copied to
   Windows and served on the Default Switch host address (172.20.208.1:80), with
   `cinminai-repo.invalid` mapped in the guest's `/etc/hosts`. Needed an inbound firewall allow
   rule, and disabling stale Public-profile *Block* rules for `powershell.exe` (Block beats Allow).
2. **Hyper-V `Msvm_Keyboard.TypeText` garbles text on Linux guests**, so no scripted guest input
   that way. Screenshots via `GetVirtualSystemThumbnailImage` work (RGB565, 4 trailing bytes).
   Automated boot tests later: serial console / automated install, not keystrokes.
3. **apt i386 notice:** the repo line lacked `arch=amd64`; fixed in `make-repo.sh` (takes effect
   from the next package version).
4. **Hyper-V Gen1 needs `nomodeset`.** Normal boot ends in failed `gpu-manager` + `lightdm`;
   the unmodified upstream Mint 22.3 ISO fails identically, so it's Mint vs. Gen1 video, not the
   remaster. "Compatibility mode" boots; the installed system needs `nomodeset` in
   `GRUB_CMDLINE_LINUX_DEFAULT`. Not a concern for real hardware; revisit only if we ship VM images.
5. **No KVM in WSL2 on this PC** (Windows 10 + AMD: no nested virtualization for WSL), so
   `vm.sh` can't run here; BIOS was tested with a Hyper-V Gen1 VM instead of QEMU. `vm.sh` stays
   for Linux build hosts / CI.

### Decision

**GO on Stage 1 (PLAN D11).** Scripted remaster of the pinned Mint ISO plus our signed apt repo
gives a bootable (UEFI Secure Boot and BIOS), installable, updateable system. Carry into M1:
real repo hosting + key management, `arch=amd64` in the source line, and an automated boot/install
test (Hyper-V can't script guest input — use an automated install and serial log instead).

---

## Terminal relay

Code: `spikes/relay/`: `relay.py` (pty relay), `analyzer.py` (child process: markers, pyte,
segmentation, control socket), `emulator.py` (terminal-spike `AltScreen` + scrollback capture),
`hooks.bash` (OSC 133 A/B/C/D, OSC 7, private OSC 7717 for command text and `ai on|off`),
`relayctl.py` (stand-in for the daemon: `status`, `history`, `screen`, `send`), `check.py`.

Design: the relay loop only copies bytes and never waits on analysis. A copy of the output goes
to the analyzer over a non-blocking pipe (framed). If the analyzer falls behind, the relay drops
data and records a gap, but still forwards the OSC markers so command boundaries survive; if a
single read is large, the analyzer scans it for markers and emulates only the last 64 KB.
If the analyzer dies, the relay keeps passing bytes through. Send-to-prompt writes a bracketed
paste into the pty (readline inserts it, never runs it); refused unless the shell is in the
foreground at its prompt and sharing is on and no password prompt is up.

### Result: 36/36 automated checks (WSL Ubuntu 24.04, pyte 0.8.0); 21/22 on the Mint box (pyte 0.8.2, the miss is the vim check — vim isn't installed there)

| Area | Checks |
|------|--------|
| Identity (same keys → same screen, plain vs. relay) | basic/colours, vim, less, htop, tmux, python REPL, Ctrl-C, Ctrl-Z/jobs/kill, resize (`tput` sees 120×40) |
| Segmentation | command text + output + exit code, stderr, repeated command (ignoredups) from screen, space-prefixed command stays private, cwd (OSC 7), 3000-line output kept past the screen, multi-line command, full-screen program flagged with no redraw noise |
| Privacy | password prompt detected (`read -s`, Mint-style sudo pwfeedback), send refused there, typed secret never captured, `ai off` records nothing and drops the ◆ indicator |
| Control | send puts text at the prompt without running it; refused while a program runs; nested relay execs the shell instead; relay survives the analyzer dying; exit status passed through |
| Latency (keystroke echo, first byte) | WSL/3900X: +0.16 ms median (0.15 → 0.31), p99 0.53 ms. Mint/4790K: +0.44 ms median (0.31 → 0.75), p99 0.83 ms |
| Throughput (`cat` 97 MB) | WSL: 10 → 7 MB/s; Mint: 24 → 24 MB/s (harness-bound). Byte-exact; gaps recorded; segmentation recovers after the flood |

Manual on the Mint desktop (gnome-terminal 3.52 / VTE 0.76): normal use, `less`, editors,
resize, Ctrl-C — no difference noticed. `sudo -i`, `ssh localhost`, `ai off`, send-to-prompt
checked via relayctl over SSH.

### Findings

1. **Mint's sudo defeats the simple echo-off rule.** Mint ships `/etc/sudoers.d/0pwfeedback`:
   sudo reads the password in character mode to print `*`, so "echo off + canonical" missed it.
   Ubuntu's `use_pty` also puts the terminal in full raw mode while sudo relays a command.
   Rule now: echo off + canonical, **or** echo off + character mode + ISIG on + a password program
   (`sudo`, `su`, `ssh`, `passwd`, `pkexec`, `gpg`, …) in the foreground. Verified on real sudo.
2. **Nested sessions are opaque.** `sudo -i` and `ssh` show up as one long command (the whole
   root/remote session is captured as its output); our hooks don't run there. Remote password
   prompts inside ssh can't be detected locally (the remote tty's echo state isn't visible).
   M1: ship the hooks system-wide (`/etc/bash.bashrc`) so root shells emit markers; decide
   whether ssh/root sessions are captured at all by default (leaning: not, with an opt-in).
3. **Nesting guard by env var is not enough for the distro.** `sudo -i` strips
   `CINMINAI_RELAY`, and Ubuntu's sudo already gives the root shell its own pty. With system-wide
   startup the root shell would start a second relay. M1: start the relay only when the shell's
   parent is a terminal emulator (not sudo/su/sshd/tmux/another relay).
4. **Command text:** `history 1` from PS0 is exact but can't tell ignoredups repeats from
   hidden (ignorespace) commands; the screen line between OSC 133 B and C settles it (leading
   space → hidden). Both sources are kept per command (`cmd`, `screen_cmd`).
5. **Analyzer failure is silent.** Started with a Python lacking pyte, the analyzer died and the
   terminal kept working with nothing recorded — correct behaviour, but the user can't tell.
   M1: the ◆ indicator should reflect whether anything is actually listening.
6. **Throughput:** the Python relay loop costs ~30% on a pure flood on the 3900X; not noticeable
   on the Mint box. If it matters, the relay loop is ~150 lines and a C/Rust rewrite is cheap;
   the analyzer can stay Python.

### VTE patch (desk evaluation, not built)

A VTE patch would only cover VTE terminals (gnome-terminal, Mint's default), gives nothing in
other emulators, TTYs or ssh-launched shells, and means carrying a fork of a security-sensitive
library through every VTE update. The relay already delivers command segmentation, clean text,
cwd and send-to-prompt with no measurable feel difference. The one thing a patch adds is exact
per-cell knowledge of what the terminal drew (no second emulator); not worth the fork for M1.

### Decision

**GO: the relay is the terminal integration for M1** (PLAN D13), with findings 1–3 and 5 as M1
work items. The VTE patch is dropped from M1; revisit only if pyte's emulation proves wrong in
practice.

---

## Desktop surface

Code: `spikes/desktop/`: `daemon.py` (stub `org.cinminai.Assistant1`: State/Model/Awareness
properties, `Ask` streaming fake tokens as signals, D-Bus activated), `sidebar.py` (GTK 3 docked
sidebar, single-instance GApplication, `--toggle|--show|--hide`), `applet/cinminai@cinminai`
(CJS panel applet), `install.sh` / `uninstall.sh` (user-level, reversible), `check.py`.
Only what Mint ships: PyGObject/GTK 3, libX11/libXtst through ctypes, CJS.

### Result: 27/27 checks on the Mint box (Cinnamon 6.6.9, X11, 4K at 3× scaling) + hands-on use

Checks drive the real X server (XTest keys and mouse clicks, xprop/xwininfo, screenshots) and read
the applet's live icon/tooltip through Cinnamon's `org.Cinnamon.Eval`.

| Area | Checks |
|------|--------|
| Daemon | D-Bus activated on first call; the applet does *not* auto-start it |
| Sidebar docking | right edge, full height above the panel; work area shrinks by its width (3840 → 2700 px); maximized windows stop at it; on all workspaces; Escape / ✕ / hotkey hide it and give the space back |
| Resolution change | 4K@3× → 1920×1080@1× → back: re-docks with correct width, height and strut each time |
| Focus | opens focused (show / hotkey); a click back into the Ask field refocuses it; second prompt after that works |
| Hotkey | `Super+A` from another window opens it focused; typed text reaches the daemon; again hides it |
| Applet | icon + tooltip follow idle, thinking (while streaming), approval, error, off, and the daemon dying |

Hands-on (user): "clean in and out in every way I tried" — terminals, Firefox alongside, minimize,
attempts to break it.

### Findings

1. **Window type: DOCK, plus focus on click.** Muffin keeps normal windows out of all struts,
   including their own (the sidebar got pushed left of its own strip), and applies
   focus-stealing prevention to them. Dock windows are exempt from both, but Muffin doesn't focus
   a dock when clicked: typing then went to IBus's fallback pop-up and the toggle misjudged focus
   (user-reported). Fix: a capture-phase click gesture requests focus with the event time;
   hotkey/show use the X server time.
2. **Cinnamon custom keybindings** (`keybindings.js`) are read only when `custom-list` changes,
   and only entries whose name contains `custom` are cleaned up. Write the binding first, then
   list it as `custom-…`. The package will ship the default via a gsettings override/first-login
   script instead.
3. **Panels set to (intelli)hide reserve no space**, so the work area includes them and a
   full-height sidebar hides the panel for good. The sidebar reads `org.cinnamon panels-enabled/
   panels-height` and stops above/below them.
4. **Resolution changes arrive in a burst**, and Cinnamon changes the scale factor a moment after
   the mode. Re-dock on monitor geometry/workarea/scale-factor notifications, debounced (150 ms).
5. **Context for the hotkey:** the focused window's class/title is captured before the sidebar
   takes focus. Mapping a gnome-terminal *window* to its relay needs more (one
   `gnome-terminal-server` process owns every window): M1 idea — pick the relay with the most
   recent input, or have the hooks tag the terminal title.
6. **`org.Cinnamon.Eval`** makes applet state testable in CI-style checks; keep using it.
7. Not covered: multiple monitors (one available), Wayland (Mint 22 is X11 by default; Cinnamon's
   Wayland session is experimental — struts and XTest won't carry over), fullscreen video vs. a
   visible sidebar.

### Decision

**GO: Stage 1 (GTK dock + struts) is good enough for M1** (SPEC §5.1). The Cinnamon patch
(Stage 2) is only needed for multi-monitor polish or Wayland; revisit after M1.

---

## Streaming

Code: `spikes/desktop/daemon.py` (now with a real backend), `spikes/desktop/sidebar.py` (Stop
button, error display), `spikes/streaming/check.py`. Backend: the existing `qwen14b.service` on the
Mint box (llama.cpp b10603 CUDA, Qwen3-14B Q4_K_M, 16K ctx, q8_0 KV; see PLAN §3), untouched.

The daemon reads `[inference] url / api_key / model` from `~/.config/cinminai/config.toml`,
streams `/v1/chat/completions` (SSE) on a worker thread and hands each chunk to the GLib main loop
(`idle_add`) → one `Token` D-Bus signal per chunk. Multi-turn history; `Cancel` closes the HTTP
stream (llama-server stops generating); errors → `Error` signal + `error` state.

### Result: 12/12 checks on the Mint box

| Measure | Idle | While generating into the visible sidebar |
|---------|------|------------------------------------------|
| Compositor frames (animated window) | 59.8 fps, p99 16.7 ms, 0 hitches >50 ms | 59.6 fps, p99 16.8 ms, 0–1 hitches |
| Shell keystroke echo | p99 0.44 ms | p99 0.11 ms (CPU clocks up under load) |
| GPU | 1–4 % | 99 %, VRAM 10.8 GiB of 11 |

- Generation 28 tok/s, prompt 280–310 tok/s; first token 0.1 s warm, 2.2–2.5 s waking from idle
  unload; token gaps p50 36 ms, p99 37 ms, max 38 ms (smooth).
- Stop → idle in 23 ms; llama-server's `requests_processing` back to 0.
- Server unreachable → `error` state and "Connection refused" in the sidebar within a second.
- Follow-up question uses the previous turn.

### Findings

1. **The 1080 Ti drives the desktop and runs the model at 99 % without visible cost**: Pascal's
   compute preemption keeps compositing at 60 fps. The real constraint is VRAM (≈300 MB left at
   16K), not GPU time.
2. **A long model name widened the sidebar off-screen** (its header label didn't wrap and GTK
   grew the window past 380). Labels in the dock must wrap/ellipsize; now checked.
3. **`xrandr` resolution tests change the user's saved scale.** Cinnamon re-derives the scale when
   the mode returns and saves it (3× → 2× on the Mint box). Use `org.cinnamon.Muffin.DisplayConfig`
   for automated display tests; the `--xrandr` option now carries a warning.
4. Thread + `GLib.idle_add` is enough for streaming in the daemon; no async HTTP library needed.
5. Not covered: waking the model while the user is typing elsewhere (the 2.2 s wake is visible as
   "thinking"; a "loading model" state would be clearer), and several clients streaming at once.

### Decision

**GO.** llama-server (our CUDA build) → daemon → D-Bus → sidebar is the M1 streaming path.

---

## Sandbox

Code: `spikes/sandbox/sandbox.py` (runner: `sandbox.py --workspace DIR [--net pasta|none|host]
[--limits] [--timeout S] -- CMD`), `spikes/sandbox/check.py` (SPEC §16.1 + indirect paths +
function; `--stress` for limits). bubblewrap 0.9.0 on both machines; passt 2024-02-20.

Profile: `--new-session --die-with-parent --unshare-all --cap-drop ALL`, same uid/gid as the user,
`/usr` `/etc` `/var` `/sys` read-only, fresh `/tmp` `/var/tmp` `/run` `/home` `/root` `/mnt` …,
`--dev` minimal `/dev`, `--proc`, workspace bound read-write, `--clearenv` + PATH/HOME/USER/LANG/TERM,
own `resolv.conf`; network: `pasta --config-net -T none -U none --no-map-gw --dns-forward`.

### Result: 50/50 in WSL (with `--stress`), 50/50 on the Mint box (pasta unpacked user-level)

| SPEC §16.1 — the AI path cannot … | Result (host and pasta modes) |
|---|---|
| acquire sudo / su / pkexec | all fail; `setuid(0)` → EINVAL (root isn't mapped); NoNewPrivs 1, CapEff/CapBnd 0 |
| reach the system or session D-Bus | sockets absent (`/run` is fresh); `systemctl restart` / `busctl` / `gdbus` fail fast, no polkit prompt |
| talk to the daemon's approval API | `$XDG_RUNTIME_DIR` sockets absent |
| rewrite the admin mechanism or polkit policy | read-only / permission denied |
| write raw block devices | no block devices in `/dev` |
| open serial ports or debug probes | no ttyUSB/ACM/S, hidraw, `/dev/bus/usb`, gpiochip |
| flash firmware | efivars permission denied; no mtd, mem, port, nvram |
| write PCI configuration | permission denied (25 devices on the Mint box) |
| modify protected system files | read-only / permission denied |
| read $HOME outside the workspace | `$HOME` is an empty tmpfs; `.ssh`, `.config`, … invisible; `/mnt/c` (WSL) invisible |

| Indirect path | host netns | pasta | none |
|---|---|---|---|
| X server (abstract socket) | **ACCEPTED on the Mint box** (58 abstract sockets visible) | unreachable (0 visible) | unreachable |
| host 127.0.0.1 services | **reachable** | unreachable | unreachable |
| TIOCSTI into the launching terminal | blocked | blocked | — |
| host processes | invisible (pid ns) | invisible | — |
| leaked env (bus, DISPLAY, ssh-agent, daemon) | none | none | — |

Function: workspace read/write (files owned by the user on the host), https for builds (host and
pasta), network off in `none`, git, C build + run, `/proc` `/sys` dpkg, `lspci`, `lsusb` (via
sysfs), `lsblk`. Lifecycle: timeout kills the whole tree incl. background jobs; `$HOME` and system
dirs refused as workspaces. Limits (WSL `--stress`, systemd `--user` scope): fork bomb stopped by
`TasksMax=256`, 3 GiB allocation killed at `MemoryMax=2G`.

### Findings

1. **The host network namespace breaks the boundary.** Abstract unix sockets are per network
   namespace; with the host's, sandboxed code reached the X server, which on Mint accepts any
   process of the user (`xhost: SI:localuser:mint`) → keylogging, input injection, screenshots.
   Also every 127.0.0.1 service (llama-server, CUPS, …). Fix: pasta private namespace
   (`--no-map-gw`, no port forwards), verified on the Mint desktop.
2. **`/etc/resolv.conf` is a symlink into `/run`** (systemd-resolved) or `/mnt/wsl` — both hidden,
   so DNS broke. The sandbox gets its own copy; under pasta, `--dns-forward` to the host resolver.
3. **pasta's own user namespace makes the user uid 0** (capability-less) unless bwrap maps back
   with `--uid/--gid`; done.
4. **bwrap's minimal `/dev` is a writable tmpfs**: `open("/dev/sda", "w")` silently creates a plain
   file. Harmless (no mknod), but tests must open without O_CREAT.
5. **User namespaces:** Mint 22 ships `kernel.apparmor_restrict_unprivileged_userns=0`; stock
   Ubuntu 24.04 restricts them. Our distro inherits Mint's setting; watch it on rebases.
6. Not covered: seccomp filtering (the namespaces already block the paths above), GPU inside the
   sandbox (no `/dev/nvidia*`, deliberately), pasta throughput for large downloads.

### Decision

**GO: bwrap + pasta is the `SANDBOXED` lane** (PLAN D1 updated). `cinminai-sandbox` depends on
`bubblewrap` and `passt`; host networking is test-only.

---

## Admin mechanism

Code: `spikes/admin/`: `mechanism/cinminai-admin` (root, system bus `org.cinminai.Admin1`, D-Bus
activated through `cinminai-admin.service`, exits after 60 s idle), D-Bus policy, polkit policy
(`org.cinminai.admin.*`), `client/cinminai-admin-demo` (stands in for the daemon after in-sidebar
approval), `test/` (demo service; test-only polkit rule), `install.sh`/`uninstall.sh` (WSL),
`build-deb.sh` (→ `cinminai-admin-spike` in the spike repo), `check.py`.

Verbs in the spike: `RestartService`, `SetServiceEnabled`, `InstallPackage`, `RemovePackage`,
`WriteFile` (load/unload module and `run_argv` follow the same pattern). Per request:
validate → polkit `CheckAuthorization` (caller as subject, verb's own action, details naming the
target, interactive only if the caller allowed it) → fixed argv, no shell → append-only audit.

### Result: 20/20 automated checks in WSL + live test in the VM installed from our ISO

WSL (test polkit rule answers yes/no/nothing): policy is `auth_admin` for all 5 actions, never
`*_keep`; D-Bus activation starts it as root; authorized requests really run, denied ones leave the
system untouched; **3 requests → 3 polkit checks** (no caching); **23 unsafe requests rejected
before polkit** (shell injection, `../`, protected units — dbus, polkit, systemd-*, display
manager, itself — protected packages, writes outside `/etc` or into sudoers/shadow/passwd/polkit/
pam/systemd/apt/cron/profile, symlinked targets, setuid modes, >1 MiB); atomic write with backup;
enable/disable; real `apt-get install`/`remove` (package `hello`) and a clean error for a missing
package; concurrent requests; unreachable from the sandbox; audit log with caller uid/pid/exe,
decision and result, `chattr +a`; idle exit.

VM (`cinminai-uefi`, installed from our ISO; package installed with `apt` from our signed repo):
the real Cinnamon polkit dialog for each request — two restarts, two separate password prompts;
Cancel → `Dismissed`, service untouched; `dbus.service` → `Rejected` with no dialog; all four in
the audit log.

### Findings

1. **Backup names need sub-second uniqueness**: two writes in one second collided and the second,
   already approved, failed. Fixed (microseconds + random suffix). Rule: nothing that can fail
   after approval should depend on timing.
2. **polkit only offers `auth_admin` to active local sessions**: from a non-graphical session (WSL
   shell, SSH) every request is simply denied — correct for us, and why the dialog test needs the VM.
3. **Ubuntu runs `polkitd --no-debug`**, which drops `polkit.log()` from rules; test rules count
   through a file instead.
4. **The audit log fits Ubuntu's convention** (`root:adm 0640`, like `/var/log/syslog`) plus
   `chattr +a`; `logrotate` will need `copytruncate` off and a `chattr -a/+a` wrapper.
5. `apt` through the mechanism works non-interactively; the in-sidebar dialog should show apt's
   simulated plan (`apt-get -s`, which the daemon can run unprivileged) before asking — M4 work.
6. Not covered: wrong-password lockout behaviour, `run_argv` with the destructive dialog,
   load/unload module, several users on one machine.

### Decision

**GO: this is the `ADMIN` lane** (SPEC §8.4). M4 turns the spike into `cinminai-admin` with the
remaining verbs and the in-sidebar approval card.

---

## LibreOffice

Code: `spikes/libreoffice/`: `extension/` (Python-UNO `.oxt`: `cinminai_lo.py` = ProtocolHandler +
startup Job + D-Bus service `org.cinminai.LibreOffice1` on its own GLib thread; `pythonpath/
cinminai_tools.py` = the toolkit; `Addons.xcu` = the **Assistant** menu), `build_oxt.py`, `lo.py`
(headless LibreOffice with a throwaway profile + sample docs), `check_tools.py`, `check_ext.py`,
`assist.py` (schemas, prompt, constrained call), `eval.py`, `lo_assist.py` (hands-on stand-in for the
sidebar), `live.sh`. LibreOffice 24.2.7, `python3-uno`, on the Mint box; user profile never touched.

### Result

- **Toolkit 34/34** against real Writer/Calc/Impress: doc_info, outline, get_selection,
  get_paragraphs, read_range (sheet-qualified, case-insensitive), used_range, slide_text;
  replace_selection, write_range, set_formula, set_slide_text — each preview → apply → **one named
  undo step** ("Assistant: …") → redo; stale previews, wrong doc types, bad ranges, huge ranges,
  missing slides refused.
- **Extension 15/15**, driven over D-Bus: installs with `unopkg`; service runs inside LibreOffice
  (started by the `onFirstVisibleTask` Job in the GUI); unshared documents refused; sharing only from
  the menu (no D-Bus method), per document; "Explain formula" shares; forged snapshot refused; bad
  arguments → clean error, LibreOffice unharmed.
- **Model eval (Qwen3-14B Q4_K_M, JSON-schema constrained): 28/30 = 93 % first try** (target ≥ 90 %),
  median 1.2 s per request. First run was 24/30 (80 %); see findings 4–5 for what changed and why.
  Remaining misses are model limits: "make it shorter" only fixed spelling; a header + six formulas
  in one instruction wrote only the header.
- **Hands-on (user, Mint desktop, separate LibreOffice profile):** Writer spelling fix previewed,
  approved, undone with Ctrl+Z; Calc `=AVERAGE(B2:B7)` into B9 and "which month was warmest" →
  "June, 22.4 °C" (2.1 s); Impress bullet added. "Everything seems to work as planned."

### Findings

1. **LibreOffice's API undo is uneven.** Writer text edits are recorded; Calc `setFormulaArray()` is
   *not* (write cell by cell with `setFormula()`, which is); Impress/Draw API text changes are not
   recorded at all (register our own `XUndoAction`). All three now give one named, redoable step.
2. **Python extension layout:** `pythonpath/` must sit next to the component `.py` (not at the `.oxt`
   root) to be importable.
3. **Threads:** the D-Bus service runs on its own thread with its own `GLib.MainContext`
   (LibreOffice's GTK main loop is never used); UNO calls from that thread work.
4. **Tool design beats prompt tweaking.** The model copied the *read* shape (`"values": [[339.0]]`)
   into writes — numbers instead of formulas, repeated rows. Fixed by the tool surface, not the
   prompt: a dedicated `set_formula(cell, formula)`, `write_range` takes `cells` (strings), and small
   sheets (≤ 200 cells) go into the context whole. Example-heavy descriptions made it worse.
5. Scorer corrections (2 cases where the model's answer was right) and "read first if the data
   isn't in the context" were the other changes; a retry with the tool's error message is built in
   (the daemon will do the same) but was not needed in the final run.
6. **GPU memory (see SPEC §4.2):** extra 4K LibreOffice windows grew Xorg to 1.44–1.64 GB; the
   idle-unloaded model then crash-looped on reload (99 restarts; recovered at 8K by Codex), and with
   the model loaded, *other apps' windows rendered garbage*. Design rules added to SPEC §4.2.
7. `lo_assist.py` works on the most recently shared document; the product sidebar should show
   which document it sees and prefer the focused window (§5.3). Several shared documents at once is
   supported by the extension already.

### Decision

**GO** (PLAN D20). M6 builds the full SPEC §7.7 toolkit on this extension, with the preview/Apply
card in the sidebar instead of the terminal.

## Firefox

Code: `spikes/firefox/`: `extension/` (MV3 WebExtension `assistant@cinminai.org`: sidebar, context
menu "Ask Cin-MinAI about “…”" / "… about this page", page text capped at 12,000 chars in the
extension), `host/cinminai-firefox-host` (native messaging host: Firefox framing on stdio ↔
`AskAbout` on the daemon's session D-Bus, caps text again), `check_host.py`, `live.sh` (throwaway
profile on the Mint desktop), `amo_fetch.py`, `build-deb.sh` (package for test B). The spike daemon
(`spikes/desktop/daemon.py`) gained `AskAbout`: page text goes to the model as quoted, untrusted data
(SPEC §7.4). Firefox 156 on the Mint box.

### Result

- **Signing:** signed **unlisted** on AMO (self-distributed) as 0.1.0, then 0.1.1; release Firefox
  installs both with no warnings. Key only in WSL `~/.config/cinminai/amo.env` (mode 600).
- **Host checks 8/8** on the Mint box (Qwen3-14B via the daemon): status; selection + question →
  streamed answer; web text quoted as untrusted data; prompt injection in page text noted (info);
  oversize text capped with a note to the model; Stop ends the answer (< 2 s); garbage input → error,
  host keeps working; host exits when Firefox closes the connection.
- **Hands-on (user, Mint desktop, throwaway profile):** ask about a selection and a page, Stop and
  resume — "model great". One bug: the ✕ on the shared-text box didn't hide it (our CSS overrode
  `[hidden]`); fixed in 0.1.1 and confirmed.
- **Test B, as the ISO will ship it** (VM `cinminai-uefi`, installed from our ISO; user's normal
  Firefox profile): `apt install cinminai-firefox-spike` from our signed repo →
  - extension present on first start with **no prompt**, listed in `about:policies`, **not
    removable** in `about:addons`; sidebar → host → daemon (stub replies, no model in the VM) works;
  - `apt upgrade` 0.1.0 → 0.1.1: Firefox keeps 0.1.0 while running and has **0.1.1 after a restart**;
  - `apt purge`: the extension **stays installed**, now removable (finding 3); removing it by hand
    sticks across restarts.

### Findings

1. **Policy force-install from a `file://` URL works** (`/etc/firefox/policies/policies.json`,
   `ExtensionSettings` → `force_installed`). Mint 22.3 ships no policy file of its own, but Firefox
   reads only **one** `policies.json`: the product must own it as the single place for all our
   Firefox policies (one package, one conffile), and anything else we want in it goes there too.
2. **Updates ride on the install URL.** The package ships the xpi under a versioned path
   (`/usr/share/cinminai/firefox/assistant-VERSION.xpi`); a new `install_url` is what makes Firefox
   reinstall, at its next start. No AMO update server or `update_url` needed. The sidebar should say
   "restart Firefox to finish updating" when the daemon sees the package changed.
3. **Package removal orphans the extension**: with the policy file gone it becomes an ordinary
   user-removable add-on whose host no longer exists. Fix (M1): the extension removes itself with
   `browser.management.uninstallSelf()` when `connectNative` reports the host as missing ("No such
   native application") — a permanent condition, not a transient one — so nothing is left behind on
   purge. Rejected: leaving a `blocked` policy behind after removal (a file `apt purge` should delete).
4. **AMO signing from this PC:** `web-ext sign` uploads fine, but its status polling fails with "JWT
   iat is invalid" because the Windows clock (and WSL) runs ~30 s fast. `amo_fetch.py` stamps tokens
   with AMO's own time (its `Date` header). Real fix: sync the clock; for releases, sign in CI.
5. **Native messaging needs no D-Bus policy work**: Firefox runs the host as the user, in the session,
   so it reaches the session-bus daemon directly; the manifest's `allowed_extensions` limits it to our
   id. Size caps sit in both the extension and the host.
6. Not covered: Firefox as a snap/flatpak (Mint ships a deb; snap Firefox reads policies and native
   hosts from other paths), several Firefox profiles at once, "Send to assistant" into a terminal
   conversation (§7.3, needs the real sidebar).

### Decision

**GO** (PLAN D14, confirmed). M6 builds `cinminai-firefox` on this: policy + versioned xpi + host, with the
self-removal fix and the product daemon in place of the spike one.
