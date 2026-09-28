# Benchmarks — model cycle 0 (M0, 2026-09-25)

The public record of each model cycle (PLAN D31, SPEC §10.7): every candidate, every result,
failures included. Cycle 0 is the M0 bakeoff. **Status: guide track measured on the 1080 Ti; big
track and the RTX 4070 still to run.**

Setup: Mint box (i7-4790K, 32 GB DDR3, GTX 1080 Ti 11 GB, driver 580, Mint 22.3, 4K desktop).
llama.cpp `v0.5.0` (`7fe450e`), three separate builds: CUDA (sm_61, CUDA 12.0), Vulkan, CPU (all
`GGML_NATIVE=OFF`). Server settings for every run: 8K context, q8_0 K/V cache, flash attention on,
one slot, reasoning off, temperature 0. Harness `bench/run.py` (Codex) for speed/memory/JSON,
`training/eval/guide/run_eval.py` for quality. Candidate files, revisions and SHA-256 are pinned in
`bench/candidates.toml` (all 12 downloaded files verified).

## Guide track (PLAN D23–D25)

### Quality — guide eval, 157 items (82 tasks; 15 in all six languages)

Percent of items passed. Stage A = right first action; B = reply checks (language, Mint's own
names, facts, steps, length, no terminal commands). See `training/eval/guide/README.md`.

| Model (quant) | **All** | Win→Mint | Lessons | Office | System | Declines | Boundary | Safety | en | es | pt | fr | de | ja |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| *Qwen3-14B (Q4_K_M) — big-model reference* | *83* | *81* | *76* | *79* | *95* | *100* | *86* | *33* | *85* | *87* | *87* | *80* | *87* | *67* |
| **Gemma 4 E2B (QAT Q4_0)** | **78** | **92** | 72 | 68 | 77 | 65 | 71 | 67 | 72 | 87 | 80 | 87 | 80 | **87** |
| **Qwen3.5-4B (Q4_K_M)** | **74** | 63 | 56 | 79 | 86 | 100 | 86 | 67 | 76 | 60 | 73 | 67 | 73 | 87 |
| Gemma 4 E4B (QAT Q4_0) | 68 | 60 | 56 | 75 | 82 | 100 | 14 | 67 | 68 | 73 | 67 | 67 | 60 | 73 |
| Qwen3.5-2B (Q4_K_M) | 59 | 54 | 76 | 64 | 68 | 30 | 57 | 67 | 61 | 60 | 60 | 60 | 47 | 53 |
| Qwen2.5-1.5B (Q4_K_M) — old baseline | 39 | 56 | 28 | 25 | 68 | 0 | 29 | 67 | 34 | 47 | 40 | 47 | 47 | 47 |
| Granite 4.2 3B (Q4_K_M) | 38 | 54 | 36 | 14 | 50 | 0 | 86 | 33 | 59 | 27 | 7 | 33 | 7 | 0 |

What the failures are (read by hand, not only counted):

- **Gemma 4 E2B**: mostly style — skips numbered steps (9), sends off-topic questions to the help
  lookup instead of declining (7; with the real knowledge base that lookup finds nothing), reads the
  sheet again before acting. **Serious for the careful newcomer (D28): it declined the scam-email and
  "does this send my typing online?" questions**, and one checkbook entry targeted row 2 instead of
  the next empty row (the preview would catch it; `append_rows`, SPEC §7.11, removes the risk).
- **Qwen3.5-4B**: best tool discipline (146/157 first actions right), perfect declines; misses Mint's
  names and numbered steps in replies (35 stage-B misses).
- **Gemma 4 E4B**: **over-declines** in-scope questions (6 of 7 boundary items, e.g. word count in an
  essay, "what is Linux?") — worse for our users than a wrong answer.
- **Granite 4.2 3B**: answers in English to non-English questions (38 items) — out for D25.
- **Qwen3-14B** (reference): answers from Windows habits without looking up ("Ctrl+Alt+Del opens Task
  Manager"; `sudo apt install` for a beginner), English replies to Japanese (3/15), declines instead
  of helping on A02/A03. Even the big model needs the knowledge base and the behaviour fine-tune.

### Speed and memory (8K context; 4,006-token prompt; 50 schema-constrained tool calls)

| Model | Backend | Read prompt (tok/s) | Write (tok/s) | Time to first token | Peak model memory | Tool-call JSON | 6 GB budget (≤ 4.7 GiB) |
|---|---|---|---|---|---|---|---|
| Gemma 4 E2B | CUDA (1080 Ti) | 1,874 | 77.3 | 2.2 s | 1,720 MiB VRAM | 50/50 | ✓ |
| Gemma 4 E2B | Vulkan (1080 Ti) | 255 | 36.1 | 15.7 s | 1,568 MiB VRAM | 50/50 | ✓ |
| Gemma 4 E2B | CPU (i7-4790K, 4 threads) | 34 | 9.2 | 117 s | 4.5 GiB RAM | 50/50 | — |
| Qwen3.5-4B | CUDA | 1,187 | 57.2 | 3.4 s | 3,062 MiB VRAM | 50/50 | ✓ |
| Qwen3.5-4B | Vulkan | 208 | 51.1 | 19.2 s | 2,901 MiB VRAM | 50/50 | ✓ |
| Qwen3.5-4B | CPU | 19 | 5.2 | 206 s | 5.0 GiB RAM | 50/50 | — |
| Qwen3.5-2B | CUDA | 2,929 | 109.1 | 1.4 s | 1,504 MiB VRAM | 50/50 | ✓ |
| Qwen3.5-2B | CPU | 46 | 12.0 | 86 s | 2.4 GiB RAM | 50/50 | — |

Notes:
- **Vulkan on Pascal is not an AMD measurement.** NVIDIA's Vulkan path on a 1080 Ti reads prompts
  ~7× slower than CUDA; AMD cards run Vulkan natively and may do much better. **Vulkan/AMD is a
  community beta:** we have no AMD card and won't run a second machine or swap drivers. AMD owners:
  run `bench/run.py --build vulkan` and `training/eval/guide/run_eval.py` and send the results.
- **CPU (live USB, D27):** writing speed is readable for E2B (9 tok/s) but reading a 4K prompt takes
  ~2 minutes, so the CPU path keeps prompts to ~1K tokens. Gemma 4 E2B needs ~4.5 GiB RAM there —
  fine on 8 GB, not on 4 GB (minimum requirements, D24).
- The first 2B CPU run overlapped a Qwen3-14B eval on the same box; CPU numbers will be re-run before
  the cycle closes.
- **Packaged build vs. the bench build, CPU (2026-09-28, D33 A/B):** `cinminai-llama` (one build, a CPU
  module per instruction-set level picked at start, D48) against the M0 build (`GGML_NATIVE=OFF`), shipped
  guide, i7-4790K, 4 threads, same flags: prompt 27.2 vs 27.5 tok/s, generation 6.05 vs 6.07 tok/s,
  first token 147 vs 146 s, identical generated text. **No speed change on Haswell** (the old build already
  used AVX2); the modules are for portability: the same package runs on CPUs without AVX2 and uses
  AVX-512 where present. Also 2026-09-28: the public guide eval with the product's own `lookup_help`
  instead of each task's card: 92 % (145/157), the same items as with task cards.

### Phase 1 — prompt v2 (public eval only, 2026-09-25)

Prompt v2 (`run_eval.py --prompt v2`, text in `SYSTEM_V2`/`STYLE_V2`): general rules aimed at the
cycle-0 failures — scams, privacy and passwords are in scope; decline off-topic directly without a
lookup; "if unsure, it's about the computer: help"; reply in the user's language even when the card
is English; numbered steps; names exactly as given. Plus one integration fix: the document context
carries `next_empty_row`. No eval task is quoted in the prompt. v1 stays as the recorded baseline.

| Model | v1 | **v2** | Win→Mint | Lessons | Office | System | Declines | Boundary | Safety | ja |
|---|---|---|---|---|---|---|---|---|---|---|
| Qwen3.5-4B | 74 | **87** | 81 | 88 | 89 | 86 | 100 | 86 | 100 | 87 |
| Gemma 4 E2B | 78 | **84** | 92 | 80 | 79 | 86 | 90 | 57 | 33 | 80 |
| *Qwen3-14B (reference)* | *83* | *82* | *79* | *60* | *89* | *86* | *100* | *100* | *33* | *80* |

(Public eval, 157 items; v1 scores use the full 157-item set.)

What's left:
- **Qwen3.5-4B**: misses are mostly in the Windows→Mint area — it opens an app instead of explaining
  (7, once the wrong app), and misses Mint's names in two replies; one arithmetic slip ($65.50 for
  $64.85: sums should be spreadsheet formulas, not model arithmetic); one malformed JSON call.
- **Gemma 4 E2B**: still **declines the scam-email and privacy questions** despite the rule, runs a
  system check for how-to questions (6), and skips numbered steps in Japanese — problems a transition
  fine-tune doesn't target.
- The prompt helps small models much more than the 14B (whose lessons got worse, 76 → 60).

### Guide recommendation after phase 0 (stock prompt)

Take **Gemma 4 E2B** and **Qwen3.5-4B** into the fine-tune (PLAN §3 step 4) and choose after both are
re-run through the same eval. E2B is the favourite: within 5 points of the 14B at a fifth of the
memory, strongest on Windows→Mint and Japanese, fastest on the CPU; its misses are the behaviour the
fine-tune targets. Qwen3.5-4B is the fallback with the best tool discipline.

Fine-tune targets from this cycle: numbered steps, declining off-topic without a lookup, **helping
with scams and privacy questions** (never declining them), using the knowledge base's names, the
next empty row, replying in the user's language.

**After phase 1:** Qwen3.5-4B leads (87 %) and its remaining misses are exactly the transition work the
fine-tune (D32) is for; Gemma 4 E2B (84 %) keeps the edge in size and CPU speed but its remaining
misses (declining scam/privacy questions) are not transition problems. Both still go into the
fine-tune; the pick follows the held-out eval.

## Big track

To run: Qwen3-14B vs Qwen3.5-9B (Q4_K_M/Q5_K_M/Q6_K), Qwen3.5-4B Q8_0, Qwen2.5-Coder-7B on the 1080 Ti
(files ready) and the RTX 4070 (dev PC, WSL build with the same tag); Qwen3.6-35B-A3B on the dev PC
only (over the Mint box's 60 GB cap). Measures per PLAN §3 "Bakeoff matrix", including free VRAM with
a realistic desktop open (SPEC §4.2 reserve).
