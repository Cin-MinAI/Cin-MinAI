# SPDX-License-Identifier: GPL-3.0-or-later
"""Accounts (src/cin_minai/daemon/accounts.py; docs/accounts-and-cloud.md): GitHub linked once through the device flow,
the tokens kept in the keyring and renewed when due; no token in an error; git's credential helper answers only for
github.com.

    python3 -m unittest tests.unit.test_accounts -v        (from the repo root)
"""

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
import urllib.error
import urllib.parse
from unittest import mock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))

from cin_minai.daemon import accounts  # noqa: E402

HELPER = os.path.join(ROOT, "distro", "packages", "cinminai-daemon", "root", "usr", "libexec", "cinminai-git-credential")


class FakeKeyring:
    def __init__(self):
        self.items = {}

    def get(self, account):
        return dict(self.items.get(account, {}))

    def put(self, account, label, value):
        self.items[account] = dict(value)

    def forget(self, account):
        self.items.pop(account, None)


class FakeGitHub:
    """Answers by address, in order; records what was asked (never sends anything anywhere)."""

    def __init__(self, answers):
        self.answers, self.asked = answers, []

    def __call__(self, req, timeout=0):
        body = urllib.parse.parse_qs(req.data.decode()) if req.data and not req.full_url.startswith(accounts.API) \
            else (json.loads(req.data) if req.data else {})
        self.asked.append((req.full_url, body, req.headers.get("Authorization", "")))
        answer = self.answers[req.full_url].pop(0)
        if isinstance(answer, tuple):  # (status, body): GitHub answering with an error
            raise urllib.error.HTTPError(req.full_url, answer[0], "no", {}, io.BytesIO(json.dumps(answer[1]).encode()))
        return io.BytesIO(json.dumps(answer).encode())


class GitHubLink(unittest.TestCase):
    def setUp(self):
        self.clock = [1000.0]
        env = mock.patch.dict(os.environ, {"CINMINAI_GITHUB_CLIENT_ID": "Iv23liTEST", "CINMINAI_GITHUB_APP": "cin-minai",
                                           "XDG_RUNTIME_DIR": tempfile.mkdtemp()})
        env.start()
        self.addCleanup(env.stop)

    def gh(self, answers):
        self.fake, self.keys = FakeGitHub(answers), FakeKeyring()
        return accounts.GitHub(opener=self.fake, keyring=self.keys, now=lambda: self.clock[0],
                               sleep=lambda s: self.clock.__setitem__(0, self.clock[0] + s))

    def test_signing_in_once_waits_for_the_persons_approval_and_keeps_the_tokens(self):
        gh = self.gh({accounts.DEVICE: [{"device_code": "dev1", "user_code": "WDJB-MJHT",
                                         "verification_uri": "https://github.com/login/device", "interval": 5,
                                         "expires_in": 900}],
                      accounts.TOKEN: [{"error": "authorization_pending"}, {"error": "slow_down", "interval": 10},
                                       {"access_token": "ghu_secret1", "expires_in": 28800,
                                        "refresh_token": "ghr_secret1", "refresh_token_expires_in": 15897600}],
                      f"{accounts.API}/user": [{"login": "brickmii"}]})
        start = gh.start()
        self.assertEqual(start["user_code"], "WDJB-MJHT")
        self.assertEqual(self.fake.asked[0][1]["client_id"], ["Iv23liTEST"])  # the public id, no secret
        self.assertEqual(gh.finish(start), "brickmii")
        kept = self.keys.items["github"]
        self.assertEqual((kept["access"], kept["refresh"], kept["login"]), ("ghu_secret1", "ghr_secret1", "brickmii"))
        self.assertEqual(self.clock[0], 1000 + 5 + 5 + 10)  # GitHub's pace, slowed when it asked
        self.assertEqual(gh.status(), {"linked": True, "login": "brickmii", "renew_by": kept["refresh_expires"],
                                       "ready": True})
        self.assertNotIn("client_secret", json.dumps([a[1] for a in self.fake.asked]))

    def test_a_refusal_or_a_late_approval_links_nothing(self):
        gh = self.gh({accounts.DEVICE: [{"device_code": "d", "user_code": "C", "verification_uri": "u", "interval": 5,
                                         "expires_in": 900}],
                      accounts.TOKEN: [{"error": "access_denied"}]})
        with self.assertRaises(accounts.AccountError) as e:
            gh.finish(gh.start())
        self.assertIn("you said no on GitHub", str(e.exception))
        self.assertEqual(self.keys.items, {})
        gh = self.gh({accounts.TOKEN: [{"error": "authorization_pending"}] * 3})
        with self.assertRaises(accounts.AccountError) as e:
            gh.finish({"device_code": "d", "interval": 5, "expires_in": 12})
        self.assertIn("ran out", str(e.exception))

    def test_the_token_renews_itself_when_due_and_says_when_the_link_ran_out(self):
        gh = self.gh({accounts.TOKEN: [{"access_token": "ghu_new", "expires_in": 28800, "refresh_token": "ghr_new",
                                        "refresh_token_expires_in": 15897600}]})
        self.keys.items["github"] = {"access": "ghu_old", "expires": 5000, "refresh": "ghr_old",
                                     "refresh_expires": 99999999, "login": "brickmii"}
        self.assertEqual(gh.token(), "ghu_old")  # hours left: as it is
        self.clock[0] = 4800  # within five minutes of its end: renewed first
        self.assertEqual(gh.token(), "ghu_new")
        self.assertEqual(self.fake.asked[-1][1]["grant_type"], ["refresh_token"])
        self.assertEqual(self.keys.items["github"]["refresh"], "ghr_new")  # the replaced refresh token is kept
        self.assertEqual(self.keys.items["github"]["login"], "brickmii")
        self.keys.items["github"].update(expires=0, refresh_expires=0)
        with self.assertRaises(accounts.AccountError) as e:
            gh.token()
        self.assertIn("sign in again", str(e.exception))
        gh.sign_out()
        with self.assertRaises(accounts.AccountError) as e:
            gh.token()
        self.assertIn("isn't linked to GitHub", str(e.exception))

    def test_no_client_id_says_so_and_errors_never_repeat_a_token(self):
        with mock.patch.dict(os.environ, {"CINMINAI_GITHUB_CLIENT_ID": "", "CINMINAI_ACCOUNTS": "/nonexistent"}):
            with self.assertRaises(accounts.AccountError) as e:
                self.gh({}).start()
        self.assertIn("isn't set up in this build yet", str(e.exception))
        import urllib.error

        def refuse(req, timeout=0):
            raise urllib.error.HTTPError(req.full_url, 401, "no", {}, io.BytesIO(b'{"message": "Bad credentials"}'))
        gh = accounts.GitHub(opener=refuse, keyring=FakeKeyring(), now=lambda: 0)
        gh.keyring.items["github"] = {"access": "ghu_topsecret", "expires": 99999, "refresh": "r", "refresh_expires": 9,
                                      "login": "x"}
        with self.assertRaises(accounts.AccountError) as e:
            gh.repos()
        self.assertEqual(str(e.exception), "GitHub said 401: Bad credentials")

    def test_repositories_and_a_new_one(self):
        gh = self.gh({f"{accounts.API}/user/installations": [{"total_count": 1, "installations": [{"id": 7}]}],
                      f"{accounts.API}/user/installations/7/repositories?per_page=100": [{"repositories": [
                          {"full_name": "brickmii/game", "private": True, "clone_url": "https://github.com/brickmii/game.git",
                           "other": 1}]}],
                      f"{accounts.API}/user/repos": [{"full_name": "brickmii/test8", "private": True,
                                                      "clone_url": "https://github.com/brickmii/test8.git"}]})
        self.keys.items["github"] = {"access": "ghu_x", "expires": 99999, "refresh": "r", "refresh_expires": 99999,
                                     "login": "brickmii"}
        self.assertEqual(gh.repos(), [{"full_name": "brickmii/game", "private": True,
                                       "clone_url": "https://github.com/brickmii/game.git"}])
        made = gh.create_repo("test8")
        self.assertEqual(made["full_name"], "brickmii/test8")
        self.assertEqual(self.fake.asked[-1][1], {"name": "test8", "private": True, "description": "",
                                                  "auto_init": False})  # private unless the person says otherwise
        self.assertEqual(self.fake.asked[-1][2], "Bearer ghu_x")
        self.assertEqual(gh.install_url(), "https://github.com/apps/cin-minai/installations/new")

    def test_the_machines_name_and_its_pages(self):
        pages = f"{accounts.API}/repos/cinminaidevbox/test20/pages"
        gh = self.gh({f"{accounts.API}/user": [{"login": "cinminaidevbox", "name": "Simon",
                                                "bio": "Simon is maintained by Brickmii"}],
                      pages: [(404, {"message": "Not Found"}),  # no site yet
                              {"html_url": "https://cinminaidevbox.github.io/test20/", "status": None},  # turned on
                              {"html_url": "https://cinminaidevbox.github.io/test20/", "status": "built"},
                              (409, {"message": "already exists"}),  # on already: fine
                              {"html_url": "https://cinminaidevbox.github.io/test20/", "status": "built"},
                              (403, {"message": "Resource not accessible by integration"})]})
        self.keys.items["github"] = {"access": "ghu_x", "expires": 99999, "refresh": "r", "refresh_expires": 99999,
                                     "login": "cinminaidevbox"}
        self.assertEqual(gh.profile()["name"], "Simon")
        self.assertIsNone(gh.pages("cinminaidevbox/test20"))
        site = gh.enable_pages("cinminaidevbox/test20")
        self.assertEqual(self.fake.asked[-2][1], {"build_type": "legacy", "source": {"branch": "main", "path": "/"}})
        self.assertEqual(site, {"url": "https://cinminaidevbox.github.io/test20/", "status": "built"})
        self.assertEqual(gh.enable_pages("cinminaidevbox/test20")["status"], "built")
        with self.assertRaises(accounts.AccountError) as e:
            gh.enable_pages("cinminaidevbox/test20")
        self.assertIn("Pages permission", str(e.exception))
        self.assertEqual(e.exception.code, 403)


class CredentialHelper(unittest.TestCase):
    def run_helper(self, action, ask):
        env = {**os.environ, "PYTHONPATH": os.path.join(ROOT, "src")}
        return subprocess.run([sys.executable, HELPER, action], input=ask, capture_output=True, text=True, env=env)

    def test_only_github_over_https_and_only_get(self):
        self.assertEqual(self.run_helper("get", "protocol=https\nhost=gitlab.com\n\n").stdout, "")
        self.assertEqual(self.run_helper("store", "protocol=https\nhost=github.com\npassword=x\n\n").stdout, "")
        self.assertEqual(self.run_helper("get", "protocol=http\nhost=github.com\n\n").stdout, "")

    def test_without_a_link_git_gets_nothing_and_is_told_why(self):
        env = {"CINMINAI_GITHUB_CLIENT_ID": "Iv23liTEST", "XDG_RUNTIME_DIR": tempfile.mkdtemp()}
        with mock.patch.dict(os.environ, env):
            r = self.run_helper("get", "protocol=https\nhost=github.com\n\n")
        self.assertEqual(r.stdout, "")
        self.assertIn("Cin-MinAI:", r.stderr)


if __name__ == "__main__":
    unittest.main()
