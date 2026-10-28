# SPDX-License-Identifier: GPL-3.0-or-later
"""The assistant on a cloud model (PLAN D35, Ian, 2026-10-23: "I'd also like a way for people to use cloud services to
run their whole computer like this if they want instead of local stuff"; "People will have to API until they say
otherwise but the option should be there").

The sidebar's guide asks its model for one call, {"tool": ..., "args": {...}}, then for a reply in plain text. Here the
same two calls go to the person's own cloud model (inference/cloud.py: Anthropic or OpenAI, the key read from the
login keyring at each call): the guide's tools become the cloud's tools, the call comes back in the guide's own shape,
and everything after it — the tools themselves, Allow cards, the admin password, the reply guard — is the guide's,
unchanged, since those live in the system, not the model.

* **The choice** is the person's, kept in ~/.local/share/cinminai/assistant/.cinminai/cloud.json with its budget; the
  calls and their cost are logged beside it (cloud-usage.jsonl), as a project's are.
* **Any model the person has a key for** is offered, the ones AICUI's Cloud models menu lists. Not measured first:
  Ian, 2026-10-28: "Dont worry about evals on cloud models, theres not much I can do about them and I wont make them
  better in any way. We can give them our guide cards but thats about it" (they get the guide's prompt and its help
  cards, as the guide does).
* **Said plainly** when chosen: what the person asks, and what's read to answer it, goes to the provider.
"""

from __future__ import annotations

import json
import os
import threading
from typing import Callable

from . import cloud
from .backend import BackendError, Cancelled, InferenceBackend, Status


def root() -> str:
    base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return os.path.join(base, "cinminai", "assistant")


BUDGET_USD = 2.0  # the first budget, raised by the person in the Models view


def choice(where: str | None = None) -> dict | None:
    """The person's cloud model for the assistant, or None (the guide on this computer)."""
    where = where or root()
    try:
        with open(os.path.join(where, cloud.SETTINGS), encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, ValueError):
        return None
    if raw.get("role") != "assistant" or not raw.get("model"):
        return None
    s = cloud.settings(where)
    return {"provider": s["provider"], "model": s["model"], "label": cloud.label(s["model"]),
            "budget_usd": s["budget_usd"], "spent_usd": round(cloud.spent(where), 4)}


def choose(model: str, budget_usd: float | None = None, where: str | None = None) -> dict:
    """Run the assistant on this cloud model ("" = back to the guide on this computer)."""
    where = where or root()
    now = choice(where)
    budget = budget_usd if budget_usd is not None else (now or {}).get("budget_usd") or BUDGET_USD
    # written here, not with cloud.save_settings: that one also makes it AICUI's last model
    path = os.path.join(where, cloud.SETTINGS)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        json.dump({"model": model, "role": "assistant" if model else "off", "budget_usd": float(budget)}, f, indent=1)
    os.replace(path + ".tmp", path)
    return choice(where) or {"model": ""}


def offers(keyed: dict) -> list[dict]:
    """The models offered for the assistant: for each provider with a key here, the ones AICUI's menu lists."""
    return [{"model": m, "label": cloud.label(m), "provider": p}
            for p in ("anthropic", "openai") if keyed.get(p)
            for m in (cloud.cached_models(p) or [cloud.PROVIDERS[p]["default"]])]


def to_steps(schema: dict) -> dict:
    """The guide's call schema ({"anyOf": [{"tool": const, "args": {...}}]}) as the agent's step schema the cloud
    backend turns into one tool per action (cloud.flat_tools): each tool's args flat beside `tool`."""
    variants = []
    for v in (schema or {}).get("anyOf") or []:
        props = v.get("properties") or {}
        name = (props.get("tool") or {}).get("const")
        if not name:
            continue
        args = props.get("args") or {}
        variants.append({"type": "object", "properties": {"tool": {"const": name}, **(args.get("properties") or {})},
                         "required": ["tool", *(args.get("required") or [])]})
    return {"type": "object", "properties": {"thinking": {"type": "string"}, "action": {"anyOf": variants}},
            "required": ["thinking", "action"]}


def from_step(text: str) -> str:
    """The cloud's step ({"thinking", "action": {"tool", ...}}) as the guide's call {"tool", "args"}."""
    try:
        step = json.loads(text)
    except ValueError:
        return text
    act = step.get("action") if isinstance(step, dict) else None
    if not isinstance(act, dict) or "tool" not in act:
        return text
    return json.dumps({"tool": act["tool"], "args": {k: v for k, v in act.items() if k != "tool"}},
                      ensure_ascii=False)


class CloudGuide(InferenceBackend):
    """The guide's backend on a cloud model: nothing to load, the same chat() the guide calls."""

    def __init__(self, provider: str, model: str, where: str | None = None, inner=None) -> None:
        self.where = where or root()
        self.model = model
        self.inner = inner or cloud.backend(self.where, provider, model)
        self.cfg = {"context": cloud.window(model)}

    def status(self) -> Status:
        return Status(state="ready", model=cloud.label(self.model), build="cloud", context=self.cfg["context"])

    def load(self) -> None:
        pass

    def unload(self) -> None:
        pass

    def chat(self, messages: list[dict], *, schema: dict | None = None, max_tokens: int = 600,
             on_text: Callable[[str], None] | None = None, cancel: threading.Event | None = None,
             sampling: dict | None = None) -> tuple[str, dict]:
        if cancel is not None and cancel.is_set():
            raise Cancelled("stopped")
        try:
            if schema is None:
                text, timings = self.inner.chat(messages, max_tokens=max_tokens, on_text=on_text)
            else:
                raw, timings = self.inner.chat(messages, schema=to_steps(schema), max_tokens=max_tokens)
                text = from_step(raw)
                if on_text:
                    on_text(text)
        except cloud.CloudError as e:
            raise BackendError(str(e)) from None
        if cancel is not None and cancel.is_set():
            raise Cancelled("stopped")
        return text, timings
