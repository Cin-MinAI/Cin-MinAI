# SPDX-License-Identifier: GPL-3.0-or-later
"""Long sessions: one conversation, continuity underneath (PLAN D40, SPEC §11.5.1).

The guide never carries the whole conversation; this does, and hands it only what matters now:

* **The transcript** — every turn (the person's words, the reply, the tool), one file a day in
  ~/.local/share/cinminai/conversation/, on this computer only, kept KEEP_DAYS days. Never kept (docs/memory-design.md
  §5): the journal's talk (it isn't the guide's turn), secrets (filtered before writing), declined requests.
* **The notebook** — short lines: the person's goal, what was decided and tried, what's open, facts about their
  computer. When the guide's history is trimmed, the turns it drops are folded in by the model (one short call), and
  the person is shown what was kept, line by line, each removable: never silent, always correctable.
* **Recall** — when the person's words match an earlier turn that's no longer in view (keywords, no model), that one
  turn is put in front of the guide.
* **The rundown** — when the sidebar opens after a pause, "Want a quick rundown of where we left off?": yes reads the
  notebook back, no goes straight in; after NOS no's in a row it asks once whether to stop offering (Rule 9, D39).
  New conversation starts the notebook fresh (the transcript stays).
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import time

KEEP_DAYS = 30
MAX_LINES = 12          # the notebook stays short: the guide has ~8K tokens on a card (D27)
PAUSE_S = 2 * 3600      # a rundown is offered after this long without a turn
NOS = 3
CATCH_UP = 8            # turns of an earlier session folded at most, at its first need
WORD = re.compile(r"[^\W\d_]{4,}", re.U)
COMMON = {"what", "when", "where", "which", "with", "this", "that", "there", "have", "does", "your", "about", "from",
          "they", "them", "then", "than", "into", "will", "would", "could", "should", "just", "like", "want", "make",
          "como", "para", "pero", "esto", "esta", "cómo", "qué", "pour", "avec", "dans", "cette", "comment", "wie",
          "eine", "einen", "nicht", "kann", "habe", "mein", "meine", "isso", "você", "como", "computer", "help"}

FOLD = ("Here are earlier turns of a conversation between a person and their computer's assistant, and the notes kept "
        "so far. Write the notes again with what matters from these turns added: the person's goal, what was decided, "
        "what was tried and how it went, what is still open, facts about their computer. One short line each, at most "
        "{most} lines, most important first, in the language of the conversation. Drop small talk and anything already "
        "finished that won't matter again. Write only the lines, each starting with \"- \".\n\nThe notes so far:\n"
        "{notes}\n\nThe turns:\n{turns}")
IN_VIEW = ("\n\nNotes on this conversation so far (kept for you; the person can see them): \n{notes}\n"
           "Use them when they help; don't repeat them unless asked.")
RECALLED = ("\n\nFrom earlier in this conversation ({when}):\nThe person: {user}\nYou: {reply}")


def home() -> str:
    base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return os.path.join(base, "cinminai", "conversation")


def words_of(text: str) -> set[str]:
    return {w.lower() for w in WORD.findall(text or "")} - COMMON


class Notebook:
    def __init__(self, where: str | None = None, clock=time.time) -> None:
        self.where = where or home()
        self.clock = clock
        self.started = clock()
        # the replies of the turns still in the guide's history (by the reply: the person's words may carry the
        # terminal's lines in front there)
        self.recent: set[str] = set()

    # --- files ------------------------------------------------------------------------------------------------
    def path(self, name: str) -> str:
        return os.path.join(self.where, name)

    def state(self) -> dict:
        try:
            with open(self.path("notebook.json"), encoding="utf-8") as f:
                s = json.load(f)
        except (OSError, ValueError):
            s = {}
        return {"lines": list(s.get("lines", [])), "folded_until": float(s.get("folded_until", 0)),
                "nos": int(s.get("nos", 0)), "rundown": s.get("rundown", "offer")}

    def save(self, **change) -> dict:
        s = {**self.state(), **change}
        os.makedirs(self.where, exist_ok=True)
        with open(self.path("notebook.json.tmp"), "w", encoding="utf-8") as f:
            json.dump(s, f, ensure_ascii=False, indent=1)
        os.replace(self.path("notebook.json.tmp"), self.path("notebook.json"))
        return s

    def record(self, user: str, reply: str, tool: str = "") -> None:
        """One turn into today's transcript, secrets filtered out first (passwords, keys, tokens: the terminal's own
        filter, SPEC §12.3; memory-design §5); days past KEEP_DAYS are removed."""
        from .terminal import redact
        user, reply = redact(user), redact(reply)
        now = self.clock()
        os.makedirs(self.where, exist_ok=True)
        day = dt.date.fromtimestamp(now).isoformat()
        with open(self.path(f"{day}.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps({"time": now, "user": user, "reply": reply, "tool": tool}, ensure_ascii=False) + "\n")
        oldest = (dt.date.fromtimestamp(now) - dt.timedelta(days=KEEP_DAYS)).isoformat()
        for name in os.listdir(self.where):
            if name.endswith(".jsonl") and name[:-6] < oldest:
                try:
                    os.remove(self.path(name))
                except OSError:
                    pass

    def turns(self, since: float = 0, before: float | None = None) -> list[dict]:
        out = []
        try:
            names = sorted(n for n in os.listdir(self.where) if n.endswith(".jsonl"))
        except OSError:
            return []
        for name in names:
            try:
                with open(self.path(name), encoding="utf-8") as f:
                    for line in f:
                        try:
                            t = json.loads(line)
                        except ValueError:
                            continue
                        if t.get("time", 0) > since and (before is None or t["time"] < before):
                            out.append(t)
            except OSError:
                continue
        return out

    # --- the notebook -----------------------------------------------------------------------------------------
    def timed(self, pairs: list[tuple[str, str]]) -> list[dict]:
        """The guide's dropped (user, reply) pairs as transcript turns, with their times (the last one that matches)."""
        if not pairs:
            return []
        found = {t.get("reply", ""): t for t in self.turns()}
        return [found.get(p[1]) or {"time": 0, "user": p[0], "reply": p[1]} for p in pairs]

    def lines(self) -> list[str]:
        return self.state()["lines"]

    def fold(self, turns: list[dict], chat) -> list[str]:
        """Fold these turns ({"user", "reply"}) into the notebook with one model call; returns the new lines."""
        if not turns:
            return self.lines()
        s = self.state()
        talk = "\n".join(f"The person: {t['user'][:600]}\nThe assistant: {t['reply'][:600]}" for t in turns)
        out, _ = chat([{"role": "user", "content": FOLD.format(most=MAX_LINES, notes="\n".join(
            "- " + x for x in s["lines"]) or "(none yet)", turns=talk)}], max_tokens=400)
        lines = [x.strip()[2:].strip() for x in out.splitlines() if x.strip().startswith(("- ", "* ", "• "))]
        lines = [x[:200] for x in lines if x][:MAX_LINES]
        if not lines:  # the model wrote nothing usable: keep what was there rather than lose it
            lines = s["lines"]
        last = max((t.get("time", 0) for t in turns), default=s["folded_until"])
        self.save(lines=lines, folded_until=max(s["folded_until"], last))
        return lines

    def remove(self, index: int) -> list[str]:
        lines = self.lines()
        if 0 <= index < len(lines):
            del lines[index]
            self.save(lines=lines)
        return lines

    def fresh(self) -> None:
        """New conversation: the notebook starts empty; the transcript stays (and isn't folded again)."""
        self.save(lines=[], folded_until=self.clock())
        self.recent = set()

    def earlier(self) -> list[dict]:
        """Turns from before this session that aren't in the notebook yet (the last CATCH_UP of them)."""
        return self.turns(self.state()["folded_until"], before=self.started)[-CATCH_UP:]

    def catch_up(self, chat) -> list[str]:
        return self.fold(self.earlier(), chat)

    # --- what the guide sees ----------------------------------------------------------------------------------
    def system_note(self, text: str) -> str:
        """The notebook, and the one earlier turn these words recall, for the end of the guide's system text."""
        out = ""
        lines = self.lines()
        if lines:
            out += IN_VIEW.format(notes="\n".join("- " + x for x in lines))
        hit = self.recall(text)
        if hit:
            when = dt.datetime.fromtimestamp(hit["time"]).strftime("%Y-%m-%d %H:%M")
            out += RECALLED.format(when=when, user=hit["user"][:400], reply=hit["reply"][:600])
        return out

    def recall(self, text: str) -> dict | None:
        """The earlier turn these words match best, if it matches well and isn't still in view: two or more of the
        message's own words, at least half of them (keywords, no model: SPEC §11.5.1)."""
        asked = words_of(text)
        if len(asked) < 2:
            return None
        best, score = None, 0
        for t in self.turns():
            if t.get("reply", "") in self.recent:
                continue  # still in view
            shared = asked & words_of(t.get("user", "") + " " + t.get("reply", ""))
            if len(shared) >= 2 and len(shared) * 2 >= len(asked) and len(shared) > score:
                best, score = t, len(shared)
        return best

    # --- the rundown ------------------------------------------------------------------------------------------
    def offer(self) -> dict:
        """Should the sidebar offer a rundown now? After a pause, with something to tell, unless the person said
        to stop asking."""
        s = self.state()
        if s["rundown"] == "never":
            return {"offer": False}
        last = max((t.get("time", 0) for t in self.turns()[-1:]), default=0)
        something = bool(s["lines"]) or bool(self.earlier())
        quiet = self.clock() - last >= PAUSE_S if last else False
        return {"offer": something and (quiet or last < self.started)}

    def said(self, choice: str) -> dict:
        """The person's answer: yes (counted as a yes), no (after NOS in a row, ask whether to stop), stop, keep."""
        s = self.state()
        if choice == "yes":
            self.save(nos=0)
            return {}
        if choice == "no":
            nos = s["nos"] + 1
            self.save(nos=nos)
            return {"ask_stop": nos >= NOS and s["rundown"] == "offer"}
        if choice == "stop":
            self.save(rundown="never", nos=0)
        elif choice == "keep":
            self.save(rundown="asked", nos=0)  # asked once: not again
        return {}
