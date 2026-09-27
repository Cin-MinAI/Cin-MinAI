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

Declining off-topic requests, scam help, office tools and system checks are *not* trained **in these
two corpora**; they're handled by the prompt (v2), the knowledge base, the tools, and checks in the daemon.

**Update 2026-09-27: the shipped guide is trained on two later corpora, not these** (sections
"Session corpus" and "Office corpus" below). Tuning on these two alone made the guide forget what they
don't contain — declines fell from 100 % to 0–10 % and system checks collapsed into `lookup_help`
(micro-sweep A–E, `docs/guide-model-journal.md`). A LoRA learns whatever pattern its data has, so the
later corpora carry every behaviour the guide must keep, in proportion. The two corpora above stay
published: their questions and checks fed the session generator.

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

## Session corpus (`sessions/`, 2026-09-26) — what the shipped guide learned from

**Purpose.** One coherent, unique conversation per example, mixing the kinds of message a real user
sends, so the guide learns to *choose* — look up, check the computer, walk through, offer options,
decline, or just chat — instead of learning one pattern per corpus (Ian's design). Two turn types are
"journalistic" (Ian's second idea), to stop the teacher inventing complete solutions: a **report**
says only what a system check shows, then asks what to do next; a **walkthrough** gives one step from
the help card, then asks "what do you see now?" — sometimes without reaching the end.

**How it was made.** `sessions/generate.py --mix journal` (two runs, seeds jc and jd, 400 sessions
attempted, 6.3 h each on the 1080 Ti, same teacher as above). We plan every turn's *type*; the teacher
only writes the words. One persona and one life thread per session ("keeps the household budget",
"is worried about scams after a friend got tricked", …); the user's next message is written in context
of the conversation so far; sometimes the same need comes back once clearly and once vaguely. Each
assistant turn uses the forced right action and must pass its type's checks, or gets one retry; if it
fails twice, a sturdier fallback turn (report or decline) replaces it. System-check results are
synthetic (disk sizes, printer states, battery health…), so no real machine's data is in the corpus.
Generation-only instructions (e.g. "use only what the card says") are never stored; the stored system
prompt is the runtime one (prompt v2).

**Checks, at generation and again at merge** (`sessions/merge.py`, per turn, with the current scorer):
- every quoted UI name must appear in the help card, the tool result, Mint's own labels, or the user's
  words (**grounding** — how invented buttons like "Add Device" showed up); Menu at the bottom-left; no
  terminal; no Windows-only names ("Settings app", "Control Panel", "C: drive");
- reports: the result's facts, no instructions, end with a question; walkthroughs: one step, end with a
  question, no step repeated from the previous turn; vague turns: at least two numbered *offers* ("I can
  …"), not instructions; small talk short;
- **declines must refuse** (a per-language pattern: "can't", "no puedo", "できません", …) — 35 sessions
  were cut here: medical, voting or stock advice passed off as a decline, "Yes, *The Crown* is based on
  real people…";
- the reply is in the user's language: no English line inside a non-English reply; **56 English closing
  questions** ("…クリックしてください。What do you see now?") were repaired to the native phrase — the cause
  was the English example in our own walkthrough instruction, fixed for future runs; any other English
  question is rejected;
- no user message within 0.5 (3-gram Jaccard) of any public, held-out or vague-set eval item;
  near-duplicate sessions (same opening, same language) dropped.
A session is cut before its first bad turn and kept if at least 2 good turns remain.

**Counts.** 319 generated → **292 kept** (21 cut short, 27 dropped), 2,729 assistant messages.
Sessions per language: en 59, de 55, es 49, fr 48, pt 42, ja 39. Turn types: report 393 (29 %),
decline 303 (22 %), walkthrough 250 (18 %), clear 145 (11 %), safety 116 (9 %), system 71 (5 %),
vague 49 (4 %), chat 29 (2 %).

**The skew, and how training handles it.** The planned mix was 15 % vague, but the teacher failed the
vague turn more than any other (229 failed vague turns across the two runs, against 74 for clear
turns, the next worst: its replies gave instructions instead of offers), and each failure became a report or decline fallback. Training
therefore doesn't use the corpus as it is: `training/guide/make_session_mix.py` picks turns to planned
shares (shipped guide, preset h: clear 30 %, walkthrough 12 %, report 12 %, vague 12 %, decline 10 %,
safety/system/chat 8 % each; walkthroughs train only their follow-up steps), marks the rest
`"train": false` as context, and prefers reports that name the program to open.

## Office corpus (`office/`, 2026-09-27)

**Purpose.** The guide with a LibreOffice document shared, one request each. Added because the
session-tuned guide, with a spreadsheet already in its context, called `read_range` or
`inspect_system` instead of answering from it: sessions never share a document.

**How it was made.** `office/generate.py` (one run, 280 attempted, 1.5 h, same teacher). The teacher
invents each document in the user's language — a spreadsheet (a name column and a number column with a
realistic range), a letter or note (title, headings, a sentence, and the same sentence with mistakes),
or a slide show — on everyday themes chosen to stay clear of the eval's documents. The context is built
in the product's sidebar format (Calc sheets named as LibreOffice names them per language: Tabelle1,
Hoja1, Planilha1, Feuille1, Sheet1). **We decide the right action and compute every argument**: which
cell and range, which formula (`=SUM`/`=AVERAGE` under the column), the next empty row, which paragraphs
under a heading, which slide. The teacher writes only the user's message and free text (an answer, a
corrected or rewritten sentence). 15 % of requests with a document open are about the computer
(`lookup_help`) or off-topic (`decline`), so a shared document doesn't turn every message into an office
call.

**Checks.** The message must contain the literal values the action needs (the new row's name and number,
the heading, the slide number); answers must contain the computed fact (the total, the largest, the
count, a line from the slide); a corrected sentence must stay close to the original; declines must
refuse; language; the call is valid against the eval's own tool schema; decontamination as above
(max 0.30).

**Counts.** 280 attempted → **252 kept** (9 documents failed the teacher's language or shape checks,
9 user messages lacked a required value, 10 teacher answers failed their check). Languages: en 97,
es 35, fr 34, pt 30, de 29, ja 27. Documents: Calc 117, Writer 81, Impress 54. Actions: answer 80,
lookup_help 27, replace_selection 25, set_formula 23, get_paragraphs 23, set_slide_text 19,
decline 18, write_range 17, read_range 12, slide_text 8. The shipped guide used 115 of them (~15 % of
its training sequences).

**Known gaps (both corpora).**
- **Complaints paired only with system checks:** in the sessions, "why is there no sound", "the display"
  and "the printer" always lead to `inspect_system`, and nothing pairs a complaint whose answer is a
  setting with a how-to lookup. The shipped guide learned it: "all the text on the screen is a bit
  small" makes it check the display (held-out transition loss, `MODEL_CARD.md`). Next cycle: add
  complaint-style how-tos → `lookup_help`, in proportion.
- **Formulas always right under the data** → the guide infers a range from the target cell. Next cycle:
  formulas in a cell the user names.
- **Office totals and counts are thin** (ask_total 2, ask_count 2 in Calc): the teacher's arithmetic
  failed the check more than other intents.
- **Vague turns are few (49)** — the teacher's weakest turn type; the interpretation corpus above is the
  place to draw more from.
- **Session reports only describe**: they rarely say what the result means or offer the matching
  action (only about one report in five names the program to open). Next cycle: "what it means +
  offer the action", with a check that the program is named.
- Card-internal UI labels still English in some non-English replies (as above); one teacher, one run.

## Licence

The corpus is published under the project's licence (to be decided before M1, PLAN §6), together with
the scripts that make it. The teacher model's licence (Apache-2.0) permits using its outputs this way.
