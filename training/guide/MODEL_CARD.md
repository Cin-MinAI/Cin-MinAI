# Cin-MinAI guide model — model card (cycle 0)

> Filled in as the fine-tune (`README.md` in this folder) progresses. Sections still marked
> *pending* have no result yet; nothing here is written ahead of a measurement.

## The pick

*Pending (phase 5).* Model, base, licence, files and SHA-256, and one paragraph on why.

## What we tested, and how

- **Candidates (cycle 0):** Gemma 4 E2B, Gemma 4 E4B, Qwen3.5-2B, Qwen3.5-4B, Granite 4.2 3B,
  Qwen2.5-1.5B (baseline); Qwen3-14B as the big-model reference. Files pinned in
  `bench/candidates.toml`.
- **Quality:** `training/eval/guide/` — 157 items (82 tasks; 15 in English, Spanish, Portuguese,
  French, German and Japanese), mechanical scoring: right first action (tool + arguments), then a
  reply checked for language, Mint's own names in that language, facts, numbered steps, length, and
  no terminal commands. Plus the hidden eval (phase 1).
- **Speed and memory:** `bench/run.py` — 8K context, 4K-token prompt, 50 schema-constrained tool
  calls; peak GPU and RAM against the 6 GB-card budget (≤ 4.7 GiB for the model).
- **Hardware:** GTX 1080 Ti (CUDA 12.0, sm_61), same card via Vulkan, i7-4790K CPU-only; RTX 4070
  (pending). No AMD card (community beta).
- **Software:** llama.cpp `v0.5.0` (`7fe450e`), q8_0 KV cache, flash attention, temperature 0.

## How it turned out

Stock results: `docs/benchmarks.md` (Gemma 4 E2B 78 %, Qwen3.5-4B 74 %, reference 83 %).
Prompt v2, public eval (phase 1): **Qwen3.5-4B 87 %, Gemma 4 E2B 84 %**, reference 82 %.
*Pending:* fine-tuned, held-out eval, before/after by category and language.

## Tuning after the pick

*Pending (phases 1–4):* prompt changes; training data (source models, count, languages, filters,
decontamination, review sample and rejection rate); LoRA settings, tool versions, loss, time;
export and quantization.

## Who did the work

Directed by Ian McClenathan. Eval, knowledge base, corpus tooling and training scripts: Claude
(Anthropic); bakeoff harness and model inventory: Codex (OpenAI); initial plan: Gemini (Google) —
see README "credits". The training corpus itself comes only from local open-weight teacher models
(named above), never from these assistants.

## Known limits

- Vulkan/AMD not measured on AMD hardware (community beta).
- Eval is mechanical; tone and patience are not rated by people yet.
- *Pending:* failures that remain after tuning, listed by task.
