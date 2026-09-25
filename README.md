# Cin-MinAI OS

A Linux Mint Cinnamon–derived distribution with a local AI assistant built into the operating
system: a desktop sidebar, panel applet, and hotkey; awareness of your real terminals, of
Firefox, and of LibreOffice documents; Linux and hardware knowledge; and a human-controlled
boundary for anything privileged or hardware-writing.

**Status:** M0 spikes — see [docs/PLAN.md](docs/PLAN.md). Design: [docs/SPEC.md](docs/SPEC.md).
Spike results: [docs/spikes.md](docs/spikes.md).

## Core rule

The assistant may recommend, explain, and prepare a dangerous action.
It never approves one. The user owns the computer, and the user owns the button.

## Targets

- Base: Linux Mint Cinnamon 22.x (Ubuntu 24.04), x86-64
- NVIDIA optional; tuned for Pascal (GTX 1070 / 1080 Ti) through modern RTX, with CPU fallback
- Model runs locally (llama.cpp, tuned per machine); nothing leaves the machine unless you use a web feature

## How it's built — credits

Cin-MinAI is led by **Ian McClenathan** (Brickmii): vision, decisions, hardware, and every approval.
It is built with AI assistants, in the open, each used where it worked best — **none preferred**:

- **Gemini** (Google) — the initial plan.
- **Claude** (Anthropic, via Claude Code) — lead developer on the dev PC: specification and
  decisions log, the M0 spikes, the guide eval and held-out eval, the transition knowledge base and
  corpus tooling, write-ups. Commits carry a `Co-Authored-By: Claude` line.
- **Codex / ChatGPT** (OpenAI) — junior developer and backup on the test machine: the llama.cpp
  test build, the Qwen VRAM recovery, the bakeoff harness (`bench/`), candidate inventory and
  checksummed downloads, the Vulkan build dependencies. Its brief is `AGENTS.md`.

The assistants build the project; they are **not** the source of the guide model's training data.
That corpus is written by local open-weight models (Apache-2.0) and published with its scripts
(PLAN D32), so anyone can inspect or rebuild it. Every decision and result — including the
failures — is in `docs/` (PLAN D26: built in the open, under the oversight of its community).

