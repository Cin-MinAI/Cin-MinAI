# Cin-minAI

A local-first, dual-panel Linux AI workspace for Linux Mint/Cinnamon: a real persistent terminal
on the left, a locally running Qwen assistant on the right, with Linux and hardware awareness and
a human-controlled permission boundary for anything privileged or hardware-writing.

**Status:** planning — see [docs/PLAN.md](docs/PLAN.md). Original design: [docs/SPEC.md](docs/SPEC.md).

## Core rule

The assistant may recommend, explain, and prepare a dangerous action.
It never approves one. The user owns the computer, and the user owns the button.

## Targets

- Linux Mint Cinnamon (Ubuntu/Debian base), x86-64, Python 3.11+
- NVIDIA optional; tuned for Pascal (GTX 1070 / 1080 Ti) through modern RTX, with CPU fallback
