# Resume note — where things stand, how we got here, what's next

Updated 2026-09-26 ~20:45, before an IDE/Claude restart. For Ian, Claude, and Codex alike. Read this
first; the reasoning behind every decision is in `docs/PLAN.md` (D1–D42) and `docs/SPEC.md`.

## Update 2026-09-26 ~21:30 — step 1 done, run G measured

- **Merge done** (`training/datasets/sessions/merge.py`, commit `1c44495`): 319 → **292 sessions**. New checks:
  declines must refuse (35 cut: medical/voting/stock advice, "Yes, The Crown is based on…"); the exact
  "What do you see now?" in ja/fr/pt walkthroughs **repaired** to the native phrase (56×, Ian's choice B);
  repeated walkthrough steps cut (14). `WALK_GUIDE` fixed for future runs.
- **Mix** (`training/guide/make_session_mix.py`): 160 turns to the journal shares, others kept as context
  (`"train": false`, honoured by `train_lora.py`); reports that name the program to open picked first. 317 sequences.
- **Run G** (Qwen3.5-4B, lr 5e-5, 1 epoch): **72 %** (stock 87 %). **The collapse is fixed:** declines 100 %,
  system checks 91 % (stock 86 %), tool choice 141/157 (stock 142). **New loss: numbered steps** — 25 of the
  failures are "no numbered steps": correct content written as prose. Cause: walkthrough and report turns are
  trained "no numbered list" after the same lookup call, so the model learned prose after a lookup.
  Vague set 0/19 (as stock) — it doesn't discriminate yet.
- Reading of the sessions (for the next generation run): reports describe the problem but rarely say what it
  means or offer the fix (only 81/381 name the program to open) — make them "what it means + offer the action".

- **Run H** (preset h: clear 30 %, walkthroughs train follow-ups only; 290 sequences, lr 5e-5, 1 epoch):
  **91 % — first tune above stock (87 %).** Transition 92 % (stock 81), lessons 96 % (88), system 86 % (86),
  declines 95 % (100: D01 de → lookup), office 86 % (89), ja/fr 100 %, **de 73 %** (stock 80: 3 of its 4 misses
  are numbered steps). Per item vs stock: 14 fixed, 8 broken. Vague set still 0/19.
  Next (proposed): repeat H with another seed to see whether +4 points is real, then full run at this recipe
  → held-out eval (once) → D31 gate.

- **Full run HF** (H's recipe, 360 turns = 647 sequences, 1 epoch, lr 5e-5, 31 min on the 4070): **public 92 %**
  (stock 87, H 91). Transition 90 % (81), lessons 100 % (88), system 91 % (86), declines 100 %, boundary 100 % (86),
  safety 100 %, ja/fr/pt 100 %, de 80 % (= stock; misses are numbered steps). **Office 82 % (stock 89): −2 items**
  (O04, O17: the spreadsheet is already shown, stock answers from it, HF calls read_range / inspect_system
  again) — a D31 "loses nowhere else" problem on the public eval. Sessions never contain a shared document,
  so nothing in the data teaches "answer from what's shown". Held-out eval still unused (Ian decides when).
- **Decision (Ian, 2026-09-26 ~22:40):** HF is the **working baseline** for now ("ahead of stock in a way
  that's satisfactory"). Adapter: `C:\Users\Ian\cinminai-train-out\sweep\sweep-HF-lora.gguf` (Mint
  `~/cin-minai/adapters/`); recipe = `bash training/guide/sweep.sh HF`. Held-out eval still **unused**; the
  office gap (−2) and German numbered steps are known open points; stock + prompt v2 stays the shipping
  fallback until the D31 gate is run.

- **Office fix (2026-09-27):** office corpus (`training/datasets/office/`, 252 examples, teacher-invented
  documents in the sidebar context format, calls computed by us, 15 % guard turns). **Run HO** = HF recipe +
  115 office examples (762 sequences, 27 min): **public 94 %** — office 89 % (= stock; was 82 in HF),
  transition 92, lessons 96, system 91, declines 100, boundary 100, safety 100; ja/fr/pt 100, de 80.
  **Clears the D31 gate on the public eval.** Per item vs stock: 14 fixed, 4 broken (T01/T06 de numbered
  steps; O01 es formula range B2:B8 instead of B2:B7 — it infers the range from the target cell, since our
  formulas always go right under the data; S04 "how much memory" → storage). Watch: L05 "difference between
  a file and a folder" is DECLINED (stock failed it too, differently). Held-out eval: next, Ian decides.

- **Run GO (Gemma 4 E2B, HO recipe, 2026-09-27): 50 %** (stock Gemma 84 % re-scored). 64/111 replies after
  a tool result written as JSON calls; declines 3/20 (answers off-topic). 5.5 h training with a 15 GB RAM
  spill (Ian: let it run). Details in `docs/guide-model-journal.md`. Decision pending with Ian.

- **Held-out eval, run once (2026-09-27, Ian's pick of contenders):** stock Qwen 66 %, **tuned Qwen (HO) 73 %**,
  stock Gemma 51 %. Qwen3.5-4B is the model. HO fails the D31 gate's letter: held-out transition 24/37 vs
  stock 26/37 (complaint-style how-tos -> inspect_system). Ship decision (stock vs tuned) with Ian.

## State right now (before the update above)

- **Repository:** everything committed and pushed (`main`, last code commit `7e2c930`).
- **Nothing running** anywhere. The corpus teacher on the Mint box is stopped (GPU back to 1.7 GB).
  Ian's `qwen14b.service` (port 8080) is untouched and not ours to start or stop.
- **Mint box work area:** `~/cin-minai/repo-train/` (generator runs, raw corpora), `~/cin-minai/eval-guide/`
  (public eval + results), `~/cin-minai/eval-guide-interp/` (vague set), `~/cin-minai/adapters/` (LoRA GGUFs),
  `~/cin-minai/models/` (guide candidates), `~/cin-minai/llama.cpp/` (pinned `v0.5.0`, builds cuda/vulkan/cpu).
- **Dev PC:** WSL `~/cinminai-train/` (`.venv`, `base/gemma-4-E2B-it`, `base/Qwen3.5-4B`, `llama.cpp/` for
  `convert_lora_to_gguf.py`, `runs/`, `data/`); results and readable files in `C:\Users\Ian\cinminai-train-out\`
  (`sweep\` = micro runs, `sessions-read\` = readable session batches).
- **Teacher control:** `TEACHER_TUNE=1 ~/cin-minai/repo-train/teacherctl.sh start|stop` (PID file). **Never
  `pkill -f` with a pattern over ssh** — it matches the ssh command itself and kills the session.
- **Long jobs on the dev PC:** launch detached with PowerShell `Start-Process` (see below) — Claude Code's
  memory reaper kills its own background shells when Windows runs low on memory (it did, twice), but not
  detached processes. Windows had ~1.8 GB free overnight with training + WSL cache; with apps closed ~6 GB.
  A `.wslconfig` memory cap is still to discuss before training Gemma (it spills past 12 GB VRAM).

## What we did, and why (the guide fine-tune, cycle 0)

1. **Stock bakeoff** (`docs/benchmarks.md`): 7 guide candidates on the 157-item public eval. Leaders:
   Qwen3.5-4B and Gemma 4 E2B. **Prompt v2** lifted them to **87 %** and **84 %** (reference Qwen3-14B 82 %).
2. **Fine-tune goal (D32, D39):** make the Windows→Linux transition and "understanding vague requests"
   better, with a published corpus. Built: transition knowledge base (63 topics, every Mint name verified),
   **transition corpus** (1,456 examples) and **interpretation corpus** (691), both teacher-generated by local
   Qwen3-14B, mechanically checked, decontaminated against the evals, hand-read. Datasheet:
   `training/datasets/DATASHEET.md`. Many teacher failure modes found and fixed along the way (wrong-language
   questions, junk under list format, persona labels, English lines inside non-English replies, …).
3. **First full tune collapsed to 16 %** — it answered everything with "It sounds like… 1. 2. 3.". Cause: a
   format bug — Qwen3.5's template puts an empty thinking block before the *last* assistant turn only; the
   lookup call was only ever trained as an earlier turn. **Fixed:** every assistant turn is trained in
   last-turn position, rendered exactly as at run time (`train_lora.py`, verified token by token).
4. **Micro-sweep** (Ian: "find a baseline, squeeze don't push"; `training/guide/sweep.sh`, Qwen3.5-4B,
   300–800 sequences, 1 epoch): tuning **raised Windows→Mint 81 → 96 % and lessons 88 → 100 %**, but
   **declines (100 → 0–10 %) and system checks (86 → 0–41 %) collapsed** into `lookup_help`. Dose and
   learning rate didn't fix it. **Reply-only tuning** (run F) restored system checks (91 %) but the guide
   then *answered* off-topic questions (lasagna recipe, WWII). **Lesson: a LoRA generalises the attitude
   of its data; there's no narrow targeting. The data must contain every behaviour, in proportion.**
5. **Ian's redesign — session corpus:** one coherent, unique conversation per example, mixing turn types
   (clear lookup, vague → offers + question, decline, system check, safety, small talk), so the model
   learns to *choose*. Then Ian's second idea — **journalistic turns**: *report* (describe only what the
   tool shows, then ask) and *walkthrough* (one step at a time, "what do you see now?", sometimes
   unfinished) — to cut the teacher's invention, which happens when it writes complete solutions.
   `training/datasets/sessions/generate.py` (`--mix journal`). Checks added from hand-reading: grounding
   (quoted UI names must exist in the card/result/labels/user's words), Menu at bottom-left, no terminal,
   no Windows-only UI names, no copied messages, fallback turn instead of dropping a session.
6. **Result:** invented steps went from "nearly every session" (old mix) to a few; keep rate 34 % → **80 %**.
   **Big journal batch: 319 sessions** (~1,500 assistant turns), balanced across the six languages.
   Raw: Mint `~/cin-minai/repo-train/journal-jc/` + `journal-jd/`; copies:
   `C:\Users\Ian\cinminai-train-out\sessions-read\journal-big-319.jsonl` (+ readable `.txt`).

## Known issues in the 319 sessions (to fix at merge — not by regenerating)

- **Turn-type skew from the fallback:** reports 28 %, **declines 24 %**, walkthroughs 18 %, clear 10 %,
  safety 8 %, system 5 %, **vague 3 %**, chat 2 % (planned: 18/12/20/15/8/5/15/7). Training on this as-is
  risks an over-cautious guide that rarely clarifies.
- **A "decline" that answers** (The Crown: "Yes, it's based on real people…") — seen 1 in 6 sampled.
- **English inside Japanese walkthroughs:** "…してください。 What do you see now?" — from the English example
  in the walkthrough format instruction (`WALK_GUIDE` in the generator).
- Card-internal UI labels still English ("Extract Here", "Apply Changes", "Left handed") — KB gap for next cycle.

## Next steps — the plan (step by step; Ian decides each step)

1. **Merge the sessions** (write a `--kind sessions` path in `training/datasets/merge.py` or a small
   `sessions/merge.py`): per turn, drop/truncate at the first bad turn (keep sessions with ≥ 2 good turns):
   decline must contain a refusal ("can't/cannot", "no puedo", "não posso", "je ne peux", "kann … nicht",
   "できません"); the closing question of walkthrough/report turns must be in the user's language (reject
   "What do you see" in non-English replies); re-run the existing checks with the current scorer;
   decontaminate against all three evals. Also fix `WALK_GUIDE`'s English example for future runs.
2. **Build a balanced training mix** (`make_mix.py` extension): down-sample decline and report turns toward
   the planned shares; add vague turns from `training/datasets/interpretation/corpus.jsonl` (single-turn, 691)
   to reach ~15 %. Record the mix in the run's `run.json`.
3. **Micro run G** (sessions only, balanced): Qwen3.5-4B, lr 5e-5, 1 epoch, ~300–400 sequences, all turns in
   last-turn position, `--targets q,k,v,o,gate,up,down`. Evaluate with prompt v2 on the public eval + vague
   set on the 1080 Ti (same as the sweep): `bash training/guide/sweep.sh` pattern — add a run "G" there.
   **Success = declines and system checks at stock level (≈100 % / ≈86 %), Windows→Mint up, vague set up.**
4. **Micro run H** (only if G is promising): sessions + a small share of transition examples.
5. If one works: **full run** at that recipe, then held-out eval (used once) → pick → `MODEL_CARD.md`.
   Then the same recipe for Gemma 4 E2B (memory: discuss `.wslconfig` first).
6. Stock model + prompt v2 stays the fallback (D31 gate): the tuned guide ships only if it beats stock.

How to launch a long job detached from Claude Code (dev PC):
`Start-Process -FilePath "C:\Program Files\Git\bin\bash.exe" -ArgumentList '-lc "cd /c/Users/Ian/Cin-minAI && bash training/guide/sweep.sh G"' -WindowStyle Hidden`
(`sweep.sh` currently has a special case for `F`; add `G`/`H` the same way.)

## Decisions and ideas recorded this session (for context)

D26 vision + built in the open · D27 USB reduced, install recommended · D28 careful newcomer (offline mode,
checkbook, scam help) · D29 watchable updates + sights/sounds · D30 suggest, don't decide · D31 twice-yearly
public model cycle · D32 fine-tune = transition (+ D39 interpretation) with a published corpus · D33 measured
optimizations · D34 MVP = careful newcomer + everyday user; seed community AI · D35/M10 cloud backends + IDEs
(post-v0.1) · D36 HELP-WANTED · D37 target 8 GB, min 6 GB, older gaming laptops · D38 familiarity is a feature,
our own aesthetics · D40 one continuous Jarvis-like conversation, rundown offered on open · D41 public model
reviews (6-week nomination cutoff) · D42/M11 AI recovery mode (post-MVP). Ideas parked in PLAN §6: Pi 5 /
tinkerer version (domain packs, board-level repair, dump discipline), home cluster on old server GPUs,
training on old cards + ricer-style tuning, Microsoft open-source review list, vision (AT-SPI first).
Credits (README): Ian leads; Gemini (initial plan), Claude and Codex/ChatGPT build it, none preferred.
