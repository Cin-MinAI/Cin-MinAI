# Development journal

How the work actually goes — the flow of each session, what went wrong, what we learned — written so the
project's history is honest and others can see how a human-directed, AI-built project runs day to day
(PLAN D26, built in the open). Decisions themselves live in `docs/PLAN.md`; the guide model has its own
journal (`docs/guide-model-journal.md`). Newest entry first.

---

## 2026-09-26/27 — from a tuned guide to a branded, tested ISO

*One long session, about 26 hours of wall-clock time with training and builds running in between.
Ian directed and decided; Claude (lead) did the work; Codex wasn't involved this session.*

### The flow

**Morning of the 27th, where we started:** a session corpus (Ian's design) generated overnight, a plan in
`RESUME.md`, and the rule we've kept all along — *Ian decides each step*.

1. **Merge and first run (G).** Merging the 319 sessions turned up problems RESUME didn't list: "declines"
   that gave voting and stock advice, and 68 English "What do you see now?" lines inside Japanese, French and
   Portuguese replies. Ian chose to *repair* the phrase (it came from our own prompt), not reject it. Run G
   fixed the collapse we'd been chasing (declines 100 %) but lost numbered steps (72 %).
2. **A question from Ian that reframed the work.** "How effective is the assistance dialogue?" — reading the
   sessions showed the reports stated problems without offering the fix. Then: "how are we looking against a
   baseline tune right now?" — which pushed us to measure before polishing. Run H (more full answers, walk-
   throughs trained only on their follow-ups): **91 %, the first tune above stock.** Ian: "Full run with this
   recipe. Let's do it, this looks sharp." Full run HF: 92 %.
3. **Baseline, then the gap.** Ian accepted HF as the working baseline, then chose to fix the office gap
   (two spreadsheet items lost to stock). A new office corpus → run HO: 94 %, office back to stock.
4. **"We were testing base models, not 14B — we're still doing that, right?"** A good catch: it stopped me
   from spending the one-shot held-out eval on Qwen alone. Gemma had to be tuned first. That run (GO)
   crawled at 205 s per step with 15 GB of the GPU's overflow in system RAM; Ian: *let it ride, don't change
   the architecture mid-comparison.* It finished at 50 %, and Ian chose to decide cycle 0 without a tuned Gemma.
5. **The held-out eval, once:** tuned Qwen 73 %, stock 66 %, stock Gemma 51 %. The tune missed the strict
   gate by 2 transition items; Ian shipped it anyway (D43), for the everyday gains — noting that users can
   run the bakeoff for their own machines. Then: merge and quantize (the 3900X's 24 threads quantized it in 26
   seconds — "we finally justified this 3900 five years after I built it"), the model card, the datasheet, a
   plain-language release note, and the licences (GPL-3.0-or-later; CC BY-SA 4.0 for data; Apache-2.0 for
   the model).
6. **Towards an ISO you can boot.** Ian split the boot confirmation in two — live USB at the Alpha, a full
   install on his spare SSD before the beta (D45) — "so if anything goes wrong it's easier to find." GitHub
   Pages for the apt repo (D46). Clean installs, one OS per drive (D47, from his console-modding days).
7. **M1: the build script.** A reproducible ISO pipeline grew out of the M0 spike. Making it reproducible
   exposed a real bug hidden since M0 (below). Then an automated boot test in a throwaway Hyper-V VM, with a
   report over the serial port.
8. **Ian's artwork.** He made a logo, a designer's note, and three concept images (generated with ChatGPT
   from his prompt) — "these designs for you to work from, always planned on you doing the final run." The
   logo became a vector (Archivo fitted to his letters automatically; "Oh. Then it's perfect lol" once the
   comparison was labelled clearly), the concepts became three generated vector wallpapers ("brighter like the
   concepts, but I like the simplicity"), and his mark A went onto the menu button. The last screenshot of the
   day shows the live desktop in his colours, his mark bottom-left.

### What went wrong (and what we changed)

- **C: filled to 0 bytes.** Two ISO builds plus unpacking both for a comparison pushed WSL's disk file past
  what was left. Found when WSL refused to start. Recovered (sparse disk, Ian uninstalled old games; 102 GB
  free). Now: `build-iso.sh` refuses to start below 20 GB free and deletes its 11 GB working tree.
- **A bug hidden since M0:** apt's update hooks rebuilt Mint's command-not-found database and software
  catalogue from *our* repo alone, so every ISO shipped near-empty copies. Only the reproducibility test
  exposed it. Fixed, and a check added so it can't return.
- **The memory reaper.** Claude Code stops its own background shells when Windows runs low on memory — twice
  during Gemma's run. Training was always launched detached, so only the watchers died.
- **Someone pressed Stop Service** (Ian, in Hyper-V Manager, meaning to stop a VM) mid-test. The test VM kept
  running unmanaged; the runner's cleanup crashed and lost its log. The runner is now fault-tolerant.
- **The screenshot that took five tries:** Hyper-V's own thumbnail call refused ("invalid state"); the serial
  port dropped bytes even when paced; the fix was a raw 32 MiB "results disk" the guest writes onto and the
  host reads after shutdown, checksum-verified.
- **My own mistakes, so they're on record:** Python on Windows saved nine files with CRLF line endings (one
  broke a script in WSL); a "—" in a PowerShell script broke Windows PowerShell 5.1; a wait loop matched the
  previous run's log; I picked the same splash priority Mint uses (a tie keeps theirs); and the first menu
  icon change did nothing, because Mint's menu applet ignores the global setting — found by reading its code.
- **Misread comparison:** the first logo comparison had three rows, the third a "difference map". Ian took it
  for the vector logo ("kind of transparent and hard to see"). Replaced with a labelled side-by-side.

### What we learned

- **A LoRA learns the corpus's patterns, not its facts** — the same sentences in a different mix moved the
  score 19 points (G → H). Check the data's *shape* before training. (Details in the guide journal.)
- **Tests before refactoring, a new test after every fix.** Ian had read it on Reddit; we'd been doing it all
  day without naming it: `check-iso.sh` guarded every change to the build, the Mint-database bug became a
  check, and the boot test now *fails* if the wallpaper, theme, splash or menu icon stop being ours.
- **Ask before spending a one-shot resource.** The held-out eval can only be used once per cycle; the right
  moment was after *both* candidates were tuned (or set aside) — Ian's question caught it.
- **A shared machine needs resource hygiene:** free-space guards, cleaning up after tests, shutting WSL down
  after training, detached jobs. Windows' own overhead plus a GPU spilling into RAM leaves little margin.
- **The human sets the direction and the taste; the agent does the volume.** Every turning point today was
  a question or a call of Ian's — the baseline check, the office gap, "we're testing base models", shipping
  the tune, splitting the boot checks, the designs, mark A.

### Talked about along the way (parked in PLAN §6)

A home AI platform (one GPU box on the LAN, everything else a client — the "real Jarvis apparatus"); home
diagnostics and errands (the owner approves every purchase); a generalized Pi Zero + touchscreen tool with
adapters (OBD-II, NAND reader, a Rock Band controller clone); and conversations on Google and the transformer
("confused inventors"), AI's head start for defenders, and where hardware goes when AI becomes like phones.
Ian's reason for the project: someone on Reddit asked what it takes to build a community AI program — *work,
and joining others doing the work, until it's big enough to organise.* This is that work.
