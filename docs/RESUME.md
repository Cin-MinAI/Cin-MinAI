# Resume note — where things stand, what's next

Updated **2026-10-03 night** (latest: journal "persistence: habits on the bitcode, a memory design, and the Quaddle board"; before it "what the next OS might be, and where Quaddle fits"; before it "AICUI's next version, and a wedding page"; before it "the assistant learns to see"; before it "all six goals, the BIOS change, and a game Ian can launch"; before it "watching the blackjack game get built, and a senior/junior setup
by hand"; before it the night of 2-3 Oct, AICUI's first real project; before it "AICUI, and knowing where every model is"; before it "a writing partner with a shape, and the right model for every machine"; before it the night of 30 Sept–1 Oct; before it the 28–29 Sept session: from the assistant's engine to an installed
Cin-MinAI; journal entry of that date). For Ian, Claude and Codex alike: **read this first.** Reasons
behind decisions: `docs/PLAN.md` (D1–D67). How the work went, day by day: `docs/dev-journal.md`. The guide
model's story: `docs/guide-model-journal.md`.

## Where we stopped (2026-10-03, evening) — AICUI's next version done; direction talk recorded

- **Test SSD state.** All 11 packages installed; latest: aicui `0.0.1+git20261003.204240`, daemon `…195159`,
  sidebar/applet/desktop `…132747` (`dpkg -l 'cinminai-*'`). **Install test packages only with
  `~/cinminai-debs/install-debs.sh FILES…`** (stops before the password if apt would remove or downgrade anything —
  3 Oct apt removed the sidebar when an old, exactly-pinned package met a new daemon). After a dependency-rule change,
  rebuild and ship **all** packages. **Desktop on the board's graphics** (Ian's BIOS change): the 1080 Ti is free;
  coding = the 27B whole on the card at **32K**, 12-15 tok/s. Prompts for Ian to paste: `~/Desktop/prompts.txt`.
- **AICUI's next version — built and tested (8c9eae1..e40fde6):** compaction keeps file maps; every change checked
  (Python compiles / no duplicates, HTML tags, JSON, and a **web name cross-check** HTML↔CSS↔JS); a goal is ticked
  only when the project's checks pass (tests, entry point started 5 s, web page names/tags — "no tests" never passes
  by default); a **Run** button (run.sh → main.py with the venv → index.html in the browser; crashes in the chat with
  "Send to the AI"); no hard step limit while it makes progress (handover every 60 steps, stop after 15 without
  progress, 600 safety); "waiting for you" in amber with Allow / Always / No (Ian: "perfect and pronounced"); the
  agent asks for the card right before every model load and says so if it lands on the processor. **Ask stays the
  default permission mode, always** (Ian).
- **Test projects on the SSD:** blackjack `~/aicui-test` (6/6 goals, `run.sh`, some game bugs left on purpose);
  wedding page `~/wedding-test` (6/6, confirmed by Ian in Firefox: RSVP opens the email, the menu folds behind ☰ on a
  narrow window, Reader view works). Vision/video tools: `spikes/vision/`; SSD `~/cinminai-src/vision`,
  `~/cinminai-src/tools` (uv, yt-dlp, cmake, whisper.cpp v1.9.4), projectors + whisper model `~/cinminai-models/vision`,
  results `~/Pictures/vision-test`, `~/Videos/vision-test`.
- **Decisions today:** D62 (publish from AICUI via GitHub Pages; dedicated dev email + authenticator/passkey; device
  flow; "this is public" warning), D63 (cloud senior guiding the local junior over D-Bus), D64 (the assistant can see:
  27B recommended, 4B "works, no quality promise"; measured on photos, a screenshot and two videos), D65 (every
  choice a simple presentation with an easy, accurate description, for non-techy people).
- **Direction, not decisions** (journal "what the next OS might be, and where Quaddle fits"): Ian's aim is
  *industrial AI, not frontier* — what works every time for the small painful jobs. AICUI as an AI-first IDE (human
  conveniences slimmed, AI machinery out of sight). "The AI is the kernel" as a later venture (v1 AI on an OS → v2 AI
  as the session → v3 AI-first OS on a tiny deterministic core). Ian's research *Quaddle* (`docs/kernel doc/`,
  **untracked — his, not to be committed without him**): its Choice Atom (allowed Γ / chosen d / deterministic
  realization T_d / checked result w / append-only record R; reversible acts may run alone, irreversible ones ask) is
  the discipline we can use now — for actions and for the **persistent personality with recollection** Ian wants
  (addressed memories, recall by shared context path, append-only episodes, summaries as reversible folds).
  "A binary allows for a switch but no wall for the switch to exist on. Quaddle supplies the switch and the wall."
- **Persistence (night of 3 Oct) — now in the plan:** **D66** memory and personality (`docs/memory-design.md`:
  one shared daemon-owned memory, addressed hash-chained record, facts as reversible folds, "keep the changes, fold
  the sameness", visible remembering with hideable notices, never the sealed journal / secrets / declined requests;
  seven starting personalities by people matching, the system never lies while Buddy/Coach/Teacher may play;
  personality grows through habits — Ian's 3+1 nesting, `spikes/habits/`), **D67** the Choice Atom as the
  architecture of action and memory (Γ policy / d proposed / T_d deterministic / w checked / R append-only record;
  reversible actions paired with their inverse). New milestone **M4b** after M4. Ian's Quaddle research and his Tang
  Nano 20K testbed archive (flash dump, the board's later bitstream, the 1 July Gowin project) sit in
  `docs/kernel doc/` — beside the project, ignored by git; independent check script there (23 checks pass). **Still
  to rescue:** the board's newer HDL source and `quaddle/node.py`, on the Mint NVMe — when that drive is next in.
- **Build order from here (Ian: finish the early steps first, then the full OS plan with this incorporated):**
  1. **Early steps to finish:** mark M0's bakeoff done in PLAN; M1 — the live-USB splash, an automated install
     test, CI and publishing (waits on Ian: `cinminai-apt` Pages repo, a Hugging Face org, the offline signing key);
     Alpha/M2 — the guide model copied into installed systems (needed before boot check 2), LibreOffice/writer/
     journal/web features packaged and boot-tested, the sidebar's cards seen on screen; a fresh ISO with everything
     since 28 Sept through the VM boot test. Then the guide's cycle 1 list.
  2. **M3** — the terminal relay as a real package, command cards, terminal context.
  3. **M4** — the action boundary built as Choice Atoms (D67): one action path, approvals, the admin lane, the
     record as audit log, replay, security tests.
  4. **M4b** — memory and personality (D66), on M4's record (v0.1 slices: Ian's call, suggested 1–3).
  5. **M5 → M6 → M7** — first boot and hardware, Firefox packaging, the deeper fork and installer pages → boot check 2
     → **v0.1**. M8–M11 as planned (AICUI = M9/M10 already well started; D62 publishing, D63 senior/junior, D64 use
     cases fit there).
  Small AICUI polish when convenient (wedding cards wider than the text column, countdown wrapping 3+1 on a phone).

## State right now

- **Repository:** pushed; nothing running on the dev PC (WSL stopped, no VMs but the two M0 ones, off).
  C: 85 GB free.
- **The Mint box** now has three systems on three drives: its own Mint (NVMe, with Ian's `qwen14b.service`),
  Windows (SATA), and **Cin-MinAI installed on the 120 GB SSD** (boot check 2). On the SSD system: kernel
  6.14.0-37 works with the NVIDIA 580 driver and the assistant on the GPU; **under kernel 7.0.0-34 this old SSD's
  SATA link fails under load** (4 MiB writes, `ICRC ABRT`) and the driver fails at startup (zeros in the cached
  module; the file on disk is fine, `modprobe` by hand works) — journal 2026-09-29/30. Left on the SSD system for
  the tests: `openssh-server`, the `cinminai_ssdtest` key, `/etc/sudoers.d/cinminai-test`. **Now on the 6.8
  long-term kernel only** (`linux-generic`, 6.8.0-146; switched by Ian in Update Manager, 7.0 and 6.14 removed):
  driver loads, 0 link errors. The NVMe (Ian's Mint) and the Windows 7 drive stay unplugged until this release is
  done; the Windows 7 drive is for another project of Ian's.
- **On the Mint box's own Mint** (user `mint`): the test assistant from `~/cin-minai/alpha/` — our panel icon
  and Super+A are installed in Ian's user (undo: `~/cin-minai/alpha/applet-test/undo-applet-test.sh`); the
  M0 spike's applet and keybinding are uninstalled. `~/cin-minai/` also holds the eval, models and builds.

## Where things are

| What | Where |
|---|---|
| Shipped guide model | `Qwen3.5-4B-guide-HO-Q4_K_M.gguf`, SHA-256 `b9b132b0…e8c8e4` — Mint `~/cin-minai/models/`, WSL `~/cinminai-train/out/` |
| Training environment | WSL `~/cinminai-train/` (`.venv` via uv, `base/`, `runs/`, `llama.cpp/` at `7fe450e` with a CPU build of export-lora/quantize) |
| Training results, logs | `C:\Users\Ian\cinminai-train-out\` (`sweep\`, `held-out\`) |
| Distro build area | WSL `~/cinminai-build/` (`upstream/` = pinned Mint ISO; `m1/` = our pkgs, repo, ISOs, dev key `gnupg-dev`) |
| Test ISO + boot-test logs and screenshots | `C:\Users\Ian\cinminai-vm\iso\`, `C:\Users\Ian\cinminai-vm\boottest-logs\` |
| Eval on the Mint box | `~/cin-minai/eval-guide/` (public), `eval-guide-hidden/` (**used once for cycle 0**), `eval-guide-interp/` |

## What's done

**Guide model, cycle 0 — complete** (D43). Tuned Qwen3.5-4B (run HO: sessions corpus, preset h, + office
corpus): public **92 %** as the merged file (stock 87), held-out **73 %** (stock 66, Gemma 51); 66 tok/s and
3.0 GiB on the 1080 Ti, fits the 6 GB budget. Ships despite a 2-item held-out transition loss (Ian's call).
Documents: `training/guide/MODEL_CARD.md`, `training/datasets/DATASHEET.md` (all four corpora),
`docs/release-notes/cycle-0-guide.md`. Gemma's tune (50 %) set aside: it needs a memory fix first.

**Licences** (D44): code GPL-3.0-or-later, data and docs CC BY-SA 4.0, fine-tuned models Apache-2.0
(`LICENSE`, `LICENSES/`, `LICENSING.md`, SPDX headers).

**M1, distro skeleton — mostly done:**
- `distro/`: `build-packages.sh` (source dirs → .debs, bit-for-bit reproducible; build hooks, maintainer
  scripts, `links`), `signing-key.sh` (dev key "not for release"), `make-repo.sh` (signed, rebuilt each
  time), `build-iso.sh` (pinned Mint 22.3 → our ISO; `BOOTTEST=1` test variant; free-space guard),
  `check-iso.sh` (5 checks incl. reproducibility with `--rebuild`), `vm-boottest.ps1` (throwaway Hyper-V
  VM, UEFI + Secure Boot, report via COM1, screenshot via a raw results disk, regression checks).
- Packages: `cinminai-archive-keyring`, `cinminai-desktop` (meta), `cinminai-branding`; test-only
  `cinminai-boottest` (never in the repo).
- **Branding** (from Ian's designs, `artwork/`): vector logo (Archivo fitted to Ian's original, approved),
  three vector wallpapers (data-stream default, also on the login screen), Mint-Y-Dark-Aqua theme +
  Mint-Y-Aqua icons as defaults, Plymouth splash (installed systems), **menu button = Ian's mark A** (via a
  diversion of Mint's menu-applet override, regenerated by a trigger). Verified in the VM with a screenshot
  (`artwork/live-desktop-2026-09-27.png`).
- `docs/install/make-usb-stick.md` (plain-language, Etcher/Rufus, clean installs per D47).

## Next — the Alpha (D45, boot check 1)

**M1 + a trimmed M2** (PLAN §4 "Alpha"). **Done 2026-09-28 (D48):** `cinminai-llama` + `cinminai-llama-cuda`
(`distro/build-llama.sh`: pinned v0.5.0 in a clean noble build root; CPU variants + Vulkan + CUDA as modules),
`cinminai-daemon` (`src/cin_minai/`: D-Bus service, `LlamaCppBackend` with load-time budget and step-down,
the guide's turn protocol as trained, `lookup_help` retrieval, `inspect_system`, `open_app`; `python3 -m
cin_minai.daemon.client "question"` asks it), `cinminai-guide-model` (the model is its own file on the ISO;
fetch + SHA-256 into installed systems), boot test asks the assistant. Tests: `python3 -m unittest
tests.unit.test_helpcards tests.unit.test_guide tests.unit.test_llamacpp`. Verified on the Mint box from the
unpacked .debs: CUDA, Vulkan and CPU all answer. Full pipeline (`distro/build-all.sh`): 5.9 GB ISO, all
`check-iso.sh` checks pass (no CHS cylinder alignment above 4.27 GB: noted, not compared), VM boot test PASS
with the assistant answering on the processor in 52 s. **Sidebar done** (`cinminai-sidebar`, `src/cin_minai/sidebar/`):
VM boot test opens it and gets an answer (18 s, CPU); Ian's hands-on on the Mint box went well (D49 came out of
it). **Applet + Super+A done** (`cinminai-applet`: the icon, `/usr/libexec/cinminai-desktop-setup` once per user;
VM boot test checks the icon is really running). On the Mint box the spike was uninstalled and ours runs from
`~/cin-minai/alpha/applet-test/` (undo: `undo-applet-test.sh` there).

**Boot check 1 done (2026-09-28, journal entry 9, photos in `docs/images/boot-check-1/`)**: the live USB booted
on the Mint box (compatibility mode: 4K TV + nouveau) and the assistant answered a lookup, a system check and
a decline on the processor. Not yet confirmed: `lsblk` shows nothing of the internal disks mounted. Fixed after
it: boot menus and live splash in our name, "Install Cin-MinAI", the live-session disk message, "write a
document" retrieval. **Model on installed systems:** `cinminai-guide-model`'s ubiquity target-config hook;
the **install test** (`INSTALLTEST=1` ISO + `vm-boottest.ps1 -Install`, part of `build-all.sh`) installs
unattended and checks the installed system — first PASS 2026-09-28 (model copied and SHA-checked, assistant
answered, icon, Super+A).

**Screen first (D50, 2026-09-29):** the live USB's default entries boot without nouveau (Ian's stick test: a
proper 4K desktop where nouveau gave a black screen), a named entry keeps nouveau, an installer hook carries it
into installed systems; Driver Manager + the guide take it from there. The offline NVIDIA installer is parked
(`docs/nvidia-edition-licence.md`).

**Boot check 2 (2026-09-29, journal 14):** the install onto the 120 GB SSD went smoothly and Update Manager got
the 580 driver — then after a kernel update (6.14 → 7.0.0-34) the NVIDIA driver didn't load on 7.0, though built
for both (Secure Boot is **off**, so not a signature), and a hard power-off damaged the root filesystem (fsck at
the initramfs prompt). On 6.14 the driver works and the assistant runs on the GPU. **Diagnosed 2026-09-30**
(journal): kernel 7.0 and the old Kingston V300 SSD — 7.0 writes 4 MiB pieces (6.14: 1.25 MiB), the link fails
under load, and the driver reads as zeros at startup though correct on disk. Next on it: the 1280 cap as a
udev rule at startup; then `libata.force` boot options; then the HDD. Open: the installer slideshow still says
"Welcome to Linux Mint".

**Diagnostics, first slice built (2026-09-30, D51/D53, SPEC §20.9):** `src/cin_minai/diag/` + `cinminai-diag`
(status / report / show / guide / capture), codes G101 S301 I301 I302 S401 H401 I101 S101 with trees (plain words,
no-terminal steps first, commands with what they do and how to undo), tested on two recorded cases from the Mint box
(`tests/fixtures/diag/`, 20 tests). The shipped guide gets active findings through `inspect_system`
(`problems_found`); with the recorded 7.0 case it answered three newcomer questions with the right fix (switch to the
long-term kernel in Update Manager). The sidebar shows commands as cards with Copy (D53). Not yet built: packaged
and boot-tested (`build-all.sh`), the root system service (SMART, boot record, in-memory event log), B401/U101,
translations. **Research round done (2026-09-30):** 15 more codes from Debian / Ubuntu / Mint troubleshooting
(P101 P301 P302 B301 G102 A101 X101 N101 N102 D301 D302 I303 S102 U201 S601; SPEC §20.3), 23 in all, 32 diag
tests; the guide answered a Windows-drive (Fast Startup) and a Wi-Fi-off question right on the first try. **Next:**
the LibreOffice toolkit (D20) into the Alpha; then package + boot-test the diagnostics; the root service; help
cards for symptoms the rules can't see (sound on HDMI, printers, Bluetooth).

**LibreOffice in the Alpha (2026-09-30, D20/D53):** `cinminai-libreoffice` (the extension, bundled), the daemon's `office.py` (the trained document prompt, exactly), preview cards with Apply/Discard in the sidebar; real guide + real LibreOffice: the eval's 5 expenses-sheet questions 5/5 (`tests/integration/check_libreoffice.py --guide`). New spreadsheets: `make_spreadsheet` (`sheets.py`, our formulas, a new file in Documents) in **prompt v2.1**, adopted after the A/B on the 1080 Ti (Vulkan): 140/157 vs v2's 141/157, the same tool choices, never called by mistake; creation items 4/7 → the Spanish/German per-month misses fixed in code (`wants_by_month`). Not yet: packaged + boot-tested, the sidebar's cards seen on screen. **Writing projects built (2026-10-01, D54, SPEC §7.12):** gather ideas as notes → outline card → a rough-draft chapter as a new .odt (A5, ~28 lines a page): the guide wrote 4,000–4,400 words / 15–17 pages in ~2½ min on the 1080 Ti, the key fact held; the whole flow passes over D-Bus with the real daemon (`tests/integration/check_writer_dbus.py`). Not yet: the sidebar's project bar and cards seen on screen; packaged + boot-tested. **The journal built (2026-10-01, D55, SPEC §7.13):** the interviewer, dated entries in Documents/Journal, the conversation never on disk, private entries sealed with GnuPG + a login-keyring key behind a 4-digit PIN, read only in the sidebar; passes over D-Bus with the real model and keyring (`tests/integration/check_journal_dbus.py`). The test install's keyring now holds a "Cin-MinAI journal key". **Web search built (2026-10-01, D55, SPEC §7.5):** an offer card (the exact query, nothing sent before Search), DuckDuckGo + page text, answers from the pages with sources; live-tested in English and Spanish. **Prompt v2.2** (rule 2: world questions → web_search, writing → help, advice → decline) measured on the 1080 Ti: 138/157 vs v2.1's 140/157 — the unchanged items better (123 vs 120 of 137), the moved declines 15/20 (quadratic equations answered directly instead of searched, ×5); misses B02 ("What is Linux?" searched), B03 (DVDs → a driver check), D10 (the essay still half-refused); new items 5/5. **Where we stopped (2026-10-01 ~03:20, Ian asleep):** the loop fix is installed on the test SSD and the daemon restarted at 03:19 (the 02:59 draft "The Red Warning" in Writing/The Coming War was written by the *old* code: 6 repeated paragraphs, 1 echo) — **next: write that project's draft again and compare** (`tests/integration/check_writer.py` `quality()`). **Product gap found:** installing an update doesn't restart a running daemon, and logging out isn't always enough (other sessions keep the user's services alive): the daemon should notice its files changed and restart when idle, or the sidebar offer it. Test-install state: kernel 6.8 only, CUDA build, prompt v2.2, `~/cinminai-debs/`, SSH key + narrow sudoers rule, the journal key in its keyring; Ian's own projects (Grandman Stan, The Coming War) and journal on it.

**Story Circle (D56, Ian, 2026-10-01 afternoon):** the story assistant is to be rebuilt around Dan Harmon's Story Circle (eight steps, any form: novel, movie, play). **Built the same day** (SPEC §7.12): the circle in the notes, a story in one chapter or over 2-8 chapters, outline by steps, sidebar Notes card + shape; 21 writer tests. Real model on the test SSD (from ~/cinminai-src, results /tmp/circle-1650): one chapter is a real arc with a steady soldier; over chapters, chapter 2 retold chapter 1. Ian's redraft of "The Coming War" with the loop fix: 0 repeats, 0 echoes (6 and 1 before). Then **D57** (Ian): a review before every chapter, from the files as they are now (SPEC §7.12) — built; before chapter 2 the guide marked all 8 steps "written" after one chapter. Evidence for "written" (the chapter's own words, checked in code) built and rerun: chapter 2 planned as Go + Search, the soldier stays an ally (SPEC §7.12). Installed and hands-on (Ian: review questions "great", one chapter "excellent"); fixes for the glued repeat and chapter pacing; tick boxes; "Missed the Moon", the first whole book. Then D58 Make a manuscript, the circle's own question while gathering, and **D59 the daemon restarts itself after an update** (tested: same PID, project reopened, a broken update refused). Ian generated the "Missed the Moon" manuscript (fine). **2026-10-02:** writing quality is the model's limit: the writing bakeoff (4B, 9B Q4/Q5/Q6, 14B, 35B-A3B MoE with experts in RAM) → **D60** (writing model by system; gguf.py reads each model's memory need; desktop_reserve_mib setting). Models on the test SSD in ~/cinminai-models (SHA-checked), results /tmp/bake. **Next:** build the system analysis + offer card + download/benchmark (M5) for the writing model, and the writer switching models; small fixes queued: pronouns kept in notes, no step names in chapter titles, 'one new event per scene', measured desktop reserve; README credits draft (Mint/Ubuntu/Debian, llama.cpp, open-weight makers, AI pioneers) awaiting Ian's OK. **Coding on the 1080 Ti (2026-10-02):** Qwen3.8-27B (dense, Apache-2.0) UD-IQ3_XXS fully on the card at **14.1 tok/s** writing, 250 tok/s reading: desktop moved to the i7's Intel graphics (cable on the board + `prime-select on-demand`; Xorg still keeps ~350 MiB on the NVIDIA card — BIOS Init Display First → Onboard frees it), `-ngl 99 -fa on -c 8192 -ub 256 -ctk q4_0 -ctv q4_0`, peak 11.0/11.26 GB. Walk-away: IQ4_XS 2.8 tok/s with 45/64 layers. IQ2_S 16 tok/s but loops. The 0.8B draft doesn't fit. The tuned 27B found a real bug: manuscript.read_scenes iterates nested text:p (footnotes, frames) twice — fix next. Files in ~/cinminai-models on the test SSD; scripts ~/cinminai-src/codebench2.py, tune27.py. **System matcher, slice 1 (443473e):** `python3 -m cin_minai.inference.matcher` reports the best model per task with its llama.cpp flags and an estimated speed (calibrated: 4B 57-106 vs 66 measured, 9B 25-47 vs ~40, 35B MoE 19-35 vs 25). Mint box: picks 27B IQ3_XXS `-ub 256` q4_0 for coding (the hand-tuned setup), 14B for writing. WSL + RTX 4070 (our llama packages + Ubuntu's libcudart12/libcublas12 unpacked by apt-get download, no install): same picks. Next: the VM testbed through the boot test (report to COM1), then the offer card + download/benchmark. **Done since (2 Oct evening):** VM boot test reports the matcher; the offer card + resumable SHA-checked download + benchmark (14B 27.8 tok/s); **AICUI** slices 1-2 (D61, SPEC §21: Ian's layout, real VTE terminal, cinminai-code agent with permissions, shadow-git changelog with undo, goals; package cinminai-aicui with a Programming menu entry and a sidebar button; the sidebar steps aside); the matcher's near-fit for dense models and the desktop share from nvidia-smi; the **model record** (store / parked with drive label / deleted, replaced_by; download brings a parked copy back). Test install: 35B MoE, 27B IQ4_XS, 9B parked on the 1.8 TB exFAT drive "USB Storage"; SSD 60 GB free. **Next:** AICUI slices 3-5 (file-watching changelog for any agent, goals interview, cloud providers: Claude key/OAuth if allowed, GitHub device flow, local+cloud together); a Models view in the sidebar (park/bring back by button).

**Hands-on round 1 (2026-10-01, the full packages on the test SSD):** copy cards, web search, writing (with "Put in Writer" after the fix), a new spreadsheet, the journal ("just perfect") and a writing project ("Grandman Stan": 5,200 words) work. Fixed from it: "Put in Writer" under answers, visible buttons for the writing project and the journal, and the draft's loops (6 repeated paragraphs, a scene echoing the last ending, stray Chinese characters → 0, with llama.cpp's DRY sampler and a clean-up pass; `dry_penalty_last_n -1` is refused by llama-server, 1024). **LibreOffice (test 5) not tested: Ian wants to rework it "in some other ways" first** — ask what he has in mind. **v2.2 adopted (Ian, 2026-10-01):** gen_data ships v2.2 (`CINMINAI_GUIDE_PROMPT` tries another one in a test daemon). **Found:** with the screen asleep the 1080 Ti stays at P5 (memory 810 MHz) under Vulkan and runs 6× slower — the daemon now keeps the screen awake during a draft; test CUDA with the screen asleep; a diagnostic code for it.

**Next: diagnostics (D51, SPEC §20)** — `cinminai-diag`, an OBD-II for the computer along one operational tree;
first slice §20.8 (boot record, drivers/kernels, updates, disk; codes G101 S301 B401 H401 U101; the command,
the report, the guide's `diagnose` tool), with the evidence of 2026-09-29/30 as the first fixtures. Smaller: Mint's
"Welcome to Linux Mint" on first login (rebrand, SPEC §3.2); `casper-md5check.service` failed in the installed
VM (compare with plain Mint on the Mint box); the cycle-1 list (multi-turn declines, "help me write a
document" declined bluntly). **Exit:** the live USB boots on
the Mint box, the assistant answers a lookup, a system check and a decline; nothing on its disks touched.

**Open from 2026-09-28 (Ian to decide):** declines go wrong a few turns into a conversation in English and
Japanese (the text lists the off-limits topics as things it helps with; 4/12 in a probe) — a daemon guard now,
or a prompt/training fix in cycle 1; mixed-language drift. Lesson cards (`training/kb/lessons.py`) need their
facts rechecked on Mint; search words (`training/kb/search.py`) need native speakers. `lookup_help` is 78.7 %
right on the clean held-out queries. Model into *installed* systems: the installer doesn't copy it yet (needed
before boot check 2: a ubiquity success command or first boot).

Also open in M1 (smaller):
- **Live-USB splash:** the live system's Plymouth theme sits in `casper/initrd.lz` — rebuild or patch it in
  `build-iso.sh` (update md5sum.txt; keep the boot check passing).
- **Automated install test** (preseed / automatic-ubiquity in the test ISO; results disk as today).
- **CI and publishing** — needs Ian: the public `cinminai-apt` repo with Pages, a Hugging Face account/org,
  and where the offline release signing key lives.
- Bonus: an icon-theme variant in the palette; circuit-floor's side towers (optional).

## Waiting on Ian

- Create `cinminai-apt` (public, Pages) and a Hugging Face account/org — only when publishing starts.
- Decide where the offline master signing key lives (e.g. a USB stick he keeps).

## Cycle 1 list (the guide, next model cycle)

**Ian's test runs on the installed system (2026-09-30): "it wasn't much help with troubleshooting and it
wouldn't fill in spreadsheets."** (1) *"Make a spreadsheet for monthly expenses with a list of expenses that
lets me add up the total spent each month"* — declined. Expected before D20's toolkit: say what it can't do
yet, open Calc (`open_app`), walk through it (Date / Item / Amount; a total per month with `SUMIFS`, or a
sheet per month with `SUM`), "works like Excel"; after D20: build it with a preview, one Ctrl+Z. (2) Tonight's
kernel 7.0 fault: the guide sees only `inspect_system`, not the kernel log, dkms, SMART or link errors — D51's
`diagnose` tool is the fix; the case becomes a test. Both into the eval and the training sessions. (3) The guide
with the diagnostics (2026-09-30): invented a command not in the result (`smartctl`), skipped the first finding for a
display question, and said "restart to apply" after a command that a restart undoes — fixed for now with hints in the
data ("the first problem causes the others", "only the commands listed", "don't restart after it"); train
`diagnose` and these habits in cycle 1. (4) "Make me a spreadsheet that tells me which stocks to buy" (eval C05): v2.1 made a blank sheet instead of declining the advice part — teach the decline in cycle 1. (5) Prompt v2.2's misses: "What is Linux?" (B02) searched instead of the built-in help; "Can I watch DVDs?" (B03) a driver check; "Write my essay about Napoleon" (D10) still half-refused (the trained decline of writing, D54); quadratic equations answered directly instead of searched (acceptable, but decide).

Complaint-style how-tos → `lookup_help` in the sessions (the held-out transition loss); formulas in a cell
the user names; German numbered steps; report turns "what it means + offer the action"; the vague set scores
0 % for every model — fix the set; Gemma: keep per-layer embeddings off the GPU, then tune; a new held-out
set; an imatrix quant A/B (D33).

## How to (dev PC)

- **Long jobs:** launch detached — Claude Code stops its own background shells when Windows is low on
  memory: `Start-Process -FilePath "C:\Program Files\Git\bin\bash.exe" -ArgumentList '-lc "…"' -WindowStyle Hidden`.
- **Build + check + boot test, all:** `bash distro/build-all.sh` (packages → repo → ISO + `check-iso.sh`
  → `BOOTTEST=1` ISO → `vm-boottest.ps1`), ~25 min; results in `cinminai-train-out\br-*.log` (`br-done.log`
  sums up) and the boot-test logs folder.
- **Windows gotchas:** Python on Windows writes CRLF (write with `newline='\n'`); Windows PowerShell 5.1
  reads BOM-less UTF-8 as ANSI (keep `.ps1` ASCII); Git Bash's `grep` hides `\r` (use `file`); git here
  stores no symlinks (use a package's `links` file); `\` in Python heredocs — use the Edit tool.
- **Hyper-V:** "Stop Service" in Hyper-V Manager stops `vmms` for everything (a VM keeps running unmanaged);
  starting it again needs admin. Hyper-V's thumbnail call returns 32775 here; the boot test uses its own
  screenshot path.
- **Mint box:** never `pkill -f` over ssh (it matches the ssh command); GPU check before every run; the
  teacher: `~/cin-minai/repo-train/teacherctl.sh start|stop`.

## History, in short

- **2026-09-24/25:** M0 spikes, all GO; stock bakeoff (Qwen3.5-4B 87 %, Gemma 4 E2B 84 % with prompt v2).
- **2026-09-26:** first tune collapsed (16 %, template bug, fixed); micro-sweep showed forgetting; Ian's
  session corpus with journalistic turns.
- **2026-09-26/27:** session merge → runs G, H, HF, HO → held-out → D43; merge/quantize; model card,
  datasheet, release note; licences; M1 build, reproducibility, boot test; branding from Ian's designs.
  Full account: `docs/dev-journal.md`.
