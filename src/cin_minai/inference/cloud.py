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
import re
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


FAMILIES = ("opus", "sonnet", "haiku")  # the order the box lists them in
MODELS_CACHE = os.path.join(os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache"), "cinminai",
                            "cloud-models.json")


def offered(models: list) -> list:
    """The models worth offering from a provider's list: its current families, newest first, two of each."""
    import re

    def version(m: str) -> tuple:
        return tuple(int(x) for x in re.findall(r"(?<![0-9])(\d{1,2})(?![0-9])", m))
    out = []
    for fam in FAMILIES:
        mine = sorted((m for m in models if fam in m and m.startswith("claude-")), key=version, reverse=True)
        out += mine[:2]
    return out


def cached_models(provider: str = "anthropic") -> list:
    """The models a provider offered when last asked ([] before the first ask)."""
    try:
        with open(MODELS_CACHE, encoding="utf-8") as f:
            return list(json.load(f).get(provider, []))
    except (OSError, ValueError):
        return []


def cache_models(models: list, provider: str = "anthropic") -> None:
    try:
        with open(MODELS_CACHE, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {}
    data[provider] = list(models)
    os.makedirs(os.path.dirname(MODELS_CACHE), exist_ok=True)
    with open(MODELS_CACHE + ".tmp", "w", encoding="utf-8") as f:
        json.dump(data, f)
    os.replace(MODELS_CACHE + ".tmp", MODELS_CACHE)


CHECKED = ("claude-haiku-4-5", "claude-sonnet-4-6", "claude-opus-4-8")  # prices read on Anthropic's page, 2026-10-11


def price_checked(model: str) -> bool:
    """Is this model's price one we read? Others are counted at their family's price — an estimate, said so."""
    return model.startswith(CHECKED)


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


def as_call(content, names) -> dict | None:
    """One of our steps ({"thinking", "action": {"tool", …}}) as the tool_use block it was; None for anything else
    (an answer, an earlier write said as a sentence, a tool not offered now)."""
    if not names or not isinstance(content, str) or not content.startswith("{"):
        return None
    try:
        step = json.loads(content)
    except ValueError:
        return None
    act = step.get("action") if isinstance(step, dict) else None
    if not isinstance(act, dict) or act.get("tool") not in names:
        return None
    inputs = {k: v for k, v in act.items() if k != "tool"}
    return {"type": "tool_use", "name": act["tool"], "input": {WHY: str(step.get("thinking", "")), **inputs}}


WHY = "reason"  # the step's thinking, as the cloud's tools call it: named "thinking", Claude models closed it with
#                 </thinking> and went on in their own call markup inside it (2026-10-12, Haiku leading on test12)
MARKUP = re.compile(r"</?(thinking|invoke|parameter|function_calls)\b")
XML_PARAM = re.compile(r'<parameter name="(\w+)">(.*?)(?:</parameter>|$)', re.S)


def unleak(inputs: dict, required: list) -> dict:
    """Parameters a model wrote into its reason text taken back out, when the call is missing one it needs —
    JSON-style (2026-10-12, Haiku: `Read it.", "path": "a.txt", "start": 1} </invoke>` as the reason, no path) or
    in its own markup (`</thinking> <parameter name="command">…`); call markup is cut off the reason either way."""
    inputs = dict(inputs)
    why = str(inputs.get(WHY, ""))
    if not all(r in inputs for r in required):
        for name, value in XML_PARAM.findall(why):
            inputs.setdefault(name, value.strip())
        if '", "' in why:
            head = why[:why.rfind("}") + 1] if "}" in why else why + "}"
            for text in (head, why + '"}', why + "}"):
                try:
                    got = json.loads('{"' + WHY + '": "' + text)
                except ValueError:
                    continue
                if isinstance(got, dict):
                    inputs = {**got, **{k: v for k, v in inputs.items() if k != WHY}}
                    why = str(inputs.get(WHY, ""))
                    break
    m = MARKUP.search(why)
    if m:
        inputs[WHY] = why[:m.start()].strip()
    return inputs


def flat_tools(schema: dict) -> list[dict]:
    """The agent's step schema (thinking + one action out of many, each with its own fields) as Anthropic tools: one
    per action, its fields flat, with `thinking` first. Claude models fill flat tools reliably; the one nested choice
    the local models are held to token by token came back as unusable replies (2026-10-12, Haiku on test10: 25 in a
    row). [] when the schema has no actions."""
    variants = (((schema or {}).get("properties") or {}).get("action") or {}).get("anyOf") or []
    why = ((schema or {}).get("properties") or {}).get("thinking") or {"type": "string"}
    tools = []
    for v in variants:
        props = dict(v.get("properties") or {})
        name = (props.pop("tool", None) or {}).get("const")
        if not name:
            continue
        required = [r for r in v.get("required", []) if r != "tool"]
        tools.append({"name": name, "description": f"Your next step: {name}. `{WHY}` first: a sentence or two on why.",
                      "input_schema": {"type": "object", "properties": {WHY: why, **props},
                                       "required": [WHY, *required]}})
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
    def shape(messages: list[dict], names: set | frozenset = frozenset()) -> tuple[list[dict], list[dict]]:
        """Our messages as Anthropic's: the system text apart, one turn per speaker in turn (notes after a result are
        merged into it), starting with the person; the last turn and the system text marked for the cache. With the
        tools' `names`, each earlier step (our JSON) goes as the tool call it was and its result as that call's
        tool_result (2026-10-12: shown its own steps as JSON text but made to answer with tool calls, Haiku mixed the
        two — calls the API dropped, parameters written into its thinking)."""
        system = [{"type": "text", "text": m["content"]} for m in messages if m["role"] == "system"]
        turns: list[dict] = []
        calls = 0
        for m in messages:
            if m["role"] == "system":
                continue
            role = "assistant" if m["role"] == "assistant" else "user"
            parts = blocks(m["content"])
            call = as_call(m["content"], names) if role == "assistant" else None
            if call:
                calls += 1
                call["id"] = f"toolu_step{calls}"
                parts = [call]
            elif role == "user" and turns and turns[-1]["role"] == "assistant" and \
                    turns[-1]["content"][-1].get("type") == "tool_use":  # the answer to that call, first in its turn
                said = "\n\n".join(p["text"] for p in parts if p["type"] == "text")
                said = said[len("Result: "):] if said.startswith("Result: ") else said
                parts = [{"type": "tool_result", "tool_use_id": turns[-1]["content"][-1]["id"],
                          "content": said or "(nothing)"}] + [p for p in parts if p["type"] != "text"]
                turns.append({"role": "user", "content": parts})
                continue
            if turns and turns[-1]["role"] == role and turns[-1]["content"][-1].get("type") == "tool_use":
                turns.append({"role": "user", "content": [{"type": "tool_result", "content": "(nothing)",
                                                           "tool_use_id": turns[-1]["content"][-1]["id"]}]})
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
        tools = flat_tools(schema) if schema is not None else None
        system, turns = self.shape(messages, {t["name"] for t in tools or []})
        body = {"model": self.model, "max_tokens": int(max_tokens or 4096), "messages": turns}
        if system:
            body["system"] = system
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
            if block is None:  # no tool called: a step written as text is still a step; the reply is kept to study
                text = "".join(b.get("text", "") for b in got.get("content", []) if b.get("type") == "text").strip()
                self.keep(got)
            elif tools:  # the agent's step: {"thinking", "action": {"tool": the tool called, its inputs}}
                need = next((t["input_schema"]["required"] for t in tools if t["name"] == block.get("name")), [])
                inputs = unleak(dict(block.get("input") or {}), need)
                thinking = str(inputs.pop(WHY, "") or inputs.pop("thinking", ""))
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

    def keep(self, got: dict) -> None:
        """A reply with no step in it, kept as it came (its content and why it stopped; never the key) in
        .cinminai/cutoffs, to see what the model did instead (2026-10-12: Haiku leading, 8 unusable replies)."""
        folder = os.path.join(self.root, ".cinminai", "cutoffs")
        try:
            os.makedirs(folder, exist_ok=True)
            with open(os.path.join(folder, time.strftime("cloud-%Y%m%d-%H%M%S.json")), "w", encoding="utf-8") as f:
                json.dump({k: got.get(k) for k in ("stop_reason", "content", "usage")}, f, ensure_ascii=False, indent=1)
        except OSError:
            pass

    def log(self, usage: dict, usd: float) -> None:
        path = os.path.join(self.root, USAGE)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"time": time.strftime("%Y-%m-%dT%H:%M:%S"), "model": self.model, **{
                k: usage.get(k, 0) for k in ("input_tokens", "output_tokens", "cache_creation_input_tokens",
                                             "cache_read_input_tokens")}, "usd": round(usd, 6)}) + "\n")
