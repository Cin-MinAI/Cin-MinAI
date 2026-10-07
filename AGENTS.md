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
  lead is unavailable**, you and Ian carry on from this file plus `docs/`: same rules, same decision
  log. The Mint box's own Mint install (the NVMe) has **no GitHub or Google credentials, by design**
  (Ian keeps the footprint minimal). The Cin-MinAI test SSD in the same box is different (2026-10-03):
  it carries **the machine's own accounts** — a development email, Hugging Face, Thunderbird on that
  email — which belong to the assistant and the OS, not to Ian (D62), plus Ian's GitHub sign-in in
  Firefox for the repos. The lead keeps a read-only copy of `docs/` + this file in `~/cin-minai/repo-docs/`
  (see its `VERSION`). The repo itself is `git@github.com:Cin-MinAI/Cin-MinAI.git` (public since 2026-10-04).
- Hand-offs between lead and Codex go through `~/cin-minai/notes/` on the Mint box (dated Markdown
  notes, both directions).

## What we are building

**Vision** (SPEC §1, PLAN D26): AI becomes how people use their computer, as the internet changed it
before; people will build their own software instead of renting SaaS. We build the local, owned,
human-approved version of that, **in the open, under the oversight of the community it's for**.

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

## Status (2026-10-07)

Cin-MinAI 0.0.1 is public (ISO on Hugging Face `CinMin/Cin-MinAI-OS`, signed apt repo, website
`cin-minai.github.io`); four signed updates since. M0–M3 done; **M4** (one action path, D67/D85) has slices 1–3:
the action record and walls, the daemon's actions on it, and `cinminai-admin` (your package, merged and live-tested
2026-10-06) wired in. D84 coverage of what Mint offers is under way (`docs/d84-coverage.md`); prompt v2.3 adopted.
Read `docs/RESUME.md` first — it is always the current state — then the latest `docs/dev-journal.md` entry.

## Credits

The project credits every contributor plainly, none preferred (README "credits"): Ian leads; the
initial plan was made with Gemini; Claude and Codex/ChatGPT build it, each where it works best.
When you report work, say what you did so it can be credited.

## Machines

| Machine | Use | Notes |
|---|---|---|
| Dev PC (Windows 10) | development, builds, VM tests (the lead works here) | Ryzen 9 3900X, RTX 4070 12 GB. WSL `Ubuntu-24.04` (user `brickmii`, sudo needs Ian's password), ~930 GB free. Build work area `~/cinminai-build` (ISO, signed spike repo, key in `~/cinminai-build/gnupg`). Hyper-V: the boot/install tests make throwaway VMs (`distro/vm-boottest.ps1`); the M0 VMs were deleted 2026-10-05; ISOs and test logs in `C:\Users\Ian\cinminai-vm`. |
| Mint box `mint@192.168.5.70` | **test machine only**; Codex works here | i7-4790K, GTX 1080 Ti 11 GB (Pascal: driver must stay ≤ 580.x), 32 GB DDR3, Mint 22.3, 4K display at 3× scaling. No passwordless sudo. Vulkan build deps (`libvulkan-dev glslc spirv-headers`) installed 2026-09-25 with Ian's approval. |

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

## Your current task: catch a looping reply as it streams

The task note is `~/cin-minai/notes/2026-10-07-task-for-codex-loop-detector.md` (your own design from the
repetition report). Earlier tasks — bakeoff prep (2026-09-25), admin/security/SBOM (2026-10-06), the repetition-guard
study (2026-10-07) — are done and credited. GPU etiquette (hard rule 2) as always.
