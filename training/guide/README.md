# Guide fine-tune — plan and record (model cycle 0)

Goal: pick the built-in guide model (PLAN D23) from **Gemma 4 E2B** and **Qwen3.5-4B** (the two leaders
of `docs/benchmarks.md`), tuned for our users, and publish exactly how (PLAN D26, D31): what we
tested, how it turned out, why we picked it, and every step of tuning. `MODEL_CARD.md` is filled in
as each phase finishes; nothing in it is written ahead of a measurement.

Order follows SPEC §14.2: stock → benchmark → prompt/tools → benchmark → data → LoRA → compare.

## Phase 0 — stock baseline ✓ (2026-09-25)

Guide eval (157 items) + speed/memory on the 1080 Ti (CUDA, Vulkan) and CPU: Gemma 4 E2B 78 %,
Qwen3.5-4B 74 %, reference Qwen3-14B 83 %. Details: `docs/benchmarks.md`.

## Phase 1 — a hidden eval, then prompt and knowledge base (no training)

1. **Hidden eval** (`training/eval/guide-hidden/`, kept out of the public repo until the cycle closes,
   then published and replaced next cycle): ~50 new tasks in the same categories and languages,
   written without looking at any model's output, never used for prompt tuning or training data.
   The public eval has been seen while fixing scorer bugs and will be seen while tuning the prompt;
   the hidden one is what the final claim rests on.
2. **Prompt v2** aimed at the measured failures (numbered steps, scams and privacy are in scope,
   decline off-topic without a lookup, the next empty row, reply in the user's language). Re-run both
   candidates on the public eval; report the gain from the prompt alone.

## Phase 2 — training data (published with its scripts)

- **Source: local open models only** — Qwen3-14B and Qwen3.5-9B (Apache-2.0) as teachers through
  llama-server, never a proprietary API, so the data's licence is clean and anyone can regenerate it.
  The lead writes the generator, the scenario lists, and the checks, and reviews samples.
- **Scenarios**: Windows→Mint topics and lessons from the knowledge base, LibreOffice operations
  (incl. the checkbook), read-only system checks, off-topic requests, scams and privacy, approvals —
  in all six languages (D25), phrased the way beginners actually ask (typos, vague wording).
- **Format = runtime format**: system prompt v2 + question → the stage-A JSON call → tool result →
  the reply. The model learns exactly what the product will ask of it.
- **Filters**: the eval's own mechanical checks (schema, language, Mint names from `labels.json`,
  facts from the card, numbered steps, length, no terminal commands); duplicates removed;
  **decontamination**: any question too close to a public or hidden eval task (word n-gram overlap)
  is dropped, and the count is reported.
- Target ~3,000 examples, balanced by category and language; a random 5 % read by the lead before
  training, with the rejection rate reported.

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
beats the stock one overall and on the hidden eval, and loses nowhere critical — safety, declines,
boundary, and the careful-newcomer tasks (D28). Then write `MODEL_CARD.md` and the release note.

## Limits we state up front

- **Vulkan / AMD is a community beta.** We have no AMD card and won't run a second machine or swap
  drivers; our Vulkan numbers come from NVIDIA's Vulkan path on a 1080 Ti, which is not
  representative of AMD. We publish that plainly and invite AMD owners to run `bench/run.py` and
  `run_eval.py` and send results.
- One reference machine per backend; the eval is mechanical (no human rating of tone yet).
