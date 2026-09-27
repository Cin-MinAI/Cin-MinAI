# Cin-MinAI guide model — model card (cycle 0)

The small model built into Cin-MinAI OS that helps people who came from Windows use their computer: it
looks things up in the built-in help, checks the computer, opens programs, works with a shared
LibreOffice document, and politely declines everything else. Runs locally with llama.cpp; nothing leaves
the machine. Everything below is measured unless it says otherwise. Decision: PLAN **D43**; the
story of how we got here, failures included: `docs/guide-model-journal.md`.

## The pick

**Qwen3.5-4B, fine-tuned (run HO), Q4_K_M.** Chosen over Gemma 4 E2B — the other finalist — on both
evals: stock vs stock, public 87 % vs 84 %, held-out 66 % vs 51 %. Tuned, it beats its own stock
version overall on both (public 92–94 %, held-out 73 % vs 66 %), with its biggest gains exactly where a
newcomer needs them: lessons, declining off-topic requests kindly, and staying inside its role. It loses
nothing on safety, system checks or office work. **One known cost:** on the held-out set, Windows→Mint
questions are 2 items below stock (see "Known failures"). Ian accepted that for the other gains (D43);
the stock model with prompt v2 stays one switch away.

| | |
|---|---|
| File | `Qwen3.5-4B-guide-HO-Q4_K_M.gguf` — 2,783,446,848 bytes |
| SHA-256 | `b9b132b05530879ae528dbd195161398b69768fa87b347ffd92a2b6f67e8c8e4` |
| Base | `Qwen/Qwen3.5-4B` (Hugging Face, revision `851bf6e806`), **Apache-2.0** |
| Architecture | `qwen35` (32 layers: full + linear attention), text only |
| Runtime | llama.cpp `v0.5.0` (`7fe450e`), prompt v2 (`training/eval/guide/run_eval.py`), temperature 0 |
| Languages | English, Spanish, Brazilian Portuguese, French, German, Japanese (D25) |

## What it's for — and not for

- **For:** a newcomer's everyday questions about this computer — Windows habits → Linux Mint, how-to
  lessons, checking storage/updates/network/printers/sound/display/battery/drivers, scam and privacy
  questions, and requests about an open LibreOffice document (answer from it, add a row, put a formula
  in, fix or rewrite the selected text, change a slide).
- **Not for:** anything else. It is trained to decline history, politics, health, law, money advice,
  news, homework, recipes and writing texts for people, and to say what it can help with instead. It
  gives no terminal commands. It never approves anything: installs and admin actions go through the
  user's password (D3), edits are previewed (D20).
- **Not a general chatbot, and not the big model.** Bigger models are optional downloads (D23).

## Training

- **Method:** QLoRA (nf4 double-quant, bf16 compute) on the bf16 base, rank 16, alpha 32, dropout 0.05,
  targets `q,k,v,o,gate,up,down` (Qwen3.5's linear-attention projections left out: llama.cpp can't
  convert adapters on them); 21.2 M trainable parameters. 1 epoch, lr 5e-5 (linear warm-up and decay),
  batch 1 × 8 accumulation, 95 steps, max 2,048 tokens, seed 1. Every assistant turn trained in
  last-turn position, rendered with the model's own template (the cause of cycle 0's first failed tune).
  RTX 4070, 1,594 s, peak 10.6 GiB. torch 2.11.0+cu128, transformers 5.17.0, peft 0.21.0, Python 3.12.3.
  Loss 0.59 → 0.33.
- **Data: 762 training sequences** from two published corpora (`make_session_mix.py --turns 360
  --preset h --office 115 --seed 7`):
  - **Session corpus** (`training/datasets/sessions/`, 292 conversations; 212 used): one coherent,
    unique conversation per example mixing turn types, so the model learns to *choose* — clear lookups
    (30 % of trained turns), walkthroughs one step at a time (12 %), reports of what a system check
    shows (12 %), vague requests answered with offers and a question (12 %), declines (10 %), safety
    (8 %), system checks (8 %), small talk (8 %). Untrained turns stay as context.
  - **Office corpus** (`training/datasets/office/`, 252 examples; 115 used): a LibreOffice document
    shared in the sidebar's format; 15 % of requests are about the computer or off-topic.
  - **Who wrote it:** only a local open-weight teacher — **Qwen3-14B** Q4_K_M (Apache-2.0) on a GTX
    1080 Ti. The documents are the teacher's inventions, never eval documents. The right tool call and
    its arguments (which cell, which formula, which paragraphs) are computed by our code, not written by
    the teacher. No proprietary model or API wrote any training text.
  - **Checks on every example:** grounding (every quoted menu or button name must exist in the help
    card, the tool result, Mint's own labels, or the user's words), declines must refuse, replies in
    the user's language (56 English closing questions in non-English walkthroughs repaired to the
    native phrase; the cause was our own prompt), no terminal, facts from the tool result, and
    **decontamination**: no training message within 0.5 (3-gram Jaccard) of any eval item; against the
    held-out set the closest is 0.25.
  - The datasheet (`training/datasets/DATASHEET.md`) describes the earlier transition and
    interpretation corpora; **a section for the session and office corpora is still owed** — until then
    their generator docstrings and `merge-stats.json` files are the record.
- **Export:** `training/guide/merge_quantize.sh` — base → f16 GGUF → adapter merged with
  `llama-export-lora` → `llama-quantize` Q4_K_M (no importance matrix). All 128 adapter tensors
  verified merged from the weights.

## Results

Mechanical scoring (`training/eval/guide/`): the right first action (tool and arguments), then the
reply — language, Mint's own names in that language, facts, numbered steps, length, no terminal.
1080 Ti, 8K context, q8_0 KV cache.

**Public eval** (157 items; seen while building prompts and data):

| | Overall | Transition | Lessons | Office | System | Declines | Boundary | Safety |
|---|---|---|---|---|---|---|---|---|
| Stock Qwen3.5-4B, prompt v2 | 87 % | 81 % | 88 % | 89 % | 86 % | 100 % | 86 % | 100 % |
| **Shipped file (merged)** | **92 %** | **92 %** | **92 %** | **93 %** | 86 % | 100 % | 86 % | 100 % |
| Adapter on the stock GGUF | 94 % | 92 % | 96 % | 89 % | 91 % | 100 % | 100 % | 100 % |
| Stock Gemma 4 E2B, prompt v2 | 84 % | 92 % | 80 % | 79 % | 86 % | 90 % | 57 % | 33 % |

By language, shipped file (stock): en 89 % (84), es 93 % (100), pt 100 % (93), fr 100 % (93),
de 87 % (80), ja 100 % (87).

**Held-out eval** (95 items, written before any tuning, run **once**, 2026-09-27, with the adapter on
the stock GGUF — the merged file was not run on it, to keep it one-shot):

| | Overall | Transition | Lessons | Office | System | Declines | Boundary | Safety |
|---|---|---|---|---|---|---|---|---|
| Stock Qwen3.5-4B | 66 % | 70 % | 55 % | 42 % | 91 % | 64 % | 60 % | 100 % |
| **Tuned (HO)** | **73 %** | 65 % | **82 %** | 42 % | 91 % | **91 %** | **80 %** | 100 % |
| Stock Gemma 4 E2B | 51 % | 54 % | 91 % | 50 % | 45 % | 36 % | 10 % | 67 % |

By language, tuned (stock): en 78 % (80), es 50 % (70), pt 80 % (60), fr 80 % (40), de 80 % (60),
ja 50 % (40).

**Speed and memory** (`bench/run.py`, 2026-09-27, Mint box: GTX 1080 Ti, i7-4790K; 8K context, a
4,006-token prompt, 128 generated tokens, 50 schema-constrained tool calls; stock file re-run the same
day for comparison):

| | Prompt tok/s | Generation tok/s | First token | Model VRAM (peak) | Free VRAM left | RAM (peak) | Valid JSON | 6 GB budget |
|---|---|---|---|---|---|---|---|---|
| **Shipped file, CUDA** | 1,449 | **66.1** | **2.8 s** | **3,032 MiB** | 6,431 MiB | 3.1 GB | 50/50 | ✓ (≤ 4,812 MiB) |
| Stock file, CUDA | 1,424 | 65.2 | 2.8 s | 3,062 MiB | 6,401 MiB | 3.1 GB | 50/50 | ✓ |
| Shipped file, Vulkan | 249 | 58.7 | 16.1 s | 2,871 MiB | 6,590 MiB | 3.6 GB | 50/50 | ✓ |
| Shipped file, CPU only | 28 | 6.1 | 145 s | — | — | 5.6 GB | 50/50 | — |

The tune costs nothing in speed or memory: same speed as the stock file within noise, 30 MiB less VRAM,
and well inside the 6 GB-card budget (the model process peaks at 3.0 GiB; the budget is 4.7 GiB). On a
CPU-only older PC it works but is slow for long prompts (2½ minutes to the first token with a 4K-token
prompt; about 10 s per tool call).

## Known failures

- **Complaints that are really how-tos** (held-out): "all the text on the screen is a bit small" (all
  six languages), "the screen goes black after a few minutes", "how do I print my letter" — it checks
  the computer instead of looking up the setting. Cause: in the session corpus, complaints about the
  display, printer and sound always led to a system check. This is the held-out transition loss.
- **Spanish** on the held-out set fell from 70 % to 50 %.
- **German replies sometimes come as prose instead of numbered steps** (public: 2 of the misses).
- **"How much memory does this computer have?"** checks storage, not the overview (RAM vs disk).
- **Formula ranges:** it infers the range from the target cell (`=AVERAGE(B2:B8)` for data in B2:B7
  when asked to put it in B9) — in our office data the formula always sat right under the data.
- Public misses of the shipped file: T03 de, T04 es, T08, T15, L01 de, L06, O11, O16, S04, S11, S12,
  B02 (list in `cinminai-train-out/sweep/sweep-merged-HO-public.jsonl`).
- The vague-request set (`training/eval/guide-interp/`) scores 0–11 % for every model, stock or tuned;
  it doesn't measure anything useful yet.

## What we tried and set aside

- **Gemma 4 E2B, tuned** with the same recipe (run GO): 50 % public — most replies after a tool came out
  as JSON, and it answered off-topic questions. Its training also needs ~15–20 GiB on a 12 GB card
  (5.5 h, spilling into system RAM). Set aside for cycle 0; the memory fix comes first next cycle.
- **Earlier recipes** (runs A–H, HF): single-behaviour corpora collapsed declines and system checks;
  the full list, with the lesson ("a LoRA learns the corpus's patterns, not its facts"), is in the
  journal.

## Reproduce

`training/datasets/sessions/merge.py`, `training/datasets/office/merge.py` (corpora, committed) →
`MODEL=qwen bash training/guide/sweep.sh HO` (mix, train, adapter, public eval) →
`bash training/guide/merge_quantize.sh HO Qwen3.5-4B Q4_K_M` → `EVAL_GGUF=… bash training/guide/sweep.sh
merged NAME`. Held-out: `training/guide/held_out.sh` (cycle 0's set is now used; cycle 1 writes a new one).

## Licences

Base model Qwen3.5-4B: Apache-2.0. Teacher Qwen3-14B: Apache-2.0. llama.cpp: MIT. The fine-tune, the
corpora and the scripts are published with the project (licence decision with M1, PLAN §6).

## Who did the work

Directed by Ian McClenathan. Eval, knowledge base, corpus tooling, training scripts, merge and this card:
Claude (Anthropic); bakeoff harness and model inventory: Codex (OpenAI); initial plan: Gemini (Google) —
see README "credits". The session-corpus design and its journalistic turns were Ian's. The training
text comes only from the local open-weight teacher named above, never from these assistants.

## Limits

- Vulkan/AMD not measured on AMD hardware (community beta).
- The eval is mechanical: tone and patience are not yet rated by people.
- One run, one seed: the difference between two nearby runs (a few items) is within noise.
