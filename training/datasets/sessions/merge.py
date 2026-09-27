#!/usr/bin/env python3
"""Merge raw session runs into the published session corpus (guide fine-tune, cycle 0).

Every session is split into its turns (the planned types in meta.turns) and each turn is checked
again with the current checks, whatever run produced it:
  - the generator's own per-type checks (grounding, one step per walkthrough reply, offers in vague
    turns, facts from the result in reports, …), re-run with the current scorer;
  - a decline must actually refuse — seen: "Yes, 'The Crown' is based on real people…", voting and
    stock advice passed off as declines;
  - a non-English walkthrough or report must not ask its closing question in English — seen:
    "…クリックしてください。What do you see now?" (the English example in the old WALK_GUIDE);
  - no user message too close to any eval task (public, held-out, vague set);
  - a walkthrough step that repeats the previous one ends the walkthrough;
  - near-duplicate sessions (same opening message, same language) are dropped.
A session is cut before its first bad turn (a walkthrough before its first bad follow-up) and kept
if at least 2 good turns remain.

    python3 merge.py --out . [--english-question repair|reject] RAW [RAW ...]      # RAW: a run directory (sessions.jsonl) or a .jsonl file

Writes OUT/corpus.jsonl and OUT/merge-stats.json.
"""

from __future__ import annotations

import argparse
import collections
import importlib.util
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("sessions_generate", os.path.join(HERE, "generate.py"))
G = importlib.util.module_from_spec(_spec)
sys.modules["sessions_generate"] = G
_saved, sys.argv = sys.argv, [sys.argv[0]]
_spec.loader.exec_module(G)
sys.argv = _saved
T, R, I = G.T, G.R, G.I

# A decline names what it can't do. Hedges ("私の助けにならないかもしれません", "I mainly answer…") and
# "Lamento que no pueda ayudar" (says the *user* can't help) don't count.
REFUSAL = {
    "en": r"\b(can't|cannot|can not|unable to|not able to|outside (?:of )?what I)\b",
    "es": r"\bno puedo\b|\bno me es posible\b|fuera de (?:lo que|mi)|no está relacionad",
    "pt": r"\bnão posso\b|\bnão consigo\b|fora do (?:que|meu|escopo)",
    "fr": r"\bje ne (?:peux|suis pas en mesure)\b|\bne peux pas\b|en dehors de ce que",
    "de": r"\bkann (?:ich )?(?:\w+ ){0,3}(?:nicht|keine?n?)\b|\baußerhalb\b|"
          r"\bnicht (?:\w+ ){0,2}(?:beantworten|helfen|verwalten) kann\b|nicht etwas, wofür",
    "ja": r"できません|られません|範囲外|お答えしかねます|仕事ではありません|に関する質問ではありません",
}
# English closing questions inside non-English replies (the sentence as it appears, any line).
EN_QUESTION = re.compile(r"\b(what do you see|do you see|what would you like|would you like|let me know|"
                         r"what happens|is that (?:ok|right))\b", re.I)
# Ian, 2026-09-26: the exact closing "What do you see now?" came from our own prompt's example, not the
# teacher's judgement — repair that one phrase to the native question (counted in the stats); any
# other English question is still rejected.
EN_WALK_CLOSE = re.compile(r"\s*What do you see now\?\s*$")
NATIVE_WALK_CLOSE = {"es": " ¿Qué ve ahora?", "pt": " O que você vê agora?", "fr": " Que voyez-vous maintenant ?",
                     "de": " Was sehen Sie jetzt?", "ja": "今、何が見えますか？"}


def turns(s: dict) -> list[tuple[str, list[list[dict]]]]:
    """[(kind, [segment, ...])]: a segment is the messages of one exchange (user message + assistant
    side); a walkthrough has its first segment plus one per follow-up."""
    m, kinds, out, i = s["messages"], list(s["meta"]["turns"]), [], 1
    while i < len(m):
        u, a = m[i], m[i + 1]
        if u["role"] != "user" or a["role"] != "assistant":
            raise ValueError(f"unexpected roles at message {i}")
        if not a["content"].startswith("{"):  # plain text right after a user message: a walkthrough follow-up
            out[-1][1].append([u, a])
            i += 2
            continue
        n = 4 if json.loads(a["content"])["tool"] in ("lookup_help", "inspect_system") else 2
        out.append((kinds.pop(0), [m[i:i + n]]))
        i += n
    if kinds:
        raise ValueError("fewer turns than meta.turns")
    return out


def user_texts(msgs: list[dict]) -> list[str]:
    return [m["content"] for m in msgs if m["role"] == "user" and not m["content"].startswith("Result of ")]


def question_language(text: str, lang: str) -> list[str]:
    if lang != "en" and EN_QUESTION.search(text):
        return ["closing question in English"]
    return []


def card_topic(res: str, lang: str) -> str | None:
    for tid, t in G.KB.items():
        if T.resolve(t["card"], lang) in res:
            return tid
    return None


def check_segment(kind: str, lang: str, seg: list[dict], ctx: list[dict], first: bool) -> list[str]:
    """Failures of one exchange; ctx = the conversation before it (for grounding sources)."""
    said = user_texts(ctx + seg)
    reply = seg[-1]["content"]
    if kind == "walk" and not first:
        cards = [m["content"] for m in ctx if m["role"] == "user" and m["content"].startswith("Result of ")]
        fails = G.one_step(reply, lang)
        bad = G.invented_names(reply, lang, cards + said)
    elif kind in ("clear", "safety", "walk"):
        if json.loads(seg[1]["content"])["tool"] != "lookup_help":
            return ["wrong tool"]
        topic = card_topic(seg[2]["content"], lang)
        if topic is None:
            return ["help card not in the knowledge base"]
        card = T.resolve(G.KB[topic]["card"], lang)
        if kind == "walk":
            fails = G.one_step(reply, lang)
        else:
            must = [[T.label(k, lang) for k in (x if isinstance(x, list) else [x])] for x in G.KB[topic]["must"]]
            fails = R.stage_b({"lang": lang, "must": must, "must_not": T.NO_CMD + G.WRONG_ANY,
                               "steps": 2 if G.KB[topic]["steps"] else 0}, reply)
        bad = G.invented_names(reply, lang, [card] + said)
    elif kind in ("system", "report"):
        if json.loads(seg[1]["content"])["tool"] != "inspect_system":
            return ["wrong tool"]
        raw = seg[2]["content"].split("\n", 1)[1].split("\n\n")[0]
        result = json.loads(raw)
        fails = R.stage_b({"lang": lang, "must": [G.result_facts(result)],
                           "must_not": T.NO_CMD + G.WRONG_ANY + G.WRONG_SYSTEM}, reply)
        if kind == "report":
            if R.STEP.findall(reply):
                fails.append("report gives instructions")
            if not re.search(r"[?？]\s*$", reply.strip()):
                fails.append("doesn't end with a question")
        bad = G.invented_names(reply, lang, [raw] + said)
    else:
        call = json.loads(reply)
        want = "decline" if kind == "decline" else "answer"
        if call["tool"] != want:
            return ["wrong tool"]
        text = call["args"]["text"]
        bad = []
        if kind == "vague":
            fails = I.checks(lang, text)
            if G.offers(text, lang) < 2:
                fails.append("options are instructions, not offers")
            if any(re.search(w, text, re.I) for w in G.WRONG_ANY):
                fails.append("wrong fact or terminal")
        elif kind == "decline":
            fails = []
            if lang not in R.language_candidates(text) or T.mixed_language(text, lang):
                fails.append("language")
            if R.STEP.findall(text) or len(text.split()) > 70:
                fails.append("answers instead of declining")
            if not re.search(REFUSAL[lang], text, re.I):
                fails.append("decline doesn't refuse")
        else:  # chat
            fails = []
            if lang not in R.language_candidates(text) and R.language(text) != "?" or T.mixed_language(text, lang):
                fails.append("language")
            if R.STEP.findall(text) or len(text.split()) > 45:
                fails.append("too long for small talk")
        reply = text
    if bad:
        fails.append("invented names")
    if kind in ("clear", "safety", "system") and T.mixed_language(reply, lang):
        fails.append("a line in another language")
    if kind in ("walk", "report"):
        fails += question_language(reply, lang)
    return fails


def check_user(kind: str, lang: str, q: str, follow: bool, evalq: list[str]) -> list[str]:
    if not follow and kind != "chat" and not T.valid_question(q, lang):
        return ["invalid user message"]
    if max((T.similar(q, e) for e in evalq), default=0) >= 0.5:
        return ["user message too close to an eval task"]
    return []


def repair(kind: str, lang: str, seg: list[dict], why: collections.Counter) -> list[dict]:
    text = seg[-1]["content"]
    if kind == "walk" and lang != "en" and EN_WALK_CLOSE.search(text):
        why["repaired: English 'What do you see now?' -> native"] += 1
        text = EN_WALK_CLOSE.sub("", text).rstrip() + NATIVE_WALK_CLOSE[lang]
        return seg[:-1] + [dict(seg[-1], content=text.lstrip())]
    return seg


def merge_session(s: dict, evalq: list[str], why: collections.Counter, fix: bool = True) -> dict | None:
    lang = s["meta"]["lang"]
    msgs, kept = s["messages"][:1], []
    for kind, segs in turns(s):
        good = 0
        for j, seg in enumerate(segs):
            if fix:
                seg = repair(kind, lang, seg, why)
            fails = check_user(kind, lang, seg[0]["content"], j > 0, evalq) or \
                    check_segment(kind, lang, seg, msgs, j == 0)
            if not fails and kind == "walk" and j > 0 and T.similar(seg[-1]["content"], msgs[-1]["content"]) >= 0.5:
                fails = ["repeats the previous step"]  # seen: "Click the picture you want to use." three times
            if fails:
                why[f"{kind}{'' if j == 0 else ' follow-up'}: {fails[0]}"] += 1
                break
            msgs = msgs + seg
            good += 1
        if good == 0:
            break
        kept.append(kind)
        if good < len(segs):  # a walkthrough cut after a bad follow-up: the session ends there
            break
    if len(kept) < 2:
        return None
    meta = dict(s["meta"], turns=kept)
    if kept != s["meta"]["turns"]:
        meta["cut_from"] = len(s["meta"]["turns"])
    return {"messages": msgs, "meta": meta}


def sources(paths: list[str]):
    for p in paths:
        path = os.path.join(p, "sessions.jsonl") if os.path.isdir(p) else p
        for line in open(path, encoding="utf-8"):
            yield os.path.basename(os.path.normpath(p)), line


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--english-question", choices=["repair", "reject"], default="repair",
                    help="walkthrough replies ending in English 'What do you see now?': repair the phrase or reject")
    ap.add_argument("raw", nargs="+")
    o = ap.parse_args()
    evalq = T.eval_questions()
    spec = importlib.util.spec_from_file_location("v", os.path.join(T.ROOT, "training", "eval", "guide-interp", "tasks.py"))
    v = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(v)
    evalq += [q for task in v.TASKS for q in task["q"].values()]
    why, drop, n_in = collections.Counter(), collections.Counter(), 0
    kept, openers = [], collections.defaultdict(list)
    for src, line in sources(o.raw):
        n_in += 1
        try:
            s = json.loads(line)
        except json.JSONDecodeError:
            drop["unparseable line"] += 1
            continue
        try:
            m = merge_session(s, evalq, why, o.english_question == "repair")
        except (ValueError, KeyError, IndexError, json.JSONDecodeError) as e:
            drop[f"malformed session ({type(e).__name__})"] += 1
            continue
        if m is None:
            drop["fewer than 2 good turns"] += 1
            continue
        lang, first = m["meta"]["lang"], m["messages"][1]["content"]
        if any(T.similar(first, x) >= 0.8 for x in openers[lang]):
            drop["near-duplicate session"] += 1
            continue
        openers[lang].append(first)
        m["meta"]["source_run"] = src
        kept.append(m)
    os.makedirs(o.out, exist_ok=True)
    with open(os.path.join(o.out, "corpus.jsonl"), "w", encoding="utf-8") as f:
        for m in kept:
            f.write(json.dumps(m, ensure_ascii=False) + "\n")
    types = collections.Counter(k for m in kept for k in m["meta"]["turns"])
    total = sum(types.values())
    stats = {"kind": "sessions", "sources": sorted({m["meta"]["source_run"] for m in kept}), "sessions_in": n_in,
             "kept": len(kept), "cut": sum(1 for m in kept if "cut_from" in m["meta"]), "dropped": dict(drop),
             "first_bad_turn": {k: n for k, n in why.most_common() if not k.startswith("repaired")},
             "repaired": {k[10:]: n for k, n in why.items() if k.startswith("repaired")},
             "turn_types": {k: f"{n} ({n / total:.0%})" for k, n in types.most_common()},
             "assistant_messages": sum(1 for m in kept for x in m["messages"] if x["role"] == "assistant"),
             "by_language": dict(collections.Counter(m["meta"]["lang"] for m in kept))}
    json.dump(stats, open(os.path.join(o.out, "merge-stats.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print(json.dumps(stats, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
