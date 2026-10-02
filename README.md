# Cin-MinAI OS

A Linux Mint Cinnamon–derived distribution with a local AI assistant built into the operating
system: a desktop sidebar, panel applet, and hotkey; awareness of your real terminals, of
Firefox, and of LibreOffice documents; Linux and hardware knowledge; and a human-controlled
boundary for anything privileged or hardware-writing.

**Status:** M0 spikes — see [docs/PLAN.md](docs/PLAN.md). Design: [docs/SPEC.md](docs/SPEC.md).
Spike results: [docs/spikes.md](docs/spikes.md).
What we can't do alone and would love help with: [docs/HELP-WANTED.md](docs/HELP-WANTED.md).

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

**Standing on the shoulders of others.** Cin-MinAI is a layer on top of decades of other people's work:

- **The Linux Mint team**, for Mint and Cinnamon, the system we build on and keep as Mint-like as we can;
  **Ubuntu (Canonical) and Debian** underneath it; and the **Linux kernel and GNU** communities underneath all of it.
- **llama.cpp and ggml** (Georgi Gerganov and contributors), the engine that runs every model here, tuned to
  each machine.
- **The open-weight model makers**: the **Qwen team** (Alibaba), whose models we tune and ship; Google (Gemma)
  and IBM (Granite), whose models we tested; and **Hugging Face** and the people who publish GGUF conversions
  (Unsloth, ggml-org).
- **LibreOffice (The Document Foundation) and Mozilla**, whose programs the assistant works inside.
- **The researchers and builders who started this era**: from the Transformer paper (Google, 2017) to OpenAI's
  public release of ChatGPT in 2022, which put these tools in everyone's hands and pushed the whole field, open
  models included, forward.

The assistants build the project; they are **not** the source of the guide model's training data.
That corpus is written by local open-weight models (Apache-2.0) and published with its scripts
(PLAN D32), so anyone can inspect or rebuild it. Every decision and result — including the
failures — is in `docs/` (PLAN D26: built in the open, under the oversight of its community).


## Licence

Our code is **GPL-3.0-or-later** (`LICENSE`). Data and documents — the training corpora, eval tasks and
docs — are **CC BY-SA 4.0**; our fine-tuned guide models are **Apache-2.0**, like their base. What covers
what, and the licences of what we build on: [`LICENSING.md`](LICENSING.md).
