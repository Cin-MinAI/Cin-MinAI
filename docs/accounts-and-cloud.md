# Accounts and cloud models (2026-10-11)

Ian, 2026-10-10/11: AICUI's GitHub and Cloud buttons, reserved since 2026-10-09. "My goal is to make the key transfer
one time, and you never have to touch it again because its all on the system like it does for me with Pycharm. You
just do the sign in through the browser and it links up." Cloud has two roles: **Senior** (a cloud model leads, the
local model is the Junior) and **Exclusive** ("if the user doesnt want any local models on their stuff that should be
an option"). Sign-in by API key for power users and by account (OAuth) where a provider allows it. With voice ("a
Jarvis setup") coming later, the approvals are one mechanism it can plug into.

## What each provider offers a person (checked 2026-10-11)

| Provider | Sign-in an app like Cin-MinAI may use | What the person pays with | Notes |
|---|---|---|---|
| **GitHub** | A **GitHub App with the device flow**: AICUI shows a short code, the person approves on github.com in their own browser | free | User tokens expire after 8 hours and renew silently with a refresh token for 6 months; limited to what both the app and the person may do, on the repos the person installs it on. No app secret ships in the ISO. |
| **OpenAI** | an **API key**, or **Sign in with ChatGPT** (OAuth 2.0 + PKCE + OpenID Connect at auth.openai.com) | API: usage billing. Sign in with ChatGPT: the person's Plus/Pro plan allowance, with weekly caps they set per app | Open-source desktop apps without a backend are explicitly supported: a public client, PKCE, a loopback redirect (`http://127.0.0.1`). A client ID (`oaiapp_…`) comes after OpenAI's interest form. Access tokens last 1 hour; refresh tokens 30 days, replaced at each refresh. Calls go to the Responses API. |
| **Anthropic** | an **API key** only | usage billing (prepaid credits in the console) | Claude Free/Pro/Max sign-in is for Anthropic's own apps only (enforced since 2026-01, restated 2026-10-07): a third-party app may not offer it. Haiku 4.5 $1/$5 per million tokens in/out, Sonnet 4.6 $3/$15, Opus 4.8 $5/$25. |

## The security model (one for every sign-in)

1. **Keys and tokens live in the login keyring** (Secret Service, unlocked by the login password — as the journal's key
   and the news sources' keys already do). Never in a file, a log, the action record or the conversation.
2. **No model ever sees a key or a token.** Tools act through code that reads the keyring at the moment of the request:
   the cloud backend for its calls, a git credential helper of ours for pushes and pulls. A key pasted into the chat is
   caught before the model sees it (keys.looks_like_key).
3. **One hand-over, then it keeps itself.** Expiring tokens renew themselves from their refresh tokens; the person signs
   in again only when a refresh token runs out (GitHub: 6 months unused; OpenAI: 30 days unused) or they sign out.
4. **Least access.** GitHub: Contents read/write and Metadata read on the repos the person chooses (Administration
   write only to create a new repo). OpenAI: the plan-usage scope only (no conversations, no account context).
5. **Every outward action follows the permission modes**: Ask asks each time; Auto asks once per repo (or per provider)
   per session; No permissions is the person's own choice. What goes out to a cloud model is said before it's sent, as
   with web search. Voice later: a spoken yes answers the same questions — no second path.
6. **Sign out removes the keyring items and revokes** where the provider allows it (GitHub: the person can also revoke
   the app at github.com/settings/applications).

## GitHub: the app to register (Ian, on the CinMin bot account)

github.com → Settings (of the CinMin account) → Developer settings → GitHub Apps → **New GitHub App**:

- **GitHub App name:** `Cin-MinAI` (or `CinMin` if taken)
- **Description:** "The Little Bot that Could — Cin-MinAI's assistant links your projects to GitHub from your own PC."
- **Homepage URL:** `https://cin-minai.github.io`
- **Callback URL:** leave empty (the device flow doesn't use one); if the form insists, `https://cin-minai.github.io`
- **Expire user authorization tokens:** ✔ on
- **Request user authorization (OAuth) during installation:** off
- **Enable Device Flow:** ✔ on
- **Webhook → Active:** off (nothing is sent to us; there's no server)
- **Repository permissions:** Contents **Read and write** · Metadata **Read-only** (required) · Administration **Read and
  write** (only to create a new repository for a project; leave it off if you'd rather create repos on github.com)
- **Account permissions:** none
- **Where can this GitHub App be installed?** Any account
- **Create GitHub App**, then copy its **Client ID** (starts `Iv`). No client secret and no private key are needed for
  the device flow — don't generate them. The Client ID is public: it ships in the package.

Each person then signs in from AICUI (device code) and installs the app on their account — all repositories, or the ones
they pick. AICUI shows the install page when the app isn't installed yet.

**Registered 2026-10-12:** "AICUI GitHub" (`aicui-github`, app id 5291496, owner `Brickmii`), Client ID
`Iv23lifpctLOPB9TqgNO` (in `/usr/share/cinminai/accounts.json`, cinminai-daemon); the device flow answers. The first
app (2026-10-11, on the CinMin bot account `cinminaidevbox`) can't sign anyone in while GitHub keeps that new account
flagged (support ticket sent); it isn't used. GitHub asks for a private key to exist before an app can be installed;
keep it off this repository (AICUI never uses it).

## OpenAI: Sign in with ChatGPT (Ian)

Fill in OpenAI's interest form for Sign in with ChatGPT (openai.com/form/sign-in-with-chatgpt-interest) for Cin-MinAI:
open-source, desktop, no backend, public client with PKCE and a loopback redirect. When the client ID comes, it ships in
the package like GitHub's. Until then OpenAI works with an API key. **Sent 2026-10-16** by Ian, with a link to the project's page; OpenAI reviews the requests quarterly.

**Built 2026-10-16: OpenAI by API key** (`inference/cloud.py`, `class OpenAI`). The key is pasted once in AICUI's Cloud
models menu ("Add an OpenAI API key…"), checked with the free model list, and kept in the login keyring like
Anthropic's. Calls go through OpenAI's **Responses API** — the GPT-6 models take tools only there — with the same
contract as Anthropic's: the budget checked first, every call logged with its cost, the agent's step as one required
function call among flat tools (`strict` off, so optional fields stay optional), earlier steps sent back as the calls
and results they were, pictures as input images, `store: false` (OpenAI keeps nothing of the call for later), and low
reasoning effort on the reasoning models to spend less. Prices from OpenAI's pricing page, read 2026-10-16 (dollars per
million tokens, input / cached input / output): GPT-6.1 Sol 2.00 / 0.10 / 10.00 (the default), GPT-6 Luna 0.10 / 0.01 /
0.50, GPT-6 Astra 10.00 / 1.00 / 50.00, GPT-5.6 Terra 2.00 / 0.20 / 12.00, GPT-5.6 Luna 0.20 / 0.02 / 1.20. All four
roles (Finisher, Exclusive, Lead, Advisor) work with either provider; the provider follows the model chosen.

**The panel's WEB / CLOUD sign** (`inference/reach.py`, the applet): every request out of the daemon or AICUI is
marked while it's out and eight seconds after — CLOUD for a cloud model's API, WEB for anything else (our own search
and git to GitHub mark themselves) — and the panel icon shows WEB or CLOUD beside it, its tooltip naming where;
nothing extra when everything is local. Each request is also a line in a local record of where things were sent
(`~/.local/state/cinminai/sent.jsonl`: when, what kind, where — never what was in it), the start of D28's "what has
this computer sent?" page.

## Build order

1. ✔ **Accounts and GitHub** (built 2026-10-11/12, signed in and working on Ian's PC; using it waits for GitHub to lift
   the flag on the CinMin bot account, the account it's meant for): the keyring store for accounts; the device flow, renewal and sign-out; the git credential
   helper; AICUI's GitHub button — sign in, link the project to a repo (new or existing), push, pull.
2. ◐ **Cloud** (Anthropic built 2026-10-12: the key pasted once into the keyring and checked with a free call; the
   cloud backend — every action its own flat tool (one nested tool gave Haiku 25 unusable replies in a row), pictures
   as image blocks, prompt caching, every call's cost logged in
   `.cinminai/cloud-usage.jsonl`, a budget per project checked before each call; AICUI's Cloud models menu with
   **Finisher** (the local models built it, the cloud takes it to working, Ian 2026-10-12: "develop mostly locally and
   then have cloud come in and finalize") and **Exclusive**; **Lead** built the same day (Ian: "turn the 2 local models
   into tool calls locally to conserve tokens. Fetch this, write that, test this, correct that with this"): the cloud
   model is the Senior, with the plan, assign (write, fix, check, test), brief, distill, LFD, follow-up and review;
   **one** local contributor (the coding model) or **two** (team B's pair: the 35B writes, fixes and tests, the 9B
   fetches, reads and briefs; LFD between the two of them), so the cloud's tokens go to directing. OpenAI next).
   Seen on test11 (2026-10-12): Haiku as Finisher alone lost the thread at every stop and re-read the same files;
   the local team picked it up at once — the reason for Lead, and for the carry-over between requests.
   **Advisor** built 2026-10-13 (Ian: "this was about incorporating the local with the cloud, not 2 cloud models"):
   the local models do all the work as chosen (one model, team A or B), and the lead local model has an `advisor`
   tool — its question goes to the cloud model with the request, the goals, the last 8 steps and what the checks find,
   and the advice comes back as its result; AICUI asks by itself after 12 steps without progress, before the stuck
   rule stops the work; 5 calls a request at most, each against the budget. The pattern of Anthropic's advisor tool
   (a cheap model consulting a stronger one in the same request) turned around: there both models are Anthropic's and
   run on their servers, so it can't serve a local model; here AICUI makes the call. Within Anthropic's terms: the
   person's own API key, the outputs used in their app, nothing trained on them. Was: **Cloud:** API keys for Anthropic and OpenAI (pasted once into the keyring); a cloud backend with schema-held tool
   calls; AICUI's Cloud button — provider, model, role (Senior or Exclusive); what's sent said first.
3. **The models' own GitHub work** (push and pull as tools, under the same approvals); Sign in with ChatGPT when the
   client ID comes.
