# SPDX-License-Identifier: GPL-3.0-or-later
"""Cloud models for AICUI (docs/accounts-and-cloud.md): Anthropic by API key, for now.

Ian, 2026-10-12: "develop mostly locally and then have cloud come in and finalize. This way you save tokens where you
can." So every call here is made to cost little and to say what it cost:

* **The key** comes from the login keyring (accounts.cloud_key) at the moment of the call; it never reaches a model, a
  file, a log or the screen.
* **A budget per project** (`.cinminai/cloud.json`, "budget_usd"): checked before every call against what the project's
  usage log already holds, so a run can't go past it; stopping says how much was spent.
* **Every call is logged with its cost** (`.cinminai/cloud-usage.jsonl`): tokens in, out, from the cache, and dollars.
* **Prompt caching**: the instructions and the conversation so far are marked for Anthropic's cache, so the context
  each step repeats is charged at a tenth.
* The agent's steps are held to its JSON schema the way the local models' are, through one forced tool call.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Callable

API = "https://api.anthropic.com/v1"
VERSION = "2023-06-01"
# dollars per million tokens: input, output, writing the cache, reading the cache (Anthropic's prices, 2026-10)
PRICES = {"haiku": (1.00, 5.00, 1.25, 0.10), "sonnet": (3.00, 15.00, 3.75, 0.30), "opus": (5.00, 25.00, 6.25, 0.50)}
DEFAULT_MODEL = "claude-haiku-4-5-20251001"
SETTINGS = os.path.join(".cinminai", "cloud.json")
USAGE = os.path.join(".cinminai", "cloud-usage.jsonl")


class CloudError(Exception):
    """Said to the person as it is: a refused key, a budget used up, the service down."""


def settings(root: str) -> dict:
    """The project's cloud choice: {"provider", "model", "role": off|finisher|exclusive|lead, "budget_usd",
    "crew": one|two (a lead's local contributors)}."""
    try:
        with open(os.path.join(root, SETTINGS), encoding="utf-8") as f:
            s = json.load(f)
    except (OSError, ValueError):
        s = {}
    return {"provider": s.get("provider", "anthropic"), "model": s.get("model", DEFAULT_MODEL),
            "role": s.get("role", "off"), "budget_usd": float(s.get("budget_usd", 1.0)),
            "crew": "two" if s.get("crew") == "two" else "one"}


def save_settings(root: str, **change) -> dict:
    s = {**settings(root), **change}
    path = os.path.join(root, SETTINGS)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        json.dump(s, f, indent=1)
    os.replace(path + ".tmp", path)
    return s


def spent(root: str) -> float:
    """Dollars this project has spent on cloud models, from its usage log."""
    total = 0.0
    try:
        with open(os.path.join(root, USAGE), encoding="utf-8") as f:
            for line in f:
                try:
                    total += float(json.loads(line).get("usd", 0))
                except ValueError:
                    pass
    except OSError:
        pass
    return total


def price_of(model: str) -> tuple[float, float, float, float]:
    return next((p for k, p in PRICES.items() if k in model), PRICES["sonnet"])  # unknown: the dearer guess


def blocks(content) -> list[dict]:
    """A message's content as Anthropic's blocks: text, and pictures (our image_url data: addresses) as images. No
    empty text: Anthropic refuses it (2026-10-12: a command that printed nothing ended Haiku's run)."""
    if isinstance(content, str):
        content = [{"type": "text", "text": content}]
    out = []
    for part in content or []:
        if part.get("type") == "image_url":
            head, _, data = ((part.get("image_url") or {}).get("url") or "").partition(",")
            mime = head[5:].split(";")[0] if head.startswith("data:") else "image/jpeg"
            out.append({"type": "image", "source": {"type": "base64", "media_type": mime, "data": data}})
        elif part.get("type") == "text" and str(part.get("text") or "").strip():
            out.append({"type": "text", "text": str(part["text"])})
    return out or [{"type": "text", "text": "(nothing)"}]


def flat_tools(schema: dict) -> list[dict]:
    """The agent's step schema (thinking + one action out of many, each with its own fields) as Anthropic tools: one
    per action, its fields flat, with `thinking` first. Claude models fill flat tools reliably; the one nested choice
    the local models are held to token by token came back as unusable replies (2026-10-12, Haiku on test10: 25 in a
    row). [] when the schema has no actions."""
    variants = (((schema or {}).get("properties") or {}).get("action") or {}).get("anyOf") or []
    thinking = ((schema or {}).get("properties") or {}).get("thinking") or {"type": "string"}
    tools = []
    for v in variants:
        props = dict(v.get("properties") or {})
        name = (props.pop("tool", None) or {}).get("const")
        if not name:
            continue
        required = [r for r in v.get("required", []) if r != "tool"]
        tools.append({"name": name, "description": f"Your next step: {name}. `thinking` first: a sentence or two.",
                      "input_schema": {"type": "object", "properties": {"thinking": thinking, **props},
                                       "required": ["thinking", *required]}})
    return tools


def label(model: str) -> str:
    """claude-haiku-4-5-20251001 → Claude Haiku 4.5"""
    parts = [x for x in model.split("-") if not (x.isdigit() and len(x) == 8)]
    words = [x.capitalize() for x in parts if not x.isdigit()]
    nums = [x for x in parts if x.isdigit()]
    return " ".join(words) + (" " + ".".join(nums) if nums else "")


def cost(model: str, usage: dict) -> float:
    p_in, p_out, p_write, p_read = price_of(model)
    return (usage.get("input_tokens", 0) * p_in + usage.get("output_tokens", 0) * p_out
            + usage.get("cache_creation_input_tokens", 0) * p_write
            + usage.get("cache_read_input_tokens", 0) * p_read) / 1e6


class Anthropic:
    """A chat backend shaped like the local one: chat(messages, schema, max_tokens, cancel, on_text) -> (text, timings)."""

    def __init__(self, root: str, key: Callable[[], str], model: str = DEFAULT_MODEL, context: int = 32768,
                 opener: Callable = urllib.request.urlopen) -> None:
        self.root, self.key, self.model, self.opener = root, key, model, opener
        self.cfg = {"context": context}
        self.profile = None

    def alive(self) -> bool:
        return True

    def unload(self) -> None:
        pass

    def _post(self, path: str, body: dict | None = None) -> dict:
        key = self.key()
        if not key:
            raise CloudError("no Anthropic key on this computer — add one from AICUI's Cloud models menu")
        req = urllib.request.Request(f"{API}/{path}", data=json.dumps(body).encode() if body is not None else None,
                                     headers={"x-api-key": key, "anthropic-version": VERSION,
                                              "content-type": "application/json", "User-Agent": "Cin-MinAI"},
                                     method="POST" if body is not None else "GET")
        try:
            with self.opener(req, timeout=300) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            try:
                said = json.loads(e.read() or b"{}").get("error", {}).get("message", "")
            except ValueError:
                said = ""
            raise CloudError(f"Anthropic said {e.code}" + (f": {said[:200]}" if said else "")) from None
        except OSError as e:
            raise CloudError(f"Anthropic didn't answer: {getattr(e, 'reason', e)}") from None

    def models(self) -> list[str]:
        """The models this key may use (a free call: it checks the key too)."""
        return [m["id"] for m in self._post("models?limit=50").get("data", [])]

    @staticmethod
    def shape(messages: list[dict]) -> tuple[list[dict], list[dict]]:
        """Our messages as Anthropic's: the system text apart, one turn per speaker in turn (notes after a result are
        merged into it), starting with the person; the last turn and the system text marked for the cache."""
        system = [{"type": "text", "text": m["content"]} for m in messages if m["role"] == "system"]
        turns: list[dict] = []
        for m in messages:
            if m["role"] == "system":
                continue
            role = "assistant" if m["role"] == "assistant" else "user"
            parts = blocks(m["content"])
            if turns and turns[-1]["role"] == role:
                last = turns[-1]["content"]
                for part in parts:  # text runs on in one block; a picture is a block of its own
                    if part["type"] == "text" and last[-1]["type"] == "text":
                        last[-1]["text"] += "\n\n" + part["text"]
                    else:
                        last.append(part)
            else:
                turns.append({"role": role, "content": parts})
        if turns and turns[0]["role"] != "user":
            turns.insert(0, {"role": "user", "content": [{"type": "text", "text": "(the conversation so far)"}]})
        if system:
            system[-1]["cache_control"] = {"type": "ephemeral"}
        if turns:
            turns[-1]["content"][-1]["cache_control"] = {"type": "ephemeral"}
        return system, turns

    def chat(self, messages: list[dict], schema: dict | None = None, max_tokens: int = 0, cancel=None, on_text=None,
             **_kw) -> tuple[str, dict]:
        s = settings(self.root)
        already = spent(self.root)
        if already >= s["budget_usd"]:
            raise CloudError(f"the cloud budget for this project is used up (${already:.2f} of ${s['budget_usd']:.2f}"
                             "); raise it in AICUI's Cloud models menu to go on")
        system, turns = self.shape(messages)
        body = {"model": self.model, "max_tokens": int(max_tokens or 4096), "messages": turns}
        if system:
            body["system"] = system
        tools = flat_tools(schema) if schema is not None else None
        if tools:  # every action its own tool with flat inputs; the model calls exactly one (see flat_tools)
            body["tools"] = tools
            body["tool_choice"] = {"type": "any"}
        elif schema is not None:  # a schema without actions (a distill's items): one forced tool, its input the reply
            body["tools"] = [{"name": "reply", "description": "Your reply.", "input_schema": schema}]
            body["tool_choice"] = {"type": "tool", "name": "reply"}
        start = time.monotonic()
        got = self._post("messages", body)
        usage = got.get("usage", {})
        usd = cost(self.model, usage)
        self.log(usage, usd)
        if schema is not None:
            block = next((b for b in got.get("content", []) if b.get("type") == "tool_use"), None)
            if block is None:
                text = ""
            elif tools:  # the agent's step: {"thinking", "action": {"tool": the tool called, its inputs}}
                inputs = dict(block.get("input") or {})
                thinking = str(inputs.pop("thinking", ""))
                text = json.dumps({"thinking": thinking, "action": {"tool": block.get("name", ""), **inputs}},
                                  ensure_ascii=False)
            else:
                text = json.dumps(block.get("input") or {}, ensure_ascii=False)
        else:
            text = "".join(b.get("text", "") for b in got.get("content", []) if b.get("type") == "text")
        if on_text:
            on_text(text)
        seconds = time.monotonic() - start
        out_n = usage.get("output_tokens", 0)
        return text, {"prompt_n": usage.get("input_tokens", 0) + usage.get("cache_creation_input_tokens", 0),
                      "cache_n": usage.get("cache_read_input_tokens", 0), "gen_n": out_n, "predicted_n": out_n,
                      "seconds": round(seconds, 1), "gen_tps": round(out_n / seconds, 1) if seconds else 0,
                      "usd": round(usd, 5), "capped": got.get("stop_reason") == "max_tokens"}

    def log(self, usage: dict, usd: float) -> None:
        path = os.path.join(self.root, USAGE)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"time": time.strftime("%Y-%m-%dT%H:%M:%S"), "model": self.model, **{
                k: usage.get(k, 0) for k in ("input_tokens", "output_tokens", "cache_creation_input_tokens",
                                             "cache_read_input_tokens")}, "usd": round(usd, 6)}) + "\n")
