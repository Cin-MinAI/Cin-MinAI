# Datasheet — guide fine-tune corpus, model cycle 0 (2026-09-25/26)

What's in the data the Cin-MinAI guide is fine-tuned on, how it was made, and what's wrong with it.
Published so anyone can inspect it, rebuild it, or build their own guide from it (PLAN D26, D32, D34).

## Purpose

Two behaviours, nothing else (PLAN D32, D39):
1. **Transition** (`transition/corpus.jsonl`): Windows habits → Linux Mint, answered from the
   knowledge base with Mint's own names in the user's language, numbered mouse steps, no terminal.
2. **Interpretation** (`interpretation/corpus.jsonl`): vague requests answered by restating what was
   understood, offering 2–4 things the guide can do, naming out-of-scope parts honestly, and ending
   with a question the user answers — the user is the pilot.

Declining off-topic requests, scam help, office tools and system checks are *not* trained; they're
handled by the prompt (v2), the knowledge base, the tools, and checks in the daemon.

## Sources

- **Teacher:** Qwen3-14B Q4_K_M (Apache-2.0, official `Qwen/Qwen3-14B-GGUF`), run locally with
  llama.cpp `v0.5.0` (`7fe450e`) on a GTX 1080 Ti. **No proprietary model or API wrote any of it**; the
  AI assistants that built the project (Claude, Codex) wrote the tooling and checks, not the data.
- **Facts:** `training/kb/transition.py` (57 topics), every name from Linux Mint 22.3's own
  `.desktop` / Nemo action files (`training/eval/guide/labels.json`), every UI label checked in
  Cinnamon's settings modules, keybindings, and Nemo.
- **Questions:** written by the teacher for varied personas (older, worried, polite, hurried, vague,
  typo-prone, "my grandchild told me to ask", …) in English, Spanish, Brazilian Portuguese, French,
  German, and Japanese.
- **Format:** the guide's runtime format — system prompt (v2), user message, the tool call (JSON),
  the help card as tool result, the reply (transition); system prompt, user message, an `answer` call
  (interpretation). Loss is applied to the assistant turns only.

## How it was made

`transition/generate.py`, `interpretation/generate.py` (teacher calls, checks, retries),
`merge.py` (final checks on everything), `transition/resume.py` (resume after interruptions).
Runs: pilot (10 topics), full run (47 topics × 7 questions + 10 × 3), interpretation run (28
situations × 4) and two top-ups for thin languages.

**Every example passed, at merge time:**
- the question is valid: no junk the teacher produced when derailing (`fmt`, `%s,%s`, `errors`,
  `user1`, emoji spam), no persona descriptions, labels or teacher commentary (also Japanese notes),
  written in the requested language;
- the reply passes the eval's own checks with the current scorer (language, Mint's names in that
  language, required facts, numbered steps, length, no terminal commands) — or, for interpretation,
  2–5 numbered options, a closing question, and the out-of-scope part named when it was asked for;
- **no line of a non-English reply is in English**, and the reply doesn't just echo the question;
- **decontamination:** no question has 3-gram Jaccard ≥ 0.5 with any public or held-out eval task
  (transition max 0.43, interpretation max 0.25);
- no near-duplicate question (≥ 0.8) in the same language.

## Counts

| | en | es | pt | fr | de | ja | total |
|---|---|---|---|---|---|---|---|
| transition | 347 | 244 | 277 | 202 | 226 | 162 | 1,456 |
| interpretation | *(final after top-up 2 — see `interpretation/merge-stats.json`)* | | | | | | |

Per-topic and per-situation counts: `*/merge-stats.json`. Raw generator statistics (accepted,
rejected and why, by language): `transition/pilot-stats.json` and the run logs.

## What we found and fixed while building it (so others don't repeat it)

1. The teacher wrote questions in the wrong language (English instead of Spanish/Japanese) → question
   language check before any reply is generated.
2. Under the list format the teacher sometimes derailed into junk → validity check; question
   temperature 0.9 → 0.7.
3. It copied persona labels and descriptions into the questions (`user1] …`, `texte 1 – par une
   personne … ] :`) → cleaning, and dropping what can't be cleaned.
4. The eval's language detector counted English "do" and German "das" as Portuguese → fixed (logged
   in `training/eval/guide/README.md`, "Scorer changes").
5. **A quarter of the interpretation replies had an English sentence inside a non-English reply**
   ("It sounds like you want to…" opening a Portuguese answer) — found only by reading samples by
   hand → a line-by-line language check; the instruction repeated in the target language.
6. A reply check that required naming the out-of-scope part even when it wasn't asked for → the
   teacher now also reports whether it was asked for.

## Known gaps

- **One teacher, one run:** Qwen3-14B's own habits (phrasing, what it thinks is helpful) are in the
  data. A second teacher next cycle would reduce that.
- **Some option names inside help cards are still English** (e.g. "Left handed" in a Portuguese
  reply): they come from the card text, not from `labels.json`. Next cycle: translate card-internal
  labels from Cinnamon's own translations.
- **Japanese is the thinnest language** and the one the teacher handled worst; native-speaker review
  is on `docs/HELP-WANTED.md`.
- Mechanical checks can't judge tone, kindness, or whether an answer is the *best* one; a 5 % sample
  was read by the lead (two rounds, 20 examples); native speakers and more readers are welcome.
- Interpretation examples are single-turn: the user's choice and the follow-up are not in the data yet.

## Licence

The corpus is published under the project's licence (to be decided before M1, PLAN §6), together with
the scripts that make it. The teacher model's licence (Apache-2.0) permits using its outputs this way.
