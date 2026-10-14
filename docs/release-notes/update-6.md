# Cin-MinAI update 6

*October 2026. What's new, what changed without asking, and what it still gets wrong. Plain words first; the
details are linked at the end.*

## What's new

- **Its own web search.** The assistant now searches through a search engine of its own on your computer
  (SearXNG, the new `cinminai-search` package). It asks DuckDuckGo and Bing at once, for pages and for pictures,
  starts on the first search and stops itself after 15 minutes without one. Ads and pages that share no word with
  the search are dropped. It says what it is to every site and never gets around a site's bot checks; a site that
  refuses is set aside. If it can't answer, the search goes the old way: DuckDuckGo, then Bing.
- **Models matched to jobs, chosen by you.** A Models view in the sidebar shows which model does each job and lets
  you give a job another model. It searches Hugging Face for every model that runs on your computer, with licences
  labelled, and a Download… button checks a model's files before fetching them.
- **A Requests view.** Each request, its steps, which model did it, and Stop on anything not finished. One request
  waits its turn while another is being answered, instead of both slowing down (the new `cinminai-table` package,
  Ian's Team Table, keeps the turns).
- **Install through the assistant.** Ask for a program by name, or the graphics driver; with an NVIDIA driver in,
  the faster CUDA engine is offered on one card. Each still asks for your password, as in update 5.
- **AICUI, the coding workspace, grew up:**
  - **Two local models as a team.** A bigger model plans the project, lays out its files and reviews; a smaller one
    writes the files it's given. The plan is shown to you once, and what each model is doing stays on screen.
  - **Questions you can see.** When a model needs your answer, its question stays on screen and says who is asking
    and why.
  - **The project remembers.** Your first request is kept, word for word, in the project
    (`original-request.txt`); every project has a screenshots folder (a Screenshots button opens it) where you can
    put pictures to show the models what you see; and the next request, or a restart, picks up where the last
    one left off.
  - **A screen for the models' programs.** A window a model's program opens appears on a hidden screen of its own,
    so the models can test a program with windows without touching yours.
  - **GitHub.** Link the computer to GitHub once, in your own browser; pushes and pulls then work without a
    password, and the sign-in renews itself.
  - **Cloud models, if you want them.** Paste an Anthropic API key once (it goes into your login keyring, never to
    a model) and choose how a cloud model helps:
    - **Finisher:** the local models build it to a running point, the cloud model finishes it.
    - **Lead:** the cloud model directs and your local models do the work it hands them (write, fix, check, test,
      fetch), which keeps the cloud bill small.
    - **Advisor:** your local models do all the work and ask the cloud model only when they're stuck, at most five
      times a request. Each question and answer shows in its own blue ☁ bubble, with what the project has spent.
    - **Exclusive:** the cloud model does everything.

    The box at the bottom right picks the cloud model, from the provider's own list with prices. Every call's cost
    is logged and checked against a budget you set for the project. OpenAI comes once its sign-in is open to us.

## What changed without asking

These fixes come with the update on their own (PLAN D52), so they're listed here:

- **A locked keyring is said, not mistaken for a missing key.** With automatic login, the login keyring stays
  locked after a restart; AICUI now says so and offers to unlock it, instead of asking for a key you already gave.
- **The live USB reads the model once, start to finish,** before the assistant starts, with progress in the header
  (scattered reads from the stick made the first start very slow).
- **The model offer waits** until the first time you ask, not ten minutes after every boot.
- **The assistant moves back onto the graphics card** once it has room again.
- **The sidebar's writing tool no longer glitches** when no writing project is open.

## What's sent, and when

Everything update 5 listed still holds. New in this update:

| You ask for | What is sent | Where |
|---|---|---|
| A web search | the search words you see on the card | DuckDuckGo and Bing (through the search on your computer) |
| A model search or download | the search words, the model's name | Hugging Face |
| GitHub, in AICUI | the project's files, when you push | GitHub, to the repository you chose |
| A cloud model, in AICUI | the request, the plan, the files it reads, the last steps | Anthropic, only with your key and a role you turned on |

Each time, you're told first what goes where. Nothing goes to a cloud model unless you turn a role on.

## What it still gets wrong

- **Big projects outgrow small models.** Once a project has many files, the local models can lose track of it;
  a cloud model in the Lead or Finisher role carries it further, at a cost.
- **A cloud model can lose the thread too.** In our testing, a cloud model got stuck on a large project and the
  local team picked it back up. Switching roles in the middle of a project works; that's how we found it.
- **The cloud is Anthropic only, by API key**, for now.
- **The new search's own words are English** for now; the rest of the cards are in all six languages.

## How it was tested

Ian built real projects in AICUI on his own computer, run after run, local and cloud; behind each run we read every
step the models took and fixed what we found. 600 automatic tests and 20 security tests pass. A new installation
image was built and passes the boot and install tests in a virtual machine.

## Made in the open

Led by Ian McClenathan. Built with Claude (Anthropic) and Codex (OpenAI). The first plan was made with Gemini
(Google). The search is SearXNG, made by its community; the turn-taking is Ian's Team Table.

**Details:** the decisions (`docs/PLAN.md`, D93–D97), the cloud roles (`docs/accounts-and-cloud.md`), how the work
went (`docs/dev-journal.md`, 2026-10-07 to 2026-10-14), and what we repeat for every release
(`docs/release-checklist.md`).
