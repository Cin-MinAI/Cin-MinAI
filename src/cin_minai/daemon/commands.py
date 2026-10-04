# SPDX-License-Identifier: GPL-3.0-or-later
"""What a command does, from the system itself — for "Explain" on a command card (M3, SPEC §6.4).

Measured 2026-10-04: asked to explain `sudo apt upgrade` and `chmod +x backup.sh`, the guide looked up "command…",
drew the command-not-found card, and called both commands wrong. So the facts go in front of the question (§11.5:
state outside the model): a short table for the subcommands and flags newcomers meet, the manual's one-line
summary (whatis), and bash's own help for builtins (cd, source).
"""

from __future__ import annotations

import re
import shlex
import subprocess

# the question the sidebar sends (its words.explain_question puts the command after it, in backticks)
EXPLAIN = {
    "en": "What does this command do, in plain words, and does it change anything on my computer?",
    "es": "¿Qué hace este comando, en palabras sencillas, y cambia algo en mi ordenador?",
    "pt": "O que este comando faz, em palavras simples, e ele muda alguma coisa no meu computador?",
    "fr": "Que fait cette commande, en mots simples, et est-ce qu'elle change quelque chose sur mon ordinateur ?",
    "de": "Was macht dieser Befehl, in einfachen Worten, und ändert er etwas an meinem Computer?",
    "ja": "このコマンドは何をしますか？簡単な言葉で教えてください。パソコンに何か変更を加えますか？",
}

# (program, word or flag after it) -> what it does; checked against apt 2.7, pip 24, bash 5.2, coreutils 9.4
KNOWN = {
    ("apt", "update"): "refreshes the list of programs and versions available; installs nothing",
    ("apt", "upgrade"): "installs newer versions of the programs already installed",
    ("apt", "full-upgrade"): "installs newer versions, and may add or remove packages to do it",
    ("apt", "install"): "downloads and installs the named programs and what they need",
    ("apt", "remove"): "uninstalls the named programs (their settings files stay)",
    ("apt", "purge"): "uninstalls the named programs and their system-wide settings",
    ("apt", "autoremove"): "removes packages that were only installed as dependencies and aren't needed now",
    ("apt", "search"): "lists programs whose name or description matches; installs nothing",
    ("pip", "install"): "downloads Python libraries from the internet and installs them (into the active venv)",
    ("pip", "uninstall"): "removes Python libraries",
    ("python3", "-m venv"): "creates a Python virtual environment: a folder with its own python and pip",
    ("chmod", "+x"): "marks a file as a program that may be run; changes nothing else",
    ("rm", "-r"): "deletes folders, with everything inside them",
    ("rm", "-f"): "deletes without asking, and without complaining about missing files",
    ("sudo", ""): "runs the rest of the line as administrator (root); asks for your password",
    ("source", ""): "runs a script inside the current terminal (how a venv is switched on)",
}
ALIASES = {"apt-get": "apt", "pip3": "pip", "python": "python3", ".": "source"}


def is_explain(text: str) -> str | None:
    """The command, if this message is an Explain question."""
    for q in EXPLAIN.values():
        if text.startswith(q):
            m = re.search(r"`([^`]+)`", text[len(q):])
            return m.group(1).strip() if m else None
    return None


def _manual(program: str) -> str | None:
    try:
        r = subprocess.run(["whatis", "-l", program], capture_output=True, text=True, timeout=3)
        line = next((l for l in r.stdout.splitlines() if l.startswith(program + " ")), None)
        if line:
            return line.split(" - ", 1)[1].strip()
        r = subprocess.run(["bash", "-c", f"help -d {shlex.quote(program)}"], capture_output=True, text=True,
                           timeout=3)
        if r.returncode == 0 and " - " in r.stdout:
            return r.stdout.split(" - ", 1)[1].strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return None


def describe(command: str) -> list[str]:
    """Plain facts about each part of the command, in order."""
    try:
        words = shlex.split(command)
    except ValueError:
        words = command.split()
    facts = []
    while words:
        prog = ALIASES.get(words[0], words[0])
        rest = words[1:]
        known = [what for (p, w), what in KNOWN.items() if p == prog and (
            w == "" or (w.startswith("-") and " " not in w and any(a.startswith("-") and not a.startswith("--")
                                                                   and set(w[1:]) <= set(a[1:]) for a in rest))
            or (w.startswith("+") and w in rest) or (" " in w and " ".join(rest[:2]) == w)
            or (rest[:1] == [w]))]
        if known:
            facts += [f"{words[0]}: {k}" for k in known]
        else:
            manual = _manual(prog)
            if manual:
                facts.append(f"{words[0]}: {manual} (from the manual)")
        if prog == "sudo" and rest:  # the command sudo runs gets its own facts
            words = rest
            continue
        break
    return facts


def context(command: str) -> str:
    facts = describe(command)
    head = "[About this command — it's a valid command; explain what it does and whether it changes anything, " \
           "directly, without looking it up."
    return head + ("\n" + "\n".join(facts) if facts else "") + "]"
