# SPDX-License-Identifier: CC-BY-SA-4.0
"""Eval items for prompt v2.6 (D68): sums go to the calculator, a subject to learn about goes to Wikipedia, news and
weather stay with web_search, and the computer's own Calculator app is still opened or looked up, not used as the
tool. Same format as tasks.py. Stage B for the calculator: the reply must carry the calculator's answer (decimal
commas allowed).

    python3 run_eval.py --prompt v2.6 --tasks tasks_d68.py --url ...
"""

from tasks import BRANDS  # noqa: F401  (run_eval loads BRANDS from the tasks file)

TASKS = [
    # ---------------- the calculator --------------------------------------------------------------------------
    {"id": "M01", "cat": "calculate",
     "q": {"en": "What's 15% of 240?", "es": "¿Cuánto es el 15 % de 240?", "pt": "Quanto é 15% de 240?",
           "fr": "Combien font 15 % de 240 ?", "de": "Wie viel sind 15 % von 240?", "ja": "240の15%はいくつ？"},
     "expect": [{"tool": "calculate"}], "must": [["36"]]},
    {"id": "M02", "cat": "calculate",
     "q": {"en": "We're splitting a $187.50 dinner bill between 6 people. How much does each person pay?",
           "es": "Vamos a dividir una cuenta de 187,50 € entre 6 personas. ¿Cuánto paga cada uno?",
           "de": "Wir teilen eine Rechnung von 187,50 € durch 6 Personen. Wie viel zahlt jeder?"},
     "expect": [{"tool": "calculate"}], "must": [["~31[.,]25"]]},
    {"id": "M03", "cat": "calculate",
     "q": {"en": "Solve 3x + 7 = 25", "fr": "Résous 3x + 7 = 25", "ja": "3x + 7 = 25 を解いて"},
     "expect": [{"tool": "calculate"}], "must": [["6"]]},
    {"id": "M04", "cat": "calculate", "q": {"en": "How many seconds are there in a week?",
                                            "pt": "Quantos segundos tem uma semana?"},
     "expect": [{"tool": "calculate"}], "must": [["~604[.,\\s]?800"]]},
    {"id": "M05", "cat": "calculate",
     "q": {"en": "I earn $18.25 an hour and work 37.5 hours a week. What do I make in a week?"},
     "expect": [{"tool": "calculate"}], "must": [["~684[.,]3[78]"]]},
    {"id": "M06", "cat": "calculate", "q": {"en": "What is the square root of 2?"},
     "expect": [{"tool": "calculate"}], "must": [["~1[.,]41"]]},

    # ---------------- Wikipedia: a subject to learn about -------------------------------------------------------
    {"id": "K01", "cat": "wikipedia",
     "q": {"en": "Who was Marie Curie?", "es": "¿Quién fue Marie Curie?", "pt": "Quem foi Marie Curie?",
           "fr": "Qui était Marie Curie ?", "de": "Wer war Marie Curie?", "ja": "マリー・キュリーってどんな人？"},
     "expect": [{"tool": "wikipedia", "args": {"title": "~curie|キュリー"}}]},
    {"id": "K02", "cat": "wikipedia", "q": {"en": "What is the Great Barrier Reef?",
                                            "fr": "Qu'est-ce que la Grande Barrière de corail ?"},
     "expect": [{"tool": "wikipedia", "args": {"title": "~barrier|barri[eè]re"}}]},
    {"id": "K03", "cat": "wikipedia", "q": {"en": "Tell me about the history of the Roman Empire.",
                                            "de": "Erzähl mir etwas über die Geschichte des Römischen Reiches."},
     "expect": [{"tool": "wikipedia", "args": {"title": "~rom|röm"}}]},
    {"id": "K04", "cat": "wikipedia", "q": {"en": "How do volcanoes form?", "es": "¿Cómo se forman los volcanes?"},
     "expect": [{"tool": "wikipedia"}, {"tool": "web_search"}]},

    # ---------------- still the web: news, weather, results ---------------------------------------------------
    {"id": "R01", "cat": "web", "q": {"en": "What's the weather in Madrid today?",
                                      "es": "¿Qué tiempo hace hoy en Madrid?"}, "web_only": True,
     "expect": [{"tool": "web_search"}]},
    {"id": "R02", "cat": "web", "q": {"en": "What's the latest news about the Linux kernel?"}, "web_only": True,
     "expect": [{"tool": "web_search"}]},

    # ---------------- the computer's own Calculator is still the computer's ------------------------------------
    {"id": "N01", "cat": "computer", "q": {"en": "Open the calculator", "es": "Abre la calculadora"},
     "expect": [{"tool": "open_app"}]},
    {"id": "N02", "cat": "computer", "q": {"en": "Where is the calculator app on this computer?"},
     "expect": [{"tool": "lookup_help"}, {"tool": "open_app"}]},
]
