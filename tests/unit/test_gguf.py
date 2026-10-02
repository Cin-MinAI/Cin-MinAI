# SPDX-License-Identifier: GPL-3.0-or-later
"""gguf.py: a model's needs read from its file header (SPEC §4.2, §10.1), on a small hand-built GGUF.

    python3 -m unittest tests.unit.test_gguf -v        (from the repo root)
"""

import os
import struct
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))

from cin_minai.inference import gguf  # noqa: E402


def s(text: str) -> bytes:
    b = text.encode()
    return struct.pack("<Q", len(b)) + b


def build(path: str, meta: dict, tensors: list[tuple[str, int]]) -> None:
    kv = b""
    for k, v in meta.items():
        if isinstance(v, str):
            kv += s(k) + struct.pack("<I", 8) + s(v)
        elif isinstance(v, list) and v and isinstance(v[0], str):
            kv += s(k) + struct.pack("<IIQ", 9, 8, len(v)) + b"".join(s(x) for x in v)
        elif isinstance(v, list):
            kv += s(k) + struct.pack("<IIQ", 9, 4, len(v)) + b"".join(struct.pack("<I", x) for x in v)
        else:
            kv += s(k) + struct.pack("<II", 4, v)
    info, off = b"", 0
    for name, size in tensors:
        info += s(name) + struct.pack("<I", 1) + struct.pack("<Q", size) + struct.pack("<I", 0) + struct.pack("<Q", off)
        off += size
    head = b"GGUF" + struct.pack("<IQQ", 3, len(tensors), len(meta)) + kv + info
    pad = (32 - len(head) % 32) % 32
    with open(path, "wb") as f:
        f.write(head + b"\0" * pad + b"\1" * off)


class Gguf(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(tempfile.mkdtemp(), "m.gguf")
        build(self.path, {"general.architecture": "llama", "llama.block_count": 4, "llama.attention.head_count": 8,
                          "llama.attention.head_count_kv": 2, "llama.embedding_length": 512,
                          "tokenizer.ggml.tokens": ["a", "b", "c"]},
              [("token_embd.weight", 1000), ("blk.0.attn_q.weight", 500), ("blk.0.ffn_up_exps.weight", 4000),
               ("blk.1.ffn_up_exps.weight", 4000), ("output.weight", 1000)])

    def test_header_and_tensor_sizes(self):
        m = gguf.read(self.path)
        self.assertEqual((m.arch, m.layers), ("llama", 4))
        self.assertEqual(m.tensors["blk.0.ffn_up_exps.weight"], 4000)
        self.assertEqual(sum(m.tensors.values()), 10500)
        self.assertEqual((m.expert_bytes(), m.expert_bytes(1)), (8000, 4000))
        self.assertNotIn("tokenizer.ggml.tokens", {k for k, v in m.meta.items() if v is not None})  # skipped

    def test_kv_cache_and_need(self):
        m = gguf.read(self.path)
        # 4 layers x 2 KV heads x (64 + 64) per head x 1 byte (f16 = 2) ; head size 512 / 8 = 64
        self.assertEqual(m.kv_bytes_per_token("f16"), 4 * 2 * 128 * 2)
        m.meta["llama.full_attention_interval"] = 2  # hybrid: only every 2nd layer attends
        self.assertEqual(m.kv_bytes_per_token("f16"), 2 * 2 * 128 * 2)
        self.assertEqual(gguf.need_mib(m, 0, "f16"), 300)  # the compute margin's floor dominates a toy model

    def test_moe_options(self):
        self.assertIsNone(gguf.cpu_moe_layers(["--threads", "8"]))
        self.assertEqual(gguf.cpu_moe_layers(["--cpu-moe"]), -1)
        self.assertEqual(gguf.cpu_moe_layers(["--n-cpu-moe", "20"]), 20)
        with self.assertRaises(ValueError):
            gguf.read(__file__)


if __name__ == "__main__":
    unittest.main()
