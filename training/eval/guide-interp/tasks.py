"""Vague-request eval (cycle 0): the right first move is to restate, offer 2-4 things the guide can do,
and ask — the user is the pilot (PLAN D39). Used to tune how much interpretation training the guide
gets: the public eval checks nothing is lost on clear questions, this set checks clarifying works.

Situations are deliberately different from the interpretation corpus's 28 (generalisation, not recall).
Scoring: first action `answer`; the text has >= 2 numbered options, ends with a question, is in the
user's language, has no terminal commands.
"""

STEPS = {"steps": 2}
NO_CMD = ["sudo", r"\bapt(-get)?\s+(install|remove)", r"\brm\s+-", r"\bchmod\b"]
ASKS = [[r"~[?？]\s*$"]]
BRANDS = {"writer", "calc", "impress", "timeshift", "video_player", "firefox"}
ANSWER = [{"tool": "answer"}]

TASKS = [
    {"id": "V01", "cat": "interpret",
     "q": {"en": "I want to do something nice for my wife's birthday on the computer.",
           "es": "Quiero hacer algo bonito en la computadora para el cumpleaños de mi esposa.",
           "de": "Ich möchte am Computer etwas Schönes zum Geburtstag meiner Frau machen.",
           "ja": "パソコンで妻の誕生日に何か素敵なことをしたいです。"},
     "expect": ANSWER, "must": ASKS, "must_not": NO_CMD, **STEPS},
    {"id": "V02", "cat": "interpret", "q": {"en": "my son keeps saying I should get organized on here"},
     "expect": ANSWER, "must": ASKS, "must_not": NO_CMD, **STEPS},
    {"id": "V03", "cat": "interpret",
     "q": {"en": "Can you help me with the insurance papers?",
           "fr": "Tu peux m'aider avec les papiers de l'assurance ?",
           "pt": "Você pode me ajudar com os papéis do seguro?"},
     "expect": ANSWER, "must": ASKS, "must_not": NO_CMD, **STEPS},
    {"id": "V04", "cat": "interpret", "q": {"en": "The grandkids are coming over this weekend."},
     "expect": ANSWER, "must": ASKS, "must_not": NO_CMD, **STEPS},
    {"id": "V05", "cat": "interpret",
     "q": {"en": "I'd like to keep some kind of diary on here.",
           "de": "Ich würde hier gern so eine Art Tagebuch führen.",
           "ja": "ここで日記のようなものをつけたいです。"},
     "expect": ANSWER, "must": ASKS, "must_not": NO_CMD, **STEPS},
    {"id": "V06", "cat": "interpret", "q": {"en": "something about my email isn't right"},
     "expect": ANSWER, "must": ASKS, "must_not": NO_CMD, **STEPS},
    {"id": "V07", "cat": "interpret",
     "q": {"en": "I'm selling some old tools, can the computer help with that?",
           "es": "Estoy vendiendo unas herramientas viejas, ¿me puede ayudar la computadora?"},
     "expect": ANSWER, "must": ASKS, "must_not": NO_CMD, **STEPS},
    {"id": "V08", "cat": "interpret", "q": {"en": "help me get ready for the holidays"},
     "expect": ANSWER, "must": ASKS, "must_not": NO_CMD, **STEPS},
    {"id": "V09", "cat": "interpret", "q": {"en": "I need to sort out my music somehow."},
     "expect": ANSWER, "must": ASKS, "must_not": NO_CMD, **STEPS},
    {"id": "V10", "cat": "interpret",
     "q": {"en": "There's a neighbourhood meeting next week and I'm supposed to handle some of it.",
           "fr": "Il y a une réunion de quartier la semaine prochaine et je dois m'occuper d'une partie."},
     "expect": ANSWER, "must": ASKS, "must_not": NO_CMD, **STEPS},
]
