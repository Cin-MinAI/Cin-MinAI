# Resume note — where things stand and how to pick up after an interruption

Written 2026-09-25 21:25 (Mint box clock) because storms may cut the power. Keep this file current
at every natural stopping point; it's for Ian, Claude, and Codex alike.

## State right now

- **Repository:** everything committed and pushed to GitHub (`main`). Nothing on the dev PC is at risk.
- **Running on the Mint box** (`~/cin-minai/repo-train/`): the overnight **transition corpus run**
  (guide fine-tune, phase 2 — `training/guide/README.md`).
  - `full_run.sh` → first `full-rest/` (47 topics × languages, 7 questions each), then
    `full-pilot-topics/` (the 10 pilot topics, 3 each). Done marker: `full.done`.
  - Progress at 21:22: 1,030 accepted in `full-rest/examples.jsonl`, 223 of 267 batches finished;
    `pilot/examples.jsonl` has 208 more (from the afternoon pilot).
  - Teacher: Qwen3-14B via our llama-server on port 18091, **36 GPU layers** (keeps ~1.9 GB free for
    the desktop). Controlled only by `./teacherctl.sh start|stop` (PID file). **Never `pkill -f` with a
    pattern over ssh — it matches the ssh command itself and kills the session.**
- **Nothing running on the dev PC.** Training environment ready in WSL: `~/cinminai-train/`
  (`.venv`, `base/gemma-4-E2B-it`, `base/Qwen3.5-4B`); `training/guide/train_lora.py` smoke-tested.
- Ian's `qwen14b.service` (port 8080) is untouched and not ours to start or stop.

## Update 23:22 — the transition run finished; the interpretation run is going

- Transition run finished at 22:44: 1,548 raw → **1,458 kept** after cleanup (junk questions,
  persona labels and the teacher's own commentary removed; decontamination: 0 hits).
- Now running (Mint box, `~/cin-minai/repo-train/`): **interpretation corpus** —
  `training/datasets/interpretation/generate.py --out interp --per 4 --workers 2 --seed 31`, log
  `interp.log`, ~50 % accepted, expected done ~02:30. Teacher runs the tuned profile
  (`TEACHER_TUNE=1 ./teacherctl.sh start`: 2 slots, pinned threads, `--poll 0`; ~1.5 GB GPU free).
- To resume after a cut: `TEACHER_TUNE=1 ./teacherctl.sh start`, then re-run the same command with
  `--out interp` (it appends; duplicates and finished themes get removed at merge — the script has no
  per-theme resume yet, so a restart repeats all themes; fine, the merge dedupes).

## What a power cut does

- Mint box: the generator and teacher stop. Examples are written one at a time, so at most the one in
  progress is lost; a half-written last line in `examples.jsonl` is dropped at merge. Neither
  restarts by itself after a reboot (on purpose).
- Dev PC / WSL: nothing in flight. Git history is safe on GitHub.

## How to resume (Mint box, as `mint`)

```bash
cd ~/cin-minai/repo-train
ls full.done 2>/dev/null && echo "run had finished — go to 'After the run'"
./teacherctl.sh start                      # wait for {"status":"ok"} and check ~1.9 GB GPU memory free
P=install,control_panel,notepad,windows_update,antivirus,wallpaper,keyboard_layout,screenshot,zip,lock_screen
REST=$(python3 -c "import sys; sys.path.insert(0,'training/kb'); import transition as t; p=set('$P'.split(',')); print(','.join(x['id'] for x in t.TOPICS if x['id'] not in p))")
# 1) unfinished batches of the main part (also retries batches that errored):
setsid -f python3 training/datasets/transition/resume.py --log full-rest.log --log full-rest-resume.log \
    --out full-rest --topics "$REST" --per 7 --seed 21 --run > resume-rest.out 2>&1 < /dev/null
# 2) when that's done, the pilot-topic part (if full-pilot-topics/stats.json doesn't exist yet):
#    python3 training/datasets/transition/resume.py --log full-pilot-topics.log --log full-pilot-topics-resume.log \
#        --out full-pilot-topics --topics "$P" --per 3 --seed 41 --run
```

Before resuming, copy the latest `generate.py` / `run_eval.py` from the repo to the Mint box
(they carry the junk-question filter and the fixed language detector, commit `d6f4c82`):
`training/datasets/transition/generate.py`, `training/eval/guide/run_eval.py`.

## After the run (next steps, in order)

1. Stop the teacher (`./teacherctl.sh stop`) unless the supplement follows right away.
2. **Supplement run** for short languages (French lowest: 89 vs 187 English at 19:54), with the new
   question filter.
3. **Merge**: all `examples.jsonl` (pilot, full-rest, full-pilot-topics, supplement) → drop invalid
   JSON lines, junk questions (`valid_question`), persona labels (`clean_question`), duplicates →
   `training/datasets/transition/` + datasheet (counts, languages, teacher, filters, decontamination,
   rejects by reason, a hand-read sample).
4. **Train** both candidates on the 4070 (WSL): `train_lora.py` → export GGUF → eval public +
   held-out → pick → `MODEL_CARD.md`.
5. Then **M1** (distro skeleton). New ideas go on the "later" list (PLAN D34: pick a lane).

## Where the reasoning lives

`docs/PLAN.md` (decisions D1–D38, milestones), `docs/SPEC.md`, `docs/benchmarks.md` (model cycle 0),
`training/guide/README.md` + `MODEL_CARD.md`, `docs/HELP-WANTED.md`, `docs/WHY.md` (draft),
`AGENTS.md` (Codex brief). Mint box read-only copy of the docs: `~/cin-minai/repo-docs/`.
