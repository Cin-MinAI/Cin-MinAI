# SPDX-License-Identifier: GPL-3.0-or-later
"""Jobs and their models (SPEC §22.3): the Models view's data, giving a job a model that runs here, our pick again,
and the guide keeping help and the system (D94)."""

import dataclasses
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))

from test_gguf import build  # noqa: E402

from cin_minai.daemon import jobs, vision  # noqa: E402
from cin_minai.daemon.models import ModelStore  # noqa: E402
from cin_minai.inference import matcher  # noqa: E402
from cin_minai.sidebar import words  # noqa: E402

BIG = "Qwen3.8-27B-UD-IQ3_XXS.gguf"  # in our catalog, with a picture reader


def machine(free=11159):
    return matcher.Machine([{"name": "NVIDIA GeForce GTX 1080 Ti", "api": "CUDA0", "total_mib": 11264,
                             "free_mib": free}], 32, 26, 4, True, 5.0, 50)


def tiny(path: str) -> None:
    """A model that isn't in our catalog: what the person brought (an old coder, say)."""
    build(path, {"general.architecture": "llama", "llama.block_count": 4, "llama.attention.head_count": 8,
                 "llama.attention.head_count_kv": 2, "llama.embedding_length": 512},
          [("token_embd.weight", 1000), ("blk.0.attn_q.weight", 500), ("output.weight", 1000)])


class Jobs(unittest.TestCase):
    def setUp(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        self.store = ModelStore(os.path.join(d, "models"))
        os.makedirs(self.store.root, exist_ok=True)
        self.guide = os.path.join(d, matcher.CATALOG["help"][0].file)
        open(self.guide, "wb").close()
        tiny(self.store.path("old-coder-7b.Q4_K_M.gguf"))
        open(self.store.path(BIG), "wb").close()  # the catalog's figures stand in for its header
        p = mock.patch.object(matcher, "read_machine", lambda **kw: machine())
        p.start()
        self.addCleanup(p.stop)

    def job(self, name):
        return next(j for j in jobs.view(self.store, self.guide)["jobs"] if j["job"] == name)

    def test_the_view(self):
        v = jobs.view(self.store, self.guide)
        system = self.job("system")
        self.assertTrue(system["locked"])
        self.assertEqual(system["current"]["file"], os.path.basename(self.guide))
        self.assertEqual(system["choices"], [])
        self.assertFalse(self.job("junior")["active"])
        coding = self.job("coding")
        self.assertEqual(coding["current"]["file"], BIG)  # ours: the best here that runs
        self.assertFalse(coding["chosen"])
        self.assertEqual({c["file"] for c in coding["choices"]}, {BIG, "old-coder-7b.Q4_K_M.gguf"})
        self.assertTrue(all(c["fits"] for c in coding["choices"]))
        self.assertEqual([c["file"] for c in self.job("vision")["choices"]], [BIG])  # only with a picture reader
        self.assertEqual({m["where"] for m in v["models"]}, {"system", "store"})

    def test_give_a_job_another_model_and_take_it_back(self):
        out = jobs.assign(self.store, "writing", "old-coder-7b.Q4_K_M.gguf", self.guide)
        self.assertEqual(out["model"], "old-coder-7b.Q4_K_M")
        plan = self.store.in_use("writing")
        self.assertEqual((plan["why"], plan["context"]), ("your choice", matcher.CONTEXT["writing"]))
        self.assertIn("-c", plan["args"])
        writing = self.job("writing")
        self.assertTrue(writing["chosen"])
        self.assertEqual(writing["current"]["model"], "old-coder-7b.Q4_K_M")
        jobs.assign(self.store, "writing", "", self.guide)  # our pick again
        self.assertIsNone(self.store.in_use("writing"))
        self.assertFalse(self.job("writing")["chosen"])

    def test_chosen_as_ours_would_be(self):
        """2026-10-08: the 27B ran at 32K as our pick and dropped to 16K once chosen in the Models view."""
        ours = matcher.match(machine())["coding"]
        jobs.assign(self.store, "coding", BIG, self.guide)
        mine = self.store.in_use("coding")
        self.assertEqual(ours["file"], BIG)
        self.assertEqual((mine["context"], mine["mode"]), (ours["context"], ours["mode"]))
        self.assertIn(str(ours["context"]), mine["args"])
        self.assertEqual(ours["context"], matcher.MORE_CONTEXT["coding"])  # 32K fits a free 1080 Ti

    def test_refused(self):
        for job, file, why in (("system", BIG, "stay with the guide"), ("junior", BIG, "hand-offs"),
                               ("vision", "old-coder-7b.Q4_K_M.gguf", "picture reader"),
                               ("coding", "not-here.gguf", "bring it back"), ("nope", BIG, "no job")):
            with self.assertRaisesRegex(jobs.JobError, why):
                jobs.assign(self.store, job, file, self.guide)
        with mock.patch.object(matcher, "read_machine", lambda **kw: matcher.Machine([], 4, 2, 2, False, 1.0, 50)):
            with self.assertRaisesRegex(jobs.JobError, "doesn't run"):
                jobs.assign(self.store, "coding", BIG, self.guide)
        self.assertEqual(self.store.state()["use"], {})

    def test_pictures_go_to_the_chosen_reader(self):
        jobs.assign(self.store, "vision", BIG, self.guide)
        c = vision.choose(self.store, {"model": self.guide})
        self.assertEqual((c["file"], c["plan"]["why"]), (BIG, "your choice"))
        self.assertEqual(c["projector"].file, "Qwen3.8-27B-mmproj-F16.gguf")


class Header(unittest.TestCase):
    def test_a_model_from_its_first_bytes(self):
        """The fit check reads the start of a file (a range request on Hugging Face) with the whole file's size."""
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        full, part = os.path.join(d, "full.gguf"), os.path.join(d, "part.gguf")
        tiny(full)
        with open(full, "rb") as f, open(part, "wb") as g:
            g.write(f.read(600))  # the header, none of the weights
        whole = matcher.model_from_gguf(full)
        start = matcher.model_from_gguf(part, name="full", size=os.path.getsize(full))
        self.assertEqual(whole, dataclasses.replace(start, file="full.gguf"))
        self.assertEqual(whole.weights, 2500)  # the tensors, not the header


class Words(unittest.TestCase):
    def test_job_lines(self):
        job = {"job": "coding", "active": True, "locked": False, "chosen": True,
               "current": {"model": "Qwen2.5-Coder 7B", "file": "c.gguf"}}
        for lang, (name, mine) in {"en": ("Writing code (AICUI)", "your choice"), "es": ("Escribir código (AICUI)",
                                   "tu elección"), "ja": ("コードを書く（AICUI）", "あなたの選択")}.items():
            self.assertEqual(words.job_lines(job, lang), (name, f"Qwen2.5-Coder 7B · {mine}"))
        self.assertIn("hand work", words.job_lines({"job": "review", "active": False}, "en")[1])
        self.assertIn("doesn't run", words.choice_label({"model": "X", "fits": False}, "en"))


if __name__ == "__main__":
    unittest.main()
