# SPDX-License-Identifier: GPL-3.0-or-later
"""Eval items for terminal context (M3 slice 2): the person asks about what just happened in their shared terminal,
and the daemon puts the terminal's last commands in front of the message, exactly as cin_minai.daemon.terminal
formats them. Needs cin_minai on PYTHONPATH (src/).

    PYTHONPATH=../../../src python3 run_eval.py --prompt v2.2 --tasks tasks_terminal.py --url ...

Checked: the right first action (an answer, or a lookup), and in the reply the actual cause named and a way out.
"""

from cin_minai.daemon.terminal import context
from tasks import BRANDS  # noqa: F401  (run_eval loads BRANDS from the tasks file)

H = "/home/sam"


def cmd(c, out, code, cwd=H, secret=False):
    return {"cmd": c, "cwd": cwd, "exit": code, "output": out, "secret": secret, "start": 0, "end": 1}


def ask(commands, question):
    return context(commands) + "\n\n" + question


SITUATIONS = {
    # Ian's own first capture, 2026-10-04
    "T_UPD": [cmd("sudo update", "\nsudo: update: command not found", 1, secret=True)],
    "T_PKG": [cmd("sudo apt install chromium-browser",
                  "Reading package lists... Done\nBuilding dependency tree... Done\nReading state information... Done\n"
                  "E: Unable to locate package chromium-browser", 100, secret=True)],
    "T_MOD": [cmd("python3 blackjack.py",
                  "Traceback (most recent call last):\n  File \"/home/sam/aicui-test/blackjack.py\", line 3, in <module>\n"
                  "    import pygame\nModuleNotFoundError: No module named 'pygame'", 1, cwd=H + "/aicui-test")],
    "T_PERM": [cmd("./backup.sh", "bash: ./backup.sh: Permission denied", 126)],
    "T_GCC": [cmd("gcc main.c -o main",
                  "main.c: In function 'main':\nmain.c:7:5: error: 'count' undeclared (first use in this function)\n"
                  "    7 |     count = count + 1;\n      |     ^~~~~\n"
                  "main.c:7:5: note: each undeclared identifier is reported only once for each function it appears in",
                  1, cwd=H + "/code")],
    "T_CD": [cmd("cd Documents/Taxes 2025", "bash: cd: too many arguments", 1)],
    # venv breakages (Ian's test, 2026-10-04: "correct a venv setup in the hello world folder")
    "T_ENSUREPIP": [cmd("python3 -m venv .venv",
                        "The virtual environment was not created successfully because ensurepip is not\navailable.  "
                        "On Debian/Ubuntu systems, you need to install the python3-venv\npackage using the following "
                        "command.\n\n    apt install python3.12-venv\n\nYou may need to use sudo with that command.  "
                        "After installing the python3-venv\npackage, recreate your virtual environment.\n\n"
                        "Failing command: /home/sam/hello_world_test/.venv/bin/python3", 1, cwd=H + "/hello_world_test")],
    "T_ACTIVATE": [cmd(".venv/bin/activate", "bash: .venv/bin/activate: Permission denied", 126,
                       cwd=H + "/hello_world_test")],
    "T_MOVED": [cmd(".venv/bin/pip install requests",
                    "bash: /home/sam/hello_world_test/.venv/bin/pip: /home/sam/hello_test/.venv/bin/python3: "
                    "bad interpreter: No such file or directory", 126, cwd=H + "/hello_world_test")],
    # Ian's own run on the test SSD, 2026-10-04, inside an activated .venv
    "T_TK": [cmd("pip install tinkter", "ERROR: Could not find a version that satisfies the requirement tinkter (from "
                 "versions: none)\nERROR: No matching distribution found for tinkter", 1, cwd=H + "/hello_world_test")],
    # the M3 exit test on the SSD (2026-10-04): a folder without a venv
    "T_NOVENV": [cmd(".venv/bin/python hello.py", "bash: .venv/bin/python: No such file or directory", 127,
                     cwd=H + "/m3-exit-test")],
    "T_PEP668": [cmd("pip install requests",
                     "error: externally-managed-environment\n\n× This environment is externally managed\n╰─> To install "
                     "Python packages system-wide, try apt install\n    python3-xyz, where xyz is the package you are "
                     "trying to\n    install.", 1, cwd=H + "/hello_world_test")],
}

TASKS = [
    {"id": "R01", "cat": "terminal", "terminal": SITUATIONS["T_UPD"],
     "q": {"en": ask(SITUATIONS["T_UPD"], "why didnt this work?"),
           "es": ask(SITUATIONS["T_UPD"], "¿por qué no funcionó esto?")},
     "expect": [{"tool": "answer"}, {"tool": "lookup_help"}],
     "must": [["apt update", "apt upgrade", "{update_manager}", "Update Manager"]]},
    {"id": "R02", "cat": "terminal", "terminal": SITUATIONS["T_PKG"],
     "q": {"en": ask(SITUATIONS["T_PKG"], "what does this error mean?")},
     "expect": [{"tool": "answer"}, {"tool": "lookup_help"}],
     "must": [["snap", "flatpak", "{software_manager}", "Software Manager", "apt update", "chromium", "name"]]},
    {"id": "R03", "cat": "terminal", "terminal": SITUATIONS["T_MOD"],
     "q": {"en": ask(SITUATIONS["T_MOD"], "my game won't start, why?")},
     "expect": [{"tool": "answer"}, {"tool": "lookup_help"}],
     "must": [["pygame"], ["install", "pip"]]},
    {"id": "R04", "cat": "terminal", "terminal": SITUATIONS["T_PERM"],
     "q": {"en": ask(SITUATIONS["T_PERM"], "why is permission denied?")},
     "expect": [{"tool": "answer"}, {"tool": "lookup_help"}],
     "must": [["chmod", "executable", "permission to run", "run it with bash", "bash backup.sh"]]},
    {"id": "R05", "cat": "terminal", "terminal": SITUATIONS["T_GCC"],
     "q": {"en": ask(SITUATIONS["T_GCC"], "what did I do wrong?")},
     "expect": [{"tool": "answer"}, {"tool": "lookup_help"}],
     "must": [["count"], ["declare", "undeclared", "int count", "defined"]]},
    {"id": "R06", "cat": "terminal", "terminal": SITUATIONS["T_CD"],
     "q": {"en": ask(SITUATIONS["T_CD"], "it says too many arguments?"),
           "de": ask(SITUATIONS["T_CD"], "Warum geht das nicht?")},
     "expect": [{"tool": "answer"}, {"tool": "lookup_help"}],
     "must": [["\"Documents/Taxes 2025\"", "'Documents/Taxes 2025'", "Taxes\\ 2025", "quote", "space",
               "Anführungszeichen", "Leerzeichen"]]},
    {"id": "R07", "cat": "terminal", "terminal": SITUATIONS["T_ENSUREPIP"],
     "q": {"en": ask(SITUATIONS["T_ENSUREPIP"], "why can't I make a venv?")},
     "expect": [{"tool": "answer"}, {"tool": "lookup_help"}],
     "must": [["python3-venv", "python3.12-venv"], ["python3 -m venv"]]},
    {"id": "R08", "cat": "terminal", "terminal": SITUATIONS["T_ACTIVATE"],
     "q": {"en": ask(SITUATIONS["T_ACTIVATE"], "how do I turn on my venv? this didn't work")},
     "expect": [{"tool": "answer"}, {"tool": "lookup_help"}],
     "must": [["source .venv/bin/activate", ". .venv/bin/activate"]]},
    {"id": "R09", "cat": "terminal", "terminal": SITUATIONS["T_MOVED"],
     "q": {"en": ask(SITUATIONS["T_MOVED"], "my venv was working yesterday, what happened?")},
     "expect": [{"tool": "answer"}, {"tool": "lookup_help"}],
     "must": [["moved", "renamed", "rename", "move"], ["python3 -m venv"]]},
    {"id": "R11", "cat": "terminal", "terminal": SITUATIONS["T_TK"],
     "q": {"en": ask(SITUATIONS["T_TK"], "how do I get tkinter in my venv?")},
     "expect": [{"tool": "answer"}, {"tool": "lookup_help"}],
     "must": [["python3-tk"]],
     "must_not": [r"rm -rf"]},  # the venv is fine: remaking it (Ian's run) was unnecessary
    {"id": "R12", "cat": "terminal", "terminal": SITUATIONS["T_TK"],
     # the same moment, asked the way Ian did on the test SSD; the guide had looked up something generic
     "q": {"en": ask(SITUATIONS["T_TK"], "why didnt this work?")},
     "expect": [{"tool": "answer"}, {"tool": "lookup_help"}],
     "must": [["python3-tk", "tkinter"]],
     "must_not": [r"rm -rf"]},
    {"id": "R13", "cat": "terminal", "terminal": SITUATIONS["T_NOVENV"],
     "q": {"en": ask(SITUATIONS["T_NOVENV"], "why didnt this work?")},
     "expect": [{"tool": "answer"}, {"tool": "lookup_help"}],
     # the cause first: there's no venv here (the exit test's answer led with "it wasn't activated")
     "must": [["python3 -m venv .venv"], ["~^[\\s\\S]{0,200}(no virtual environment|no venv|doesn't have|does not have|doesn't exist|does not exist|isn't there|missing|not found|no \\.venv)"]]},
    {"id": "R10", "cat": "terminal", "terminal": SITUATIONS["T_PEP668"],
     "q": {"en": ask(SITUATIONS["T_PEP668"], "what does this mean?"),
           "es": ask(SITUATIONS["T_PEP668"], "¿qué significa esto?")},
     "expect": [{"tool": "answer"}, {"tool": "lookup_help"}],
     "must": [[".venv", "venv", "virtual environment", "entorno virtual"]]},
]
