# SPDX-License-Identifier: GPL-3.0-or-later
"""Cloud models for AICUI (docs/accounts-and-cloud.md): Anthropic and OpenAI, each by API key.

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
# the 5.5 generation first (read 2026-10-26 from Anthropic's model table; cache writes at 1.25x input; Haiku 5.5's cache
# read a tenth of its input, as Anthropic's caching page says for every model but Fable and Opus 5.5), then each family
PRICES = {"haiku-5-5": (0.10, 0.50, 0.125, 0.01), "sonnet-5-5": (2.00, 10.00, 2.50, 0.20),
          "opus-5-5": (4.00, 20.00, 5.00, 0.20),
          "haiku": (1.00, 5.00, 1.25, 0.10), "sonnet": (3.00, 15.00, 3.75, 0.30), "opus": (5.00, 25.00, 6.25, 0.50)}
# a price step: past this many prompt tokens a call costs this many times more (Anthropic's model table: Haiku 5.5 is
# $0.10/$0.50 up to 100K-token prompts, $0.50/$2.50 above; 2026-10-27, test29: 261 of 828 calls were past it, $1.31
# logged against about $4.17 billed, and the credit ran out mid-run)
STEPS = {"haiku-5-5": (100_000, 5.0)}
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
    model = s.get("model") or last_model() or DEFAULT_MODEL
    return {"provider": provider_of(model), "model": model,
            "role": s.get("role", "off"), "budget_usd": float(s.get("budget_usd", 1.0)),
            "crew": "two" if s.get("crew") == "two" else "one"}


def _last_model_path() -> str:
    return os.path.join(os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache"), "cinminai",
                        "cloud-last-model")


def last_model() -> str:
    """The cloud model the person chose last, in any project: a new project starts from it (2026-10-26, test22: a new
    project started on Haiku 4.5, the built-in default, though Ian had chosen GPT-6 Luna)."""
    try:
        with open(_last_model_path(), encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def save_settings(root: str, **change) -> dict:
    s = {**settings(root), **change}
    if change.get("model"):
        try:
            os.makedirs(os.path.dirname(_last_model_path()), exist_ok=True)
            with open(_last_model_path(), "w", encoding="utf-8") as f:
                f.write(str(change["model"]))
        except OSError:
            pass
    path = os.path.join(root, SETTINGS)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        json.dump(s, f, indent=1)
    os.replace(path + ".tmp", path)
    return s


REPRICED = re.compile(r"claude-(haiku|sonnet|opus)-5-5")


def spent(root: str) -> float:
    """Dollars this project has spent on cloud models, from its usage log."""
    total = 0.0
    try:
        with open(os.path.join(root, USAGE), encoding="utf-8") as f:
            for line in f:
                try:
                    e = json.loads(line)
                    model = str(e.get("model", ""))
                    # the 5.5 generation's calls logged before its prices were read (Haiku 5.5 at Haiku 4.5's, ten
                    # times too high) are counted again from their tokens (2026-10-26)
                    total += cost(model, e) if REPRICED.search(model) and "output_tokens" in e else \
                        float(e.get("usd", 0))
                except (ValueError, TypeError, AttributeError):
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


CHECKED = ("claude-haiku-4-5", "claude-sonnet-4-6", "claude-opus-4-8",  # prices read on Anthropic's page, 2026-10-11
           "claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5")  # and the 5.5 generation's, 2026-10-26


# --- forced tool use, tried first and given up per model when refused (Ian, 2026-10-26: "make a 2 time attempt for every
# cloud model, first with our arrangement then with whatever you do next"; Claude Sonnet 5.5 said 400 "tool_choice: type
# "tool" and "any" are not supported for this model", as Opus 5.5 and Fable 5.1 do) ----------------------------------------
CHOOSE_ONE = "Reply only by calling exactly one of your tools, never in plain text."
# the 5 generation thinks before every answer, and its thinking counts against max_tokens (2026-10-26: Sonnet 5.5's
# picture answers came back empty at look's 300 tokens): room on top, as OpenAI's reasoning models get REASONING_ROOM
THINKING_ROOM = 4096
FALLBACK_BETA = "server-side-fallback-2026-07-01"  # a refused step goes to the model Anthropic picks for its category


def thinks(model: str) -> bool:
    return bool(re.match(r"claude-(opus|sonnet|haiku|fable|mythos)-5", model))


def is_step(text: str) -> bool:
    """A step written as JSON text (it's tried as it is)."""
    try:
        return isinstance(json.loads(text), dict) and "action" in json.loads(text)
    except ValueError:
        return False


def falls_back(model: str) -> bool:
    """The models Anthropic's server-side fallback serves (its "default" routing)."""
    return model.startswith(("claude-sonnet-5-5", "claude-opus-5-5", "claude-fable-5-1"))


def _free_choice_path() -> str:
    return os.path.join(os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache"), "cinminai",
                        "cloud-free-choice.json")


def free_choice(model: str) -> bool:
    """Has this model refused forced tool use before (on this computer)? Then it's asked with a free choice at once."""
    try:
        with open(_free_choice_path(), encoding="utf-8") as f:
            return model in json.load(f)
    except (OSError, ValueError, TypeError):
        return False


def remember_free_choice(model: str) -> None:
    path = _free_choice_path()
    try:
        with open(path, encoding="utf-8") as f:
            known = set(json.load(f))
    except (OSError, ValueError, TypeError):
        known = set()
    known.add(model)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path + ".tmp", "w", encoding="utf-8") as f:
            json.dump(sorted(known), f)
        os.replace(path + ".tmp", path)
    except OSError:
        pass  # remembered for this call only


def refused_choice(e: Exception) -> bool:
    """The provider refused the request's tool_choice (a 400 that names it), not the request as a whole."""
    said = str(e)
    return " 400" in said and "tool_choice" in said


def price_checked(model: str) -> bool:
    """Is this model's price one we read? Others are counted at their family's price — an estimate, said so."""
    return model in OPENAI_PRICES or model.startswith(CHECKED)  # OpenAI's: read on its pricing page, 2026-10-16


def price_of(model: str) -> tuple[float, float, float, float]:
    """(input, output, writing the cache, reading the cache) in dollars per million tokens. OpenAI writes its cache
    for free: its third figure is the input price (the uncached tokens) and the fourth its cached-input price."""
    if provider_of(model) == "openai":
        p = OPENAI_PRICES.get(model) or next((v for k, v in sorted(OPENAI_PRICES.items(), key=lambda kv: -len(kv[0]))
                                              if model.startswith(k)), OPENAI_PRICES["gpt-6.1-sol"])
        return (p[0], p[2], p[0], p[1])
    return next((p for k, p in PRICES.items() if k in model), PRICES["sonnet"])  # unknown: the dearer guess


# --- OpenAI (D35, 2026-10-16): by API key, through the Responses API (the GPT-6 models take tools only there) ----------
OPENAI_API = "https://api.openai.com/v1"
# dollars per million tokens: input, cached input, output — OpenAI's pricing page, read 2026-10-16
OPENAI_PRICES = {"gpt-6-astra": (10.00, 1.00, 50.00), "gpt-6.1-sol": (2.00, 0.10, 10.00), "gpt-6-luna": (0.10, 0.01, 0.50),
                 "gpt-6-sol": (2.00, 0.20, 10.00), "gpt-5.6-sol": (4.00, 0.40, 20.00),
                 "gpt-5.6-terra": (2.00, 0.20, 12.00), "gpt-5.6-luna": (0.20, 0.02, 1.20), "gpt-5.5": (5.00, 0.50, 30.00),
                 "gpt-5.4": (2.50, 0.25, 15.00), "gpt-5.4-mini": (0.75, 0.075, 4.50), "gpt-5.4-nano": (0.20, 0.02, 1.25),
                 "gpt-5": (1.25, 0.125, 10.00), "gpt-5-mini": (0.25, 0.025, 2.00), "gpt-5-nano": (0.05, 0.005, 0.40),
                 "gpt-4.1": (2.00, 0.50, 8.00), "gpt-4.1-mini": (0.40, 0.10, 1.60)}
OPENAI_OFFER = ("gpt-6.1-sol", "gpt-6-luna", "gpt-6-astra", "gpt-5.6-terra", "gpt-5.6-luna")  # the box, in this order
OPENAI_DEFAULT = "gpt-6.1-sol"
REASONING_ROOM = 4096  # output tokens a reasoning model may think with, besides the step itself (paid only if used)
PROVIDERS = {"anthropic": {"name": "Anthropic", "default": DEFAULT_MODEL},
             "openai": {"name": "OpenAI", "default": OPENAI_DEFAULT}}


def provider_of(model: str) -> str:
    return "openai" if model.startswith(("gpt-", "o1", "o3", "o4", "chatgpt-")) else "anthropic"


def offered_openai(models: list) -> list:
    """OpenAI's models worth offering: the current ones we've read the price of, in our order."""
    have = set(models)
    return [m for m in OPENAI_OFFER if m in have] or [m for m in OPENAI_PRICES if m in have][:5]


# the context a cloud model works in: far past a local model's, so AICUI rarely trims its history — each trim changes
# the start of the prompt and its cache is written again (2026-10-26, test16: at 32K, Sonnet 5.5 rewrote ~28K tokens
# of cache on every step, 77 % of a $3.92 stretch). Below the models' own windows, so a long task is still summed up
# once in a while rather than read whole at every step (a cache read costs too).
CLOUD_CONTEXT = 120_000
# the models' own windows, where they're known (Anthropic's model table): AICUI works in the model's own context and
# doesn't trim it (Ian, 2026-10-27: "let the clouds tools be used over ours unless theres something that verifiably
# reduces token usage without affecting performance"); a model not listed keeps CLOUD_CONTEXT
# Haiku 5.5 works below its price step (STEPS): its history is summed up before a prompt reaches 100K tokens, where
# each call would cost five times as much (Ian's rule, 2026-10-27: a local step stays when it cuts tokens 60% or more)
WINDOWS = {"claude-haiku-5-5": 85_000, "claude-sonnet-5-5": 1_000_000, "claude-opus-5-5": 1_000_000,
           "claude-fable-5-1": 1_000_000}


def window(model: str) -> int:
    return WINDOWS.get(model, CLOUD_CONTEXT)


def backend(root: str, provider: str, model: str, context: int = 0):
    """The cloud backend for a provider, its key read from the keyring at each call (never kept)."""
    from cin_minai.daemon import accounts
    cls = OpenAI if provider == "openai" else Anthropic
    return cls(root, lambda: accounts.cloud_key(provider), model, context or window(model))


def blocks(content) -> list[dict]:
    """A message's content as Anthropic's blocks: text, pictures (our image_url data: addresses) as images, and a PDF
    (our file part) as a document, read whole, its pages' pictures too. No empty text: Anthropic refuses it
    (2026-10-12: a command that printed nothing ended Haiku's run)."""
    if isinstance(content, str):
        content = [{"type": "text", "text": content}]
    out = []
    for part in content or []:
        if part.get("type") == "image_url":
            head, _, data = ((part.get("image_url") or {}).get("url") or "").partition(",")
            mime = head[5:].split(";")[0] if head.startswith("data:") else "image/jpeg"
            out.append({"type": "image", "source": {"type": "base64", "media_type": mime, "data": data}})
        elif part.get("type") == "file":
            data = ((part.get("file") or {}).get("file_data") or "").partition(",")[2]
            out.append({"type": "document", "source": {"type": "base64", "media_type": "application/pdf",
                                                       "data": data}})
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


def listed(inputs: dict, tools: list, name: str | None) -> dict:
    """A list input sent as its JSON text, or as one item, made a list (2026-10-27, test27: Haiku 5.5 gave distill's
    sources as the text '["sources/Ru…"]', and the rulebook's path was read letter by letter)."""
    props = next((t["input_schema"].get("properties", {}) for t in tools if t["name"] == name), {})
    for k, v in list(inputs.items()):
        if isinstance(v, str) and (props.get(k) or {}).get("type") == "array":
            try:
                got = json.loads(v)
            except ValueError:
                got = None
            inputs[k] = got if isinstance(got, list) else [v] if v.strip() else []
    return inputs


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
    """claude-haiku-4-5-20251001 → Claude Haiku 4.5; gpt-6.1-sol → GPT-6.1 Sol"""
    if model.startswith("gpt-"):
        head, *rest = model[4:].split("-")
        return "GPT-" + head + "".join(" " + w.capitalize() for w in rest)
    parts = [x for x in model.split("-") if not (x.isdigit() and len(x) == 8)]
    words = [x.capitalize() for x in parts if not x.isdigit()]
    nums = [x for x in parts if x.isdigit()]
    return " ".join(words) + (" " + ".".join(nums) if nums else "")


def cost(model: str, usage: dict) -> float:
    """Dollars for one call's usage. OpenAI's usage counts cached tokens inside input_tokens; ours is logged the
    Anthropic way (input apart from cache reads), so both cost the same sum."""
    p_in, p_out, p_write, p_read = price_of(model)
    prompt = (usage.get("input_tokens", 0) + usage.get("cache_creation_input_tokens", 0)
              + usage.get("cache_read_input_tokens", 0))
    times = next((x for k, (line, x) in STEPS.items() if k in str(model) and prompt > line), 1.0)
    return times * (usage.get("input_tokens", 0) * p_in + usage.get("output_tokens", 0) * p_out
                    + usage.get("cache_creation_input_tokens", 0) * p_write
                    + usage.get("cache_read_input_tokens", 0) * p_read) / 1e6


class Anthropic:
    """A chat backend shaped like the local one: chat(messages, schema, max_tokens, cancel, on_text) -> (text, timings)."""

    def __init__(self, root: str, key: Callable[[], str], model: str = DEFAULT_MODEL, context: int = CLOUD_CONTEXT,
                 opener: Callable = urllib.request.urlopen) -> None:
        self.root, self.key, self.model, self.opener = root, key, model, opener
        self.cfg = {"context": context}
        self.profile = None

    def alive(self) -> bool:
        return True

    def unload(self) -> None:
        pass

    def _post(self, path: str, body: dict | None = None, betas: list | None = None) -> dict:
        key = self.key()
        if not key:
            from cin_minai.daemon import accounts
            if accounts.keyring_locked():  # the key may well be there: the login keyring is locked (automatic login)
                raise CloudError("the login keyring is locked, so the Anthropic key can't be read — unlock it from "
                                 "AICUI's Cloud models menu (or Passwords and Keys), then continue")
            raise CloudError("no Anthropic key on this computer — add one from AICUI's Cloud models menu")
        headers = {"x-api-key": key, "anthropic-version": VERSION, "content-type": "application/json",
                   "User-Agent": "Cin-MinAI"}
        if betas:
            headers["anthropic-beta"] = ",".join(betas)
        req = urllib.request.Request(f"{API}/{path}", data=json.dumps(body).encode() if body is not None else None,
                                     headers=headers, method="POST" if body is not None else "GET")
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
                pictures = [p for p in parts if p["type"] != "text"]
                # a look's picture goes inside its result, so the model takes it for what its call returned (2026-10-27,
                # test29: beside the result, Haiku looked four times — "the look tool keeps returning only a path" —
                # and stopped "rather than editing blind")
                parts = [{"type": "tool_result", "tool_use_id": turns[-1]["content"][-1]["id"],
                          "content": ([{"type": "text", "text": said or "(nothing)"}] + pictures) if pictures
                          else (said or "(nothing)")}]
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
        def body_for(forced: bool) -> dict:
            body = {"model": self.model, "messages": turns,
                    "max_tokens": int(max_tokens or 4096) + (THINKING_ROOM if thinks(self.model) else 0)}
            if falls_back(self.model):
                body["fallbacks"] = "default"
            said = system
            if not forced and schema is not None:  # a free choice: said in the system text instead
                said = [dict(b) for b in system] or [{"type": "text", "text": ""}]
                said[-1]["text"] = (said[-1]["text"] + "\n\n" + CHOOSE_ONE).strip()
            if said:
                body["system"] = said
            if tools:  # every action its own tool with flat inputs; the model calls exactly one (see flat_tools)
                body["tools"] = tools
                body["tool_choice"] = {"type": "any"} if forced else {"type": "auto"}
            elif schema is not None:  # a schema without actions (a distill's items): one tool, its input the reply
                body["tools"] = [{"name": "reply", "description": "Your reply.", "input_schema": schema}]
                body["tool_choice"] = {"type": "tool", "name": "reply"} if forced else {"type": "auto"}
            return body
        start = time.monotonic()
        forced = not free_choice(self.model)
        betas = [FALLBACK_BETA] if falls_back(self.model) else []
        try:
            got = self._post("messages", body_for(forced), betas)
        except CloudError as e:
            if not (forced and schema is not None and refused_choice(e)):
                raise
            remember_free_choice(self.model)  # once: from now on this model is asked with a free choice
            got = self._post("messages", body_for(False), betas)
        usage = got.get("usage", {})
        usd = cost(got.get("model") or self.model, usage)  # a fallback is billed as the model that answered
        self.log(usage, usd)
        if got.get("stop_reason") == "refusal":  # the safety filter declined, said with its category (2026-10-26:
            self.keep(got)                       # Sonnet 5.5 refused twice on test16 and the reason wasn't kept)
            why = (got.get("stop_details") or {}).get("category") or "no category given"
            raise CloudError(f"{label(self.model)} declined this step (Anthropic's safety filter: {why}). Go on with "
                             "another model, or reword the request")
        if schema is not None:
            block = next((b for b in got.get("content", []) if b.get("type") == "tool_use"), None)
            if block is None:  # no tool called: a step written as text is still a step; the reply is kept to study
                text = "".join(b.get("text", "") for b in got.get("content", []) if b.get("type") == "text").strip()
                self.keep(got)
                if text and tools and got.get("stop_reason") == "end_turn" and not is_step(text) and                         any(t["name"] == "answer" for t in tools):
                    # with a free choice, a reply in plain text that ends the turn is the model's answer (2026-10-26:
                    # Sonnet 5.5 reported the finished board in text, and AICUI took it for an unusable step)
                    text = json.dumps({"thinking": "", "action": {"tool": "answer", "text": text}},
                                      ensure_ascii=False)
            elif tools:  # the agent's step: {"thinking", "action": {"tool": the tool called, its inputs}}
                need = next((t["input_schema"]["required"] for t in tools if t["name"] == block.get("name")), [])
                inputs = listed(unleak(dict(block.get("input") or {}), need), tools, block.get("name"))
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
                json.dump({k: got.get(k) for k in ("stop_reason", "stop_details", "model", "content", "usage")}, f,
                          ensure_ascii=False, indent=1)
        except OSError:
            pass

    def log(self, usage: dict, usd: float) -> None:
        path = os.path.join(self.root, USAGE)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"time": time.strftime("%Y-%m-%dT%H:%M:%S"), "model": self.model, **{
                k: usage.get(k, 0) for k in ("input_tokens", "output_tokens", "cache_creation_input_tokens",
                                             "cache_read_input_tokens")}, "usd": round(usd, 6)}) + "\n")


class OpenAI(Anthropic):
    """OpenAI by API key, through the Responses API (D35; the GPT-6 models take tools only there): the same chat()
    as Anthropic's — budget first, every call logged with its cost, the agent's step as one forced tool call among
    flat tools — in OpenAI's shapes. OpenAI caches repeated prompt beginnings by itself; cached input is cheaper."""

    def __init__(self, root: str, key: Callable[[], str], model: str = OPENAI_DEFAULT, context: int = CLOUD_CONTEXT,
                 opener: Callable = urllib.request.urlopen) -> None:
        super().__init__(root, key, model, context, opener)

    def _post(self, path: str, body: dict | None = None) -> dict:
        key = self.key()
        if not key:
            from cin_minai.daemon import accounts
            if accounts.keyring_locked():
                raise CloudError("the login keyring is locked, so the OpenAI key can't be read — unlock it from "
                                 "AICUI's Cloud models menu (or Passwords and Keys), then continue")
            raise CloudError("no OpenAI key on this computer — add one from AICUI's Cloud models menu")
        req = urllib.request.Request(f"{OPENAI_API}/{path}", data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Authorization": f"Bearer {key}", "content-type": "application/json",
                                              "User-Agent": "Cin-MinAI"},
                                     method="POST" if body is not None else "GET")
        try:
            with self.opener(req, timeout=300) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            try:
                said = json.loads(e.read() or b"{}").get("error", {}).get("message", "")
            except (ValueError, AttributeError):
                said = ""
            raise CloudError(f"OpenAI said {e.code}" + (f": {said[:200]}" if said else "")) from None
        except OSError as e:
            raise CloudError(f"OpenAI didn't answer: {getattr(e, 'reason', e)}") from None

    def models(self) -> list[str]:
        return [m["id"] for m in self._post("models").get("data", [])]

    @staticmethod
    def shape_input(messages: list[dict], names: set | frozenset = frozenset()) -> tuple[str, list[dict]]:
        """Our messages as the Responses API's: the system text as instructions; each earlier step (our JSON) as the
        function call it was, and the result after it as its function_call_output; pictures as input images, a PDF
        as an input file."""
        instructions = "\n\n".join(m["content"] for m in messages if m["role"] == "system" and
                                   isinstance(m["content"], str))
        items: list[dict] = []
        calls, open_call = 0, None
        for m in messages:
            if m["role"] == "system":
                continue
            content = m["content"]
            if m["role"] == "assistant":
                call = as_call(content, names)
                if open_call:  # two steps in a row: the first had no result to show
                    items.append({"type": "function_call_output", "call_id": open_call, "output": "(nothing)"})
                    open_call = None
                if call:
                    calls += 1
                    open_call = f"call_step{calls}"
                    items.append({"type": "function_call", "call_id": open_call, "name": call["name"],
                                  "arguments": json.dumps(call["input"], ensure_ascii=False)})
                    continue
                text = content if isinstance(content, str) else " ".join(
                    p.get("text", "") for p in content or [] if p.get("type") == "text")
                items.append({"role": "assistant", "content": [{"type": "output_text",
                                                                "text": text.strip() or "(nothing)"}]})
                continue
            parts = [{"type": "text", "text": content}] if isinstance(content, str) else list(content or [])
            texts = "\n\n".join(str(p.get("text") or "") for p in parts if p.get("type") == "text").strip()
            pictures = [{"type": "input_image", "image_url": (p.get("image_url") or {}).get("url", "")}
                        for p in parts if p.get("type") == "image_url"] +                 [{"type": "input_file", "filename": (p.get("file") or {}).get("filename", "document.pdf"),
                  "file_data": (p.get("file") or {}).get("file_data", "")} for p in parts if p.get("type") == "file"]
            if open_call:  # the answer to that call
                said = texts[len("Result: "):] if texts.startswith("Result: ") else texts
                items.append({"type": "function_call_output", "call_id": open_call, "output": said or "(nothing)"})
                open_call = None
                if pictures:  # the Responses API's call output is text: the picture follows, said to be its own
                    items.append({"role": "user", "content": [{"type": "input_text", "text": "The picture your last "
                                  "step's look took (what that call returned):"}] + pictures})
                continue
            body = ([{"type": "input_text", "text": texts}] if texts else []) + pictures
            items.append({"role": "user", "content": body or [{"type": "input_text", "text": "(nothing)"}]})
        if open_call:  # a call with no answer yet can't be sent alone
            items.append({"type": "function_call_output", "call_id": open_call, "output": "(nothing)"})
        return instructions, items

    def chat(self, messages: list[dict], schema: dict | None = None, max_tokens: int = 0, cancel=None, on_text=None,
             **_kw) -> tuple[str, dict]:
        s = settings(self.root)
        already = spent(self.root)
        if already >= s["budget_usd"]:
            raise CloudError(f"the cloud budget for this project is used up (${already:.2f} of ${s['budget_usd']:.2f}"
                             "); raise it in AICUI's Cloud models menu to go on")
        tools = flat_tools(schema) if schema is not None else None
        instructions, items = self.shape_input(messages, {t["name"] for t in tools or []})
        body = {"model": self.model, "input": items, "max_output_tokens": int(max_tokens or 4096), "store": False}
        if instructions:
            body["instructions"] = instructions
        if self.model.startswith(("gpt-5", "gpt-6", "o")):  # reasoning models: a little thinking, to spend less —
            body["reasoning"] = {"effort": "low"}  # and room for it on top of the answer's: OpenAI counts the hidden
            body["max_output_tokens"] += REASONING_ROOM  # reasoning against the limit (2026-10-16: GPT-5.6 Luna spent
            #   all 745 tokens of a step's limit reasoning, four times, and the step came back empty)
        if tools:
            body["tools"] = [{"type": "function", "name": t["name"], "description": t["description"],
                              "parameters": t["input_schema"], "strict": False} for t in tools]
            body["tool_choice"] = "required"
        elif schema is not None:
            body["tools"] = [{"type": "function", "name": "reply", "description": "Your reply.", "parameters": schema,
                              "strict": False}]
            body["tool_choice"] = {"type": "function", "name": "reply"}

        def free(b: dict) -> dict:  # the same request with a free choice, said in the instructions
            b = dict(b, tool_choice="auto")
            b["instructions"] = (b.get("instructions", "") + "\n\n" + CHOOSE_ONE).strip()
            return b
        start = time.monotonic()
        forced = schema is not None and not free_choice(self.model)
        try:
            got = self._post("responses", body if forced or schema is None else free(body))
        except CloudError as e:
            if not (forced and refused_choice(e)):
                raise
            remember_free_choice(self.model)
            got = self._post("responses", free(body))
        u = got.get("usage") or {}
        cached = int((u.get("input_tokens_details") or {}).get("cached_tokens") or 0)
        usage = {"input_tokens": max(0, int(u.get("input_tokens") or 0) - cached),
                 "output_tokens": int(u.get("output_tokens") or 0), "cache_creation_input_tokens": 0,
                 "cache_read_input_tokens": cached}
        usd = cost(self.model, usage)
        self.log(usage, usd)
        out = got.get("output") or []
        call = next((o for o in out if o.get("type") == "function_call"), None)
        said = "".join(c.get("text", "") for o in out if o.get("type") == "message"
                       for c in o.get("content") or [] if c.get("type") == "output_text")
        if schema is not None:
            if call is None:
                text = said.strip()
                self.keep({"stop_reason": got.get("status"), "content": out, "usage": u})
            else:
                try:
                    inputs = json.loads(call.get("arguments") or "{}")
                except ValueError:
                    inputs = {}
                if tools:
                    need = next((t["input_schema"]["required"] for t in tools if t["name"] == call.get("name")), [])
                    inputs = listed(unleak(dict(inputs), need), tools, call.get("name"))
                    thinking = str(inputs.pop(WHY, "") or inputs.pop("thinking", ""))
                    text = json.dumps({"thinking": thinking, "action": {"tool": call.get("name", ""), **inputs}},
                                      ensure_ascii=False)
                else:
                    text = json.dumps(inputs, ensure_ascii=False)
        else:
            text = said
        if on_text:
            on_text(text)
        seconds = time.monotonic() - start
        out_n = usage["output_tokens"]
        capped = got.get("status") == "incomplete" and (got.get("incomplete_details") or {}).get("reason") == \
            "max_output_tokens"
        return text, {"prompt_n": usage["input_tokens"], "cache_n": cached, "gen_n": out_n, "predicted_n": out_n,
                      "seconds": round(seconds, 1), "gen_tps": round(out_n / seconds, 1) if seconds else 0,
                      "usd": round(usd, 5), "capped": capped}
