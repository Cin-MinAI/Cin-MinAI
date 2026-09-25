# Cin-MinAI — brief for Codex

Written by the lead (Claude Code) on 2026-09-25. Codex works on the **Mint box**; a copy of this
file is delivered there as `~/cin-minai/notes/<date>-…-for-codex.md` (Codex loads this repo copy
automatically if it ever works in a clone). **Save the project summary below to your own memory**:
it is the backup if the lead's setup on the dev PC breaks.

## Roles

- **Ian** (owner): decides scope, approves anything visible or persistent, does all hardware work,
  types into VMs. Ask him when a rule below says so or when something is his to decide.
- **Claude Code** (lead): architecture, specs, spike verdicts, reviews.
- **Codex** (junior, on the Mint box): tasks the lead hands over (see "Your current task"). **If the
  lead is unavailable**, you and Ian carry on from this file plus `docs/` in the GitHub repo
  (`git@github.com:Brickmii/Cin-MinAI.git`, private): same rules, same decision log.
- Hand-offs between lead and Codex go through `~/cin-minai/notes/` on the Mint box (dated Markdown
  notes, both directions).

## What we are building

**Cin-MinAI OS**: a Linux Mint 22.3 (Cinnamon) derived distribution, shipped as an installable ISO,
with an **OS-wide local AI assistant**. The model runs on the user's own GPU (llama.cpp); nothing
goes to the cloud unless the user asks for a web search.

Audience (PLAN D22): **Windows users new to Linux**. Everyday use needs no terminal; plain language;
the assistant bridges from Windows concepts. The product is the ISO (D21): nothing may depend on
any one machine's state; everything real ships as `.deb` packages from our own signed apt repo.

Key docs (read before changing anything):
- `docs/SPEC.md` — the design. `docs/PLAN.md` — decisions log (D1–D25) + milestones; **PLAN
  overrides SPEC where they differ**. `docs/spikes.md` — M0 spike results and findings.

Architecture in one breath:
- `cinminai-daemon` owns `org.cinminai.Assistant1` on the session D-Bus; everything talks to it.
- **llama.cpp `llama-server` is the only inference backend** (D5), built by us: CUDA 12 incl. Pascal
  sm_61, Vulkan (AMD), CPU. Tool calls are schema-constrained JSON (D6).
- GPU memory is shared with the desktop (SPEC §4.2): budget at load time, keep a desktop reserve
  (≥ 1.5 GB at 4K, ≥ 0.8 GB at 1080p), step down instead of crash-looping, say so in the UI.
- Desktop: docked sidebar + Cinnamon panel applet + Super+A. Terminal: a PTY relay (pyte) sees every
  terminal. Commands run in a bwrap sandbox with a private network (pasta) (D1). Admin actions go
  through a D-Bus root mechanism with per-request polkit `auth_admin` (D3).
- Apps: LibreOffice Python-UNO extension with a previewed, one-undo-step toolkit (D20); Firefox
  AMO-signed extension, force-installed by policy, native messaging host (D14).
- **Guide model** (D23): a small model ships on the ISO so the assistant works offline from the live
  USB through install. Bigger models are optional downloads. **6 GB GPU floor, NVIDIA and AMD** (D24).
  **v1 languages** (D25): English, Spanish, Portuguese, French, German, Japanese.

## Status (2026-09-25)

M0 spikes, all **GO**: terminal emulation, ISO remaster, terminal relay, desktop surface, streaming,
sandbox, admin mechanism, LibreOffice, Firefox. **Remaining: the model bakeoff** (two tracks: guide
and big), then M1 (distro skeleton). The guide eval is written (`training/eval/guide/`, copy on the
Mint box in `~/cin-minai/eval-guide`; reference Qwen3-14B 86 %). Spike code lives in `spikes/` and is throwaway.

## Machines

| Machine | Use | Notes |
|---|---|---|
| Dev PC (Windows 10) | development, builds, VM tests (the lead works here) | Ryzen 9 3900X, RTX 4070 12 GB. WSL `Ubuntu-24.04` (user `brickmii`, sudo needs Ian's password), ~930 GB free. Build work area `~/cinminai-build` (ISO, signed spike repo, key in `~/cinminai-build/gnupg`). Hyper-V VMs `cinminai-uefi` / `cinminai-bios` (files in `C:\Users\Ian\cinminai-vm`). |
| Mint box `mint@192.168.5.70` | **test machine only**; Codex works here | i7-4790K, GTX 1080 Ti 11 GB (Pascal: driver must stay ≤ 580.x), 32 GB DDR3, Mint 22.3, 4K display at 3× scaling. ~110 GB free. No passwordless sudo. |

## Hard rules

1. **The Mint box is shared with Ian's other projects.** Work there only user-level, in
   `~/cin-minai/`, reversibly, and tell Ian before anything visible or persistent. Never touch its
   services, drivers, boot setup or desktop settings (no `xrandr` — it once changed his UI scale).
2. **`qwen14b.service`** (systemd `--user`, llama-server on :8080, Qwen3-14B, idle-unloads after
   300 s) is Ian's. Never stop, restart, or reconfigure it without asking him first. Check
   `nvidia-smi` before every GPU run there and abort if VRAM is taken.
3. Model weights and results never go in git (`*.gguf`, `bench-results/` are ignored).
4. Secrets stay where they are and are never printed: AMO key in WSL `~/.config/cinminai/amo.env`,
   llama-server API key on the Mint box.
5. The lead reviews before anything lands on `main`. On the Mint box, work in `~/cin-minai/`; the
   lead copies results into the repo. With a clone: a `codex/<topic>` branch.
6. Report results as measured, failures included.

## Gotchas (learned the hard way)

- SSH to the Mint box from **Git Bash** (key auth works); Windows OpenSSH rejects the key (ACL issue).
  For multi-line remote work: `ssh mint@192.168.5.70 bash -s < script.sh`.
- `wsl.exe` re-parses arguments through a shell: use `wsl -d Ubuntu-24.04 --cd <path> -e <cmd>` or a
  script file, and `MSYS_NO_PATHCONV=1` when calling from Git Bash.
- No KVM inside WSL on this PC: VMs are Hyper-V only. Hyper-V `TypeText` garbles Linux input; Ian
  types in VMs. The VM reaches a repo served from Windows (`serve.ps1`, Default Switch host address).
- The Windows clock runs ~30 s fast (breaks AMO JWTs; `spikes/firefox/amo_fetch.py` works around it).
- Signed Firefox xpis live only in `spikes/firefox/dist/` (git-ignored); `amo_fetch.py VERSION`
  re-downloads them from AMO.

## Your current task: bakeoff prep on the Mint box

Goal: everything ready so the lead can run the bakeoff (PLAN §3, "Guide model track" and "Bakeoff
matrix"). **Prep only**: don't score models or pick winners; the lead writes the guide eval tasks and
does the RTX 4070 side on the dev PC with your harness. Everything goes under `~/cin-minai/bench/`.

1. **Candidate inventory** → `bench/candidates.toml`: for every model in PLAN §3 (guide: Qwen3.5-2B,
   Qwen3.5-4B, Gemma 4 E2B, Gemma 4 E4B, Granite 4.2 3B, Qwen2.5-1.5B baseline; big: Qwen3-14B Q4_K_M,
   Qwen3.5-9B Q4_K_M/Q5_K_M/Q6_K, Qwen3.5-4B Q8_0, Qwen2.5-Coder-7B Q5_K_M, Qwen3.6-35B-A3B Q4_K_M)
   record the Hugging Face repo (prefer the vendor's official GGUF), exact file per quant, size,
   SHA-256, license, and the minimum llama.cpp version for its architecture. **If a model or quant
   doesn't exist or the license isn't Apache-2.0/MIT-compatible, write that down — never
   substitute or guess.**
2. **llama.cpp, one pinned release tag** (newest that loads every candidate), in
   `~/cin-minai/llama.cpp` — leave the `local-ai-testbed` build alone. Three builds, exact cmake flags
   recorded in `bench/README.md`:
   - **CUDA**: `nvidia-cuda-toolkit` 12.0 + gcc/g++-12 + `CMAKE_CUDA_ARCHITECTURES=61` (the testbed
     recipe, PLAN §2), `GGML_NATIVE=OFF`.
   - **Vulkan** (the AMD path; the 1080 Ti runs Vulkan too). If a Vulkan dev package is missing, don't
     install it: list what's needed and Ian decides (no sudo without him).
   - **CPU-only** (the live-USB case; this i7-4790K is a fair "older PC").
3. **Downloads** into `~/cin-minai/models`, **at most 60 GB** total: all guide candidates, then the big
   ones that fit, largest last. You may reuse the testbed's Qwen3-14B file read-only (path in
   `candidates.toml`, don't copy it). Everything under `~/cin-minai` is removed when M0 closes.
4. **Harness** `bench/run.py` (stdlib Python 3.12, no pip): starts `llama-server` on its own port
   (**not 8080**) with model, quant, context, `-ngl`, q8_0 KV cache, flash attention, and a build
   choice (cuda/vulkan/cpu); measures prompt and generation tok/s, time to first token on a ~4K-token
   prompt, peak VRAM (poll `nvidia-smi`: process and card total), peak RAM, **free VRAM left** (for the
   SPEC §4.2 reserve), and the valid-JSON rate over 50 schema-constrained tool calls (schemas in the
   repo's `spikes/libreoffice/assist.py`; a copy is in `~/cin-minai/spikes/libreoffice/assist.py`).
   **Guide budget mode** (`--budget-gb 6`): the llama-server process must peak ≤ 4.7 GiB at 8K
   context (6 GB card − ~0.5 GB desktop − 0.8 GB reserve); report pass/fail per run. One JSON line per
   run to `~/cin-minai/bench-results/<machine>/<date>.jsonl`; always stop the server afterwards. Keep
   it portable: the lead runs the same script on the dev PC (RTX 4070, WSL).
5. **GPU etiquette** (hard rule 2): before any GPU run, check `nvidia-smi`; if `qwen14b.service` has
   the model loaded or Ian is using the card, wait or ask him. Never stop it yourself.
6. **Smoke test only:** one small guide candidate through `run.py` on CUDA, Vulkan and CPU, then stop
   and write your report to `~/cin-minai/notes/<date>-bench-prep-report.md`: tag and flags, what is
   built and downloaded (disk used), missing candidates or licences, smoke numbers, and anything that
   surprised you.
