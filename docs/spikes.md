# M0 Spike Results

Go/no-go record for each M0 spike in [PLAN.md](PLAN.md#m0--spikes-1-week-throwaway-code-in-spikes).

| Spike | Status | Verdict |
|-------|--------|---------|
| Terminal emulation (pyte) | Done 2026-09-24 | **GO** — pyte reused inside the terminal relay |
| ISO remaster | Not started | — |
| Terminal relay (vs. VTE patch) | Not started | — |
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
