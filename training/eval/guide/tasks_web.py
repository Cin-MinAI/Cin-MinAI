# SPDX-License-Identifier: CC-BY-SA-4.0
"""Eval items for prompt v2.2 (D54, D55): knowledge questions go to web_search, writing gets help. Same format as
tasks.py; the advice declines (D06, D07) and the computer questions are in tasks.py.

    python3 run_eval.py --prompt v2.2 --tasks tasks_web.py --url ...
"""

from tasks import BRANDS  # noqa: F401  (run_eval loads BRANDS from the tasks file)

TASKS = [
    {"id": "W01", "cat": "web", "q": {"en": "How tall is the Eiffel Tower?",
                                      "fr": "Quelle est la hauteur de la tour Eiffel ?"},
     "expect": [{"tool": "web_search", "args": {"query": "~eiffel"}}]},
    {"id": "W02", "cat": "web", "q": {"en": "Will it rain in Chicago tomorrow?"},
     "expect": [{"tool": "web_search", "args": {"query": "~chicago"}}]},
    {"id": "W03", "cat": "writing", "q": {"en": "Write a short poem for my wife's birthday. She loves gardening."},
     "expect": [{"tool": "answer"}]},
    {"id": "W04", "cat": "writing",
     "q": {"en": "Help me write a polite letter to my landlord: the heater has been broken for two weeks."},
     "expect": [{"tool": "answer", "args": {"text": "~heater|heating"}}]},
]
