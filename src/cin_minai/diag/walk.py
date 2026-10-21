# SPDX-License-Identifier: GPL-3.0-or-later
"""Walking a fault's diagnostic tree (SPEC §20, PLAN D51, D7): code walks it, the guide explains (Ian, 2026-10-21:
the 4B isn't a multi-step planner, D91 — the steps are a recipe, like an OBD-II tree).

A fault code comes with its fixes in order. The person gets the first one (Copy, what it does, how to undo it, what
"fixed" looks like); "Check again" runs the checks again and the rule decides, never a model: gone (verified, Rule 6),
still there (the next fix), or the tree's end — the fixes are used up, and the full report is what whoever helps next
needs (D7's "think it through" goes there). A fix that needs a restart is checked after it: the walk is kept in
~/.local/state/cinminai/diag-walk.json and looked at once when the assistant starts again.
"""

from __future__ import annotations

import json
import os
import time

RESTART_WORDS = ("restart", "reboot")
KEEP_DAYS = 14  # an open walk older than this is dropped: the person has moved on

WORDS = {
    "en": {"gone": "Fixed: {title}. The checks no longer find it.",
           "still": "Still there: {title}. Next, another fix:",
           "end": "Still there: {title}. That was the last fix the built-in checks know. The full report has "
                  "everything someone helping you would ask for: type cinminai-diag report in the Terminal.",
           "restart_gone": "Fixed after the restart: {title}.",
           "restart_still": "Still there after the restart: {title}. Open the assistant and click Check again on "
                            "it, or ask \"check my computer\"."},
    "es": {"gone": "Arreglado: {title}. Las comprobaciones ya no lo encuentran.",
           "still": "Sigue ahí: {title}. Ahora, otro arreglo:",
           "end": "Sigue ahí: {title}. Era el último arreglo que conocen las comprobaciones. El informe completo "
                  "tiene todo lo que preguntaría quien te ayude: escribe cinminai-diag report en la Terminal.",
           "restart_gone": "Arreglado tras reiniciar: {title}.",
           "restart_still": "Sigue ahí tras reiniciar: {title}. Abre el asistente y pulsa Comprobar de nuevo, o "
                            "pregunta \"revisa mi ordenador\"."},
    "pt": {"gone": "Resolvido: {title}. As verificações não o encontram mais.",
           "still": "Continua aí: {title}. Agora, outra correção:",
           "end": "Continua aí: {title}. Essa era a última correção que as verificações conhecem. O relatório "
                  "completo tem tudo o que quem for ajudar perguntaria: digite cinminai-diag report no Terminal.",
           "restart_gone": "Resolvido depois de reiniciar: {title}.",
           "restart_still": "Continua aí depois de reiniciar: {title}. Abra o assistente e clique em Verificar de "
                            "novo, ou pergunte \"verifique meu computador\"."},
    "fr": {"gone": "Réglé : {title}. Les vérifications ne le trouvent plus.",
           "still": "Toujours là : {title}. Ensuite, une autre solution :",
           "end": "Toujours là : {title}. C'était la dernière solution que connaissent les vérifications. Le "
                  "rapport complet contient tout ce que demanderait la personne qui vous aide : tapez cinminai-diag "
                  "report dans le Terminal.",
           "restart_gone": "Réglé après le redémarrage : {title}.",
           "restart_still": "Toujours là après le redémarrage : {title}. Ouvrez l'assistant et cliquez sur Vérifier "
                            "à nouveau, ou demandez « vérifie mon ordinateur »."},
    "de": {"gone": "Behoben: {title}. Die Prüfungen finden es nicht mehr.",
           "still": "Noch da: {title}. Als Nächstes eine andere Lösung:",
           "end": "Noch da: {title}. Das war die letzte Lösung, die die Prüfungen kennen. Der vollständige "
                  "Bericht enthält alles, wonach jemand fragen würde, der Ihnen hilft: Geben Sie cinminai-diag "
                  "report im Terminal ein.",
           "restart_gone": "Nach dem Neustart behoben: {title}.",
           "restart_still": "Nach dem Neustart noch da: {title}. Öffnen Sie den Assistenten und klicken Sie auf "
                            "Erneut prüfen, oder fragen Sie „prüfe meinen Computer“."},
    "ja": {"gone": "直りました：{title}。チェックではもう見つかりません。",
           "still": "まだ残っています：{title}。次の直し方です：",
           "end": "まだ残っています：{title}。組み込みのチェックが知っている直し方はこれで最後です。手伝ってくれる"
                  "人が知りたいことは、すべて詳しいレポートにあります：端末で cinminai-diag report と入力してください。",
           "restart_gone": "再起動で直りました：{title}。",
           "restart_still": "再起動後もまだ残っています：{title}。アシスタントを開いて「もう一度チェック」を押すか、"
                            "「パソコンをチェックして」と聞いてください。"},
}


def words(key: str, lang: str, **kw) -> str:
    return WORDS.get(lang, WORDS["en"])[key].format(**kw)


def needs_restart(fix: dict) -> bool:
    text = " ".join([fix.get("verify", ""), fix.get("words", "")] + list(fix.get("steps", []))).lower()
    return any(w in text for w in RESTART_WORDS)


def step(finding: dict, n: int) -> dict | None:
    """Fix n (0-based) of a finding (report.explain's shape), as the card shows it; None past the last fix."""
    fixes = finding.get("fixes", [])
    if n >= len(fixes):
        return None
    fx = fixes[n]
    item = {"code": finding["code"], "title": finding["title"], "now": finding["status"] == "active",
            "problem": finding["meaning"], "cause": finding["cause_words"], "fix": fx.get("words", ""),
            "fix_n": n, "fixes": len(fixes), "verify": fx.get("verify", ""), "restart": needs_restart(fx)}
    if fx.get("steps"):
        item["steps"] = fx["steps"]
    if fx.get("command"):
        item["command"] = fx["command"]
        item["command_explained"] = fx.get("explain", "")
        item["undo"] = fx.get("undo", "")
    return item


def check(rep: dict, code: str, n: int, title: str = "") -> dict:
    """After fix n: the checks ran again (rep is the fresh report). The rule decides — gone, still (the next fix), or
    the end of the tree."""
    found = [f for f in rep["findings"] if f["code"] == code and f["status"] == "active"]
    if not found:
        return {"outcome": "gone", "code": code, "title": title or code}
    f = found[0]
    nxt = step(f, n + 1)
    if nxt is None:
        return {"outcome": "end", "code": code, "title": f["title"]}
    return {"outcome": "still", "code": code, "title": f["title"], "next": nxt}


def walk_path() -> str:
    base = os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state")
    return os.path.join(base, "cinminai", "diag-walk.json")


def keep(code: str, n: int, title: str, now: float | None = None) -> None:
    """A fix that needs a restart: remembered, so it's checked when the assistant starts again."""
    os.makedirs(os.path.dirname(walk_path()), exist_ok=True)
    with open(walk_path() + ".tmp", "w", encoding="utf-8") as f:
        json.dump({"code": code, "n": n, "title": title, "since": now or time.time()}, f)
    os.replace(walk_path() + ".tmp", walk_path())


def kept(now: float | None = None) -> dict | None:
    try:
        with open(walk_path(), encoding="utf-8") as f:
            w = json.load(f)
    except (OSError, ValueError):
        return None
    if (now or time.time()) - float(w.get("since", 0)) > KEEP_DAYS * 86400:
        forget()
        return None
    return w


def forget() -> None:
    try:
        os.remove(walk_path())
    except OSError:
        pass
