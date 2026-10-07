# Release checklist

Everything we repeat for every release. Two kinds: an **update** (signed packages to the apt repository, like
updates 1–4) and an **ISO release** (the installable image, twice a year with Mint's point releases and the model
cycle, PLAN D31). An ISO release does the update list too. Tick in order, and write down what was skipped and why.

## 1. Every release: before building

- [ ] **Tests pass** (in WSL, from the repo):
      `PYTHONPATH=src python3 -m unittest discover -s tests/unit` (includes `test_packaging`: everything the shipped
      code imports is in a package), `PYTHONPATH=src python3 tests/security/check_security.py` (the sandbox probes
      with the private `pasta` network, plus the admin and browser-boundary tests).
- [ ] **New features have their help card** (D84) and **their UI words in all six languages** (D25: en, es, pt, fr,
      de, ja).
- [ ] **The public promise matches the feature, in the same release** (D86): README, website, release note. Nothing
      promised before it ships.
- [ ] **Operational fixes are named in the release note** (D52: they ship without opt-in, but never silently).
- [ ] **Admin mechanism changed** (`src/cin_minai/admin`, its policy or unit)? Run the live polkit test on the test
      SSD, from a terminal on its own screen, never over SSH: `tests/security/README.md`.
- [ ] **Long inputs tested against the model's window** (the summary prompt once hit 28.8K tokens of a 16K window).

## 2. Every release: on the test SSD, before signing

- [ ] **Build all packages at HEAD with the release public keyring**, in WSL:
      `SIGNING_GNUPGHOME=~/cinminai-build/gnupg-release-public SIGNING_KEY=7EA74B93128AA95865E2BA3977CA19E6264470F6 bash distro/build-packages.sh`.
      Never commit while a build runs (the version is computed from the last commit, per step).
- [ ] **Import-test the packaged code on the SSD** from the unpacked .debs before installing (`dpkg-deb -x`, then
      `python3 -P -c "import cin_minai.daemon.service, …"` with that `PYTHONPATH`).
- [ ] **Install with `~/cinminai-debs/install-debs.sh *STAMP*.deb`.** Short glob lines (long ones break when
      copied). If a dependency rule changed, install **all** packages. apt must list no removals.
- [ ] **Ian's hands-on round** (D88): he asks real questions on the test SSD and feels it out; the lead reads every step
      behind each reply (a watcher on the assistant's D-Bus signals) and turns findings into fixes, cards and eval tasks.
- [ ] **Look at the real screen** after a real run of each changed feature (cut-off lists, over-flagging and wrong
      words only showed up there), with the real guide model.
- [ ] Put Ian's commands in `~/Desktop/prompts.txt` on the SSD.

## 3. Update: sign and publish

- [ ] **Ian signs** with the key stick (D72), in a WSL terminal: `bash /mnt/c/Users/Ian/Cin-minAI/distro/release-sign.sh D`.
- [ ] Copy `$M1/repo` (`dists`, `pool`, the keyring `.asc`) into a **fresh clone** of `Cin-MinAI/cinminai-apt`,
      bump its README line, push from Windows git.
- [ ] **Check it live** the way apt sees it: `cinminai-devtools/apt-check.sh STAMP` (local helper, not in the repo).
- [ ] Push the source; release note; website card if people will notice it; `docs/dev-journal.md` and
      `docs/RESUME.md`.

## 4. ISO release: in addition

**About six weeks before** (also the model nomination cutoff, D41):
- [ ] **The model cycle**: PLAN "Model-cycle checklist (D31)": candidates, runtime, bakeoff, fine-tune, gate, model
      card.
- [ ] **New Mint point release:** re-run `training/eval/guide/extract_labels.py`, re-check every card in `training/kb` on a real install
      (names, menus, shortcuts), note renamed or replaced programs.
- [ ] **llama.cpp pin:** loads every shipped model; CUDA still built for Pascal (sm_61); Pascal driver branch still
      ≤ 580.x; Vulkan and CPU builds.

**Coverage and inventory** (from the new ISO's own files):
- [ ] **D84 coverage re-run:** `training/kb/coverage_inventory.py` + `coverage_match.py`, name-only matches read by
      hand, `docs/d84-coverage.md` updated. The "must" row (our own features) is empty; the base 4B guide passes
      the eval for covered cards in all six languages.
- [ ] **Package inventory:** `distro/iso-package-inventory.py <iso> docs/iso-<version>-packages.tsv`.

**Build and test:**
- [ ] `bash distro/build-all.sh` (detached): the ISO, `check-iso.sh` (upstream plus exactly our packages, upstream boot
      setup, md5sums and the guide model on it), the VM boot test and the VM install test. Plus
      `check-iso.sh --rebuild` (reproducible: same SHA-256 twice).
- [ ] New dependencies are named in `check-iso.sh`'s list (anything else that appears still fails).
- [ ] **Firefox extension changed?** Signed by Mozilla: `distro/firefox-sign.py`.
- [ ] **Two boot checks on real hardware** (D45): the live USB on the Mint box (boot check 1), then an install onto the
      test SSD (boot check 2): the screen comes up, the guide answers, the assistant runs on the GPU.

**Publish:**
- [ ] ISO to Hugging Face (`CinMin/Cin-MinAI-OS`) with its SHA-256; the website's download link and checksum.
- [ ] Release note: what's new, what was fixed (D52), the model cycle's result (D31), known issues.
- [ ] README credits current (every contributor plainly).
- [ ] The apt repository has every package the new ISO carries (section 3).
