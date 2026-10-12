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
the package like GitHub's. Until then OpenAI works with an API key.

## Build order

1. **Accounts and GitHub:** the keyring store for accounts; the device flow, renewal and sign-out; the git credential
   helper; AICUI's GitHub button — sign in, link the project to a repo (new or existing), push, pull.
2. **Cloud:** API keys for Anthropic and OpenAI (pasted once into the keyring); a cloud backend with schema-held tool
   calls; AICUI's Cloud button — provider, model, role (Senior or Exclusive); what's sent said first.
3. **The models' own GitHub work** (push and pull as tools, under the same approvals); Sign in with ChatGPT when the
   client ID comes.
