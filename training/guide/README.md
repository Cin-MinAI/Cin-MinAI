# Guide fine-tune — plan and record (model cycle 0)

Goal: pick the built-in guide model (PLAN D23) from **Gemma 4 E2B** and **Qwen3.5-4B** (the two leaders
of `docs/benchmarks.md`), tuned for our users, and publish exactly how (PLAN D26, D31): what we
tested, how it turned out, why we picked it, and every step of tuning. `MODEL_CARD.md` is filled in
as each phase finishes; nothing in it is written ahead of a measurement.

Order follows SPEC §14.2: stock → benchmark → prompt/tools → benchmark → data → LoRA → compare.

**What the fine-tune is for (PLAN D32): making the move from Windows to Linux easier — nothing else.**
Everything else the eval measures (declining off-topic requests, scam and privacy help, office
tools, the next empty row, system checks) is fixed in what we build around the model: the prompt,
the knowledge base, the tools, and checks in the daemon. A good base model should need only a small
tune. The **transition corpus is published** (`training/datasets/transition/`) with the scripts that
make it — anyone can rebuild the same guide, roughly — and it's **updated with every OS release**
(D31), as Mint's programs and names change.

## Phase 0 — stock baseline ✓ (2026-09-25)

Guide eval (157 items) + speed/memory on the 1080 Ti (CUDA, Vulkan) and CPU: Gemma 4 E2B 78 %,
Qwen3.5-4B 74 %, reference Qwen3-14B 83 %. Details: `docs/benchmarks.md`.

## Phase 1 — a hidden eval, then prompt and knowledge base (no training)

1. **Held-out eval** (`training/eval/guide-hidden/`, **committed like everything else**): 45 tasks / 95 items
   in the same categories and languages, written before any tuning (the git history is the proof),
   and **used only once, for the final score** — never for prompt tuning, never shown to the data
   generator, and checked against the training data (decontamination report). The public eval has
   been seen while fixing scorer bugs and will be seen while tuning the prompt; the held-out one is
   what the final claim rests on. A new held-out set is written for each cycle.
2. **Prompt v2** aimed at the measured failures (numbered steps, scams and privacy are in scope,
   decline off-topic without a lookup, the next empty row, reply in the user's language). Re-run both
   candidates on the public eval; report the gain from the prompt alone.

## Phase 2 — the transition corpus (published with its scripts)

- **Source: local open models only** — Qwen3-14B and Qwen3.5-9B (Apache-2.0) as teachers through
  llama-server, never a proprietary API, so the data's licence is clean and anyone can regenerate it.
  The lead writes the generator, the scenario lists, and the checks, and reviews samples.
- **Scenarios — transition only**: "where is X from Windows?", "how do I do Y that I did on
  Windows?", beginner lessons with Windows habits (Ctrl+Alt+Del, .exe files, C: drive, Control
  Panel, the Start menu, Notepad, Snipping Tool, Outlook, Windows Update, antivirus…), answered with
  Mint's own names in the user's language (`labels.json`), numbered mouse steps, and the knowledge
  base's facts — in all six languages (D25), phrased the way beginners actually ask (typos, vague
  wording, Windows words). Not in the corpus: office tools, declines, system checks (integration).
- **Format = runtime format**: system prompt v2 + question → the stage-A JSON call → tool result →
  the reply. The model learns exactly what the product will ask of it.
- **Filters**: the eval's own mechanical checks (schema, language, Mint names from `labels.json`,
  facts from the card, numbered steps, length, no terminal commands); duplicates removed;
  **decontamination**: any question too close to a public or hidden eval task (word n-gram overlap)
  is dropped, and the count is reported.
- Target ~2,000 examples, balanced by topic and language; a random 5 % read by the lead before
  training, with the rejection rate reported. Stored as JSONL in `training/datasets/transition/`
  with a datasheet (sources, teacher models and versions, filters, counts, known gaps).

## Phase 3 — LoRA training (RTX 4070, WSL, dev PC)

QLoRA on the **official base weights** (Hugging Face safetensors, not third-party GGUFs), same data
and settings for both candidates: rank 16, alpha 32, learning rate ~1e-4, 2 epochs, 2,048-token
sequences, loss on assistant turns only, fixed seed. Logged: tool versions, hyperparameters, loss
curves, training time, GPU. Nothing trained on the Mint box (D21).

## Phase 4 — export and verify

Merge the adapter into the base weights → `convert_hf_to_gguf.py` → quantize (Q4_K_M; for Gemma
also Q4_0 to compare with the vendor's QAT file, whose quantization-aware training a fine-tune does
not keep) with the pinned llama.cpp (`v0.5.0`, `7fe450e`). Record SHA-256 of every file shipped.

## Phase 5 — compare and pick

Public eval + hidden eval + speed/memory (CUDA and CPU; Vulkan is a community beta, below) for
stock, prompt v2, and fine-tuned, both candidates. **The D31 gate**: ship only if the tuned model
beats the stock one on transition and lessons (public and held-out), and loses nowhere else —
safety, declines, boundary, office, and the careful-newcomer tasks (D28) must not get worse. Then write `MODEL_CARD.md` and the release note.

## Limits we state up front

- **Vulkan / AMD is a community beta.** We have no AMD card and won't run a second machine or swap
  drivers; our Vulkan numbers come from NVIDIA's Vulkan path on a 1080 Ti, which is not
  representative of AMD. We publish that plainly and invite AMD owners to run `bench/run.py` and
  `run_eval.py` and send results.
- One reference machine per backend; the eval is mechanical (no human rating of tone yet).
