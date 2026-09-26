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

**Everyday laptops with integrated graphics.** Our main users (PLAN D34) mostly have laptops with
Intel or AMD integrated graphics, not a 6 GB card. We've measured a desktop CPU (i7-4790K) but no
integrated GPU. *Wanted:* results from ordinary 3–6-year-old laptops — CPU-only and Vulkan on the
integrated GPU — so we know what "works everywhere" really means.

**Raspberry Pi 5 and other ARM boards** (later, the tinkerer version). *Wanted:* guide benchmarks on
ARM once the Pi spike is published.

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
