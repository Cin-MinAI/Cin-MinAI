# The guide in Cin-MinAI — cycle 0

*Release note for the first model cycle, September 2026. Plain words first; the details are linked at the end.*

## What the guide is

The guide is the small assistant built into Cin-MinAI. It runs on your own computer, on your own
graphics card, and it works without the internet. Nothing you type is sent anywhere.

It is there to help you use this computer, especially if you're coming from Windows:

- **"Where is…?" and "How do I…?"** It looks the answer up in the built-in help and tells you, step by
  step, using the names you actually see on your screen, in your language.
- **"Is something wrong?"** It can check the computer for you — free space, updates, the internet, the
  printer, sound, the screen, the battery, the graphics driver — and tell you what it found.
- **Your documents.** When you share a LibreOffice document with it, it can answer from what's in it,
  add a row, put in a total, fix the mistakes in a sentence, or change a slide. You see every change
  before it happens.
- **Staying safe.** It can help you spot scam emails, calls and pop-ups.
- **Everything else, it tells you kindly that it can't help** — and what it can help with. It doesn't
  give medical, legal or money advice, and it never gives you commands to type.

It speaks **English, Spanish, Portuguese, French, German and Japanese**.

## What's new in this cycle

This is the first cycle, so everything is new. We tested six small models and picked
**Qwen3.5-4B** (made by Qwen, open licence). Then we taught it more about the move from Windows and about
working with documents.

On our tests, the guide we ship answers **92 out of 100** questions right, where the same model without
our teaching gets 87. On a second set of questions it had never seen, it gets 73 against 66. It is
clearly better at:

- **explaining how to do things** step by step,
- **saying no politely** to questions that aren't about the computer,
- **staying within its job**,
- **working with your spreadsheets, letters and slides.**

## What it still gets wrong

We tell you this so you know what to expect:

- **When you describe a problem, it sometimes checks the computer instead of telling you how to fix
  it.** For example, "all the text on my screen is too small" — it may look at your screen settings
  instead of explaining how to make the text bigger. If that happens, ask "how do I make the text
  bigger?" and it will tell you. We're fixing this for the next cycle.
- **In German, it sometimes explains steps in one paragraph instead of a numbered list.**
- **It sometimes mixes up memory and disk space** when you ask how much memory the computer has.
- Spanish was a little weaker on the questions it had never seen before.

## You're in charge

- **Nothing happens without you.** Installing a program asks for your password. Changes to your
  documents are shown to you first, and you can undo them in one step.
- **You can switch back.** The original, untaught version of the model stays available, one switch
  away, if you prefer it.
- **Your computer, your choice.** The guide we ship is a good starting point for most computers. If you
  like to tinker, you can run the same tests on your own machine and pick what suits it best.

## What it needs

- A graphics card with **6 GB** of memory or more (8 GB is better). The guide itself uses about 3 GB,
  leaving room for your desktop.
- It also works without a graphics card, but much more slowly.
- **Install Cin-MinAI rather than running it from the USB stick** — installed, the guide answers in a
  few seconds; from the stick it has to use the processor and takes minutes. An **SSD** is recommended,
  an **M.2 NVMe** drive ideal.

## Made in the open

Everything behind this choice is public: the tests, every result (including the models that lost and
the attempts that failed), the training data and how it was made, and the reasons for each decision.
The training text was written only by an open model running on our own hardware.

Led by Ian McClenathan. Built with Claude (Anthropic) and Codex (OpenAI); the first plan was made with
Gemini (Google).

**Details:** the model card (`training/guide/MODEL_CARD.md`), the training data
(`training/datasets/DATASHEET.md`), the full story (`docs/guide-model-journal.md`), and the decision
(`docs/PLAN.md`, D43).
