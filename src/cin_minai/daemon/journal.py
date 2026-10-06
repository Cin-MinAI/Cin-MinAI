# SPDX-License-Identifier: GPL-3.0-or-later
"""The journal (PLAN D55): an assistant that only asks about the person — what happened, how it felt, what they
think, what changed — and, when they press the button, writes the entry with the date and time. An entry can
be private.

* Entries live in Documents/Journal/: "2026-10-01 21.30 — <title>.odt", and journal.json (the index).
* **The conversation isn't saved to disk** — only the finished entry (a private day leaves no plain transcript).
* **Private** (Ian: "just a little 4 digit pin is fine"): the entry is encrypted (GnuPG, AES-256) with a random
  key kept in the login keyring (Secret Service), so a copied disk can't be read without the login password; the
  PIN (a salted PBKDF2 hash in journal.json) opens it, inside the sidebar only — never as a file in Writer, so no
  plaintext lands in LibreOffice's recovery files. A 4-digit PIN is a lock against people looking, not strong
  encryption on its own: the keyring is what protects the file. The assistant never reads a private entry while
  it's locked.
"""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
import subprocess
import tempfile
import threading
from typing import Callable

from . import odt

ROOT = os.path.join(os.path.expanduser("~"), "Documents", "Journal")
PIN_ITERATIONS = 200_000
KEYRING_LABEL = "Cin-MinAI journal key"

INTERVIEWER = """You are a journal companion built into this computer. You only ask the person about \
themselves — what happened today, who they were with, how it felt, what they think about it, what changed, what \
they want to remember — like a kind, curious interviewer. Ask one short question at a time, in their language, \
following up on what they just said. Never give advice, never judge, never steer them to a topic they didn't \
raise, and don't talk about yourself. If they say they're done, tell them to press "Write today's entry"."""

ENTRY_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["title", "entry"],
                "properties": {"title": {"type": "string"}, "entry": {"type": "string"}}}
ENTRY_PROMPT = """Write the person's journal entry for {when}, in the first person, as they would write it, in \
their language, from what they said in this conversation. Use their own words and phrases where you can. Don't \
add events, feelings or opinions they didn't express, and don't add advice or a moral. As long as what they said \
allows, no padding; paragraphs, no headings. Also give it a title: a few words about what the day was about \
(not the date — the date is added for you).

The companion's questions (in brackets) are only there so you know what each answer was about. Never put a \
question in the entry, and never answer a question the person didn't answer: if a question has no reply after \
it, leave that topic out.

What the person said:
{conversation}"""


class JournalError(Exception):
    pass


# --- the key in the login keyring ----------------------------------------------------------------------------

def keyring_key(create: bool = True) -> str:
    """The journal's random key from the login keyring (Secret Service); made on first use."""
    import gi
    gi.require_version("Secret", "1")
    from gi.repository import Secret
    schema = Secret.Schema.new("org.cinminai.Journal", Secret.SchemaFlags.NONE,
                               {"purpose": Secret.SchemaAttributeType.STRING})
    attrs = {"purpose": "journal-key"}
    key = Secret.password_lookup_sync(schema, attrs, None)
    if key or not create:
        return key or ""
    key = secrets.token_urlsafe(32)
    if not Secret.password_store_sync(schema, attrs, Secret.COLLECTION_DEFAULT, KEYRING_LABEL, key, None):
        raise JournalError("the login keyring didn't store the journal key")
    return key


def _gpg(args: list[str], data: bytes, key: str) -> bytes:
    """GnuPG with the key on its own pipe (never on the command line) and a throwaway home (never ~/.gnupg)."""
    home = tempfile.mkdtemp(dir=os.environ.get("XDG_RUNTIME_DIR") or None, prefix="cinminai-gpg-")
    r, w = os.pipe()
    try:
        os.write(w, key.encode())
        os.close(w)
        out = subprocess.run(["gpg", "--homedir", home, "--batch", "--yes", "--quiet", "--pinentry-mode", "loopback",
                              "--passphrase-fd", str(r), *args], input=data, capture_output=True, pass_fds=(r,), timeout=60)
    finally:
        os.close(r)
        shutil.rmtree(home, ignore_errors=True)
    if out.returncode:
        raise JournalError("couldn't " + ("decrypt" if "--decrypt" in args else "encrypt") + " the entry")
    return out.stdout


def encrypt(data: bytes, key: str) -> bytes:
    return _gpg(["--symmetric", "--cipher-algo", "AES256"], data, key)


def decrypt(data: bytes, key: str) -> bytes:
    return _gpg(["--decrypt"], data, key)


# --- the journal ----------------------------------------------------------------------------------------------

class Journal:
    def __init__(self, root: str = ROOT, key: Callable[[], str] = keyring_key) -> None:
        self.root, self.key = root, key
        os.makedirs(root, exist_ok=True)
        self.index_path = os.path.join(root, "journal.json")
        self.index = {"entries": []}
        if os.path.isfile(self.index_path):
            with open(self.index_path, encoding="utf-8") as f:
                self.index = json.load(f)
        self.index.setdefault("entries", [])
        self.messages: list[dict] = []  # today's conversation: in memory only

    def save(self) -> None:
        fd, tmp = tempfile.mkstemp(dir=self.root, prefix=".journal-", suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            json.dump(self.index, f, ensure_ascii=False, indent=1)
            f.write("\n")
        os.replace(tmp, self.index_path)

    # --- the PIN ------------------------------------------------------------------------------------------
    @property
    def has_pin(self) -> bool:
        return "pin" in self.index

    def set_pin(self, pin: str, old: str = "") -> None:
        if not re.fullmatch(r"\d{4}", pin or ""):
            raise JournalError("the PIN is 4 digits")
        if self.has_pin and not self.check_pin(old):
            raise JournalError("that's not the current PIN")
        salt = secrets.token_bytes(16)
        self.index["pin"] = {"salt": base64.b64encode(salt).decode(), "iterations": PIN_ITERATIONS,
                             "hash": base64.b64encode(hashlib.pbkdf2_hmac("sha256", pin.encode(), salt, PIN_ITERATIONS)).decode()}
        self.save()

    def check_pin(self, pin: str) -> bool:
        p = self.index.get("pin")
        if not p or not re.fullmatch(r"\d{4}", pin or ""):
            return False
        h = hashlib.pbkdf2_hmac("sha256", pin.encode(), base64.b64decode(p["salt"]), int(p["iterations"]))
        return hmac.compare_digest(h, base64.b64decode(p["hash"]))

    # --- entries ----------------------------------------------------------------------------------------
    def write(self, title: str, text: str, when: dt.datetime, private: bool) -> dict:
        stamp = when.strftime("%Y-%m-%d %H.%M")
        title = (title or "Journal").strip()[:80]
        header = when.strftime("%A, %d %B %Y, %H:%M")
        if private:
            if not self.has_pin:
                raise JournalError("set a PIN first")
            folder = tempfile.mkdtemp(dir=os.environ.get("XDG_RUNTIME_DIR") or None, prefix="cinminai-entry-")
            try:  # the plain document only ever exists in memory-backed storage, for the moment it takes
                plain = odt.write(folder, "entry", title, [text], header=header)
                with open(plain, "rb") as f:
                    sealed = encrypt(f.read(), self.key())
            finally:
                shutil.rmtree(folder, ignore_errors=True)
            base, n = os.path.join(self.root, f"{stamp} — private"), 2
            path = base + ".odt.gpg"
            while os.path.exists(path):
                path, n = f"{base} ({n}).odt.gpg", n + 1
            with open(path, "xb") as f:
                f.write(sealed)
        else:
            from cin_minai.actions import hook
            path, _ = hook.run("journal_entry",
                               lambda: odt.write(self.root, f"{stamp} — {title}", title, [text], header=header),
                               "a journal entry", created=lambda p: [p])
        entry = {"file": os.path.basename(path), "title": "" if private else title, "when": when.isoformat(timespec="minutes"),
                 "private": private, "words": len(text.split())}
        self.index["entries"].append(entry)
        self.save()
        return {**entry, "path": path}

    def entries(self) -> list[dict]:
        """For the list: a private entry shows its date and a lock, not its title."""
        return [{k: e[k] for k in ("file", "title", "when", "private", "words")} for e in self.index["entries"]]

    def read_private(self, file: str, pin: str) -> dict:
        e = next((e for e in self.index["entries"] if e["file"] == file and e["private"]), None)
        if e is None:
            raise JournalError("no such private entry")
        if not self.check_pin(pin):
            raise JournalError("wrong PIN")
        with open(os.path.join(self.root, os.path.basename(file)), "rb") as f:
            doc = decrypt(f.read(), self.key())
        import io
        import xml.etree.ElementTree as ET
        import zipfile
        with zipfile.ZipFile(io.BytesIO(doc)) as z:
            root = ET.fromstring(z.read("content.xml"))
        paras = ["".join(p.itertext()) for p in root.iter("{urn:oasis:names:tc:opendocument:xmlns:text:1.0}p")]
        return {"title": paras[0] if paras else "", "text": "\n\n".join(paras[1:]), "when": e["when"]}


# --- the interviewer -------------------------------------------------------------------------------------------

class Interviewer:
    """`chat` is the backend's chat (as in writer.py)."""

    WARM = {"temperature": 0.6, "top_p": 0.9, "repeat_penalty": 1.1}

    def __init__(self, chat: Callable) -> None:
        self.chat = chat

    def reply(self, journal: Journal, text: str, on_text: Callable[[str], None], cancel: threading.Event) -> str:
        messages = [{"role": "system", "content": INTERVIEWER}, *journal.messages[-20:], {"role": "user", "content": text}]
        out, _ = self.chat(messages, max_tokens=150, on_text=on_text, cancel=cancel, sampling=self.WARM)
        journal.messages += [{"role": "user", "content": text}, {"role": "assistant", "content": out.strip()}]
        return out.strip()

    def entry(self, journal: Journal, when: dt.datetime, cancel: threading.Event | None = None) -> tuple[str, str]:
        said = [m for m in journal.messages if m["role"] == "user"]
        if not said:
            raise JournalError("there's nothing to write yet: tell me about your day first")
        # the person's words as lines; the companion's questions in brackets, and a trailing unanswered one left out
        # (2026-10-01: with "Companion: …" lines the entry quoted the last question and invented its answer)
        msgs = list(journal.messages)
        while msgs and msgs[-1]["role"] == "assistant":
            msgs.pop()
        conversation = "\n".join(m["content"] if m["role"] == "user" else f"[{m['content']}]" for m in msgs)
        raw, _ = self.chat([{"role": "user", "content": ENTRY_PROMPT.format(
            when=when.strftime("%A, %d %B %Y, %H:%M"), conversation=conversation)}], schema=ENTRY_SCHEMA,
            max_tokens=1600, cancel=cancel)
        data = json.loads(raw)
        title, text = data["title"].strip(), data["entry"].strip()
        if not title or re.search(r"\d{4}|\d{1,2}:\d{2}", title):
            # the model titled it with the date (2026-10-01): the entry's first words instead
            title = " ".join(text.split()[:5]).rstrip(",.;:") + "…"
        return title, text
