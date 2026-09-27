# Guide model journal — Qwen3.5-4B vs Gemma 4 E2B

What it took to evaluate and tune each guide candidate (PLAN D23, D31, D32): the hurdles, what we did about
them, and what each cost. Written as we go (Ian's request, 2026-09-27) so the next cycle — and anyone
choosing a small model for a local assistant — can see the practical differences, not only the scores.
Scores are from our public guide eval (157 items, prompt v2, 1080 Ti) unless noted; details in
`docs/benchmarks.md` and `docs/RESUME.md`. "Measured" and "likely" are kept apart.

## The two candidates

| | Qwen3.5-4B | Gemma 4 E2B |
|---|---|---|
| Architecture (HF) | `Qwen3_5ForConditionalGeneration`: 32 layers, hidden 2560, full attention + **linear attention** layers | `Gemma4ForConditionalGeneration`: 35 layers, hidden 1536, full + sliding-window attention, **per-layer embeddings** (256 per layer) |
| Vocabulary | 248,320 | 262,144 |
| bf16 weights on disk | 8.8 GB | 9.6 GB |
| Run-time file we evaluate | `Qwen3.5-4B-Q4_K_M.gguf` (2.7 GB) | vendor's QAT `gemma-4-E2B_q4_0-it.gguf` (3.3 GB) |
| Run-time VRAM (1080 Ti, 8K ctx) | see `docs/benchmarks.md` | 1,720 MiB (CUDA) |
| Stock, prompt v1 → v2 | 74 % → **87 %** | 78 % → **84 %** |

## Hurdles common to both

- **Forgetting under tuning (2026-09-26).** Tuning on single-behaviour corpora made both models call
  `lookup_help` for everything: declines and system checks collapsed. Cycle 0's first full tune: Qwen
  16 % (plus the template bug below), Gemma 69 % — Gemma: transition 96 %, but declines 0/20 and system
  checks 4/22. Fix (Ian's design): the **session corpus** — mixed turn types in one conversation, so the
  model learns to choose — then a balanced mix (preset h) and an **office corpus**. Found on Qwen first.
- **The dev PC's memory.** Training in WSL leaves ~10 GB of file cache Windows can't reclaim; Claude
  Code's memory reaper then stopped its own background shells (twice) and a watcher (2026-09-27, 1.2 GB
  free). Fix: long jobs launched detached (`Start-Process`), and `wsl --shutdown` after every training
  step (`sweep.sh`, 2026-09-27) — WSL on this PC exists only for this. A `.wslconfig` cap was not needed.
- **Hyper-V VMs can't train.** Windows 10 Pro gives them no usable GPU; training stays in WSL (CUDA on
  the RTX 4070). The Mint box's 1080 Ti is for evaluation only (shared with Ian's other work; Pascal has
  no bf16).

## Qwen3.5-4B

- **Chat-template trap (measured, fixed 2026-09-26).** Qwen3.5's template puts an empty thinking block
  in front of the *last* assistant turn only. Our first tune trained the lookup call only as an earlier
  turn, so the model never saw a call where it has to produce one: **16 %** ("It sounds like… 1. 2. 3."
  for everything). Fix in `train_lora.py`: every assistant turn is trained in last-turn position, rendered
  exactly as at run time (verified token by token).
- **Linear-attention layers can't carry a converted adapter.** llama.cpp's `convert_lora_to_gguf.py`
  can't convert LoRA weights on Qwen3.5's linear-attention projections (head reordering), so we train
  only the standard projections `q,k,v,o,gate,up,down` (21.2 M trainable parameters).
- **Slow kernels in training.** transformers falls back to its reference PyTorch implementation of
  `causal_conv1d` and `chunk_gated_delta_rule` (the optimised `flash-linear-attention` isn't installed).
  Correct but slower; not measured how much. Not fixed (D33: only if it's worth it).
- **Memory: fits.** 7.2 GiB peak on the 12 GB RTX 4070 (cycle 0 full tune); 10.4–10.6 GiB for the
  session runs (longer conversations).
- **Where it stands (2026-09-27).** Micro-sweep A–F 68–75 %; G 72 % (collapse fixed, numbered steps
  lost — prose replies outweighed numbered ones after a lookup); H 91 %; full run HF 92 %; **HO 94 %**
  (HF + office corpus: office back to stock). Weak spot: German numbered steps (80 %, = stock).

## Gemma 4 E2B

- **Memory: doesn't fit the 12 GB card (measured).** Training peaks at **15.8 GiB** on the RTX 4070
  (cycle 0 full tune and smoke run alike), twice Qwen's. It ran anyway because the Windows driver spills
  GPU memory into system RAM — which is what starved Windows. Speed was not hurt much: cycle 0 took
  5,876 s for Gemma vs 6,207 s for Qwen on the same 4,294 sequences.
  **Likely cause (computed from the config, not measured):** the per-layer embedding tables —
  35 layers × 256 × 262,144 ≈ 2.35 billion values, ~4.7 GB in bf16 — which 4-bit (QLoRA) loading
  doesn't compress (it quantizes linear layers only); the main embedding adds ~0.8 GB. Qwen has no
  per-layer embeddings. What we did: nothing to the model; the dev-PC memory fixes above. Possible
  later, if needed: keep the per-layer embeddings off the GPU during training.
- **No template trap (checked 2026-09-27).** Gemma's template renders an assistant turn identically
  as an earlier or the last turn (`<|turn>model\nA1<turn|>` both ways; Qwen: `<think>\n\n</think>\n\n`
  added only in last position). So the first tune didn't collapse the way Qwen's did (69 % vs 16 %);
  it had only the forgetting problem.
- **Adapter conversion works on all linear layers** (`all-linear`, 37.9 M trainable parameters) —
  including the multimodal wrapper (`Gemma4ForConditionalGeneration`), which converts as text-only.
- **QAT base.** We evaluate on Google's quantization-aware Q4_0 file with our adapter applied on top;
  the adapter was trained on the bf16 weights, and a merged fine-tune doesn't keep the QAT benefit. At
  ship time, compare our own Q4_0 and Q4_K_M of the merged model against the QAT file (training README,
  phase 4).
- **2026-09-27:** run GO started — HO's recipe on Gemma (sessions preset h, 360 turns + 115 office
  examples, lr 5e-5, 1 epoch), stock Gemma re-evaluated first under the same scorer.

## Open for the decision

- The held-out eval (95 items) runs **once**, on stock and tuned versions of both candidates together;
  it decides the model and whether the tune ships (D31 gate).
