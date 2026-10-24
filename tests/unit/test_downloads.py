# SPDX-License-Identifier: GPL-3.0-or-later
"""What's downloading, as the guide sees it (Ian, 2026-10-24: asked "Is the model downloading?" with nothing
downloading, the guide read the Wi-Fi and said yes). The daemon keeps model downloads and Wikipedia shelves this
session; inspect_system network carries them.

    python3 -m unittest tests.unit.test_downloads -v        (from the repo root)
"""

import json
import os
import sys
import types
import unittest
from unittest import mock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))

from cin_minai.daemon import tools  # noqa: E402

try:
    from cin_minai.daemon import service
except ImportError:  # no PyGObject
    service = None

GB = 2**30


class Network(unittest.TestCase):
    def reading(self, downloads) -> dict:
        t = tools.Tools({"network": {"en": "Network"}}, {}, "en")
        t.downloads = lambda: downloads
        with mock.patch.object(tools, "run", return_value=""), mock.patch.object(tools, "live_session", return_value=False):
            return t.inspect("network")

    def test_nothing_downloading_is_said(self):
        self.assertEqual(self.reading([])["downloads"], "nothing is downloading")

    def test_a_download_comes_with_its_numbers(self):
        got = [{"what": "Wikipedia (wikipedia_en_top_maxi_2026-09.zim)", "state": "running", "have_gb": 2.1,
                "total_gb": 5.3}]
        self.assertEqual(self.reading(got)["downloads"], got)


class Updates(unittest.TestCase):
    def reading(self, downloads) -> dict:
        t = tools.Tools({}, {}, "en")
        t.downloads = lambda: downloads
        with mock.patch.object(tools, "run", return_value=""), mock.patch.object(tools, "live_session", return_value=False):
            return t.inspect("updates")

    def test_only_when_something_is_downloading(self):
        # the 2026-10-24 eval: "Is the model downloading?" read the updates check once
        self.assertNotIn("downloads", self.reading([]))
        got = [{"what": "Coder 27B", "state": "stopped", "have_gb": 3.0, "total_gb": 10.0}]
        self.assertEqual(self.reading(got)["downloads"], got)


@unittest.skipIf(service is None, "needs PyGObject")
class Kept(unittest.TestCase):
    def setUp(self):
        self.s = types.SimpleNamespace(model_jobs={}, shelf_jobs={})

    def note(self, state: str, **p) -> None:
        service.Service.note_download(self.s, 7, "coder.gguf", state, json.dumps(p))

    def test_a_model_download_as_it_goes(self):
        self.note("running", model="Coder 27B", have_gb="3.0", total_gb="10.0", have=3 * GB, total=10 * GB)
        self.assertEqual(service.Service.downloads_now(self.s),
                         [{"what": "Coder 27B", "state": "running", "have_gb": 3.0, "total_gb": 10.0}])
        self.note("running", model="Coder 27B", testing=True)  # checked, now tested here: the numbers stay
        self.assertEqual(service.Service.downloads_now(self.s)[0]["state"], "checking")
        self.assertEqual(service.Service.downloads_now(self.s)[0]["have_gb"], 3.0)
        self.note("done", model="Coder 27B", measured=20)
        self.assertEqual(service.Service.downloads_now(self.s)[0]["state"], "done")

    def test_a_shelf_and_its_check(self):
        self.s.shelf_jobs = {"a.zim": {"have": GB, "total": 4 * GB, "state": "running", "error": ""},
                             "b.zim": {"have": 2 * GB, "total": 2 * GB, "state": "running", "error": ""},
                             "c.zim": {"have": 0, "total": GB, "state": "failed", "error": "no mirror answered"}}
        got = {d["what"]: d for d in service.Service.downloads_now(self.s)}
        self.assertEqual(got["Wikipedia (a.zim)"]["state"], "running")
        self.assertEqual(got["Wikipedia (b.zim)"]["state"], "checking")  # all here: the checksum is being checked
        self.assertEqual(got["Wikipedia (c.zim)"]["error"], "no mirror answered")


if __name__ == "__main__":
    unittest.main()
