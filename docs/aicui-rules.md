# Every rule an AICUI model works under (2026-10-10)

Taken from the code (`aicui/agent.py`, `pair.py`, `tandem.py`, `intake.py`), for the regroup after test5. The plan
it measures against is Ian's: **the boundaries live in the tools** ("we build safeguards into every tool"; fetch
"will define boundaries… a broad range of tools… trained to know how to use them"), and the model is given tools it
knows how to use, not a procedure.

So each rule is one of two kinds:

- **In a tool:** the tool itself refuses, checks or keeps something, and says so in its result. The model learns the
  boundary by using the tool. This is the plan.
- **On the model:** text that tells the model how to work (the instructions), or a note the loop puts into its
  steps. These steer it, and they're where the conflicts are.

"Today" marks what was added on 2026-10-10.

## A. In the tools (the boundaries)

| # | Tool | The boundary | From |
|---|---|---|---|
| A1 | fetch, download, look | https only; stand-in picture sites refused | 2026-10-09 (a grey placeholder became the card art) |
| A2 | fetch, download | **an address only if it came from somewhere**: the person, a search result, or a kept page | 2026-10-09 (picture addresses made up from memory) |
| A3 | fetch, download, web_search | each asks the person first (or "always this session") | D86 |
| A4 | download | at most 300 files and 300 MB at once | 2026-10-09 |
| A5 | fetch, download, intake | everything that comes in is kept with its origin; what came in is protected by origin, not folder | today (slice 1) |
| A6 | intake | a different address never writes over another's file | today (test5: three card lists became one) |
| A7 | web_search | DuckDuckGo first; Bing's RSS when DuckDuckGo asks for a pause | ab0a0d7 |
| A8 | distill | sources must be files in the project; a picture address must stand in the source | today |
| A9 | edit, write… | gathered material can't be edited | 2026-10-09, by origin today |
| A10 | write, append | a write longer than one step goes to a draft; the file stays whole until the last part | 2026-10-03 |
| A11 | write | placeholder content ("<219 lines written>") refused | 2026-10-02 |
| A12 | edit | `old` must appear once; replace_lines in range | early |
| A13 | every change | after a write: compiles? defined twice? HTML closed? (the result says) | 2026-10-08 |
| A14 | every change to compiled data | checked against its gathered record, item by item | today |
| A15 | Junior's changes | not most of a file of 80+ lines (kept aside, "your senior's call") | today (test4's 1,088 → 77) |
| A16 | Junior's changes | only the files its task holds; the Senior can't write a held file | style B |
| A17 | run | sandboxed, no network, time limit, no admin | D1 |
| A18 | goal_done | the project's tests run and its entry point starts; data from a source needs a test that reads it | 2026-10-03, D96 |
| A19 | goal_done (style A) | the helper's flag: a second goal_done ticks | 2026-10-09 |
| A20 | goal_add | ~~an open goal added again is refused~~ removed (a band-aid on C1) | today |
| A21 | plan (team B's Senior) | a new project starts with its plan: before it, only looking around (read, list, search, look) and talking | today (test6) |
| A22 | plan | the person's request as goals, each with what it needs from outside, its files and who does it; the person sees it once and says OK or what to change; a goal for the junior names its files | today (test6) |
| A23 | edit, write… and goal_done | a goal's files aren't written, and it isn't ticked, until what it takes `from_outside` is in (named `needs` until test8, where the model listed the project's own work there and goals waited for themselves) (pages, files or records fetched or distilled for it, as many as it has needs) | today (test6: 300 lines of card data typed from memory) |
| A24 | team B | the junior's goals go to it once their needs are in, with their files held for it; it starts nothing itself | today |
| A26 | fetch, download, the file list | every kept file says what it holds and what it's for: page text (read and distill this), page markup (for a script), document, document text, picture, sound, data, search results | today (Ian: "classifiers for both of those files") |
| A27 | plan, the needs gate | each outside item has a kind (text, pictures, sound, file); each is met by one source of its kind; a page counts once, by its text | today (test8: one page's .txt and .html met "the card lists" and "the card images") |
| A28 | team B | after the Senior moves on 3 times while a task is still with the Junior, a word on how it's going (its steps, changes, moving or not); follow_up gives the Junior direction mid-task, or with the task if it hasn't started | today (Ian: "task follow up") |
| A29 | run | Ask: commands never reach the internet (the web through fetch, download, web_search); Auto: a command with `network` true asks the person once for the session; No permissions: no sandbox (the person's choice) | today (Ian, after test9's own downloader in No permissions) |
| A30 | brief (team B's Senior) | the junior reads the files named and answers the question between the senior's steps; a brief arriving is progress (a create) | today (test9: the senior read fifteen files itself at ~20 tokens a second, one of them five minutes) |
| A31 | lfd (team B's Senior) | Large File Distillation: the project's own files by size, the junior from the smallest, the senior from the largest, each file in a fresh context, appended to notes/project-summary.md by code, meeting in the middle; then the senior's context is dumped and it plans from the summary (the open goals give way, the ticked stay) | today (Ian) |
| A32 | every question | the progress line pauses while a question waits; what's said meanwhile goes above it and the question is shown again; it says who asks and for what | today (the senior's progress line wiped the junior's question; both waited) |
| A33 | team B | the junior's permission questions go to the person and to the senior (permit n, allow); the first answer decides, the terminal says who answered | today (Ian: "If jr asks both user and sr can click yes or no") |
| A34 | every request | a new project keeps its first request in original-request.txt (the person's words; the model can't change it) and every project has screenshots/ (the person's pictures, or the AI's; AICUI's Screenshots button opens it); the system text says both, with the newest picture, and the model can ask for a screenshot | 2026-10-12 (Ian kept both by hand for test10; Haiku finished from them) |
| A35 | look, read, answer | look at a `picture` in the project; read on a picture says look; an empty answer goes back to the model; the cloud model reads pictures itself | 2026-10-12 (Haiku on test10: blind, then a blank reply) |
| A36 | every request | the next request is told what the last one read, changed and thought; a new session starts from the checkpoint; a screenshot older than the last change is said to be old | 2026-10-12 (Haiku on test11 re-read main.py 17 times and trusted a stale screenshot) |
| A37 | cloud Lead | the cloud is the Senior; one or two local contributors take assign (write, fix, check, test), brief, distill and LFD; one numbering, Stop lists both | 2026-10-12 (Ian) |
| A38 | cloud Advisor | the local models work; the lead one asks the cloud (`advisor`, its question with the request, goals, last steps and checks); AICUI asks by itself after 12 steps without progress; 5 a request; advice is progress (a create) | 2026-10-13 (Ian) |
| A25 | every step | the same refused step twice in a row: stuck, said where it is (a junior's stuck point to its senior) | today (test7: one refused step fifteen times; tool calls are greedy, temperature 0, so an unchanged state repeats) |

## B. On the model

| # | Where | What it says or does | From |
|---|---|---|---|
| B1 | instructions | one step: short thinking, one action | early |
| B2 | instructions | **FETCH / DISTILL / COMPILE / TALK as "your work runs through three steps"** | today |
| B3 | instructions | "the rule of the three": facts from sources, never from memory; if none, say so and ask | today |
| B4 | instructions (Senior, style B) | **a numbered four-stage method**: skeleton, give the junior the reading, assign, review | today (was 3 sentences) |
| B5 | instructions | at the start of a new project, ask about goals and scope and write them as goals; team B's Senior: make the plan (its tool list names plan; goal_add adds one goal to it) | 2026-10-03; the Senior's 2026-10-10 (test7) |
| B6 | instructions | read before you edit; smallest change; check after a change; never edit tests to pass | early |
| B7 | instructions | write in parts: a file longer than ~N lines is written, then appended | 2026-10-08 |
| B8 | instructions | the goals and file list, frozen at the start of each request (for the server's cache) | df1b29d |
| B9 | loop note | **"No progress in the last 6 steps … Make the change now … or ask the person"**, at 6 and 12 | 2026-10-09 (the one progress rule) |
| B10 | loop | stuck after N steps without progress: stop and hand over to the person | 2026-10-03 |
| B11 | progress rule | progress = pass/fail, write/delete, accept/reject, create/destroy; **reading, searching and fetching never count** | 2026-10-09 |
| B12 | loop | a cut-off reply: said, and a saved part counts | 2026-10-03 |
| B13 | context fit | old reads become maps; old steps become one line each; history under 60 % of the room | 2026-10-03, today |
| B14 | style B | the Junior's stuck point goes to the Senior with its last three steps | today |
| B15 | style A | errands to the helper only when they make it faster | 2026-10-09 |

## C. Where they collide (seen on the machine, test5)

1. **B2 + B4 (instructions as a procedure) → the plan is recited every step.** In the first turn of test5 the Senior
   wrote the same "first the structure and the goal list, then fetch…" in 15 steps (6 distinct). Test4 had a tool
   list and three sentences for the Senior, and each thought answered the step before.
2. **B9 + B11 against B3.** Sources first (B3) means steps of searching and fetching; those never count (B11), so
   after 6 the model is told to "make the change now" (B9). Doing what the note says means writing before the
   sources are in, i.e. typing from memory. The note was written for an editing loop and now fires during gathering.
3. **A2 + A7.** The address rule leans on search; after a burst of searches the search falls back to Bing, which
   returned character biographies and budgeting ads for `site:` and quoted searches. The model saw the right address
   pattern on a page it had fetched (`<the site>/pack/<set>`) but A2 refuses it. It spent 12 steps and asked.
4. **B4 says give the Junior the reading; nothing in the tools makes that the easy path.** Three runs, zero
   hand-offs: the Senior read everything itself. (In test4 the Junior was used once told.)
5. **A20 is a band-aid on C1:** the goals repeated because the plan was recited, not because adding a goal is wrong.
6. **B8 + B5:** a new project's frozen block says "goals: (none yet)" for the whole first request, next to "at the
   start of a new project … write them as goals". Not the cause by itself (test4 had it too), but it feeds C1.

## What worked (keep)

- A6: the card lists keep their own files now.
- The picture listing behind A8: the one set page fetched holds 129 card pictures, each beside its name
  (`[image: <card name> — https://<the site>/images/cards_small/<id>.jpg]`).
- A5, A9: protection by origin (the project's own `assets/` files are its own again).

## Decided (Ian, 2026-10-10) and built

- **B2, B4:** back to test4's tool list, plus one line for `distill` and one rule: facts the project needs come from
  sources, fetched and distilled, never typed from memory. The Senior's part is test4's three sentences plus one.
- **B9 / B11:** a new source is progress: a page or file fetched (not the same address again), files downloaded, a
  gathered record. A search alone isn't.
- **A2:** an address on a site already fetched from may be tried ("let it find patterns"); an address on a site
  nothing came from still needs a search, the person or a kept page.
- **A20:** removed.
- **Team B only:** what the Senior fetches (a page, a PDF's text) goes to the Junior first. It reads it for what the
  Senior was after (the Senior's thinking at that step and the goal) and keeps notes in `notes/`, in the source's own
  words with where they stood. The Senior gets the notes between its steps, not the page. The Junior waits on the
  Senior's direction: it works only on what it's given.
- **A7 (search):** Cin-MinAI's own search, SearXNG on the person's computer, on by default (`cinminai-search`, SPEC
  §7.5): DuckDuckGo and Bing at once, with no disguise; ads and pages that share no word with the search dropped; the
  direct way (DuckDuckGo, then Bing) when it isn't there. Pictures through `web_search` kind images.
