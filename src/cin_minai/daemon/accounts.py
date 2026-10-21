# SPDX-License-Identifier: GPL-3.0-or-later
"""Accounts: services the computer is linked to once (Ian, 2026-10-11: "make the key transfer one time, and you never
have to touch it again because its all on the system like it does for me with Pycharm. You just do the sign in through
the browser and it links up." — docs/accounts-and-cloud.md).

GitHub, through Cin-MinAI's GitHub App and the device flow: the person sees a short code, approves on github.com in
their own browser, and the computer keeps the tokens in the login keyring. User tokens expire after 8 hours and are
renewed here from the refresh token (6 months); no app secret is shipped or needed.

* **Tokens live in the login keyring only** (Secret Service, as the journal's key and the news keys): never in a file,
  a log, the action record or the conversation. No model ever sees one: git gets it from our credential helper
  (/usr/libexec/cinminai-git-credential), the API calls here read it at the moment of the request.
* Errors never repeat a token.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from contextlib import contextmanager
from typing import Callable

UA = {"User-Agent": "Cin-MinAI", "Accept": "application/json"}
CONFIG = "/usr/share/cinminai/accounts.json"   # {"github_client_id", "github_app"} — public values, set per release
DEVICE = "https://github.com/login/device/code"
TOKEN = "https://github.com/login/oauth/access_token"
API = "https://api.github.com"
RENEW_BEFORE = 300  # seconds: an access token this close to its end is renewed first


class AccountError(Exception):
    def __init__(self, message: str, code: int = 0) -> None:
        super().__init__(message)
        self.code = code  # the HTTP status when GitHub answered with one


def config() -> dict:
    """The app's public identity: CINMINAI_GITHUB_CLIENT_ID / CINMINAI_GITHUB_APP override the shipped file."""
    try:
        with open(os.environ.get("CINMINAI_ACCOUNTS", CONFIG), encoding="utf-8") as f:
            c = json.load(f)
    except (OSError, ValueError):
        c = {}
    return {"github_client_id": os.environ.get("CINMINAI_GITHUB_CLIENT_ID", c.get("github_client_id", "")),
            "github_app": os.environ.get("CINMINAI_GITHUB_APP", c.get("github_app", ""))}


# --- the login keyring ---------------------------------------------------------------------------------------------

class Keyring:
    """One Secret Service item per account; its secret is the account's tokens as JSON."""

    def _schema(self):
        import gi
        gi.require_version("Secret", "1")
        from gi.repository import Secret
        return Secret, Secret.Schema.new("org.cinminai.Account", Secret.SchemaFlags.NONE,
                                         {"account": Secret.SchemaAttributeType.STRING})

    def get(self, account: str) -> dict:
        Secret, schema = self._schema()
        raw = Secret.password_lookup_sync(schema, {"account": account}, None)
        return json.loads(raw) if raw else {}

    def put(self, account: str, label: str, value: dict) -> None:
        Secret, schema = self._schema()
        if not Secret.password_store_sync(schema, {"account": account}, Secret.COLLECTION_DEFAULT, label,
                                          json.dumps(value), None):
            raise AccountError("the login keyring didn't keep the sign-in")

    def forget(self, account: str) -> None:
        Secret, schema = self._schema()
        Secret.password_clear_sync(schema, {"account": account}, None)

    def locked(self) -> bool:
        """Is the keyring our accounts are in locked? (2026-10-13: with automatic login the login keyring stays locked
        after a restart; the key was there, AICUI said there was none.)"""
        Secret, _ = self._schema()
        svc = Secret.Service.get_sync(Secret.ServiceFlags.OPEN_SESSION, None)
        c = Secret.Collection.for_alias_sync(svc, "default", Secret.CollectionFlags.NONE, None)
        return bool(c and c.get_locked())

    def unlock(self) -> bool:
        """The desktop's own prompt for the keyring's password (we never see it). True when it's unlocked."""
        Secret, _ = self._schema()
        svc = Secret.Service.get_sync(Secret.ServiceFlags.OPEN_SESSION, None)
        c = Secret.Collection.for_alias_sync(svc, "default", Secret.CollectionFlags.NONE, None)
        if c is None or not c.get_locked():
            return True
        svc.unlock_sync([c], None)
        return not c.get_locked()


class GitHub:
    """Sign-in, renewal, sign-out and the few API calls AICUI needs. `opener` and `keyring` are swappable for tests."""

    def __init__(self, opener: Callable = urllib.request.urlopen, keyring=None, now: Callable = time.time,
                 sleep: Callable = time.sleep) -> None:
        self.opener, self.keyring, self.now, self.sleep = opener, keyring or Keyring(), now, sleep

    # --- the requests ---
    def _call(self, url: str, data: dict | None = None, token: str = "", method: str | None = None) -> dict:
        headers = dict(UA)
        if token:
            headers["Authorization"] = f"Bearer {token}"
            headers["X-GitHub-Api-Version"] = "2022-11-28"
        body = None
        if data is not None:
            if url.startswith(API):
                body, headers["Content-Type"] = json.dumps(data).encode(), "application/json"
            else:
                body = urllib.parse.urlencode(data).encode()
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with self.opener(req, timeout=30) as r:
                raw = r.read()
        except urllib.error.HTTPError as e:
            try:
                said = json.loads(e.read() or b"{}").get("message", "")
            except ValueError:
                said = ""
            raise AccountError(f"GitHub said {e.code}" + (f": {said[:200]}" if said else ""), e.code) from None
        except OSError as e:
            raise AccountError(f"GitHub didn't answer: {getattr(e, 'reason', e)}") from None
        return json.loads(raw or b"{}")

    def client_id(self) -> str:
        cid = config()["github_client_id"]
        if not cid:
            raise AccountError("GitHub sign-in isn't set up in this build yet (the app's Client ID is missing)")
        return cid

    # --- signing in: the device flow ---
    def start(self) -> dict:
        """{"user_code", "verification_uri", "device_code", "interval", "expires_in"}: the person types the code at
        the address in their own browser."""
        got = self._call(DEVICE, {"client_id": self.client_id()})
        if "device_code" not in got:
            raise AccountError(got.get("error_description") or "GitHub didn't give a sign-in code")
        return got

    def finish(self, start: dict, cancel=None) -> str:
        """Wait for the person's approval (GitHub's own pace), then keep the tokens; the GitHub login name."""
        interval = int(start.get("interval", 5))
        end = self.now() + int(start.get("expires_in", 900))
        while self.now() < end:
            if cancel is not None and cancel.is_set():
                raise AccountError("signing in was stopped")
            self.sleep(interval)
            got = self._call(TOKEN, {"client_id": self.client_id(), "device_code": start["device_code"],
                                     "grant_type": "urn:ietf:params:oauth:grant-type:device_code"})
            err = got.get("error")
            if err == "authorization_pending":
                continue
            if err == "slow_down":
                interval = int(got.get("interval", interval + 5))
                continue
            if err == "access_denied":
                raise AccountError("you said no on GitHub; nothing was linked")
            if err:
                raise AccountError(got.get("error_description") or f"GitHub: {err}")
            return self._keep(got)
        raise AccountError("the sign-in code ran out before it was approved; start again")

    def _keep(self, got: dict, login: str = "") -> str:
        now = self.now()
        tokens = {"access": got["access_token"], "expires": now + int(got.get("expires_in", 28800)),
                  "refresh": got.get("refresh_token", ""),
                  "refresh_expires": now + int(got.get("refresh_token_expires_in", 15897600)), "login": login}
        if not login:
            tokens["login"] = self._call(f"{API}/user", token=tokens["access"]).get("login", "")
        self.keyring.put("github", f"Cin-MinAI: GitHub ({tokens['login'] or 'linked'})", tokens)
        return tokens["login"]

    # --- the token, renewed when it's due ---
    def token(self) -> str:
        """The access token for a request, renewed from the refresh token when it's within RENEW_BEFORE of its end."""
        with _renewing():
            try:
                t = self.keyring.get("github")
            except Exception:  # no Secret Service, or a locked keyring: said, never a traceback
                raise AccountError("the login keyring can't be read here (is the desktop session open and "
                                   "unlocked?)") from None
            if not t:
                raise AccountError("this computer isn't linked to GitHub; sign in from AICUI's GitHub button")
            if t["expires"] - self.now() > RENEW_BEFORE:
                return t["access"]
            if not t.get("refresh") or t.get("refresh_expires", 0) <= self.now():
                raise AccountError("the GitHub link ran out; sign in again from AICUI's GitHub button")
            got = self._call(TOKEN, {"client_id": self.client_id(), "grant_type": "refresh_token",
                                     "refresh_token": t["refresh"]})
            if "access_token" not in got:
                raise AccountError("the GitHub link couldn't be renewed; sign in again from AICUI's GitHub button")
            self._keep(got, t.get("login", ""))
            return got["access_token"]

    def status(self) -> dict:
        try:
            t = self.keyring.get("github")
        except Exception:
            t = {}
        return {"linked": bool(t), "login": t.get("login", ""), "renew_by": t.get("refresh_expires", 0),
                "ready": bool(config()["github_client_id"])}

    def sign_out(self) -> None:
        self.keyring.forget("github")

    # --- what AICUI does with it ---
    def installed(self) -> bool:
        """Is the app installed on an account this person can use (so it may reach their repositories)?"""
        return int(self._call(f"{API}/user/installations", token=self.token()).get("total_count", 0)) > 0

    def install_url(self) -> str:
        return f"https://github.com/apps/{config()['github_app']}/installations/new" if config()["github_app"] else ""

    def repos(self) -> list[dict]:
        """The repositories the app may reach for this person: [{"full_name", "private", "clone_url"}]."""
        out = []
        for inst in self._call(f"{API}/user/installations", token=self.token()).get("installations", []):
            got = self._call(f"{API}/user/installations/{inst['id']}/repositories?per_page=100", token=self.token())
            out += [{"full_name": r["full_name"], "private": r["private"], "clone_url": r["clone_url"]}
                    for r in got.get("repositories", [])]
        return out

    def create_repo(self, name: str, private: bool = True, description: str = "") -> dict:
        got = self._call(f"{API}/user/repos", {"name": name, "private": private, "description": description,
                                               "auto_init": False}, token=self.token())
        return {"full_name": got["full_name"], "private": got["private"], "clone_url": got["clone_url"]}

    def profile(self) -> dict:
        """The account as GitHub shows it: its login and the name its owner gave it (a machine's name, e.g. "Simon")."""
        got = self._call(f"{API}/user", token=self.token())
        return {"login": got.get("login", ""), "name": got.get("name") or "", "bio": got.get("bio") or ""}

    def repo(self, full_name: str) -> dict:
        got = self._call(f"{API}/repos/{full_name}", token=self.token())
        return {"full_name": got["full_name"], "private": got["private"],
                "default_branch": got.get("default_branch") or "main"}

    def pages(self, full_name: str) -> dict | None:
        """The repository's GitHub Pages site ({"url", "status"}), or None when it has none."""
        try:
            got = self._call(f"{API}/repos/{full_name}/pages", token=self.token())
        except AccountError as e:
            if e.code == 404:
                return None
            raise
        return {"url": got.get("html_url", ""), "status": got.get("status") or ""}

    def enable_pages(self, full_name: str, branch: str = "main") -> dict:
        """Pages on, served from the branch's top folder: a static site needs no workflow (PLAN D62, 2026-10-20)."""
        try:
            self._call(f"{API}/repos/{full_name}/pages", {"build_type": "legacy",
                                                          "source": {"branch": branch, "path": "/"}},
                       token=self.token())
        except AccountError as e:
            if e.code == 409:  # it was on already
                pass
            elif e.code in (403, 404):
                raise AccountError("GitHub didn't let AICUI turn on Pages for this repository. Either the AICUI app "
                                   "hasn't been given the Pages permission yet (its owner adds it, then you accept "
                                   "it on GitHub), or the repository is private on a plan without private Pages — "
                                   "a public repository works on every plan.", e.code) from None
            else:
                raise
        return self.pages(full_name) or {"url": "", "status": ""}


# --- cloud model keys (docs/accounts-and-cloud.md): pasted once, kept in the keyring, read only by the cloud backend --
CLOUD = {"anthropic": {"name": "Anthropic", "shape": r"sk-ant-[A-Za-z0-9_-]{20,300}",
                       "console": "https://console.anthropic.com/settings/keys", "hint": "sk-ant-…"},
         "openai": {"name": "OpenAI", "shape": r"sk-(?!ant-)[A-Za-z0-9_-]{20,300}",
                    "console": "https://platform.openai.com/api-keys", "hint": "sk-…"}}


def cloud_key(provider: str, keyring=None) -> str:
    """The provider's key, for its own request only; "" when there's none or no keyring."""
    try:
        return (keyring or Keyring()).get(f"cloud-{provider}").get("key", "")
    except Exception:
        return ""


def keyring_locked(keyring=None) -> bool:
    try:
        return (keyring or Keyring()).locked()
    except Exception:
        return False


def unlock_keyring(keyring=None) -> bool:
    try:
        return (keyring or Keyring()).unlock()
    except Exception:
        return False


def store_cloud_key(provider: str, key: str, keyring=None) -> None:
    """Check the key's shape and keep it; the error never repeats the key."""
    import re
    p = CLOUD.get(provider)
    if p is None:
        raise AccountError("that cloud provider isn't offered")
    key = key.strip()
    if not re.fullmatch(p["shape"], key):
        raise AccountError(f"that doesn't look like an {p['name']} API key; copy it again from {p['console']}")
    (keyring or Keyring()).put(f"cloud-{provider}", f"Cin-MinAI: {p['name']} API key", {"key": key})


def forget_cloud_key(provider: str, keyring=None) -> None:
    (keyring or Keyring()).forget(f"cloud-{provider}")


@contextmanager
def _renewing():
    """One renewal at a time on this computer: a refresh token is replaced at each use, so two at once would lose one."""
    import fcntl
    runtime = os.environ.get("XDG_RUNTIME_DIR") or f"/tmp/cinminai-{os.getuid()}"
    os.makedirs(runtime, mode=0o700, exist_ok=True)
    with open(os.path.join(runtime, "cinminai-github.lock"), "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


github = GitHub()
