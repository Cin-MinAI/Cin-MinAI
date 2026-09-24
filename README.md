# Cin-MinAI OS

A Linux Mint Cinnamon–derived distribution with a local AI assistant built into the operating
system: a desktop sidebar, panel applet, and hotkey; awareness of your real terminals, of
Firefox, and of LibreOffice documents; Linux and hardware knowledge; and a human-controlled
boundary for anything privileged or
hardware-writing.

**Status:** M0 spikes — see [docs/PLAN.md](docs/PLAN.md). Design: [docs/SPEC.md](docs/SPEC.md).
Spike results: [docs/spikes.md](docs/spikes.md).

## Core rule

The assistant may recommend, explain, and prepare a dangerous action.
It never approves one. The user owns the computer, and the user owns the button.

## Targets

- Base: Linux Mint Cinnamon 22.x (Ubuntu 24.04), x86-64
- NVIDIA optional; tuned for Pascal (GTX 1070 / 1080 Ti) through modern RTX, with CPU fallback
- Model runs locally (llama.cpp, tuned per machine); nothing leaves the machine unless you use a web feature
