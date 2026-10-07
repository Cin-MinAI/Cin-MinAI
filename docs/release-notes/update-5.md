# Cin-MinAI update 5

*October 2026. What's new, what changed without asking, and what it still gets wrong. Plain words first; the
details are linked at the end.*

## What's new

- **The news, as who says what.** Ask "pull up the news about…" or "what's the latest on…". It shows what's on
  hand, in three parts: each news outlet's headline word for word with the outlet and date; posts from Reddit and
  Mastodon, credited to who posted them, under a heading that says these are claims nobody checked; and the
  subject's own pages, government sites and patent records. **It never says what happened, only who says what**, so
  you can decide for yourself. The assistant's model writes none of it, so nothing can be turned into a claim a
  source didn't make. Add "on Reddit" to ask Reddit only. X and Bluesky aren't included: searching them needs an
  account, and every report says so.
- **News watches.** Say "keep me up to date on…" or "the news about … every morning". A card shows the topic, the
  time and where the topic will be sent every day; nothing is set up until you click Set up. After the first look
  it checks once a day and shows only what's new, with a notification. Find them under **Standing tasks**, on the
  assistant's start screen or by right-clicking its icon in the panel: pause, resume or delete them there.
- **Find a video and summarize it.** "Search YouTube for a video on how to make donuts and summarize it": it shows
  the search first, lists the videos, opens the first in Firefox, and summarizes it once it's playing. Ads play as
  they normally would; the assistant leaves the player alone.
- **Write an email.** "Write an email to … about …": it writes the email and opens it as a draft in your mail
  program. You read it and send it yourself.
- **Administrator actions, one at a time, with your password every time.** When the assistant proposes something
  that needs an administrator (installing a program, changing a system setting), you see what it is and click
  Allow, then the system asks for your password. Every request asks again; the assistant is never the
  administrator. Each one is written to a record that can't be quietly changed.
- **Keys for sources that need one.** Some sources only answer people with a free key. When one is needed, the
  assistant shows the steps to get it and a box to paste it in; you register yourself. The key goes into your login
  keyring and never into the conversation. (No source uses this yet.)
- **The time.** Ask what time it is and you get the computer's own clock, in your language.
- **After an update**, the assistant says it was updated, and while one waits it offers "Restart now".

The new cards and messages are in all six languages (English, Spanish, Portuguese, French, German, Japanese). Some
older parts of the sidebar are still English only.

## What changed without asking

These fixes come with the update on their own (PLAN D52), so they're listed here:

- **Bing backs up DuckDuckGo.** Web searches still go to DuckDuckGo first. If DuckDuckGo asks for a pause (it does
  after many searches in a short time), the search goes to Bing instead, rather than failing. Every search card
  says this beforehand: "DuckDuckGo (or Bing, if DuckDuckGo asks for a pause)". The news uses Bing for official
  pages.
- **The built-in help was corrected.** Two help cards described things that aren't built yet: a WEB sign in the
  panel when something is sent, and an offline-mode switch with a "go online for updates" button. Offline mode is
  planned; until it's here, the help now says how to disconnect with the network icon. The privacy card now lists
  exactly what is sent, and where.
- **A reply that starts repeating itself is stopped** and trimmed to its last good sentence.
- **The sidebar fits narrow screens** and stays on the screen.

## What's sent, and when

Nothing you type leaves the computer unless you ask:

| You ask for | What is sent | Where |
|---|---|---|
| A web search | the search words you see on the card | DuckDuckGo, or Bing if DuckDuckGo asks for a pause |
| The news | the topic | Google News, Bing, Reddit, Mastodon |
| A news watch | the topic, once a day, until you pause or delete it | the same as the news |
| A video summary | the video's address | YouTube, for its preview pictures (the transcript is read from the page already open in Firefox) |

Each time, a card first shows the exact words and where they go. Nothing about you or this computer is sent.

## What it still gets wrong

- **Searches for a long question can be loose.** A news watch on "local AI models that can code on 12 GB graphics
  cards" finds more than one on "local coding models". Short topics work best.
- **The same name can mean two things.** "Ice Cube" brought the rapper and the IceCube neutrino observatory (which
  won the 2026 Nobel Prize in physics). The assistant shows what the outlets wrote; it doesn't guess which you meant.
- **Reddit's search is broad.** Posts are now shown only when they carry the topic's words, which removed the
  unrelated ones we saw in testing, but a loosely related post can still get through.
- **The guide model** still sometimes checks the computer when you asked how to do something, and its Japanese
  steps for a VPN are incomplete. These are for the next model cycle.

## How it was tested

Ian used it hands-on on a real installation, round after round, asking real questions in his own words; behind each
reply we read every step the assistant took, and fixed what we found. 414 automatic tests and 20 security tests
pass. The administrator service was tested live, with the password prompts on the screen.

## Made in the open

Led by Ian McClenathan. Built with Claude (Anthropic) and Codex (OpenAI); Codex built the administrator service and
the repeated-reply stop. The first plan was made with Gemini (Google).

**Details:** the decisions (`docs/PLAN.md`, D85–D92), how the work went (`docs/dev-journal.md`, 2026-10-06 and
2026-10-07), and what we repeat for every release (`docs/release-checklist.md`).
