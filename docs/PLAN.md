# Cin-minAI — Implementation Plan

Living plan for the dual-panel Linux AI workspace. The original design is in
[SPEC.md](SPEC.md); section references like §12 point there. This document
records what we decided since, and **overrides the spec where they differ**.

Last updated: 2026-09-24

---

## 1. Decisions log

| # | Decision | Replaces / amends |
|---|----------|-------------------|
| D1 | Safety boundary is enforced by an OS sandbox (bubblewrap), not by classifying command strings. The classifier only picks which button a command card shows. | §12, §50, §59, §66 |
| D2 | Three action lanes instead of two: `SANDBOXED`, `USER_APPROVED`, `ADMIN`. | §12 |
| D3 | Polkit policy uses `auth_admin` only — never `auth_admin_keep`. | §13, Rule 5 |
| D4 | The model is a config value chosen by benchmark, not "Qwen2.5-Coder". Default candidate is Qwen3.5-9B; Qwen2.5-Coder-7B stays as the control baseline. | §3, §4, §7 |
| D5 | Ollama is the default backend (it ships a CUDA 12 runner that still supports Pascal). llama.cpp stays as the second backend for LoRA work. | §5 |
| D6 | Tool calls use schema-constrained JSON output (Ollama `format`), not free-form native function calling. | §65 |
| D7 | Thinking mode off by default; opt-in for multi-step diagnosis. | new |
| D8 | LoRA base model is **not** decided until after the M7 baseline benchmark. | §31, §35 |
| D9 | Code lives in a private GitHub repo; develop on the Windows PC (WSL2), validate on the Mint box. | new |

### D1 — Sandbox details

Every AI workspace command runs under `bwrap` with:

- `--new-session` and no-new-privs → setuid binaries (`sudo`, `su`, `pkexec`) cannot elevate.
- Read-only bind of `/usr`, `/etc`, `/lib*`; read-write bind of the workspace only; `$HOME` not mounted.
- Minimal `--dev /dev` → no block devices, serial ports, or debug probes.
- System D-Bus socket (`/run/dbus/system_bus_socket`) **not** mounted → `systemctl restart …`
  cannot trigger a real polkit password dialog that looks like our approved flow.
- Network: allowed by default for builds (package fetches), toggleable per workspace.

The §50 security tests run against this real profile.

### D2 — Action lanes

| Lane | Runs where | Approval | Examples |
|------|-----------|----------|----------|
| `SANDBOXED` | bwrap, as user | none | build, test, grep, read `/sys`, `lspci`, `git diff` in workspace |
| `USER_APPROVED` | outside sandbox, as user | in-app dialog, once | `picotool load`, `esptool write_flash`, `avrdude`, anything touching `$HOME` outside workspace, `git reset --hard` |
| `ADMIN` | root helper via polkit | in-app dialog **then** polkit | package install, `systemctl restart`, `/etc` writes, `dd` to block device |

Rationale: many hardware writes (MCU flashing via `dialout`/`plugdev` groups) need no root at
all, so "admin == hardware write" is false. The sandbox blocks device access regardless of how
the classifier labels a command.

### D3 — Admin helper

- `/usr/libexec/cin-minai/admin-helper`, root:root, 0755; reads one JSON request on stdin.
- Fixed verb set (`restart_service`, `install_package`, `remove_package`, `write_file`, …) mapped to argv.
- A catch-all `run_argv` verb exists but always goes through the destructive-operation dialog (§15).
- The Cinnamon polkit dialog only shows the helper path, so the **in-app dialog is the one that explains the action**.

---

## 2. Hardware and environment

| Machine | Role | Specs | Notes |
|---------|------|-------|-------|
| Dev PC (Windows 10) | development, "modern" profile | Ryzen 9 3900X, RTX 4070 12 GB, driver 591 | Work in WSL2 Ubuntu (not installed yet: `wsl --install`) |
| Mint box (`mint@192.168.5.70`) | Pascal target, integration tests | i7-4790K (4c/8t, AVX2), GTX 1080 Ti 11 GB, 32 GB DDR3, Z97X-UD5H; Mint 22.3, kernel 7.0, driver 580.178 | Installer, polkit, USB/PCI, benchmarks |

Stock Mint 22.3 ships Python 3.12 **without** `python3-venv` or pip. The installer must not
assume them: use a user-space `uv` binary (as the spikes do) or require `python3-venv` via apt.

Pascal constraints (as of Sept 2026):

- CUDA 13 dropped Pascal (compute 6.1). Ollama still ships a CUDA 12 runner and picks it automatically.
- Requires NVIDIA driver **570+**. The **580 branch is the last to support Pascal** → installer must
  warn before any driver upgrade past 580.x on Pascal cards.
- No prebuilt Linux llama.cpp binary for Pascal: compile against CUDA 12, or use the Vulkan build.
- Pin known-good Ollama versions; projects moving to CUDA-13-only will silently drop Pascal.
- DDR3 (~20 GB/s) makes CPU-offloaded MoE models slow on prompt ingestion.

---

## 3. Model strategy

### Candidates (as of Sept 2026)

| Model | Type | Q4 size | Role |
|-------|------|---------|------|
| Qwen3.5-9B | Dense, hybrid Gated DeltaNet attention, vision, hybrid thinking | ~5.5 GB | **Expected default** (1080 Ti, 4070) |
| Qwen3.5-4B | same family | ~2.5 GB | Fallback / CPU / 8 GB cards |
| Qwen2.5-Coder-7B | Dense, standard attention | ~4.7 GB | **Control baseline**; safest LoRA path |
| Qwen3.6-35B-A3B | MoE, 3B active | ~20 GB | Experimental "deep think" profile via expert offload to RAM |

Notes:

- No coder-specific Qwen model exists below 30B in the 3.5/3.6/3.8 generations.
- Qwen3.5 needs Ollama ≥ 0.17.4.
- Hybrid attention uses much less KV cache at long context → larger usable context per GB.
- Qwen3.5 performance on Pascal is **unmeasured** — no public numbers found. The bakeoff decides.
- Many third-party benchmark claims conflict; trust our own eval, not leaderboards.

### Bakeoff matrix (M0)

Run on the 1080 Ti; repeat the same matrix on the 4070 for the modern profile.

| Candidate | Quants | Contexts |
|-----------|--------|----------|
| Qwen3.5-9B | Q4_K_M, Q5_K_M, Q6_K | 8K, 16K, 32K |
| Qwen3.5-4B | Q8_0 | 16K |
| Qwen2.5-Coder-7B | Q5_K_M | 8K, 16K |
| Qwen3.6-35B-A3B (RAM offload) | Q4_K_M | 8K |

Measure per run:

- prompt-processing and generation tok/s
- peak VRAM and RAM
- time-to-first-token on a 4K-token build log
- valid JSON tool-call rate over 50 attempts
- score on ~20 Linux diagnosis tasks (seed of the §36 eval suite)

Output: `bench-results/` (git-ignored) plus a summary committed to `docs/benchmarks.md`,
which then drives the hardware profiles in `hardware_detect.py`.

Rough expectations (to be replaced by measurements): 9B Q5/Q6 on 1080 Ti ~30–50 tok/s
generation; 35B-A3B offload ~8–15 tok/s with slow prompt ingestion.

---

## 4. Milestones

Each milestone has an exit test. Nothing moves forward on a red exit test.

### M0 — Spikes (≈1 week, throwaway code in `spikes/`)

- **Terminal**: pty + `pyte` in a custom Textual widget vs. `textual-terminal`. Test `vim`,
  `htop`, `less`, Ctrl-C/Z, resize, and throughput (`yes | head -100000`). Expected outcome:
  own ~400-line widget over `pyte` with ≤30 fps render throttling.
- **Streaming**: Ollama tokens into a Textual panel while the terminal is busy.
- **Sandbox**: bwrap profile; prove `sudo`, `pkexec`, `systemctl` via D-Bus, and writing `/dev/sda` all fail.
- **Polkit**: pkexec + helper + policy on Mint showing the Cinnamon auth dialog.
- **Model bakeoff** (§3 above).

Exit: a written go/no-go per spike in `docs/spikes.md`.

### M1 — Core shell + assistant (spec Phase 1)

- Package skeleton (`pyproject.toml`, `src/cin_minai/`, ruff, pytest).
- `TerminalSession` interface + pyte implementation.
- `InferenceBackend` interface + `OllamaBackend`.
- Split layout, status bar, streaming chat.
- Command cards: COPY and SEND TO TERMINAL (types at prompt, no Enter).
- Independent supervisors: model crash ≠ shell crash.

Exit: §51 functional tests pass, except browser/web items.

### M2 — Hardware profile + per-user installer

- `hardware_detect.py` → `~/.config/cin-minai/config.toml` (§7).
- Benchmark + fallback ladder (§6), results shown to the user.
- Driver/CUDA-runner checks for Pascal (see §2).
- `install.sh` user-level part: venv, XDG dirs, `.desktop` launcher.

Exit: fresh Mint box → working app with measured defaults, no root required.

### M3 — Context + sandboxed execution (spec Phase 2 + 3a)

- Provider framework returning `ContextResult`: shell output selection, files, git, man/info, system.
- Compiler-log extractor (§41), structured session state (§42), credential redaction (§47).
- `ActionManager` with the three lanes; bwrap runner.
- RUN IN AI WORKSPACE with exit code + output fed back to the model; visible states (§62).
- Structured JSON tools (§65).
- Start the eval harness here (not at the end).

Exit: model diagnoses a seeded build failure end-to-end inside the sandbox.

### M4 — Admin boundary (spec Phase 3b)

- Root helper, polkit policy, privileged installer section, `uninstall.sh`.
- Permission dialog, destructive-operation dialog, `ADMIN: LOCKED` indicator.
- First-run warning (§16).
- `tests/security/` covering all of §50 against the real sandbox.

Exit: all security tests green on the Mint box.

### M5 — Browser + web (spec Phase 4)

- Unix socket server with length limits and a type allowlist.
- `cin-minai-protocol` handler, `x-scheme-handler` registration, bookmarklet.
- `SearchProvider`: DuckDuckGo first, SearXNG second.
- LOCAL/WEB indicator; open sources in Firefox.

Exit: selection in Firefox lands in the running session; `/web` works and fails gracefully offline.

### M6 — Hardware providers (spec Phase 5)

- USB and PCI providers from sysfs + `usb.ids` / `pci.ids`.
- Hardware state cache with `udev` monitor refresh.
- Serial device detection; MCU flash/erase actions in the `USER_APPROVED` lane.

Exit: §70 acceptance criteria all pass → **v0.1**.

### M7 — Eval, then LoRA (spec Phase 6)

- Hidden ≥100-problem eval suite with automated harness scoring the §36 metrics.
- Stock baseline per hardware profile.
- Decide LoRA base (D8). Confirm training (Unsloth/PEFT) and llama.cpp runtime `--lora`
  support for the chosen architecture before building the dataset.
- Dataset targeted at measured failures; train off-box; A/B via `LlamaCppBackend`.

---

## 5. Risks

| Risk | Mitigation |
|------|------------|
| Terminal emulation quality/speed in Textual | M0 spike; `TerminalSession` interface allows swapping |
| Small model misusing tools | Constrained JSON, few tools, eval-driven prompt tuning |
| Pascal dropped by inference backends | Pin versions; CUDA 12 / Vulkan fallback; watch Ollama releases |
| Qwen3.5 slow on Pascal (new DeltaNet kernels, no tensor cores) | Bakeoff includes Qwen2.5-Coder-7B as a standard-attention fallback |
| LoRA tooling immature for hybrid architecture | D8: decide base after baseline; Qwen2.5-Coder is the known-good path |
| Sandbox gaps (D-Bus, `/dev`, setuid, user namespaces) | Security tests against real bwrap profile |
| Scope creep (FPGA/MCU modes, LSP) | Held to post-v0.1 per §55, §60 |

---

## 6. Open questions

- **Project name.** Working name `Cin-minAI` (package `cin_minai`). The spec's `qwen-*` names
  (URL scheme, helper, socket) are placeholders — rename them all together before M4/M5 ships.
- **License.** Private for now; choose before any public release.
- **Sync to Mint box.** `git pull` over the GitHub remote vs. PyCharm remote interpreter — decide at M0.

---

> Qwen may recommend the dangerous action.
> Qwen may explain the dangerous action.
> Qwen may prepare the dangerous action.
> Qwen does not get to approve the dangerous action.
>
> The user owns the computer. The user owns the button. (§73)
