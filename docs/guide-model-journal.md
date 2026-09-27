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
  examples, lr 5e-5, 1 epoch), stock Gemma re-evaluated first under the same scorer (84 %, unchanged).
- **The session corpus makes Gemma's memory problem much worse (measured, run GO).** The multi-turn
  sessions are longer than cycle 0's single examples, so each step needs more memory: the driver
  borrowed **15.1 GB of system RAM** as GPU overflow, and training slowed to **~205 s per step** (cycle 0:
  ~11 s) — about 5.4 h for 95 steps, with Windows down to 1.7 GB free. Qwen trains the same mix in 27 min
  inside the card's 12 GB. Ian's call: let it run on the established setup rather than change the
  training code mid-comparison. Possible fixes for next time, untested: keep the per-layer embeddings in
  system RAM; check whether the image/audio towers are loaded for text-only training.
- **Run GO result: 50 % (stock Gemma 84 %) — HO's recipe doesn't transfer (measured).** Training
  finished without a crash: 5 h 30 min, peak 20.5 GiB (on a 12 GB card). Two failures dominate:
  **64 of 111 replies after a tool result came out as a JSON tool call** instead of plain text (stock
  Gemma: 0) — so "no numbered steps" 41×; and **declines 3/20** — it *answers* off-topic questions
  through the `answer` tool (e.g. why World War II started). Office held at 89 %, system 82 %.
  Same data that took Qwen to 94 %. Likely reasons (not tested): most trained assistant messages in the
  mix are JSON calls, and Gemma's template marks the last turn no differently from earlier ones, so
  "assistant output = JSON" is the strongest pattern it can find; and `all-linear` trains 37.9 M
  parameters on Gemma vs 21.2 M on Qwen — a stronger push at the same learning rate. Another case of
  the lesson below: the same corpus is a different pattern to a different model.

## What training taught us (cycle 0, for future development)

**A LoRA learns the corpus's patterns, not its facts.** Whatever is most consistent across the examples
becomes a rule — including regularities nobody meant to put there. Same words in a different pattern
give a different model. Measured on Qwen3.5-4B this cycle:

| What changed | Result | What the model picked up |
|---|---|---|
| Same sessions, different *selection* of trained turns (G → H) | 72 % → 91 % | In G, prose replies after a lookup outnumbered numbered ones 41 to 28 → "after a lookup, write prose" |
| One template detail: `<think></think>` only before the last turn | 87 % → 16 % | It never saw a lookup call in the position where it must produce one |
| Single-behaviour corpora (sweep A–E) | declines 100 % → 0–10 % | "Every question is a lookup" |
| Train only the replies after a tool (F) | answered the lasagna recipe | "Always answer" |
| Our formulas always go right under the data | `=AVERAGE(B2:B8)` where B2:B7 was right | It infers the range from the target cell, not from the data |
| Add examples where the data is already shown (HF → HO) | office 82 % → 89 % | "When the data is in the context, answer from it" |

What we do because of it:

1. **Check the corpus's shape, not only its content.** Correct names and no invented menus aren't
   enough. Before training, count: how often each behaviour appears, in which position, and what always
   co-occurs with what (the reply format after each tool, the tool after each kind of request). The count
   that explained G took one short script — run it on every mix *before* training, not after a failed run.
2. **Every behaviour the model must keep has to be in the data, in proportion.** There is no narrow
   targeting: leave declines out and it stops declining.
3. **Vary what shouldn't matter.** If the target cell, the language, the position in the conversation or
   the phrasing is always the same, the model will treat it as part of the rule. Randomise it on purpose
   (next: formulas in a cell the user names, not always right under the data).
4. **Render training exactly as at run time**, template quirks included, and verify it token by token.
5. **Change one thing per run and read the failures** (Ian: "finish a run, study failures, decide the next
   step together"). Every fix above came from reading the failed items, not from the overall score.

## Open for the decision

- The held-out eval (95 items) runs **once**, on stock and tuned versions of both candidates together;
  it decides the model and whether the tune ships (D31 gate).
