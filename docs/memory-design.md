# Memory and personality — design draft (for discussion)

Drafted 2026-10-03 from Ian's answers and the evening's discussion (journal: "what the next OS might be, and where
Quaddle fits"). **A draft, not a decision**: once Ian has been through it, it becomes SPEC §22 and a PLAN entry.
Experiments behind the habits part: `spikes/habits/`.

## 1. What we want

Today every part of the assistant — the guide in the sidebar, the writer, the journal, office, web search, vision,
AICUI — works and **forgets**. What persists is what it made (projects, notes, goals, the changelog, the model
record), never what it learned about the person or what happened between them. The goal: **one assistant that knows
you and your work across all of it, and a personality that is yours and grows** — local, visible, and under your
control.

Ian's decisions so far:

1. **One shared memory** across every part; recall still prefers the place you're in.
2. **It remembers on its own, visibly, with undo** — and the notices can be **hidden and brought back** from the
   panel icon or the sidebar.
3. **The sealed journal never goes into memory.**
4. **Personality is chosen by the person** from a handful of starting personalities (people matching, like the
   hardware matcher), shaped by them, and it **evolves** — through habits.
5. **Buddy, Coach and Teacher may play** — entertain, push, coax — inside a frame the person chose; **the system
   never lies** (§6).

## 2. The shape: the Choice Atom

From Ian's research (Quaddle; the monograph and state-machine spec sit beside the project in `docs/kernel doc/`,
not in it). Every memory operation is one atom:

| | Memory |
|---|---|
| **Γ** — what's allowed | the memory policy (§5): what may be remembered, where, and what never |
| **d** — the choice | what to remember: proposed by the model, or a plain event (a goal ticked, a project made) |
| **T_d** — the deterministic realization | the store writes it: same input, same result, no model involved |
| **w** — the located result | the new memory, with its **address** |
| **R** — the append-only record | every write, change, forget and habit step, in order |

The model only ever *proposes*; the store *acts*, inside Γ, and keeps the record. Reversible operations (remember,
change, forget-with-undo) run on their own and show a notice; nothing irreversible happens without the person
(forgetting for good is the person's act).

## 3. What is stored

All under `~/.local/share/cinminai/memory/` (the user's own folder, mode 0700), owned by the daemon — one writer, so
it stays consistent. Nothing leaves the machine; a cloud model (D63) gets no memory unless the person says so.

**3.1 Addresses.** Everything has a path: area → project → session → moment, e.g.
`aicui / wedding-test / 2026-10-03 16:19 / step 12` or `writer / Missed the Moon / chapter 3`. Address and content
are kept apart: two memories with the same words in different places are different memories. Recall uses the
**shared prefix** — things from the same project are near each other however long ago they were (the idea that
kept Ian's PVP-nest model stable at long context).

**3.2 The record (episodes).** Append-only, one line per moment: when, address, kind (*said*, *did*, *chose*,
*result*), a short text, links. Each line carries the hash of the one before it, so the record can be checked as
whole and untampered. The AI never rewrites it. The person can delete from it (§7); a deletion leaves a marker
without the content, so the chain still checks.

**3.3 Facts.** What it believes about you and your work — preferences, facts, project knowledge — each with its
**sources** (the episodes it came from), its scope (everywhere, or one area/project), when it was made and last
confirmed. A fact is a **reversible fold**: it can always be unfolded to its sources, so it can be checked, and
corrected at the source. Never a summary that floats free of what it summarized.

**3.4 Habits.** Per address of a repeated choice (e.g. *open the scan in GIMP with the plugin*): the candidate
action and a **12-bit 3+1 register** — three levels of (three bits of switching + w), strict at the bottom,
forgiving above (`spikes/habits/`: real habits form in ~27 uses and hold steady; a coin toss forms a false one ~3 %
of the time; no thresholds stored). States: *forming → offered → accepted (automatic) | declined*. A habit is
**offered** before it's automatic ("you usually open it this way — do it like that from now on?"), pauses and asks
again after two different choices in a row, and **never applies to irreversible actions**.

**3.5 The personality profile.** The chosen starting personality, the person's tweaks (three sliders: *length*,
*humour*, *how much it explains*; or a described character for *Make your own*), what it may play (§6), and the
adjustments it has grown (accepted habits, facts about how you like to be talked to — each with sources).
Versioned: every change is in the record, and *reset to the starting personality* is always there.

## 4. How it works

**Remembering.** Two routes, both through the atom: *events* the system already knows (a goal ticked, a chapter
written, a model chosen) are written directly; the model can *propose* a memory through a structured tool
(`remember {text, scope, sources}`) when the person says something worth keeping ("I'm left-handed", "the pump is
a 2004 Audi A4"). Each new fact shows a small notice — **"I'll remember: … [Undo]"** — unless the person has hidden
the notices.

**Recalling.** Before the model answers, the memory picks what's relevant, in a fixed budget (a few hundred tokens,
more on bigger contexts): **same place first** (shared address prefix), then **meaning** (words in common to start;
a small local embedding model later, only if it measurably helps — D33), then **recency**, plus any habit for this
address. It goes in as a short, sourced block ("From your memory: … (from: writer, chapter 3, 1 Oct)") — the model
reasons, the memory supplies. A habit that has closed and was accepted runs without the model at all.

**Consolidating.** When the machine is idle and the graphics card free, older moments are folded into facts by the
local model, with their sources linked — like sleep. Moments are not deleted by consolidation; how long they are kept
is the person's setting (§8).

**Forgetting.** Any fact, any moment, a whole area or project, or everything — from the memory view, or by saying
"forget that". Undo for a while, then gone for good.

## 5. The policy (Γ) — what is never remembered

- The **sealed journal** (Ian).
- **Secrets**: passwords, keys, PINs, recovery codes, card numbers — filtered before anything is written.
- **Declined requests.** When the assistant declines something, nothing about it is kept: no record, no flag, no
  report. *It doesn't want to know* (Ian), and the memory never becomes surveillance.
- Areas or projects the person marks **"don't remember here"**.
- Anything the person says not to keep ("don't remember this").

## 6. Personality — the principles that never change

Personality is the person's: tone, voice, humour, how much it explains, even a character. Under every one of them,
the same short list:

1. **The system never lies.** What an action will do or did, whether the tests passed, warnings about your safety or
   your machine, what it remembers, what it sent anywhere — always true, in every voice. The system's own checks
   stay the source of truth whatever the voice says.
2. **Personalities may play, in the open.** *Buddy* may tell tall tales and exaggerate to entertain; *Coach* may push
   past the plain facts ("you're nearly there") to keep you going; *Teacher* may hold back the answer, play dumb,
   plant a mistake or ask "are you sure?" so you find it yourself. The description at selection says so plainly.
   **"Seriously?" always works**: ask for a straight answer and any personality drops the act. *Guide*, *Straight
   shooter* and *Professional* don't play.
3. **Your hardware, your software, your call.** It warns plainly, then helps; the safeguards are logical, not moral
   — a snapshot before risky changes, approval for anything irreversible, undo (D54).
4. **Serious harm to other people:** it declines plainly, without a lecture — and keeps no record of it (§5).

**The starting personalities** (people matching — chosen like the hardware matcher, by the person):

| | Personality | For | Plays? |
|---|---|---|---|
| 1 | **Guide** (default) | calm, plain words, newcomer-friendly | no |
| 2 | **Straight shooter** | short and technical, no padding | no |
| 3 | **Teacher** | the *why*, step by step; coaxes you to find it | yes — coaxes |
| 4 | **Buddy** | warm, casual, funny | yes — entertains |
| 5 | **Coach** | encouraging, celebrates progress | yes — pushes |
| 6 | **Professional** | formal, concise, documents what it did | no |
| 7 | **Make your own** | a described character or voice | as described, within §6 |

The chooser shows **the same answer in each voice**, so people pick by feel (D65). Each personality is tested
against the models like the writing bakeoff, so the matcher can say which model holds that voice best on this
machine (the tuned 4B guide was trained for one calm voice and may resist strong characters — to be measured).

## 7. What the person sees

- **In the sidebar, a Memory section:** *what I remember* (facts with their sources; edit, forget), recent notices,
  **show/hide memory notices**, **pause memory**, and the personality (chooser, sliders, reset).
- **On the panel icon's menu:** *Memory notices: shown / hidden* and *Pause memory*, so they're one click away
  without opening anything.
- **"What do you remember about me?"** works anywhere, in plain words, with sources.

## 8. Open for Ian

- **How long moments are kept** (forever, a year, a few months) once folded into facts.
- **How much the personality may grow on its own** beyond accepted habits — only from what you accept, or also from
  observed preferences (always visible, always resettable).
- The **names and descriptions** of the seven personalities, and whether *Make your own* ships with examples.
- Whether a **cloud senior** (D63) may ever see memory, and how that's offered.

## 9. Slices (once agreed)

1. **The store and the record**: addresses, the hash-chained record, facts with sources, "remember this", "what do
   you remember", forget; the sidebar's Memory section; D-Bus methods.
2. **Automatic remembering and recall** across the guide, the writer and AICUI, with notices and undo; the policy
   filters (secrets, declined requests, journal, don't-remember-here).
3. **Personalities**: the seven, the same-answer chooser, sliders, the play rules and "seriously?"; a bakeoff of
   voices against models.
4. **Habits**: the 3+1 registers, offered → accepted, the pause on two different choices, never for irreversible
   actions.
5. **Consolidation** while idle.
6. **An evaluation**: recall accuracy on scripted histories, false habits, "seriously?" compliance, and that nothing
   from §5 ever reaches the store.
