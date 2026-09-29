# Development journal

How the work actually goes — the flow of each session, what went wrong, what we learned — written so the
project's history is honest and others can see how a human-directed, AI-built project runs day to day
(PLAN D26, built in the open). Decisions themselves live in `docs/PLAN.md`; the guide model has its own
journal (`docs/guide-model-journal.md`). Newest entry first.

---

## 2026-09-28 — the assistant's engine: daemon, llama.cpp, the guide on the ISO

*Claude (lead) worked alone overnight while Ian slept ("take some time, no rush"): he chose the step
(daemon + `cinminai-llama` first) and left the rest to the lead. Codex wasn't involved.*

### The flow

1. **A clean build place for llama.cpp.** No compilers on the dev PC's WSL, and installing them needs Ian's
   password — so the build runs in its own Ubuntu 24.04 build root (the official base tarball, apt pinned
   to a dated snapshot), which also makes the toolchain the same on every run. One build carries every
   backend as a module; the CPU one comes in a variant per instruction-set level.
2. **The help the guide looks things up in didn't cover what it's tested on.** The eval hands each task
   its own help card; the knowledge base the product ships had only the 63 transition cards, none for the
   lessons (copy and paste, a new folder, removing a USB stick...). Lesson cards were added, and a
   retrieval that bridges six languages to English cards. It was measured on 591 labelled queries
   while being written, then **once** on a clean set (the guide's own held-out queries, labelled by hand
   before looking): 78.7 %. The misses are the same "complaint" pattern the guide itself has.
3. **First real answers, all wrong.** The first run on the Mint box answered "Who should I vote for?"
   with a system check. Cause: the generated schema was written with `sort_keys`, so the grammar made the
   model write its arguments before choosing the tool. One word; a test now guards the key order. After
   the fix the three Alpha questions came out right.
4. **The server that died with its thread.** Each answer loaded the model again: `PR_SET_PDEATHSIG` (kill
   the server if the daemon dies) fires when the *thread* that started it ends, and the loads ran on worker
   threads. Now one long-lived thread starts servers; two tests check it (outlives the asking thread, dies
   with the daemon).
5. **The ISO's 4 GiB wall.** The guide (2.8 GB) inside the live filesystem would push it past ISO 9660's
   per-file limit, so it ships as its own file on the ISO, read from the stick in the live session (D48).
6. **The whole thing, booted.** The first full build with the assistant: a 5.9 GB ISO. In the VM boot test
   (UEFI, Secure Boot, 4 vCPUs, 8 GB, no GPU) the daemon started through D-Bus as the live user, read the
   guide from the virtual DVD and answered "how do I install a program?" with a help lookup and five
   correct steps naming Software Manager, in 52 s on the processor. `check-iso.sh` then caught that the
   bigger image has no MBR cylinder alignment: CHS can describe at most 4.27 GB (1024 × 255 × 32 × 512),
   so no hybrid image of this size can have it. Only pre-LBA BIOS geometry uses it; the check now says so
   and leaves exactly those lines out, only for images over the limit.
7. **The sidebar, and the first hands-on.** Rebuilt from the M0 spike (its docking kept as it was) around
   the real daemon: streaming bubbles, a plain-words line for every tool used, the header saying what runs
   where. In the VM it answered from the processor in 18 s. Then Ian tried it on his own desktop (1080 Ti,
   4K): updates, antivirus, opening every LibreOffice program and Firefox — answers in about 2 seconds.
   Asked "can you update from terminal?", it recommended Update Manager and then gave the commands. Ian:
   "I'll nudge in the right direction, but if you insist on jumping off that cliff I'm not going with
   you... The model explicitly said use Update Manager, twice. I'm good with that." That became D49. And
   his reason for opening programs through it: people see where things live and do it themselves next
   time — "the main goal for this run is making it easier to go from Windows to Linux, period. And the
   model did that here very well by my judgment."
8. **The panel icon and Super+A** (`cinminai-applet`): a click opens the assistant; at first login a
   small setup adds the icon and the key once, and never again if the user changes them. Two traps:
   on Ian's box the icon said "no such file" — Cinnamon was still running the M0 spike's applet code
   from memory (same id), pointing at a launcher the spike's uninstall had just removed; a reload of
   the applet fixed it (and means an updated applet only takes effect at the next login). In the live
   session the icon never appeared at all, though the boot test passed: the check read the setting,
   not the panel. Made strict (ask Cinnamon what's running), it failed, and Cinnamon's own list showed
   why — the setup wrote the setting while Cinnamon was starting, in the moment after it read its
   applets and before it listened for changes. The setup now waits for Cinnamon's panel, writes, and
   confirms. Lesson: a test must check what the user sees, not what we wrote.
9. **Boot check 1 — the Alpha on real hardware (D45).** Ian flashed the ISO with balenaEtcher and booted
   the Mint box from it. The normal entry didn't give a usable picture on his 4K TV (nouveau on the
   1080 Ti), so he used **compatibility mode** — the same workaround he needed to install Mint on that
   box. He thought that ended the test, but the photos show the assistant working on the processor, as
   designed for the live USB: "Getting ready…", then *Looked it up in the built-in help* → the right
   Wi-Fi steps; *Checked the disk space*; a polite decline of "who do I vote for?"; *Opened LibreOffice
   Writer*. What the photos also showed, and what changed because of them:
   - the boot menu still said "Start Linux Mint 22.3 Cinnamon" and the boot splash was Mint's logo,
     while the shutdown screen already showed Ian's mark — the live splash lives in the initrd. Both
     are ours now (`build-iso.sh`, `distro/initrd_splash.py`, checked by `check-iso.sh`);
   - "your hard drive is 17 GB and currently empty" was the live session's memory: true and misleading.
     The system check now says it's running from the stick and the computer's disks aren't used;
   - "help me write something as a document" was declined outright, and "open something to write a
     document in" found the word-count card. The search words are fixed; the blunt decline is cycle-1
     material;
   - the 4K + NVIDIA + nouveau problem is the one a newcomer with an older gaming PC hits first. Options
     (safe-graphics entry named plainly / an NVIDIA edition with the 580 driver / driver at first boot)
     are Ian's to decide, after a licence write-up.
   Not yet confirmed on the hardware: the `lsblk` "nothing mounted" check. Photos, with their metadata
   removed: `docs/images/boot-check-1/`.

   ![The sidebar on the Mint box, from the live USB](images/boot-check-1/09-lookup-check-decline.jpg)
10. **The model into installed systems, and an install test.** Mint 22.3's installer runs hook scripts from
    `/usr/lib/ubiquity/target-config/` near the end (read in its own code, not from memory);
    `cinminai-guide-model` now ships one that copies the model from the stick and checks it. To prove it,
    an unattended install test: a test ISO whose first entry installs onto an empty VM disk (preseed), then
    the VM boots from that disk and the boot-test report runs in the installed system. First run: the
    install took 8.3 minutes and my runner then failed to eject the virtual DVD (Hyper-V won't remove the
    drive; ejecting works). Second run: PASS — the model copied and SHA-checked, the installed assistant
    answering in 47 s on the processor, icon and Super+A set for the new user. It's now part of every
    `build-all.sh`. It also showed the next gaps: Mint's "Welcome to Linux Mint" on first login, and a
    failed `casper-md5check.service` in the installed system — which plain Mint on the Mint box shows too
    (upstream, not ours).
11. **Shutting the live USB down** (Ian's photo, `images/boot-check-1/12-shutdown-at-spi-not-responding.jpg`):
    Cinnamon's shutdown dialog said `at-spi-registryd.desktop` (the accessibility registry) was "Not
    responding"; the machine shut down after a while. Whether it's ours (the sidebar is a GTK program on
    that bus; the model on the processor) or a Mint live-session quirk isn't known yet — the VM boot test
    never saw it, because its report shuts down with `systemctl poweroff`, which skips that dialog.
    **Chased (four test versions, three of them wrong in instructive ways):** `cinnamon-session-quit
    --no-prompt` and `SessionManager.Shutdown` both only open Cinnamon's confirmation dialog, so two runs
    "hung" on a dialog waiting for a click; the button's real call (`EndSessionDialog.Shutdown`) was found
    in Cinnamon's own `endSessionDialog.js`. Then the report was stopped along with everything else and went
    silent (made to survive with `DefaultDependencies=no`); one rerun was killed when Windows ran out of
    memory (WSL kept ~13 GB after the ISO build, plus the 8 GB VM; `build-all.sh` now shuts WSL down
    before any VM). Result: in the VM the session shuts down **clean in 3 s with the assistant running and
    with it stopped** — the assistant doesn't hold it up, and the dialog doesn't appear. What differs on
    the Mint box: compatibility mode (everything drawn by the processor) while the model used it too; the
    next evidence has to come from that machine. The boot test now shuts down the way a person does, every
    run, and fails if the session doesn't end.
12. **An NVIDIA edition: the licence, read.** `docs/nvidia-edition-licence.md` — permitted with conditions
    (unmodified binaries, the licence provided to each recipient); a GPL stance to take for Pascal's
    proprietary module; signed prebuilt modules exist for the ISO's kernel (verified); and the CUDA
    libraries' "only accessed by your application" condition argues for keeping them off the ISO.
13. **Screen first (D50).** Discussing an offline NVIDIA installer (a licence checkbox before the desktop),
    Ian brought it back to what matters: "the screen needs to render for any of this to work … they should
    have a clean line from USB to usable screen, and then … use Mint's existing pipelines." The black
    screen was the open nouveau driver on the 1080 Ti at 4K (plain Mint did it too when he built the
    machine). The two-minute test on the existing stick — `modprobe.blacklist=nouveau` added in the GRUB
    editor — gave a proper 4K desktop, "might have worked better" than compatibility mode; Driver Manager
    then offered `nvidia-driver-580`, and the assistant looked up how, opened Driver Manager, and — asked
    "there's 2 drivers, which one is for my computer?" — read it as the two graphics chips, but still
    named the recommended driver. Now the ISO's default entries keep nouveau out (a named entry keeps it),
    an installer hook carries that into the installed system, the drivers check says "basic mode" instead
    of "simple-framebuffer", and the checkbox installer is parked. Photos: `images/screen-first/`.
    And the shutdown bug (entry 11) went with it: booted this way, Ian's shutdown was "clean … straight to
    exit logo … and it's Cin-MinAI!" — no "at-spi-registryd not responding". Compatibility mode also
    switches off ACPI and APIC (`noapic noacpi irqpoll`), and that (or the processor load it brings) is the
    likely cause; the VM had already ruled the assistant out. One fix, two bugs: why D50 keeps nouveau out
    and nothing else, and compatibility mode stays only as the last resort.

    ![Driver Manager and the assistant, the live USB without nouveau](images/screen-first/03-driver-manager-and-assistant.jpg)

### What went wrong (and what we changed)

- **`sort_keys=True`** on the generated prompt data (above). Lesson: a JSON schema's key order is meaning,
  not formatting, when a grammar is built from it.
- **PDEATHSIG and threads** (above).
- **Heredocs through Python on Windows** turned `\n` escapes into real line breaks in two files; caught by
  a syntax check and by reading them back.
- **A secret on screen:** checking for leftover processes on the Mint box with `pgrep -a` printed the
  command line of Ian's `qwen14b.service`, API key included (hard rule 4). Only into this session's
  context; Ian was told. (It is llama-server's own key, and the server listens on 127.0.0.1 only, so the
  exposure is small; still a rule broken.) Processes there are listed by name only now (`pgrep -l`).
- **A hoped-for speed gain that wasn't:** the per-CPU modules were expected to speed up the i7-4790K;
  measured, the same speed (the old build already used AVX2). Recorded as portability, not speed.

### What we learned

- **Single-turn evals miss conversation failures.** In six-language, multi-turn probes the guide chose to
  decline correctly, but in English and Japanese its decline *text* listed the forbidden topics as things it
  can help with (4 of 12), and after a Spanish turn it answered German in Spanish. The eval (one question
  at a time) scores declines 100 %. A multi-turn check belongs in the next cycle's eval.
- **Measure the product path, not only the model.** Running the public eval with the product's own lookup
  instead of the task's card gave the same 92 %, item for item — useful, but the search words were partly
  written on those queries; the clean held-out number is the honest one.

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
