# Guide eval

Chooses the built-in guide model (PLAN D23, §3 "Guide model track"; SPEC §10.6) and later measures
its fine-tune. **82 tasks, 157 items**: every task in English, 15 of them also in Spanish, Portuguese
(Brazil), French, German and Japanese (PLAN D25), so each language is compared on the same tasks.

| Category | Tasks | What it checks |
|---|---|---|
| transition | 22 | Windows → Mint questions: looks it up, then answers with Mint's real names |
| lesson | 10 | beginner computer lessons: numbered mouse steps |
| office | 18 | LibreOffice toolkit with a shared document (same tools as `spikes/libreoffice`), incl. 3 checkbook tasks (SPEC §7.11) |
| system | 12 | read-only system checks, reply grounded in the result |
| decline | 10 | off-topic (history, maths, health, money, news, writing for people): decline, don't answer |
| boundary | 7 | sounds off-topic but is in scope (word count in an essay, DVDs, video calls, a scam email, "does this send my typing online?"): must help |
| safety | 3 | install via approval, deleting files, "the admin password" |

## How it scores

**Stage A** — one schema-constrained call (llama.cpp JSON schema): which tool, with which arguments,
against the task's `expect` list. Tools: `lookup_help`, `open_app`, `inspect_system`,
`request_install`, `answer`, `decline`, plus the LibreOffice tools when a document is shared.

**Stage B** — the fixed help card or system result is handed back and the model writes its reply
in plain text. The reply must be:
- **in the user's language** (Japanese by script; others by function words);
- **use Mint's own names in that language** — `labels.json`, extracted from Mint 22.3's `.desktop`
  and Nemo action files by `extract_labels.py` (e.g. French "Logithèque", not a made-up
  translation). Names Mint has no translation for on the test box (Printers, System Monitor, Disks,
  Disk Usage Analyzer) are used only in English tasks; brand names (Writer, Timeshift, …) are the
  same everywhere;
- **contain the facts** the task needs, **no terminal commands** (`sudo`, `apt install`, `rm -`,
  `chmod`), **numbered steps** where the task has several steps, and stay short (≤ 200 words,
  ≤ 500 characters in Japanese).

A task passes when stage A is right and stage B (if any) has no failures. Direct `answer`/`decline`
texts go through the stage B checks too. No LLM judge: every check is mechanical, so two runs on the
same model agree and a score change means the model changed.

## Run

```bash
python3 run_eval.py --dry-run                                   # validates tasks + labels
python3 run_eval.py --url http://127.0.0.1:8081 --model NAME     # any llama-server
python3 run_eval.py --config ~/.config/cinminai/config.toml       # [inference] url/api_key/model
python3 run_eval.py ... --only T01,L07 --lang ja -v               # subsets, show replies
```

Results: one JSON line per item in `bench-results/guide/` (git-ignored), summary by category and
language. Temperature 0, thinking off (`enable_thinking: false`). Stdlib only, Python ≥ 3.11.

## Reference: Qwen3-14B Q4_K_M (big model, Mint box, 2026-09-25)

Run on the first 75 tasks / 150 items; the 7 tasks added since (PLAN D28–D29: O16–O18, B06, B07,
T21, T22) were added afterwards and are scored from the bakeoff on.

**129/150 = 86 %** (stage A 142/150). By language: en 89 %, es 87 %, pt 87 %, de 87 %, fr 80 %,
**ja 67 %**. Typical misses, all the behaviour the guide's fine-tune must fix:

- answers **without looking up** and invents: "Ubuntu Software", `sudo apt install` for a beginner
  (T01 es/pt/fr), "Ctrl+Alt+Del opens the Task Manager" (L07 — on Mint it opens log-out), made-up USB
  steps (L03 fr/de), suggests an antivirus (T10);
- **replies in English to Japanese** questions (3 of 15) and skips numbered steps;
- **declines instead of helping** (A02 delete files, A03 admin password = your own login password);
- office: looks up help instead of reading the sheet (O04), writes half of a two-cell request (O06),
  "translates" by returning the same sentence (O11).

The small guide candidates are expected to score lower before fine-tuning; this run is the ceiling
to compare them with, and the misses above are the first fine-tune targets.
