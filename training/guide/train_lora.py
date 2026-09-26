#!/usr/bin/env python3
"""QLoRA fine-tune of a guide candidate on the transition corpus (training/guide/README.md, phase 3).

Same settings for every candidate; everything that affects the result is logged to OUT/run.json.

    python3 train_lora.py --base ~/cinminai-train/base/gemma-4-E2B-it \
        --data corpus/examples.jsonl --out runs/gemma-4-E2B [--epochs 2] [--limit 20]

The examples are in the runtime chat format (system, user, assistant call, tool result, assistant
reply). Loss is on the assistant turns only: each assistant turn's tokens are found by rendering the
conversation up to it with the model's own chat template, so no template-specific markers are needed.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import random
import time

import torch
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig


def encode(tok, messages: list[dict], max_len: int) -> dict | None:
    """input_ids + labels with -100 everywhere except the assistant turns.

    Template-independent: render the whole conversation once with the model's own chat template, find
    each assistant message's text in it (in order), and train on the tokens inside those spans plus
    the one token that closes the turn (end-of-turn marker). Returns None if a reply can't be found
    (the template changed it) or the example is too long."""
    text = tok.apply_chat_template(messages, tokenize=False, chat_template_kwargs={"enable_thinking": False})
    spans, pos = [], 0
    for m in messages:
        if m["role"] != "assistant":
            continue
        start = text.find(m["content"], pos)
        if start < 0:
            return None
        spans.append((start, start + len(m["content"])))
        pos = start + len(m["content"])
    enc = tok(text, add_special_tokens=False, return_offsets_mapping=True)
    ids, offs = enc["input_ids"], enc["offset_mapping"]
    if len(ids) > max_len:
        return None
    labels = [-100] * len(ids)
    for s, e in spans:
        last = None
        for k, (a, b) in enumerate(offs):
            if a >= s and b <= e and b > a:
                labels[k] = ids[k]
                last = k
        if last is not None and last + 1 < len(ids):  # the end-of-turn token
            labels[last + 1] = ids[last + 1]
    return {"input_ids": ids, "labels": labels}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True), ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--epochs", type=float, default=2), ap.add_argument("--lr", type=float, default=1e-4)
    ap.add_argument("--rank", type=int, default=16), ap.add_argument("--alpha", type=int, default=32)
    ap.add_argument("--max-len", type=int, default=2048), ap.add_argument("--accum", type=int, default=8)
    ap.add_argument("--seed", type=int, default=1), ap.add_argument("--limit", type=int)
    ap.add_argument("--targets", default="all-linear",
                    help="LoRA target modules, comma-separated, or all-linear. Qwen3.5: only the standard "
                         "attention/MLP projections — llama.cpp can't convert adapters on its linear-attention "
                         "projections (head reordering)")
    o = ap.parse_args()
    random.seed(o.seed)
    torch.manual_seed(o.seed)
    os.makedirs(o.out, exist_ok=True)

    tok = AutoTokenizer.from_pretrained(o.base)
    rows = [json.loads(l) for l in open(o.data, encoding="utf-8")]
    random.shuffle(rows)
    if o.limit:
        rows = rows[:o.limit]
    data, skipped = [], 0
    for r in rows:
        e = encode(tok, r["messages"], o.max_len)
        if e:
            data.append(e)
        else:
            skipped += 1
    print(f"{len(data)} examples, {skipped} skipped (too long or template not prefix-stable)", flush=True)

    bnb = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_use_double_quant=True,
                             bnb_4bit_compute_dtype=torch.bfloat16)
    model = AutoModelForCausalLM.from_pretrained(o.base, quantization_config=bnb, dtype=torch.bfloat16,
                                                 device_map={"": 0})
    model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True)
    model = get_peft_model(model, LoraConfig(r=o.rank, lora_alpha=o.alpha, lora_dropout=0.05,
                                             target_modules=o.targets if o.targets == "all-linear"
                                             else o.targets.split(","), task_type="CAUSAL_LM"))
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    opt = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=o.lr, weight_decay=0.0)
    steps = int(len(data) * o.epochs / o.accum)
    sched = torch.optim.lr_scheduler.LambdaLR(opt, lambda s: min(1.0, (s + 1) / max(1, steps // 20))
                                              * max(0.0, 1 - s / max(1, steps)))
    log, t0, step, seen = [], time.time(), 0, 0
    model.train()
    order = []
    while len(order) < steps * o.accum:
        order += random.sample(range(len(data)), len(data))
    order = order[:steps * o.accum]
    running = 0.0
    for k, idx in enumerate(order):
        e = data[idx]
        ids = torch.tensor([e["input_ids"]], device=0)
        lab = torch.tensor([e["labels"]], device=0)
        loss = model(input_ids=ids, labels=lab).loss / o.accum
        loss.backward()
        running += loss.item()
        seen += 1
        if (k + 1) % o.accum == 0:
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step(), sched.step(), opt.zero_grad()
            step += 1
            log.append({"step": step, "loss": round(running, 4), "lr": sched.get_last_lr()[0],
                        "elapsed_s": round(time.time() - t0, 1)})
            if step % 10 == 0 or step == steps:
                print(f"step {step}/{steps}  loss {running:.4f}  {time.time() - t0:.0f}s", flush=True)
            running = 0.0
    model.save_pretrained(os.path.join(o.out, "adapter"))
    import peft
    import transformers
    json.dump({"base": os.path.abspath(o.base), "data": os.path.abspath(o.data), "examples": len(data),
               "skipped": skipped, "epochs": o.epochs, "steps": steps, "lr": o.lr, "rank": o.rank,
               "alpha": o.alpha, "dropout": 0.05, "target_modules": o.targets, "max_len": o.max_len,
               "grad_accum": o.accum, "batch": 1, "quant": "nf4 double-quant, bf16 compute", "seed": o.seed,
               "trainable_params": trainable, "train_seconds": round(time.time() - t0),
               "gpu": torch.cuda.get_device_name(0), "peak_vram_gib": round(torch.cuda.max_memory_allocated() / 2**30, 2),
               "torch": torch.__version__, "transformers": transformers.__version__, "peft": peft.__version__,
               "python": platform.python_version(), "loss_log": log},
              open(os.path.join(o.out, "run.json"), "w"), indent=1)
    print("saved", os.path.join(o.out, "adapter"))


if __name__ == "__main__":
    main()
