#!/usr/bin/env python3
"""Session corpus (cycle 0, Ian's design 2026-09-26): one coherent conversation per example, every one
unique, mixing the kinds of input a real user sends — so the guide learns to *choose* (answer directly,
look up, check the machine, clarify with options, decline kindly, or just chat) instead of learning one
pattern per corpus. A light squeeze on judgement, not a push on one behaviour.

Why: the micro-sweep showed a LoRA generalises whatever attitude its data has — lookup-only data made
everything a lookup, answer-only data made the guide answer off-topic questions. So the data must carry
the full variance, in proportion.

How:
  - we plan each turn's TYPE (balanced mix, guaranteed), the teacher only writes the words;
  - the user's message is written in context (the session so far), one persona and thread per session,
    and sometimes the same need comes back clear in one turn and vague in another (contrast pairs);
  - each assistant turn uses the forced right action and must pass that type's checks; a turn that
    fails twice ends the session (kept if it has >= 3 good turns);
  - the stored system prompt is the plain runtime one (prompt v2); generation-only instructions are
    never stored.

    python3 generate.py --url http://127.0.0.1:18091 --model Qwen3-14B-Q4_K_M --out DIR --sessions 100
"""

from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import os
import random
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
DATASETS = os.path.join(HERE, "..")
sys.path.insert(0, os.path.join(DATASETS, "transition"))
_argv, sys.argv = sys.argv, [sys.argv[0]]
import generate as T  # noqa: E402  (transition generator: teacher, labels, cleaning, checks)
sys.argv = _argv
R = T.R
_spec = importlib.util.spec_from_file_location("interp_gen", os.path.join(DATASETS, "interpretation", "generate.py"))
I = importlib.util.module_from_spec(_spec)
sys.modules["interp_gen"] = I
_saved, sys.argv = sys.argv, [sys.argv[0]]
_spec.loader.exec_module(I)
sys.argv = _saved

KB = {t["id"]: t for t in T.KB.TOPICS}
SAFETY = ["scam_email", "scam_phone", "scam_popup", "privacy_assistant", "offline_mode", "updates_why"]
TRANSITION = [t for t in KB if t not in SAFETY]
MIXES = {
    "v1": {"clear": 0.33, "vague": 0.20, "decline": 0.15, "system": 0.15, "safety": 0.10, "chat": 0.07},
    # Ian, 2026-09-26: fewer full-solution turns (where the teacher invents), more "journalistic" ones —
    # report what's there, or walk through piece by piece, sometimes without a conclusion.
    "journal": {"clear": 0.15, "system": 0.05, "report": 0.18, "walk": 0.20, "vague": 0.15, "decline": 0.12,
                "safety": 0.08, "chat": 0.07},
    "jtest": {"walk": 0.4, "report": 0.4, "decline": 0.1, "chat": 0.1},  # smoke tests of the new turns
}
MIX = MIXES["v1"]

THREADS = [
    "just switched from Windows and is setting up the new computer", "wants to get family photos organised",
    "is getting ready for a trip", "manages a small club and its papers", "keeps the household budget",
    "wants to stay in touch with the grandchildren", "is worried about scams after a friend got tricked",
    "is learning the computer a little every day", "is cleaning up an old, slow machine",
    "writes letters and keeps records for a church group", "wants the screen easier on the eyes",
    "is getting the printer and scanner working", "likes music and old films", "is careful about privacy",
    "just got a used gaming laptop from a nephew",
]
PERSONA_SESSION = [
    "a retired teacher who types slowly with no capital letters", "a nervous first-time Linux user",
    "a very polite older man who thanks for everything", "a busy mother who writes short messages",
    "a retired mechanic who is practical and direct", "a grandmother who uses Windows words for everything",
    "a curious teenager helping a grandparent", "a small-business owner in a hurry",
    "someone who makes typos and doesn't care", "a careful person who distrusts anything online",
]
OFF_TOPIC = ["a history question", "a recipe", "last night's game", "who to vote for", "a medical symptom",
             "which stocks to buy", "a legal question about their landlord", "their grandchild's maths homework",
             "a poem for a birthday card", "tomorrow's weather", "a question about a TV show"]
SYSTEM = {  # topic -> (what they ask about, a result generator)
    "storage": "whether there's enough space", "updates": "whether updates are waiting",
    "network": "why the internet is slow or not working", "printers": "whether the printer is ready",
    "sound": "why there's no sound", "display": "a second screen or the display", "battery": "the battery",
    "drivers": "the graphics driver", "overview": "what kind of computer this is",
}
CHAT = ["thanks, that worked", "a quick compliment", "saying they'll try it later",
        "telling what happened after following the steps", "a friendly remark about their day"]


def system_result(topic: str, lang: str, rnd: random.Random) -> dict:
    lab = lambda k: T.label(k, lang)
    if topic == "storage":
        size = rnd.choice([128, 238, 256, 476, 512, 931])
        free = rnd.choice([3, 7, 12, 25, 60, 140, 300])
        free = min(free, size - 20)
        return {"disks": [{"name": "Main disk", "size_gb": size, "free_gb": free,
                           "used_pct": round(100 * (size - free) / size)}],
                "largest_folders": [{"path": "~/Videos", "gb": rnd.choice([12, 40, 96])},
                                    {"path": "~/Downloads", "gb": rnd.choice([5, 22, 41])}],
                "open_with": lab("files")}
    if topic == "updates":
        n = rnd.choice([0, 0, 3, 7, 14])
        return {"updates_available": n, "security_updates": min(n, rnd.choice([0, 1, 2, 4])),
                "last_checked": "today", "open_with": lab("update_manager")}
    if topic == "network":
        return rnd.choice([{"wifi": {"enabled": False}, "wired": "no cable", "internet": False,
                            "open_with": lab("network")},
                           {"wifi": {"enabled": True, "network": "HomeNet", "signal_pct": rnd.choice([12, 18, 25])},
                            "internet": True, "open_with": lab("network")},
                           {"wifi": {"enabled": True, "network": "HomeNet", "signal_pct": 78}, "internet": True}])
    if topic == "printers":
        return {"printers": [{"name": rnd.choice(["HP DeskJet 2700", "Canon PIXMA TS3350", "Brother HL-L2350DW"]),
                              "state": rnd.choice(["ready", "paused", "out of paper", "offline"]),
                              "jobs_waiting": rnd.choice([0, 1, 3])}],
                "open_with": lab("printers") or lab("system_settings")}
    if topic == "sound":
        return {"output": rnd.choice(["HDMI (Monitor)", "Speakers (Built-in Audio)", "Headphones"]),
                "muted": rnd.choice([True, False]), "volume_pct": rnd.choice([0, 30, 80]),
                "open_with": lab("sound")}
    if topic == "display":
        return {"monitors": [{"name": "Built-in display", "on": True, "resolution": "1920x1080"},
                             {"name": rnd.choice(["Dell P2422H", "Samsung S24", "LG 27UL500"]),
                              "on": rnd.choice([True, False]), "connected": True}],
                "open_with": lab("display")}
    if topic == "battery":
        return {"battery": {"charge_pct": rnd.choice([12, 45, 88]), "health_pct": rnd.choice([52, 71, 94]),
                            "state": rnd.choice(["charging", "discharging"])}, "open_with": lab("power")}
    if topic == "drivers":
        return {"gpu": rnd.choice(["NVIDIA GeForce GTX 1660 Ti", "NVIDIA GeForce GTX 1060 6GB", "AMD Radeon RX 580"]),
                "driver_in_use": rnd.choice(["nouveau (open source)", "nvidia-driver-580", "amdgpu (open source)"]),
                "recommended": rnd.choice(["nvidia-driver-580", "none needed"]), "open_with": lab("driver_manager")}
    return {"open_with": lab("system_info"), "os": "Cin-MinAI 1.0 (Linux Mint 22.3 base)",
            "cpu": rnd.choice(["Intel Core i5-8250U", "AMD Ryzen 5 3550H", "Intel Core i7-9750H"]),
            "ram_gb": rnd.choice([8, 16]), "gpu": rnd.choice(["NVIDIA GeForce GTX 1650", "Intel UHD Graphics 620"]),
            "disk_gb": rnd.choice([256, 512])}


def result_facts(res: dict) -> list[str]:
    """Values a grounded reply should mention (any one of them)."""
    out = []
    def walk(x):
        if isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
        elif isinstance(x, (int, float)) and not isinstance(x, bool):
            out.append(str(x))
        elif isinstance(x, str) and len(x) > 3:
            out.append(x.split(" (")[0])
    walk(res)
    return out


def plan(rnd: random.Random) -> list[str]:
    n = rnd.choice([4, 5, 5, 6])
    types = list(MIX)
    while True:
        seq = rnd.choices(types, weights=[MIX[t] for t in types], k=n)
        if seq[0] == "chat" or len(set(seq)) < 3:
            continue
        return seq


def history_text(msgs: list[dict], limit: int = 6) -> str:
    """The session so far, for the teacher (last few turns, tool noise removed)."""
    lines = []
    for m in msgs[1:]:
        c = m["content"]
        if m["role"] == "user" and c.startswith("Result of "):
            continue
        if m["role"] == "assistant" and c.startswith("{"):
            try:
                call = json.loads(c)
                c = call.get("args", {}).get("text") or f"[{call['tool']}]"
            except json.JSONDecodeError:
                pass
        lines.append(("User: " if m["role"] == "user" else "Assistant: ") + c.replace("\n", " ")[:220])
    return "\n".join(lines[-limit:]) or "(this is the first message)"


ASK = {
    "clear": "a clear, specific question about {what}",
    "vague": "a vague or underspecified message about {what}: it says the situation or goal, not the exact task",
    "decline": "a message asking about {what} — something that has nothing to do with the computer",
    "system": "a question about {what} on this computer",
    "safety": "a question about {what}",
    "chat": "a short message: {what}",
    "report": "a question about {what} on this computer",
    "follow": "a short reply after doing the step the assistant just gave ({what}): usually it worked and they "
              "say what they see now; sometimes they ask where exactly to click, using only what the step said",
}


def user_message(t, lang, persona, thread, kind, what, msgs, seed, evalq) -> str | None:
    prompt = (f"A person is talking to the help assistant built into their Linux Mint computer. They came from "
              f"Windows. Persona: {persona}; right now they {thread}.\n\nThe conversation so far:\n"
              f"{history_text(msgs)}\n\nWrite their NEXT message: {ASK[kind].format(what=what)}. It should fit "
              f"naturally after the conversation so far (a new need is fine). Use Windows words where they "
              f"would. They are talking to the computer's assistant, not to a family member — don't address it as grandma, "
              f"mum, etc. Only the words they type — no labels, no quotes, no description of them. Write it in "
              f"{T.LANG_NAMES[lang]}. {I.NATIVE[lang]}")
    schema = {"type": "object", "additionalProperties": False, "required": ["message"],
              "properties": {"message": {"type": "string", "minLength": 2, "maxLength": 300}}}
    for k in range(2):
        try:
            q = T.clean_question(json.loads(t.chat([{"role": "user", "content": prompt}], schema=schema,
                                                   temperature=0.8, max_tokens=250, seed=seed + k))["message"])
        except Exception:
            continue
        ok = T.valid_question(q, lang) if kind not in ("chat", "follow") else (len(q) >= 2 and not T.TRACES.search(q))
        if kind == "chat" and (re.search(r"[?？]", q) or len(q.split()) > 20):
            ok = False  # small talk, not a new question (seen: a security question answered as chat)
        earlier = [m["content"] for m in msgs[1:] if m["role"] == "user" and not m["content"].startswith("Result of ")]
        if ok and any(T.similar(q, e) >= 0.6 or contained(q, e) >= 0.7 for e in earlier):
            ok = False  # the teacher copied an earlier message: the planned answer wouldn't match it
        if ok and max((T.similar(q, e) for e in evalq), default=0) < 0.5:
            return q
    return None


# Generation-only guidance for replies after a tool result (never stored in the training data): the
# smoke test showed the teacher filling gaps from Windows habit ("Settings app > Devices > Printers &
# Scanners") and guessing where the Menu is.
GEN_GUIDE = ("\n\nWhen you reply after a tool result: use only the names, menus, and steps that appear in "
             "the result or the help card; never describe Windows menus as if they existed here. The Menu "
             "button is at the bottom-left of the screen. Say 'the main disk', not 'C drive'. If the result "
             "has no steps for what the person needs, say what it shows and offer to look up how. Use only "
             "what the card or result says — don't add steps, programs, or advice that aren't in it; if the "
             "card doesn't cover the question, say so and offer to look up more. Never suggest the terminal.")
# Facts every reply must get right (all languages): the panel and Menu are at the bottom, the project's name.
WRONG_ANY = [r"\bterminal\b|端末|comandos?\b", r"top[- ]left|arriba a la izquierda|superior izquierd|oben links|en haut à gauche|canto superior "
             r"esquerdo|左上", r"Cin-Min(?!AI)|CinMin(?!AI)"]
WRONG_SYSTEM = [r"Settings app|Printers (?:&|and) Scanners|Control Panel|\bC:? drive\b|Device Manager"]


REPORT_GUIDE = ("\n\nThis reply is a report: describe in plain words only what the result shows (the "
                "real names and numbers), without telling the person what to do, and end by asking what "
                "they would like to do next. No numbered list.")
WALK_GUIDE = ("\n\nThis reply walks the person through it piece by piece: give only the NEXT single step "
              "from the help card above (one action), then ask them to do it and tell you what they see. No "
              "numbered list, no other steps, nothing that isn't in the card. If they report a problem the card "
              "doesn't cover, say honestly that the help doesn't cover it and offer to check the computer or look "
              "up more — never invent buttons, menus, or options. Format: one sentence with the single step, then "
              "one short question such as 'What do you see now?' — the reply must end with that question.")


QUOTED = re.compile(r'"([^"\n]{2,40})"|“([^”\n]{2,40})”|„([^“”\n]{2,40})[“”]|«\s?([^»\n]{2,40}?)\s?»|「([^」\n]{1,40})」|『([^』\n]{1,40})』|\'([^\'\n]{2,40})\'')
ALL_LABELS: dict = {}


def labels_in(lang: str) -> str:
    if lang not in ALL_LABELS:
        ALL_LABELS[lang] = " | ".join(v for row in R.LABELS.values() for v in (row.get(lang), row.get("en")) if v)
    return ALL_LABELS[lang]


def invented_names(reply: str, lang: str, sources: list[str]) -> list[str]:
    """Quoted UI names in the reply that appear in none of the sources (card, result, Mint's labels, the
    user's messages): the way invented buttons and menus show up ("Add Device", "Restart Wi-Fi")."""
    pool = (" ".join(sources) + " " + labels_in(lang)).lower()
    bad = []
    for m in QUOTED.finditer(reply):
        name = next(g for g in m.groups() if g).strip(" .:,!?。、")
        if name and name.lower() not in pool and not re.fullmatch(r"[\d\s%.,]+", name):
            bad.append(name)
    return bad


def one_step(text: str, lang: str) -> list[str]:
    fails = []
    if lang not in R.language_candidates(text) or T.mixed_language(text, lang):
        fails.append("language")
    if len(R.STEP.findall(text)) > 1:
        fails.append("more than one step")
    if not re.search(r"[?？]\s*$", text.strip()):
        fails.append("doesn't end with a question")
    if len(text) > (260 if lang == "ja" else 90 * 6):
        fails.append("too long for one step")
    if any(re.search(w, text, re.I) for w in WRONG_ANY):
        fails.append("wrong fact or terminal")
    return fails


# A vague turn must be answered with offers ("I can ..."), not instructions — the smoke test showed
# mis-written "vague" messages getting ungrounded step lists that passed the format checks.
OFFER = {"en": r"\b(I can|I could|we can|let me)\b", "es": r"\b(puedo|podría|podemos)\b",
         "pt": r"\b(posso|poderia|podemos)\b", "fr": r"\b(je peux|je pourrais|on peut|nous pouvons)\b",
         "de": r"\b(ich kann|ich könnte|wir können)\b", "ja": r"(できます|しましょうか|ましょうか|お手伝い)"}


def offers(text: str, lang: str) -> int:
    return sum(1 for line in text.splitlines() if R.STEP.match(line) and re.search(OFFER[lang], line, re.I))


def contained(a: str, b: str) -> float:
    """Share of the shorter message's 3-grams that also appear in the longer one (a longer copy of an
    earlier message has low Jaccard similarity but high containment)."""
    ga, gb = (T.cjk_grams(a), T.cjk_grams(b)) if R.language(a) == "ja" else (T.grams(a), T.grams(b))
    if not ga or not gb:
        return 0.0
    small, big = (ga, gb) if len(ga) <= len(gb) else (gb, ga)
    return len(small & big) / len(small)


def forced(tool: str) -> dict:
    return {"anyOf": [s for s in R.schema(None)["anyOf"] if s["properties"]["tool"]["const"] == tool]}


def assistant_turns(t, lang, kind, topic, q, msgs, seed, rnd) -> list[dict] | None:
    """The assistant side of one turn (1 or 3 messages), or None if it fails its checks twice."""
    system = msgs[0]["content"]
    ctx = msgs + [{"role": "user", "content": q}]
    gen = [{"role": "system", "content": system + GEN_GUIDE}] + ctx[1:]  # teacher sees the guide; data doesn't
    for attempt in range(2):
        s = seed + 17 * attempt
        try:
            if kind in ("clear", "safety"):
                call = t.chat(ctx, schema=forced("lookup_help"), temperature=0.2, max_tokens=120, seed=s)
                card = T.resolve(KB[topic]["card"], lang)
                must = [[T.label(k, lang) for k in (m if isinstance(m, list) else [m])] for m in KB[topic]["must"]]
                res = {"role": "user", "content": f"Result of lookup_help:\n{card}\n\n{R.STYLE_V2}"}
                reply = t.chat(gen + [{"role": "assistant", "content": call}, res], temperature=0.2, max_tokens=600, seed=s)
                fails = R.stage_b({"lang": lang, "must": must, "must_not": T.NO_CMD + WRONG_ANY,
                                   "steps": 2 if KB[topic]["steps"] else 0}, reply)
                bad = invented_names(reply, lang, [card] + [m["content"] for m in ctx if m["role"] == "user" and not m["content"].startswith("Result of ")])
                if bad:
                    fails.append("invented names: " + ", ".join(bad[:3]))
                out = [{"role": "assistant", "content": call}, res, {"role": "assistant", "content": reply}]
            elif kind == "system":
                call = json.dumps({"tool": "inspect_system", "args": {"topic": topic}})
                result = system_result(topic, lang, rnd)
                res = {"role": "user", "content": f"Result of inspect_system:\n{json.dumps(result, ensure_ascii=False)}"
                                                  f"\n\n{R.STYLE_V2}"}
                reply = t.chat(gen + [{"role": "assistant", "content": call}, res], temperature=0.2, max_tokens=500, seed=s)
                fails = R.stage_b({"lang": lang, "must": [result_facts(result)],
                                   "must_not": T.NO_CMD + WRONG_ANY + WRONG_SYSTEM}, reply)
                bad = invented_names(reply, lang, [json.dumps(result, ensure_ascii=False)] + [m["content"] for m in ctx if m["role"] == "user" and not m["content"].startswith("Result of ")])
                if bad:
                    fails.append("invented names: " + ", ".join(bad[:3]))
                out = [{"role": "assistant", "content": call}, res, {"role": "assistant", "content": reply}]
            elif kind == "report":
                call = json.dumps({"tool": "inspect_system", "args": {"topic": topic}})
                result = system_result(topic, lang, rnd)
                res = {"role": "user", "content": f"Result of inspect_system:\n{json.dumps(result, ensure_ascii=False)}"
                                                  f"\n\n{R.STYLE_V2}"}
                rgen = [{"role": "system", "content": system + GEN_GUIDE + REPORT_GUIDE}] + ctx[1:]
                res_gen = {"role": "user", "content": res["content"] + REPORT_GUIDE}
                reply = t.chat(rgen + [{"role": "assistant", "content": call}, res_gen], temperature=0.2, max_tokens=300, seed=s)
                fails = R.stage_b({"lang": lang, "must": [result_facts(result)],
                                   "must_not": T.NO_CMD + WRONG_ANY + WRONG_SYSTEM}, reply)
                if R.STEP.findall(reply):
                    fails.append("report gives instructions")
                bad = invented_names(reply, lang, [json.dumps(result, ensure_ascii=False)] + [m["content"] for m in ctx if m["role"] == "user" and not m["content"].startswith("Result of ")])
                if bad:
                    fails.append("invented names: " + ", ".join(bad[:3]))
                if not re.search(r"[?？]\s*$", reply.strip()):
                    fails.append("doesn't end with a question")
                out = [{"role": "assistant", "content": call}, res, {"role": "assistant", "content": reply}]
            elif kind == "walk_first":
                call = t.chat(ctx, schema=forced("lookup_help"), temperature=0.2, max_tokens=120, seed=s)
                card = T.resolve(KB[topic]["card"], lang)
                res = {"role": "user", "content": f"Result of lookup_help:\n{card}\n\n{R.STYLE_V2}"}
                wgen = [{"role": "system", "content": system + GEN_GUIDE + WALK_GUIDE}] + ctx[1:]
                res_gen = {"role": "user", "content": res["content"] + WALK_GUIDE}
                reply = t.chat(wgen + [{"role": "assistant", "content": call}, res_gen], temperature=0.2, max_tokens=250, seed=s)
                fails = one_step(reply, lang)
                bad = invented_names(reply, lang, [card] + [m["content"] for m in ctx if m["role"] == "user" and not m["content"].startswith("Result of ")])
                if bad:
                    fails.append("invented names: " + ", ".join(bad[:3]))
                out = [{"role": "assistant", "content": call}, res, {"role": "assistant", "content": reply}]
            elif kind == "walk_next":
                wgen = [{"role": "system", "content": system + GEN_GUIDE + WALK_GUIDE}] + ctx[1:-1] + \
                       [{"role": "user", "content": ctx[-1]["content"] + "\n\n(" + WALK_GUIDE.strip() + ")"}]
                reply = t.chat(wgen, temperature=0.2, max_tokens=250, seed=s)
                fails = one_step(reply, lang)
                cards = [m["content"] for m in ctx if m["role"] == "user" and m["content"].startswith("Result of ")]
                bad = invented_names(reply, lang, cards + [m["content"] for m in ctx if m["role"] == "user" and not m["content"].startswith("Result of ")])
                if bad:
                    fails.append("invented names: " + ", ".join(bad[:3]))
                out = [{"role": "assistant", "content": reply}]
            elif kind == "vague":
                rules =I.REPLY_RULES.format(names=", ".join(filter(None, (T.label(k, lang) for k in
                                             ["files", "writer", "calc", "system_settings", "software_manager"]))),
                                             scope="", language=T.LANG_NAMES[lang], native=I.NATIVE[lang])
                raw = t.chat([{"role": "system", "content": system + "\n\n" + rules}] + ctx[1:],
                             schema=forced("answer"), temperature=0.4, max_tokens=500, seed=s)
                text = json.loads(raw)["args"]["text"]
                fails = I.checks(lang, text)
                if offers(text, lang) < 2:
                    fails.append("options are instructions, not offers")
                if any(re.search(w, text, re.I) for w in WRONG_ANY):
                    fails.append("wrong fact or terminal")
                out = [{"role": "assistant", "content": json.dumps({"tool": "answer", "args": {"text": text}},
                                                                   ensure_ascii=False)}]
            elif kind == "decline":
                raw = t.chat(ctx, schema=forced("decline"), temperature=0.3, max_tokens=200, seed=s)
                text = json.loads(raw)["args"]["text"]
                fails = []
                if lang not in R.language_candidates(text) or T.mixed_language(text, lang):
                    fails.append("language")
                if len(R.STEP.findall(text)) or len(text.split()) > 70:
                    fails.append("answers instead of declining")
                out = [{"role": "assistant", "content": raw}]
            else:  # chat
                raw = t.chat([{"role": "system", "content": system + "\n\nThis message is small talk: reply warmly "
                               "in one or two short sentences, in the user's language, and offer further help. "
                               "No lists."}] + ctx[1:], schema=forced("answer"), temperature=0.5, max_tokens=150, seed=s)
                text = json.loads(raw)["args"]["text"]
                fails = []
                if lang not in R.language_candidates(text) and R.language(text) != "?" or T.mixed_language(text, lang):
                    fails.append("language")
                if len(R.STEP.findall(text)) or len(text.split()) > 45:
                    fails.append("too long for small talk")
                out = [{"role": "assistant", "content": json.dumps({"tool": "answer", "args": {"text": text}},
                                                                   ensure_ascii=False)}]
            if kind in ("clear", "safety", "system") and T.mixed_language(out[-1]["content"], lang):
                fails.append("a line in another language")
            if not fails:
                return out
            WHY.append(f"{kind}/{lang}: {'; '.join(fails)}")
        except Exception as e:
            WHY.append(f"{kind}/{lang}: error {type(e).__name__}: {str(e)[:120]}")
    return None


WHY: list[str] = []  # why assistant turns failed (last attempts), written to stats for the datasheet


def session(t, sid, lang, rnd, evalq, stats) -> dict | None:
    persona, thread = rnd.choice(PERSONA_SESSION), rnd.choice(THREADS)
    kinds = plan(rnd)
    # a contrast pair: the same knowledge-base need, once clear and once vague (when both kinds occur)
    shared = rnd.choice(TRANSITION)
    msgs = [{"role": "system", "content": R.system_prompt({"doc": None})}]
    done = []
    for i, kind in enumerate(kinds):
        seed = rnd.randrange(1 << 30)
        if kind == "walk":
            steps = [x for x in TRANSITION if KB[x]["steps"] and lang in KB[x].get("langs", T.KB.ALL)]
            topic = rnd.choice(steps)
            q = user_message(t, lang, persona, thread, "clear", KB[topic]["windows"], msgs, seed, evalq)
            first = assistant_turns(t, lang, "walk_first", topic, q, msgs, seed, rnd) if q else None
            if first is None:
                stats["turn_fail_assistant"]["walk"] = stats["turn_fail_assistant"].get("walk", 0) + 1
                break
            msgs += [{"role": "user", "content": q}] + first
            for j in range(rnd.choice([1, 2, 3])):  # sometimes stops before the end — no conclusion needed
                f = user_message(t, lang, persona, thread, "follow", KB[topic]["windows"], msgs, seed + 100 + j, evalq)
                nxt = assistant_turns(t, lang, "walk_next", topic, f, msgs, seed + 200 + j, rnd) if f else None
                if nxt is None:
                    break
                msgs += [{"role": "user", "content": f}] + nxt
            done.append("walk")
            continue
        if kind == "report":
            topic = rnd.choice(list(SYSTEM))
            what = SYSTEM[topic]
        elif kind == "clear":
            topic = shared if ("vague" in kinds and rnd.random() < 0.5) else rnd.choice(TRANSITION)
            what = KB[topic]["windows"]
        elif kind == "vague":
            topic, what = None, (KB[shared]["windows"] if "clear" in kinds and rnd.random() < 0.5
                                 else rnd.choice(I.THEMES)[0])
        elif kind == "safety":
            topic = rnd.choice(SAFETY)
            what = KB[topic]["windows"]
        elif kind == "system":
            topic = rnd.choice(list(SYSTEM))
            what = SYSTEM[topic]
        elif kind == "decline":
            topic, what = None, rnd.choice(OFF_TOPIC)
        else:
            topic, what = None, rnd.choice(CHAT)
        if kind in ("clear", "safety") and lang not in KB[topic].get("langs", T.KB.ALL):
            topic = rnd.choice([x for x in (TRANSITION if kind == "clear" else SAFETY)
                                if lang in KB[x].get("langs", T.KB.ALL)])
            what = KB[topic]["windows"]
        q = user_message(t, lang, persona, thread, kind, what, msgs, seed, evalq)
        if q is None:
            stats["turn_fail_user"] += 1
            break
        reply = assistant_turns(t, lang, kind, topic, q, msgs, seed, rnd)
        if reply is None:
            stats["turn_fail_assistant"][kind] = stats["turn_fail_assistant"].get(kind, 0) + 1
            # one fallback with a sturdier turn type instead of throwing the session away
            fb = rnd.choice([k for k in ("report", "decline") if k != kind])
            topic = rnd.choice(list(SYSTEM)) if fb == "report" else None
            what = SYSTEM[topic] if fb == "report" else rnd.choice(OFF_TOPIC)
            q = user_message(t, lang, persona, thread, fb, what, msgs, seed + 7, evalq)
            reply = assistant_turns(t, lang, fb, topic, q, msgs, seed + 7, rnd) if q else None
            if reply is None:
                break
            stats["fallback_turns"] = stats.get("fallback_turns", 0) + 1
            kind = fb
        msgs += [{"role": "user", "content": q}] + reply
        done.append(kind)
    if len(done) < 3:
        return None
    return {"messages": msgs, "meta": {"kind": "session", "id": sid, "lang": lang, "persona": persona,
                                       "thread": thread, "turns": done}}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True), ap.add_argument("--model", required=True)
    ap.add_argument("--out", required=True), ap.add_argument("--sessions", type=int, default=100)
    ap.add_argument("--seed", type=int, default=81)
    ap.add_argument("--mix", choices=list(MIXES), default="v1")
    o = ap.parse_args()
    global MIX
    MIX = MIXES[o.mix]
    rnd = random.Random(o.seed)
    t = T.Teacher(o.url, o.model)
    evalq = T.eval_questions()
    spec = importlib.util.spec_from_file_location("v", os.path.join(DATASETS, "..", "eval", "guide-interp", "tasks.py"))
    v = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(v)
    evalq += [q for task in v.TASKS for q in task["q"].values()]
    os.makedirs(o.out, exist_ok=True)
    stats = {"teacher": o.model, "started": dt.datetime.now().isoformat(timespec="seconds"), "mix_name": o.mix, "mix": MIX,
             "sessions_ok": 0, "sessions_dropped": 0, "turn_fail_user": 0, "turn_fail_assistant": {},
             "turn_types": {}, "by_lang": {}}
    langs = T.KB.ALL
    with open(os.path.join(o.out, "sessions.jsonl"), "a", encoding="utf-8") as f:
        for k in range(o.sessions):
            lang = langs[k % len(langs)]
            s = session(t, f"s{o.seed}-{k:04d}", lang, rnd, evalq, stats)
            if s:
                f.write(json.dumps(s, ensure_ascii=False) + "\n")
                f.flush()
                stats["sessions_ok"] += 1
                stats["by_lang"][lang] = stats["by_lang"].get(lang, 0) + 1
                for kd in s["meta"]["turns"]:
                    stats["turn_types"][kd] = stats["turn_types"].get(kd, 0) + 1
            else:
                stats["sessions_dropped"] += 1
            print(f"{time.strftime('%H:%M:%S')} session {k + 1}/{o.sessions} {lang}  ok {stats['sessions_ok']}  "
                  f"dropped {stats['sessions_dropped']}", flush=True)
    stats["finished"] = dt.datetime.now().isoformat(timespec="seconds")
    stats["turn_fail_reasons"] = WHY[-200:]
    json.dump(stats, open(os.path.join(o.out, "stats.json"), "w"), indent=1)
    print(json.dumps(stats, indent=1))


if __name__ == "__main__":
    main()
