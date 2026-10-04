# SPDX-License-Identifier: GPL-3.0-or-later
"""The system matcher (PLAN D60, M5): read the machine as llama.cpp sees it, and pick per task (help, writing,
coding) the best measured model that runs well on it, with its llama.cpp settings, an estimated speed and the
reason in plain words. Advice only: nothing is downloaded or changed here (D30: offered, never imposed).

    python3 -m cin_minai.inference.matcher [--json] [--profile machine.json]

Catalog figures (weights, KV per token, experts) were read with gguf.py from the real files (2026-10-02), since a
user won't have a file before downloading it. Quality order per task is the writing bakeoff and the coding runs
(SPEC §7.12, RESUME); speeds are estimated from memory bandwidth, calibrated on the 1080 Ti measurements, and shown
as a range.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import re
import shutil
import time

GiB, MiB = 1 << 30, 1 << 20
K_GPU = 0.38          # measured tok/s x bytes per token / card bandwidth (9B 0.47, 14B 0.37, 27B 0.32)
K_RAM = 3.0           # llama.cpp's RAM reads vs our one-thread copy test: 14.8 vs ~5 GB/s (27B IQ4_XS, 20 layers in DDR3)
K_CPU = 5.2           # all on the processor, every thread reading: the boot-test VM ran the 4B at 6.25 tok/s, copy test 3.3
COMPUTE_MIN = 300 * MiB
COMPUTE_TIGHT = 192 * MiB  # with -ub 256 (Qwen3.8-27B IQ3_XXS fit a free 11 GB card this way: 14.1 tok/s)


@dataclasses.dataclass(frozen=True)
class Model:
    name: str
    file: str
    weights: int            # bytes
    layers: int
    kv8: int                # KV bytes per token, q8_0 cache
    kv4: int                # q4_0 cache
    emb: int = 0            # token embeddings: llama.cpp keeps them in RAM
    experts: int = 0        # MoE expert bytes (kept in RAM with --n-cpu-moe)
    active: float = 1.0     # share of the expert bytes read per token (Qwen3.6-35B-A3B: 2.7 %, fitted to 25 tok/s)
    partial_ok: bool = False  # worth running with dense layers in RAM ("walk-away" use)
    note: str = ""
    source: str = ""        # "repo@revision" on Hugging Face ("" = ships on the ISO)
    sha256: str = ""
    size: int = 0           # file bytes
    remote: str = ""        # the file's name in the source repository, when ours differs ("" = the same)


# Vision (D64, D78): the projector each model reads pictures with, from its own Hugging Face repository (pinned; the
# checksums are the files the lab used on 2026-10-03). They're all called mmproj-F16.gguf there; ours say whose.
PROJECTORS = {
    "Qwen3.8-27B-UD-IQ3_XXS.gguf": Model("Vision for Qwen3.8-27B", "Qwen3.8-27B-mmproj-F16.gguf", 927607488, 0, 0, 0,
                                         source="unsloth/Qwen3.8-27B-GGUF@4ca720788d1e01f1bff70c033e0d0028fd02e502",
                                         sha256="cbb841a9ee0636b2ec172f5bb8df2ea8dfeb01e90fe7c6126581d662a0b4e43e",
                                         size=927607488, remote="mmproj-F16.gguf"),
    # the tuned guide reads pictures with its untuned base model's projector: it works, quality not guaranteed (D64)
    "Qwen3.5-4B-guide-HO-Q4_K_M.gguf": Model("Vision for the guide (Qwen3.5-4B)", "Qwen3.5-4B-mmproj-F16.gguf",
                                             672423616, 0, 0, 0,
                                             source="unsloth/Qwen3.5-4B-GGUF@e87f176479d0855a907a41277aca2f8ee7a09523",
                                             sha256="cd88edcf8d031894960bb0c9c5b9b7e1fea6ebee02b9f7ce925a00d12891f864",
                                             size=672423616, remote="mmproj-F16.gguf"),
}
VISION_CONTEXT = 16384
IMAGE_MIB = 600  # room for reading the picture: at 16K this gives the 27B two layers in RAM on a free 1080 Ti, as measured


def vision_plan(m: Model, machine: Machine) -> dict | None:
    """How this machine runs m while it reads pictures: like plan(), with room kept for the image."""
    if machine.cards:
        card = dict(machine.cards[0], free_mib=machine.cards[0]["free_mib"] - IMAGE_MIB)
        machine = dataclasses.replace(machine, cards=[card, *machine.cards[1:]])
    return plan(m, machine, VISION_CONTEXT)


# best first, per task; the figures from the files (gguf.py), the order from our measurements
CATALOG = {
    "help": [
        Model("Cin-MinAI guide (Qwen3.5-4B, tuned)", "Qwen3.5-4B-guide-HO-Q4_K_M.gguf", 2772477952, 33, 17408, 9216, emb=521472000,
              note="tuned for the guide's tools; ships on the ISO"),
    ],
    "writing": [
        Model("Qwen3-14B Q4_K_M", "Qwen3-14B-Q4_K_M.gguf", 8995793920, 40, 87040, 46080, emb=437575680,
              source="Qwen/Qwen3-14B-GGUF@530227a7d994db8eca5ab5ced2fb692b614357fd",
              sha256="500a8806e85ee9c83f3ae08420295592451379b4f8cf2d0f41c15dffeb6b81f0", size=9001752960, note="steadiest on long stories: the only model that kept the circle in order"),
        Model("Qwen3.5-9B Q4_K_M", "Qwen3.5-9B-Q4_K_M.gguf", 5669554176, 32, 17408, 9216, emb=572129280,
              source="unsloth/Qwen3.5-9B-GGUF@3885219b6810b007914f3a7950a8d1b469d598a5",
              sha256="03b74727a860a56338e042c4420bb3f04b2fec5734175f4cb9fa853daf52b7e8", size=5680522464, note="1.9 % restated sentences (the 4B: 24.6 %), fast"),
        Model("Qwen3.6-35B-A3B Q4_K_M (experts in RAM)", "Qwen3.6-35B-A3B-Q4_K_M.gguf", 20408576512, 40, 10880, 5760, emb=286064640,
              experts=18119393280, active=0.027, source="ggml-org/Qwen3.6-35B-A3B-GGUF@baec3ebee244827cda0f4557eafa8b28f7545fa6",
              sha256="671e47e0ec53c665d048b98c3ecbfd5236b5ca9c3e02ed19fc8f81f7b85140c7", size=20419565568, note="35B quality on a small card when the machine has the RAM"),
        Model("Cin-MinAI guide (Qwen3.5-4B, tuned)", "Qwen3.5-4B-guide-HO-Q4_K_M.gguf", 2772477952, 33, 17408, 9216, emb=521472000,
              note="works everywhere, but repeats itself more in long stories"),
    ],
    "coding": [
        Model("Qwen3.8-27B IQ3_XXS", "Qwen3.8-27B-UD-IQ3_XXS.gguf", 10923864064, 65, 34816, 18432, emb=417177600,
              source="unsloth/Qwen3.8-27B-GGUF@4ca720788d1e01f1bff70c033e0d0028fd02e502",
              sha256="c0b7c3038681ed2e3040456c1dd45f9858b6c2290bed172c70388a94874f3eee", size=10934860704, note="the most reliable coder we tried; 14.1 tok/s fully on a free 11 GB card"),
        Model("Qwen3.6-35B-A3B Q4_K_M (experts in RAM)", "Qwen3.6-35B-A3B-Q4_K_M.gguf", 20408576512, 40, 10880, 5760, emb=286064640,
              experts=18119393280, active=0.027, source="ggml-org/Qwen3.6-35B-A3B-GGUF@baec3ebee244827cda0f4557eafa8b28f7545fa6",
              sha256="671e47e0ec53c665d048b98c3ecbfd5236b5ca9c3e02ed19fc8f81f7b85140c7", size=20419565568, note="fast interactive coding on a small card with lots of RAM"),
        Model("Qwen3.8-27B IQ4_XS (part in RAM)", "Qwen3.8-27B-UD-IQ4_XS.gguf", 14241849344, 65, 34816, 18432, emb=546304000,
              partial_ok=True, source="unsloth/Qwen3.8-27B-GGUF@4ca720788d1e01f1bff70c033e0d0028fd02e502",
              sha256="40fac4050e940397dbf13087afd50f4734a11805bf9d65ef8ddd7483470e6199", size=14252845984, note="better 4-bit weights, slow: send it a task and come back later"),
        Model("Qwen3.5-9B Q4_K_M", "Qwen3.5-9B-Q4_K_M.gguf", 5669554176, 32, 17408, 9216, emb=572129280, source="unsloth/Qwen3.5-9B-GGUF@3885219b6810b007914f3a7950a8d1b469d598a5",
              sha256="03b74727a860a56338e042c4420bb3f04b2fec5734175f4cb9fa853daf52b7e8", size=5680522464, note="small and quick"),
    ],
}
CONTEXT = {"help": 8192, "writing": 8192, "coding": 16384}  # coding: 16K keeps more of a project in view (Ian)
# More context where it costs nothing: the same model with the same placement (no more of it in RAM). On the 1080 Ti
# with the desktop on the board's graphics, the 27B takes 32K whole on the card (~290 MiB more than 16K); with the
# desktop drawn on the card, a flat 32K would have moved layers to RAM or switched model (2026-10-03).
MORE_CONTEXT = {"coding": 32768}
# Not a correction (2026-10-03, tried and reverted the same day): 32K left 51 MiB of the plan's 200 MiB margin, but
# that margin is for a desktop drawn on the card, and this one isn't; 150 MiB more took 32K away from the 1080 Ti,
# whose free memory llama.cpp reads ~100 MiB lower than nvidia-smi.
MORE_CONTEXT_EXTRA_MIB = 0

# memory bandwidth of common cards (GB/s), for the speed estimate; unknown cards: 300
CARD_BW = [("4090", 1008), ("4080", 717), ("4070 ti", 504), ("4070", 504), ("4060 ti", 288), ("4060", 272),
           ("3090", 936), ("3080", 760), ("3070", 448), ("3060 ti", 448), ("3060", 360), ("3050", 224),
           ("2080 ti", 616), ("2080", 448), ("2070", 448), ("2060", 336), ("1660", 192), ("1080 ti", 484),
           ("1080", 320), ("1070", 256), ("1060", 192), ("7900", 960), ("7800", 624), ("7700", 432), ("7600", 288),
           ("6900", 512), ("6800", 512), ("6700", 384), ("6600", 224), ("5700", 448), ("5600", 288), ("arc a770", 560),
           ("arc a750", 512), ("arc b580", 456)]


@dataclasses.dataclass
class Machine:
    cards: list            # [{"name", "api": "CUDA0"/"Vulkan0", "total_mib", "free_mib"}]
    ram_total_gib: float
    ram_avail_gib: float
    cores: int
    avx2: bool
    ram_bw_gbs: float      # measured (copy) bandwidth
    disk_free_gib: float


def card_bw(name: str) -> int:
    n = name.lower()
    return next((bw for key, bw in CARD_BW if key in n), 300)


def measure_ram_bw(mib: int = 256) -> float:
    """A rough copy-bandwidth test (one thread, a second or less); llama.cpp's many threads read faster, which
    K_RAM accounts for."""
    src = bytearray(mib * MiB)
    t0 = time.perf_counter()
    for _ in range(3):
        bytes(src)
    return round(3 * mib * MiB / (time.perf_counter() - t0) / 1e9 * 2, 1)  # read + write


def own_server_mib() -> int:
    """Graphics memory held by our own llama-server (the loaded assistant model), from nvidia-smi; 0 if unknown."""
    import subprocess
    try:
        out = subprocess.run(["nvidia-smi", "--query-compute-apps=process_name,used_memory",
                              "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.TimeoutExpired):
        return 0
    return sum(int(mem) for name, mem in (line.rsplit(",", 1) for line in out.splitlines() if "," in line)
               if "llama-server" in name and mem.strip().isdigit())


def read_machine(devices: list | None = None, models_dir: str | None = None) -> Machine:
    """devices: [(api, name, total_mib, free_mib)] as LlamaCppBackend.list_devices() returns them."""
    if devices is None:
        from .llamacpp import LlamaCppBackend
        devices = LlamaCppBackend({"server_dir": os.environ.get("CINMINAI_LLAMA_DIR", "/usr/lib/cinminai/llama")},
                                  lambda m: None).list_devices()
    ours = own_server_mib()  # our own model comes off the card when the model is switched: count it as free
    desk = desktop_mib()
    seen, cards = set(), []
    for api, name, total, free in devices:  # one card shows as CUDA and Vulkan: CUDA first
        free = min(total, free + ours) if api.startswith("CUDA") else free
        if name in seen:
            continue
        seen.add(name)
        cards.append({"name": name, "api": api, "total_mib": total, "free_mib": free,
                      **({"desktop_mib": desk} if api.startswith("CUDA") and desk is not None else {})})
    mem = dict(re.findall(r"^(\w+):\s+(\d+)", open("/proc/meminfo").read(), re.M)) if os.path.exists("/proc/meminfo") else {}
    flags = open("/proc/cpuinfo").read() if os.path.exists("/proc/cpuinfo") else ""
    from .hardware import physical_cores
    return Machine(cards, int(mem.get("MemTotal", 0)) / 2**20, int(mem.get("MemAvailable", 0)) / 2**20,
                   physical_cores(), " avx2" in flags, measure_ram_bw(),
                   shutil.disk_usage(models_dir or os.path.expanduser("~")).free / GiB)


def _compute(weights: int) -> int:
    return max(COMPUTE_MIN, int(weights * 0.05))


def margin_mib(card: dict) -> int:
    """Room for the desktop to grow: 600 MiB when it's drawn on this card, 200 when it's offloaded. From the
    graphics processes nvidia-smi reports when known (4K drawn on the card: Xorg + Cinnamon ~830 MiB; offloaded to
    the board's graphics ~350): llama.cpp's "used" also counts its own CUDA context (after a reboot: 872)."""
    desktop = card.get("desktop_mib")
    if desktop is None:
        desktop = card["total_mib"] - card["free_mib"] - 250
    return 600 if desktop > 500 else 200


def desktop_mib() -> int | None:
    """Graphics memory of the desktop's processes on the NVIDIA card (type G in nvidia-smi), or None."""
    import subprocess
    try:
        out = subprocess.run(["nvidia-smi"], capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    found = [int(m) for m in re.findall(r"\s+G\s+\S.*?(\d+)MiB\s*\|", out)]
    return sum(found) if found else (0 if "Processes" in out else None)


def room_mib(card: dict) -> int:
    """Free graphics memory to plan with: what llama.cpp reports free, minus a margin for the desktop to grow
    (bigger when the desktop is drawn on this card: something already uses it)."""
    return card["free_mib"] - margin_mib(card)


def plan(m: Model, machine: Machine, ctx: int) -> dict | None:
    """The fastest way this machine runs the model, or None. Tries: all on the card (q8_0, then q4_0 cache),
    MoE experts in RAM, dense layers in RAM (only for walk-away models), the processor."""
    card = machine.cards[0] if machine.cards else None
    ram_room = (machine.ram_avail_gib - 3) * GiB  # leave the desktop and apps their share
    if card:
        room, bw = room_mib(card) * MiB, card_bw(card["name"])
        card_w = m.weights - m.emb
        for cache, kv, compute, extra in (("q8_0", m.kv8, _compute(card_w), []), ("q4_0", m.kv4, _compute(card_w), []),
                                          ("q4_0", m.kv4, COMPUTE_TIGHT, ["-ub", "256"])):
            need = card_w + kv * ctx + compute
            if need <= room and not m.experts:
                return {"mode": "all on the graphics card", "cache": cache, "args": ["-ngl", "99", *extra],
                        "card_gb": need / GiB, "ram_gb": m.emb / GiB, "tok_s": K_GPU * bw * 1e9 / card_w}
        if m.experts:
            dense = m.weights - m.experts
            per_layer = m.experts / m.layers
            for n in range(0, m.layers + 1):  # fewest layers' experts in RAM that fit
                on_card = dense + per_layer * (m.layers - n) + m.kv8 * ctx + _compute(dense)
                in_ram = per_layer * n
                if on_card <= room and in_ram <= ram_room:
                    t = (dense + per_layer * (m.layers - n) * m.active) / (K_GPU * bw * 1e9) + \
                        in_ram * m.active / (K_RAM * machine.ram_bw_gbs * 1e9)
                    return {"mode": f"on the card, experts of {n} layers in RAM", "cache": "q8_0",
                            "args": ["-ngl", "99", "--n-cpu-moe", str(n)], "card_gb": on_card / GiB,
                            "ram_gb": in_ram / GiB, "tok_s": 1 / t}
            return None
        # a near-fit, dense: the feed-forward weights of the last 1-8 layers in RAM, everything else on the card
        # (Qwen3.8-27B IQ3_XXS: 12.9 tok/s with one layer's in RAM, 14.1 with none, 2026-10-02)
        if not m.experts:
            ffn = 0.75 * card_w / m.layers
            for k in range(1, 9):  # 1-8: each in RAM costs ~1 tok/s on DDR3
                need = card_w - k * ffn + m.kv4 * ctx + COMPUTE_TIGHT
                if need <= room:
                    t = (card_w - k * ffn) / (K_GPU * bw * 1e9) + k * ffn / (K_RAM * machine.ram_bw_gbs * 1e9)
                    last = "|".join(str(m.layers - 2 - i) for i in range(k))  # the last real layers (one is output)
                    return {"mode": f"on the card, {k} layer{'s' if k > 1 else ''}' feed-forward weights in RAM",
                            "cache": "q4_0", "args": ["-ngl", "99", "-ub", "256", "-ot",
                                                      rf"blk\.({last})\.ffn_(up|gate|down).*=CPU"],
                            "card_gb": need / GiB, "ram_gb": (m.emb + k * ffn) / GiB, "tok_s": 1 / t}
        if m.partial_ok:
            per = m.weights / m.layers
            n = int((room - m.kv8 * ctx - _compute(m.weights)) // per)
            if n > m.layers // 3 and (m.layers - n) * per <= ram_room:
                t = n * per / (K_GPU * bw * 1e9) + (m.layers - n) * per / (K_RAM * machine.ram_bw_gbs * 1e9)
                return {"mode": f"{n} of {m.layers} layers on the card, the rest in RAM", "cache": "q8_0",
                        "args": ["-ngl", str(n)], "card_gb": room / GiB, "ram_gb": (m.layers - n) * per / GiB,
                        "tok_s": 1 / t}
        return None
    cpu_room = (machine.ram_avail_gib - 1) * GiB  # mapped from the file: the page cache holds it (8 GB live VM)
    if m.weights + m.kv8 * ctx <= cpu_room and m.weights <= 6 * GiB:  # the processor: small models only
        return {"mode": "on the processor", "cache": "q8_0", "args": ["--device", "none"], "card_gb": 0,
                "ram_gb": m.weights / GiB, "tok_s": K_CPU * machine.ram_bw_gbs * 1e9 / m.weights}
    return None


def match(machine: Machine) -> dict:
    out = {}
    for task, models in CATALOG.items():
        slow = None  # the last resort: works, but slowly here
        for m in models:
            p = plan(m, machine, CONTEXT[task])
            if p and slow is None or (p and m is models[-1]):
                slow = (m, p)
            if p and (p["tok_s"] >= (2 if m.partial_ok else 6) or task == "help"):
                ctx = CONTEXT[task]
                tighter = dataclasses.replace(machine, cards=[{**c, "free_mib": c["free_mib"] - MORE_CONTEXT_EXTRA_MIB}
                                                              for c in machine.cards])
                big = plan(m, tighter, MORE_CONTEXT[task]) if task in MORE_CONTEXT else None
                if big and big["mode"] == p["mode"]:
                    ctx, p = MORE_CONTEXT[task], big
                lo, hi = p["tok_s"] * 0.7, p["tok_s"] * 1.3
                out[task] = {"model": m.name, "file": m.file, "why": m.note, **p, "context": ctx,
                             "source": m.source, "size": m.size, "sha256": m.sha256,
                             "reserve_mib": margin_mib(machine.cards[0]) if machine.cards else 0,
                             "tok_s": [round(lo, 1), round(hi, 1)],
                             "args": p["args"] + ["-c", str(ctx), "-fa", "on", "-ctk", p["cache"],
                                                  "-ctv", p["cache"]]}
                break
        else:
            out[task] = None
            if slow:
                m, p = slow
                out[task] = {"model": m.name, "file": m.file, "why": m.note + "; slow on this computer", **p,
                             "source": m.source, "size": m.size, "sha256": m.sha256,
                             "reserve_mib": margin_mib(machine.cards[0]) if machine.cards else 0,
                             "context": CONTEXT[task], "tok_s": [round(p["tok_s"] * 0.7, 1), round(p["tok_s"] * 1.3, 1)],
                             "args": p["args"] + ["-c", str(CONTEXT[task]), "-fa", "on", "-ctk", p["cache"],
                                                  "-ctv", p["cache"]]}
    return out


def report(machine: Machine, result: dict) -> str:
    lines = ["This computer:"]
    for c in machine.cards:
        lines.append(f"  graphics: {c['name']} ({c['api']}), {c['total_mib'] / 1024:.1f} GB, "
                     f"{c['free_mib'] / 1024:.1f} GB free")
    if not machine.cards:
        lines.append("  graphics: none llama.cpp can use: models run on the processor")
    lines.append(f"  memory: {machine.ram_total_gib:.0f} GB ({machine.ram_avail_gib:.0f} GB free), "
                 f"{machine.cores} cores{', AVX2' if machine.avx2 else ''}, copy speed ~{machine.ram_bw_gbs} GB/s; "
                 f"{machine.disk_free_gib:.0f} GB free on disk")
    for task, r in result.items():
        if r is None:
            lines.append(f"{task.capitalize()}: no model in our list runs well here.")
            continue
        lo, hi = r["tok_s"]
        lines.append(f"{task.capitalize()}: {r['model']} — {r['mode']}, about {lo:.0f}-{hi:.0f} tokens a second "
                     f"(~{lo * 45:.0f}-{hi * 45:.0f} words a minute); {r['why']}.")
        lines.append(f"  llama.cpp: {' '.join(r['args'])}")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--profile", help="a machine as JSON instead of this one (for tests)")
    a = ap.parse_args()
    machine = Machine(**json.load(open(a.profile))) if a.profile else read_machine()
    result = match(machine)
    print(json.dumps({"machine": dataclasses.asdict(machine), "match": result}, indent=1) if a.json
          else report(machine, result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
