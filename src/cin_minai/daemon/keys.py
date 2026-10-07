# SPDX-License-Identifier: GPL-3.0-or-later
"""Keys for sources that need one (PLAN D92, Ian 2026-10-07): the assistant sees that a source needs a key, tells the
person how to get it, and keeps it safe. The person does the registration themselves.

* A source that needs a key is declared here (SOURCES): its name, its sign-up page and the steps in plain words.
* When it's missing, the scan raises nothing: it notes the source as needed and the sidebar shows a key card — the
  steps, a button that opens the sign-up page, and a masked box. Saving sends the key to the daemon (KeySet), which
  puts it in the login keyring (Secret Service, like the journal's key) and nowhere else.
* **The key never reaches the model, the conversation, the action record or a log.** Only the source's own request
  reads it, at the moment of the request. A key pasted into the chat by mistake is caught before the model sees it.
* The keyring is unlocked by the login password, so a copied disk doesn't give the key away.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Source:
    name: str                   # "the US patent office's open data"
    signup_url: str             # where the person registers (https only)
    steps: tuple[str, ...]      # what to do there, in plain words
    shape: str = r"[A-Za-z0-9._~+/=-]{16,512}"  # what a key from this source looks like
    use: str = ""               # what it's used for, for the card: "patent records in the news scan"


# Nothing is wired yet: the patent office's key waits for Ian's go (2026-10-07). A source is one entry here plus the
# fetch that calls keys.get(its id); newsscan.KEYED lists the fetches.
SOURCES: dict[str, Source] = {}


class KeyError_(Exception):
    pass


# --- the login keyring ---------------------------------------------------------------------------------------------

class Keyring:
    """The Secret Service, one item per source."""

    def _schema(self):
        import gi
        gi.require_version("Secret", "1")
        from gi.repository import Secret
        return Secret, Secret.Schema.new("org.cinminai.SourceKey", Secret.SchemaFlags.NONE,
                                         {"source": Secret.SchemaAttributeType.STRING})

    def get(self, source: str) -> str:
        Secret, schema = self._schema()
        return Secret.password_lookup_sync(schema, {"source": source}, None) or ""

    def store(self, source: str, label: str, key: str) -> None:
        Secret, schema = self._schema()
        if not Secret.password_store_sync(schema, {"source": source}, Secret.COLLECTION_DEFAULT, label, key, None):
            raise KeyError_("the login keyring didn't store the key")

    def forget(self, source: str) -> None:
        Secret, schema = self._schema()
        Secret.password_clear_sync(schema, {"source": source}, None)


keyring = Keyring()


def get(source: str) -> str:
    """The key, for the source's own request only; "" when there's none (or no keyring)."""
    try:
        return keyring.get(source)
    except Exception:  # no Secret Service (a bare session): the source is simply not available
        return ""


def has(source: str) -> bool:
    return bool(get(source))


def store(source: str, key: str) -> str:
    """Check and keep a key; returns the source's name. The error never repeats the key."""
    src = SOURCES.get(source)
    if src is None:
        raise KeyError_("no source by that name needs a key")
    key = key.strip()
    if not re.fullmatch(src.shape, key):
        raise KeyError_(f"that doesn't look like a key from {src.name}; copy it again from their page")
    keyring.store(source, f"Cin-MinAI: key for {src.name}", key)
    return src.name


def forget(source: str) -> None:
    keyring.forget(source)


def card(source: str) -> dict:
    """What the key card shows: never the key, only how to get one."""
    src = SOURCES[source]
    return {"source": source, "name": src.name, "signup_url": src.signup_url, "steps": list(src.steps),
            "use": src.use, "saved": has(source)}


# --- a key pasted into the chat ----------------------------------------------------------------------------------

LOOKS_LIKE_KEY = re.compile(r"(?=[^\s]*\d)(?=[^\s]*[A-Za-z])[A-Za-z0-9._~+/=:-]{24,512}")
LONG_WORD = re.compile(r"^[a-z]+(-[a-z]+)*$", re.I)
FILE_NAME = re.compile(r"\.[a-z]{2,5}$", re.I)  # ubuntu-24.04-desktop-amd64.iso: a file, asked about


def looks_like_key(text: str) -> bool:
    """One long token with letters and digits and nothing else: an API key or token, not a question. A web address
    or a file path isn't one (they're questions about a page or a file)."""
    t = text.strip()
    if "://" in t or t.startswith(("/", "~")) or LONG_WORD.match(t) or FILE_NAME.search(t):
        return False
    return bool(LOOKS_LIKE_KEY.fullmatch(t))


PASTED = {
    "en": "That looks like a key or a password, so I didn't read it or keep it in our conversation. Keys go in the box "
          "on the key card, which puts them straight into your login keyring. If a source needs one, I'll show you "
          "that card with the steps.",
    "es": "Eso parece una clave o una contraseña, así que no la leí ni la guardé en la conversación. Las claves van en "
          "el recuadro de la tarjeta de clave, que las guarda directamente en tu llavero de inicio de sesión.",
    "pt": "Isso parece uma chave ou senha, então não a li nem a guardei na conversa. As chaves vão na caixa do cartão "
          "de chave, que as guarda direto no seu chaveiro de sessão.",
    "fr": "Cela ressemble à une clé ou un mot de passe : je ne l'ai ni lu ni gardé dans la conversation. Les clés se "
          "saisissent dans la case de la carte de clé, qui les range directement dans votre trousseau de session.",
    "de": "Das sieht wie ein Schlüssel oder Passwort aus, deshalb habe ich es weder gelesen noch im Gespräch behalten. "
          "Schlüssel gehören in das Feld auf der Schlüsselkarte, das sie direkt im Anmelde-Schlüsselbund ablegt.",
    "ja": "キーかパスワードのようなので、読まず、会話にも残していません。キーはキーカードの入力欄に入れてください。"
          "ログインキーリングに直接保存されます。",
}
