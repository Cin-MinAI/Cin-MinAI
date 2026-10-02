# SPDX-License-Identifier: GPL-3.0-or-later
"""What a model needs, read from its GGUF file (SPEC §4.2, §10.1): only the header and the tensor table are read
(a few MB even for a 20 GB file), with the standard library.

need_mib() replaces an estimate calibrated on the 4B guide that undercounted a 14B's context memory threefold
(2026-10-02): the weights to put on the graphics card (all, or without the MoE experts kept in RAM with
--cpu-moe / --n-cpu-moe), the KV cache from the model's own layers and heads at the chosen context and cache type,
and a margin for llama.cpp's compute buffers.
"""

from __future__ import annotations

import os
import re
import struct
from dataclasses import dataclass, field

_SCALAR = {0: "<B", 1: "<b", 2: "<H", 3: "<h", 4: "<I", 5: "<i", 6: "<f", 7: "<?", 10: "<Q", 11: "<q", 12: "<d"}
CACHE_BYTES = {"f16": 2.0, "q8_0": 34 / 32, "q4_0": 18 / 32}  # bytes per element of the KV cache


@dataclass
class Model:
    arch: str
    meta: dict
    tensors: dict = field(default_factory=dict)  # name -> bytes
    file_bytes: int = 0

    def get(self, key: str, default=None):
        return self.meta.get(f"{self.arch}.{key}", default)

    @property
    def layers(self) -> int:
        return int(self.get("block_count", 0))

    def expert_bytes(self, layers: int | None = None) -> int:
        """The MoE expert weights (all, or those of the first `layers` layers, as --n-cpu-moe keeps)."""
        total = 0
        for name, size in self.tensors.items():
            m = re.match(r"blk\.(\d+)\..*_exps", name)
            if m and (layers is None or int(m.group(1)) < layers):
                total += size
        return total

    def kv_bytes_per_token(self, cache: str = "q8_0") -> float:
        """K and V for every layer with attention (hybrid models such as Qwen3.5 attend only every n-th layer)."""
        heads_kv = self.get("attention.head_count_kv", self.get("attention.head_count", 0))
        heads = self.get("attention.head_count", 0)
        embd = int(self.get("embedding_length", 0))
        if isinstance(heads_kv, list):  # per layer; 0 = no attention in that layer
            per_layer = [int(h) for h in heads_kv]
        else:
            per_layer = [int(heads_kv)] * self.layers
        interval = self.get("full_attention_interval")
        if interval:  # recurrent layers in between keep a small fixed state, not a per-token cache
            per_layer = [h if (i + 1) % int(interval) == 0 else 0 for i, h in enumerate(per_layer)]
        head_dim = embd // int(heads if not isinstance(heads, list) else max(heads)) if heads else 0
        k = int(self.get("attention.key_length", head_dim))
        v = int(self.get("attention.value_length", head_dim))
        return sum(per_layer) * (k + v) * CACHE_BYTES.get(cache, 2.0)


def _string(f) -> str:
    (n,) = struct.unpack("<Q", f.read(8))
    return f.read(n).decode("utf-8", "replace")


def _value(f, kind: int, keep: bool = True):
    if kind == 8:
        return _string(f)
    if kind == 9:
        (sub, n) = struct.unpack("<IQ", f.read(12))
        if sub == 8:  # arrays of strings (the vocabulary): skipped, not kept
            for _ in range(n):
                (ln,) = struct.unpack("<Q", f.read(8))
                f.seek(ln, 1)
            return None
        fmt = _SCALAR[sub]
        size = struct.calcsize(fmt)
        if not keep or n > 4096:
            f.seek(size * n, 1)
            return None
        return [struct.unpack(fmt, f.read(size))[0] for _ in range(n)]
    fmt = _SCALAR[kind]
    return struct.unpack(fmt, f.read(struct.calcsize(fmt)))[0]


def read(path: str) -> Model:
    with open(path, "rb") as f:
        if f.read(4) != b"GGUF":
            raise ValueError(f"not a GGUF file: {path}")
        (version,) = struct.unpack("<I", f.read(4))
        if version < 2:
            raise ValueError(f"GGUF version {version} is too old")
        n_tensors, n_kv = struct.unpack("<QQ", f.read(16))
        meta = {}
        for _ in range(n_kv):
            key = _string(f)
            (kind,) = struct.unpack("<I", f.read(4))
            meta[key] = _value(f, kind)
        infos = []
        for _ in range(n_tensors):
            name = _string(f)
            (dims,) = struct.unpack("<I", f.read(4))
            f.seek(8 * dims + 4, 1)  # the shape and the type: the size comes from the offsets
            (offset,) = struct.unpack("<Q", f.read(8))
            infos.append((offset, name))
        align = int(meta.get("general.alignment", 32))
        start = (f.tell() + align - 1) // align * align
    size = os.path.getsize(path)
    infos.sort()
    ends = [o for o, _ in infos[1:]] + [size - start]
    tensors = {name: end - off for (off, name), end in zip(infos, ends)}
    return Model(str(meta.get("general.architecture", "")), meta, tensors, size)


def cpu_moe_layers(extra_args: list[str]) -> int | None:
    """From the configured llama-server options: None = experts on the card, -1 = all in RAM, n = first n layers."""
    args = [str(a) for a in extra_args]
    if "--cpu-moe" in args or "-cmoe" in args:
        return -1
    for flag in ("--n-cpu-moe", "-ncmoe"):
        if flag in args and args.index(flag) + 1 < len(args):
            return int(args[args.index(flag) + 1])
    return None


def cpu_overrides(extra_args: list[str]) -> list[str]:
    """The tensor patterns the options keep in RAM (-ot / --override-tensor PATTERN=CPU)."""
    args, out = [str(a) for a in extra_args], []
    for i, a in enumerate(args[:-1]):
        if a in ("-ot", "--override-tensor"):
            out += [p.rsplit("=", 1)[0] for p in args[i + 1].split(",") if p.upper().endswith("=CPU")]
    return out


def ubatch(extra_args: list[str]) -> int | None:
    args = [str(a) for a in extra_args]
    for flag in ("-ub", "--ubatch-size"):
        if flag in args and args.index(flag) + 1 < len(args) and args[args.index(flag) + 1].isdigit():
            return int(args[args.index(flag) + 1])
    return None


def need_mib(m: Model, context: int, cache: str = "q8_0", cpu_moe: int | None = None,
             cpu_patterns: list[str] = (), ub: int | None = None) -> int:
    """Graphics memory a load needs: weights on the card (not the token embeddings, which llama.cpp keeps in RAM,
    nor experts or tensors the options keep there) + KV cache + compute buffers (~ 5 % of the weights, at least
    300 MiB; ~192 MiB with -ub 256 — the 27B IQ3_XXS fit this way, matcher.COMPUTE_TIGHT)."""
    weights = (sum(m.tensors.values()) or m.file_bytes) - m.tensors.get("token_embd.weight", 0)
    if cpu_moe is not None:
        weights -= m.expert_bytes(None if cpu_moe < 0 else cpu_moe)
    rx = [re.compile(p) for p in cpu_patterns]
    weights -= sum(size for name, size in m.tensors.items() if any(r.search(name) for r in rx))
    kv = m.kv_bytes_per_token(cache) * context
    compute = (192 << 20) if ub is not None and ub <= 256 else max(300 << 20, int(weights * 0.05))
    return int((weights + kv + compute) / (1 << 20))
