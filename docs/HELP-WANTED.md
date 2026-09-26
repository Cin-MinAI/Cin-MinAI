# Help wanted — what we can't do alone

Cin-MinAI is built in the open (PLAN D26). Some things we can't test, check, or know ourselves, so we
say so here instead of guessing. Each item says what we have, what's missing, and what a useful
contribution looks like. Everything you send may be published with credit (or anonymously, if you
prefer).

## Hardware we don't have

**AMD graphics cards (Vulkan) — community beta.** Our only Vulkan numbers come from NVIDIA's Vulkan
path on a GTX 1080 Ti, which says little about AMD. *Wanted:* owners of 6–8 GB AMD cards (e.g.
RX 6600, RX 7600) running `bench/run.py --build vulkan` and `training/eval/guide/run_eval.py`, and
sending the JSON results. See `docs/benchmarks.md`.

**Older gaming laptops — the MVP's real hardware (PLAN D37).** GTX 1050 Ti / 1650 (4 GB),
GTX 1060 / RTX 2060 (6 GB), usually with Intel hybrid graphics. We only have desktop cards (GTX 1080 Ti,
RTX 4070). *Wanted:* guide benchmarks on these laptops (`bench/run.py --build cuda --budget-gb 6`, and
on 8 GB, our target), plus how hybrid-graphics switching, thermals, and battery behave under Linux
Mint. 4 GB cards are below our 6 GB minimum; results are still welcome, but we don't promise support.
If you're on smaller hardware, you're who the reusable parts are for: take the transition corpus,
fine-tune a smaller model, score it with our eval (public and held-out), and publish it — we'll link
good results.

**Everyday laptops with integrated graphics only.** *Wanted:* CPU-only and Vulkan-on-iGPU results from
ordinary 3–6-year-old laptops, so we know what "works everywhere" really means.

**Raspberry Pi and other ARM boards** (later, the tinkerer version). We only have a Pi 5 with 16 GB.
*Wanted:* guide benchmarks on the 4 GB and 8 GB Pi 5 (and Pi 4) once the Pi spike is published.

## Languages

**Native speakers of Spanish, Portuguese (Brazil and Portugal), French, German, and Japanese.** Our
eval and training data check mechanically that answers are in the right language and use the names
Linux Mint actually shows, but no machine can tell whether an answer sounds natural and kind.
*Wanted:* reading a sample of the transition corpus (`training/datasets/transition/`) or the eval
replies in your language and marking what sounds wrong, stiff, or confusing.

## Security

**An outside review before public release.** The assistant can see terminals, read shared web pages
and documents, and ask an admin mechanism to act (always with the user's approval). The design keeps
the model outside the trust boundary (SPEC §8), but we want people who break things for a living to
try. *Wanted:* reviews of the sandbox (`spikes/sandbox`), the admin mechanism (`spikes/admin`), prompt
injection through web pages and documents (SPEC §7.4, §7.10), and terminal-capture privacy (§6.3).

## Knowledge

**The Windows → Linux questions real people ask.** Our knowledge base has 57 topics
(`training/kb/transition.py`). *Wanted:* questions you, your parents, or your customers actually
asked after switching, and anything in our cards that's wrong for your version of Mint.

**Board-level repair know-how** (for the tinkerer version's first pack): known failure points of
common modules (PCMs, TCMs and others), safe ways to read chips in-circuit, and the mistakes that
destroy boards. This comes from technicians, not from models.

## How to send things

Until the repository is public (PLAN §6, "Going public"): contact Ian (Brickmii). Afterwards:
issues and pull requests. Results files are JSON and contain no personal data beyond the hardware
model; check before sending anyway.
