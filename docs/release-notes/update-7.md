# Cin-MinAI update 7

*October 2026. What's new, what changed without asking, and what it still gets wrong. Plain words first; the
details are linked at the end.*

## What's new

All of it is in AICUI, the coding workspace.

- **The Team Table: several AIs on one project.** Click the people icon at the right end of the box you type in. A
  table opens, seen from above, with two seats to start and a + for more. Each seat is a model on your computer
  (free), a cloud model by your own key (paid as it works), or an outside agent: Claude Code or Codex, on this
  computer or another one. One seat wears the crown: the lead plans, hands out the work, and accepts or rejects
  it. You're above it. The paper in the middle holds the session's goals, and you can give each goal to a seat.
  Each file has one writer at a time, and the seats talk one at a time when they need to. **Sit down** starts the
  team. An outside agent on another computer connects over SSH with a key the seat's dialog adds for it, locked to
  that one seat. With that key it can only do the seat's work: no shell, nothing outside the project, no commands
  on your computer.
- **Stop everything**, in the middle of the top bar, ends the whole session at once: the AI and its models, its
  commands and searches, and anything Run started. What was done stays, with undo.
- **Publish your project as a web page.** From the GitHub menu: link the project to a repository (AICUI can make
  a new one for you), save to GitHub, and **Publish as a web page (GitHub Pages)**. Before anything goes, you see
  the files and what AICUI spotted in them: personal details, placeholder text, its own note of your request, and
  workflows. You untick what should stay private. Publishing is done when the page's address loads.
- **Clone a repository.** Paste or type its address and click Find. You see exactly what was searched and what was
  found before anything is copied, so a typo shows up straight away.
- **The GitHub menu always shows what it can do.** Items you can't use yet are greyed out instead of hidden.
- **OpenAI by API key**, beside Anthropic, for every cloud role. The panel icon shows **WEB** or **CLOUD** while
  something is going out.
- **One model, or a team**: the Team button offers one local model on its own again, beside the two-model teams
  and the Team Table.
- **A Benchmark button** measures the setup you're on: the context sizes that really hold on your graphics card,
  and how much code the junior model can carry. A size that failed is never used again.
- **Context sizes you choose**, from the sizes your card holds.
- **Your own look** for the chat and the AI's terminal: background, text colour, font and size, a colour for each
  speaker.
- **Changes you make yourself are in the changelog too**, with undo, and the AI is told about them before its
  next step.

## What changed without asking

These fixes come with the update on their own (PLAN D52), so they're listed here:

- **The models' commands can't reach your keys.** Commands the AI runs could reach the login keyring through the
  session's message bus. Now the sandbox hides that, and also hides the folders where keys and sign-ins live (SSH,
  GnuPG, the keyring, GitHub's sign-in, browser and mail profiles) and any setting whose name says key, token,
  secret or password.
- **Git that changes a repository is AICUI's, not a model's.** A model may look at it (status, log, differences)
  but can't commit, push or set it up. AICUI keeps its own folders out at every save, and a model can't write a
  GitHub workflow.
- **The person's goals stay the person's.** The AI can tick them done, but can't reword or erase them; it erases
  only its own.
- **A lead waits for its junior** instead of asking you whether the junior has finished.
- **Every team's tasks are on the Team Table.** Nothing waits in a queue beside it, a task stopped before it
  started is still answered, and the table's refusals (budget spent, a task too big) reach the lead instead of
  being lost.
- **A command that couldn't reach the internet says so**, and how to ask for it, so the AI doesn't take it for "no
  internet here".
- **Cloud reasoning models get room to think** on top of each step's limit.

## What's sent, and when

Everything update 6 listed still holds. New in this update:

| You ask for | What is sent | Where |
|---|---|---|
| A cloud model, in AICUI | the request, the plan, the files it reads, the last steps | OpenAI or Anthropic, only with your key and a role or a seat you turned on |
| An outside agent at the Team Table | its task, and the project files it reads | that agent (Claude Code, Codex) and its own provider, over your SSH |
| Publish as a web page | the project's files you left ticked | GitHub; the page is **public** |
| Clone a repository | the address you typed | the site in that address (usually GitHub) |

## What it still gets wrong

- **Some models stall on big, open-ended tasks.** At the Team Table, a small cloud model handed "make these five
  files" often stopped to ask; the same work went through when the lead gave exact steps.
- **A lead's final report can claim more than was built.** Check the goals against the program itself before you
  take "done" at its word.
- **One cloud budget per project, shared by every cloud seat.** Several cloud seats spend it faster than one.
- **A local model given a read-only check can run out of steps** before it answers.
- **AICUI is in English** for now; the rest of Cin-MinAI is in all six languages.
- **One-button sign-in with ChatGPT** still waits on OpenAI; an API key works now.

## How it was tested

Ian built real projects in AICUI on his own computer. One was a web page published live on GitHub Pages; another
was a game built at the Team Table with four seats (two cloud models, one local model, and Claude Code joining over
SSH). Behind each run we read every step the models took and fixed what we found. 681 automatic tests and the 48
sandbox and security checks pass.

## Made in the open

Led by Ian McClenathan. Built with Claude (Anthropic) and Codex (OpenAI). The first plan was made with Gemini
(Google). The turn-taking and the table's conversation are Ian's Team Table.

**Details:** the decisions (`docs/PLAN.md`, D35, D61, D62, D93, D95), the Team Table (`docs/SPEC.md` §22.9), the
cloud roles (`docs/accounts-and-cloud.md`), AICUI's rules (`docs/aicui-rules.md`), how the work went
(`docs/dev-journal.md`), and what we repeat for every release (`docs/release-checklist.md`).
