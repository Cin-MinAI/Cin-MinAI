# M0 Spike Results

Go/no-go record for each M0 spike in [PLAN.md](PLAN.md#m0--spikes-1-week-throwaway-code-in-spikes).

| Spike | Status | Verdict |
|-------|--------|---------|
| Terminal emulation (pyte) | Done 2026-09-24 | **GO** — pyte reused inside the terminal relay |
| ISO remaster | Done 2026-09-24 | **GO** — remaster + own signed repo works (UEFI + BIOS) |
| Terminal relay (vs. VTE patch) | Done 2026-09-24 | **GO** — relay is the baseline; VTE patch not needed for M1 |
| Desktop surface (applet, sidebar, hotkey) | Not started | — |
| Firefox (extension + native messaging) | Not started | — |
| Streaming (Ollama → sidebar) | Not started | — |
| Sandbox (bwrap) | Not started | — |
| Admin mechanism (D-Bus + polkit) | Not started | — |
| Model bakeoff | Not started | — |

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
