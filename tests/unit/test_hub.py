# SPDX-License-Identifier: GPL-3.0-or-later
"""More models from Hugging Face (hub.py, SPEC §22.3): the search, a repository's files pinned to one revision with
their checksums, the fit check from a file's first bytes, models on connected drives, and the daemon's download
that's only for a checked file."""

import io
import json
import os
import shutil
import sys
import tempfile
import types
import unittest
import urllib.parse
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))

from test_jobs import machine, tiny  # noqa: E402

from cin_minai.daemon import hub, jobs  # noqa: E402
from cin_minai.daemon.models import ModelStore  # noqa: E402
from cin_minai.inference import matcher  # noqa: E402
from cin_minai.sidebar import words  # noqa: E402

try:
    from cin_minai.daemon import service
except ImportError:  # no PyGObject
    service = None

REV = "13fb94bfda8c8cf22497dc57b78f391a9acb426a"
SHA = "5" * 64


class Response(io.BytesIO):
    def __init__(self, body: bytes, status: int = 200):
        super().__init__(body)
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


class Hub:
    """Hugging Face as far as these calls go; every request is kept."""
    def __init__(self, gguf: bytes = b""):
        self.gguf, self.asked = gguf, []

    def __call__(self, req, timeout=0):
        url = req.full_url
        self.asked.append((url, req.get_header("Range")))
        if "/api/models?" in url:
            return Response(json.dumps([
                {"id": "Qwen/Qwen2.5-Coder-7B-Instruct-GGUF", "downloads": 313834, "likes": 519,
                 "tags": ["gguf", "license:apache-2.0"]},
                {"id": "someone/private-GGUF", "private": True, "tags": []},
                {"id": "../etc", "tags": []}]).encode())
        if url.endswith("/tree/" + REV + "?recursive=true"):
            return Response(json.dumps([
                {"type": "file", "path": "README.md", "size": 10},
                {"type": "file", "path": "coder-q4_k_m.gguf", "size": len(self.gguf),
                 "lfs": {"oid": SHA, "size": len(self.gguf)}},
                {"type": "file", "path": "Q8/coder-q8_0-00001-of-00002.gguf", "size": 9, "lfs": {"oid": SHA, "size": 9}},
                {"type": "file", "path": "mmproj-F16.gguf", "size": 8, "lfs": {"oid": SHA, "size": 8}},
                {"type": "file", "path": "imatrix_unsloth.gguf", "size": 6, "lfs": {"oid": SHA, "size": 6}},
                {"type": "file", "path": "odd.gguf", "size": 7}]).encode())
        if url.endswith("/api/models/Qwen/Qwen2.5-Coder-7B-Instruct-GGUF"):
            return Response(json.dumps({"sha": REV, "gated": False, "cardData": {"license": "apache-2.0"}}).encode())
        if "/resolve/" in url:
            end = int(req.get_header("Range").split("-")[1])
            return Response(self.gguf[:end + 1], 206)
        raise OSError(f"not expected: {url}")


class Searching(unittest.TestCase):
    def test_gguf_only_most_downloaded_licence_as_stated(self):
        h = Hub()
        rs = hub.search("  qwen   coder ", opener=h)
        self.assertEqual(rs, [{"repo": "Qwen/Qwen2.5-Coder-7B-Instruct-GGUF", "licence": "apache-2.0",
                               "downloads": 313834, "likes": 519}])  # private and odd names dropped
        q = urllib.parse.parse_qs(urllib.parse.urlparse(h.asked[0][0]).query)
        self.assertEqual((q["search"], q["filter"], q["sort"]), (["qwen coder"], ["gguf"], ["downloads"]))
        with self.assertRaises(hub.HubError):
            hub.search(" ", opener=h)

    def test_files_pinned_with_their_checksums(self):
        h = Hub(b"x" * 100)
        v = hub.files("Qwen/Qwen2.5-Coder-7B-Instruct-GGUF", opener=h)
        self.assertEqual((v["revision"], v["licence"], v["gated"]), (REV, "apache-2.0", False))
        why = {f["file"]: f["why_not"] for f in v["files"]}
        self.assertEqual(why, {"coder-q4_k_m.gguf": "", "coder-q8_0-00001-of-00002.gguf": "a part is missing",
                               "mmproj-F16.gguf": "picture reader", "odd.gguf": "no checksum",
                               "imatrix_unsloth.gguf": "helper file"})
        self.assertEqual(v["files"][0]["sha256"], SHA)
        for bad in ("../x", "a/b/c", "", "a/..b/../c"):
            with self.assertRaises(hub.HubError):
                hub.files(bad, opener=h)

    def test_runs_here_from_the_first_bytes(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        tiny(os.path.join(d, "m.gguf"))
        with open(os.path.join(d, "m.gguf"), "rb") as f:
            data = f.read()
        h = Hub(data)
        f = next(x for x in hub.files("Qwen/Qwen2.5-Coder-7B-Instruct-GGUF", opener=h)["files"] if x["offered"])
        with mock.patch.object(hub, "HEADER_STEPS", (64, 600)):  # too little first: it asks for more
            m = hub.model_for("Qwen/Qwen2.5-Coder-7B-Instruct-GGUF", REV, f, opener=h)
        ranges = [r for u, r in h.asked if "/resolve/" in u]
        self.assertEqual(ranges, ["bytes=0-63", "bytes=0-599"])
        self.assertIn(f"/resolve/{REV}/coder-q4_k_m.gguf", [u for u, r in h.asked if "/resolve/" in u][0])
        self.assertEqual((m.file, m.source, m.sha256, m.size, m.weights),
                         ("coder-q4_k_m.gguf", f"Qwen/Qwen2.5-Coder-7B-Instruct-GGUF@{REV}", SHA, len(data), 2500))
        self.assertEqual(set(hub.fit(m, machine())), {"coding", "writing", "review"})
        self.assertTrue(all(x["fits"] for x in hub.fit(m, machine()).values()))
        with self.assertRaises(hub.HubError):
            hub.model_for("Qwen/Qwen2.5-Coder-7B-Instruct-GGUF", "main", f, opener=h)  # only a pinned revision


class Parts(unittest.TestCase):
    """D93: a model in parts offered as one, checked from its first part, downloaded part by part; a repository that
    asks for sign-in opened with the person's token, sent only there."""

    def setUp(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        tiny(os.path.join(d, "m.gguf"))
        with open(os.path.join(d, "m.gguf"), "rb") as f:
            self.first = f.read()
        self.second = b"y" * len(self.first)
        import hashlib
        self.sums = [hashlib.sha256(x).hexdigest() for x in (self.first, self.second)]

    def opener(self, gated=False):
        asked = []

        def call(req, timeout=0):
            url = req.full_url
            asked.append((url, req.get_header("Authorization")))
            if url.endswith("/tree/" + REV + "?recursive=true"):
                return Response(json.dumps([
                    {"type": "file", "path": f"Q8/big-0000{k + 1}-of-00002.gguf", "size": len(x),
                     "lfs": {"oid": self.sums[k], "size": len(x)}} for k, x in enumerate((self.first, self.second))
                ]).encode())
            if "/api/models/" in url:
                return Response(json.dumps({"sha": REV, "gated": "auto" if gated else False}).encode())
            if "/resolve/" in url:
                body = self.first if "00001-of" in url else self.second
                rng = req.get_header("Range")
                return Response(body[:int(rng.split("-")[1]) + 1], 206) if rng else Response(body)
            raise OSError(url)
        call.asked = asked
        return call

    def test_offered_as_one_and_downloaded_part_by_part(self):
        h = self.opener()
        v = hub.files("a/big-GGUF", opener=h)
        (f,) = v["files"]
        self.assertEqual((f["file"], f["offered"], f["size"], len(f["parts"])),
                         ("big-00001-of-00002.gguf", True, 2 * len(self.first), 2))
        with mock.patch.object(hub, "HEADER_STEPS", (600,)):
            m = hub.model_for("a/big-GGUF", REV, f, opener=h)
        self.assertEqual((m.name, m.size, m.weights, len(m.parts), m.gated), ("big", 2 * len(self.first), 4000, 2,
                                                                              False))
        self.assertTrue(all(auth is None for _, auth in h.asked))  # no token for an open repository
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        store = ModelStore(d, opener=h)
        seen = []
        store.download(m, lambda have, total: seen.append((have, total)), __import__("threading").Event())
        self.assertTrue(store.has("big-00001-of-00002.gguf"))
        self.assertEqual(seen[-1], (m.size, m.size))
        self.assertEqual(list(store.models()), ["big-00001-of-00002.gguf"])  # one model, not two
        local = matcher.model_from_gguf(store.path("big-00001-of-00002.gguf"))  # read back from the parts here
        self.assertEqual((local.size, local.weights), (m.size, 4000))
        with open(store.path("big-00002-of-00002.gguf"), "rb") as x:
            kept = x.read()
        os.rename(store.path("big-00002-of-00002.gguf"), store.path("elsewhere"))
        self.assertFalse(store.has("big-00001-of-00002.gguf"))  # a part gone: the model isn't here
        os.rename(store.path("elsewhere"), store.path("big-00002-of-00002.gguf"))
        self.assertEqual(kept, self.second)
        store.delete(m)  # every part goes
        self.assertEqual([x for x in os.listdir(d) if x.endswith(".gguf")], [])

    def test_signing_in_with_the_token(self):
        h = self.opener(gated=True)
        v = hub.files("a/big-GGUF", opener=h)
        self.assertTrue(v["gated"])
        with mock.patch.object(hub, "HEADER_STEPS", (600,)):
            m = hub.model_for("a/big-GGUF", REV, v["files"][0], opener=h, token="hf_" + "x" * 30)
        self.assertTrue(m.gated)
        self.assertIn("Bearer hf_" + "x" * 30, [a for u, a in h.asked if "/resolve/" in u])
        self.assertTrue(all(a is None for u, a in h.asked if "/resolve/" not in u))  # only to the files
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        with mock.patch("cin_minai.daemon.keys.get", return_value=""):
            with self.assertRaisesRegex(OSError, "sign in"):
                ModelStore(d, opener=h).download(m, lambda *a: None, __import__("threading").Event())
        from cin_minai.daemon import keys
        self.assertIn("huggingface", keys.SOURCES)
        self.assertTrue(__import__("re").fullmatch(keys.SOURCES["huggingface"].shape, "hf_" + "A1" * 15))


class Drives(unittest.TestCase):
    def test_models_on_a_stick(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        os.makedirs(os.path.join(d, "USB", "models", ".hidden"))
        for p in ("USB/models/coder.gguf", "USB/x-00001-of-00002.gguf", "USB/mmproj-F16.gguf",
                  "USB/models/.hidden/b.gguf", "USB/notes.txt"):
            open(os.path.join(d, p), "wb").close()
        self.assertEqual([f["file"] for f in hub.on_drives([d])], ["coder.gguf"])
        self.assertEqual(hub.on_drives([os.path.join(d, "none")]), [])


class Removing(unittest.TestCase):
    def test_not_while_a_job_uses_it(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        store = ModelStore(d)
        tiny(store.path("coder.gguf"))
        store.use("writing", {"file": "coder.gguf", "model": "coder"})
        with self.assertRaisesRegex(jobs.JobError, "another model first"):
            jobs.remove(store, "coder.gguf")
        store.use("writing", None)
        self.assertEqual(jobs.remove(store, "coder.gguf"), {"removed": "coder.gguf"})
        self.assertFalse(store.has("coder.gguf"))
        self.assertEqual(store.where("coder.gguf")["where"], "deleted")


@unittest.skipIf(service is None, "needs PyGObject")
class Download(unittest.TestCase):
    def daemon(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        s = types.SimpleNamespace(store=ModelStore(d), hub_checked={}, cancel=__import__("threading").Event(),
                                  texts=[], actions=[])
        s.job = lambda rid, fn: fn(s.texts.append, lambda *a: s.actions.append(a))
        s.model_ready = lambda m, job, on_text, on_action: {"done": True, "job": job}
        return s

    def test_only_a_checked_file(self):
        s = self.daemon()
        service.Service.hub_download(s, 1, "coder.gguf", "coding")
        self.assertIn("Check that model first", s.texts[0])

    def test_a_different_model_with_the_same_name_is_left_alone(self):
        s = self.daemon()
        tiny(s.store.path("coder.gguf"))
        s.hub_checked["coder.gguf"] = matcher.Model("coder", "coder.gguf", 1, 1, 1, 1, source=f"a/b@{REV}",
                                                     sha256=SHA, size=10)
        service.Service.hub_download(s, 1, "coder.gguf", "coding")
        self.assertIn("different model", s.texts[0])

    def test_fetched_then_tested(self):
        s = self.daemon()
        m = matcher.Model("coder", "coder.gguf", 1, 1, 1, 1, source=f"a/b@{REV}", sha256=SHA, size=10)
        s.hub_checked["coder.gguf"] = m
        got = []
        s.store.download = lambda model, progress, cancel: got.append(model)
        with mock.patch.object(service.hook, "run", side_effect=lambda name, fn, *a, **k: fn()):
            service.Service.hub_download(s, 1, "coder.gguf", "writing")
        self.assertEqual(got, [m])


class Words(unittest.TestCase):
    def test_licence_never_reviewed_and_fit(self):
        self.assertEqual(words.licence_line("apache-2.0", "en"), "licence: apache-2.0 (not reviewed by us)")
        self.assertEqual(words.licence_line("", "de"), "keine Lizenz angegeben")
        lines = words.fit_lines({"coding": {"fits": True, "tok_s": 40}, "writing": {"fits": False}}, "en")
        self.assertEqual(lines, ["Writing code (AICUI): runs well here", "Writing: doesn't run here"])
        for lang in ("es", "pt", "fr", "de", "ja"):
            self.assertEqual(set(k for k in words.T["en"] if k.startswith("h_")),
                             set(k for k in words.T[lang] if k.startswith("h_")), lang)


if __name__ == "__main__":
    unittest.main()
