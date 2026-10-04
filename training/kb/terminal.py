# SPDX-License-Identifier: GPL-3.0-or-later
"""Terminal-error cards v0 (M3 slice 2, D32): what the classic terminal errors mean and the way out, as help cards.

With terminal sharing (D77) the guide sees a failed command and looks the error up (measured 2026-10-04: its
instinct is right) — but the built-in help had no terminal cards, so the lookups found nothing, and where it
answered alone it once invented a wrong fix (`cd Documents/Taxes 2025` → "cd Documents/Taxes/2025"). These cards
carry the facts. Unlike the transition cards they name commands: the person is already at a prompt. Every command
is one a beginner can run safely, with what it does; anything that changes the system says so.

Facts checked against Linux Mint 22.3 / Ubuntu 24.04 (bash 5.2, apt 2.7, Python 3.12, GCC 13). Same fields as
transition.py; the search words are in search.py.
"""

TOPICS = [
    {"id": "cmd_not_found", "windows": "a command the terminal says it doesn't know ('command not found')",
     "card": "Command not found: the terminal doesn't know that name. Check the spelling; commands are "
             "case-sensitive (ls, not LS). If it's a program that isn't installed, the message often says which "
             "package has it: install it from {software_manager}, or with sudo apt install followed by the "
             "package name. Updating isn't a command called update: open {update_manager} from the Menu (no terminal needed), or run sudo apt update "
             "and then sudo apt upgrade.",
     "must": [], "steps": False},
    {"id": "permission_denied", "windows": "'Permission denied' when running a script or opening a file",
     "card": "Permission denied when running a file such as ./backup.sh: the file isn't marked as a program. "
             "Mark it with chmod +x backup.sh (this only lets it run, nothing else changes), then run ./backup.sh "
             "again, or run it without marking it: bash backup.sh. Permission denied when opening or saving a "
             "file: it belongs to the system or another user. Only use sudo for it if you know why that file "
             "needs changing.",
     "must": [], "steps": False},
    {"id": "spaces_in_names", "windows": "a file or folder name with spaces in the terminal ('too many arguments')",
     "card": "Spaces in names: the terminal splits what you type at every space, so cd Documents/Taxes 2025 "
             "looks like two names and says too many arguments. Put the whole name in quotes: "
             "cd \"Documents/Taxes 2025\". Or type the first letters of the name and press Tab: the terminal "
             "completes it and adds what's needed.",
     "must": [], "steps": False},
    {"id": "apt_locate", "windows": "'Unable to locate package' when installing with apt",
     "card": "Unable to locate package: apt doesn't know that name. First refresh its list of programs with "
             "sudo apt update, then try again. Check the exact name with apt search followed by a word from it. "
             "Some programs have a different name here (the Chromium browser is chromium), and many are easier "
             "to find in {software_manager}, which also lists Flatpak versions.",
     "must": [], "steps": False},
    {"id": "python_module", "windows": "Python saying 'ModuleNotFoundError: No module named ...'",
     "card": "No module named …: Python can't find that library. If the project has its own environment (a .venv "
             "folder), install into it: .venv/bin/pip install followed by the name. For the system's Python, use "
             "the system package if there is one: sudo apt install python3- followed by the name. Plain pip "
             "install outside an environment is refused on Linux Mint 22 (externally-managed-environment); make "
             "an environment with python3 -m venv .venv. The import name isn't always the package name: pygame "
             "can come from pygame or pygame-ce, cv2 from opencv-python, PIL from pillow.",
     "must": [], "steps": False},
    {"id": "venv_create", "windows": "making a Python virtual environment fails ('ensurepip is not available')",
     "card": "The virtual environment was not created successfully because ensurepip is not available: the "
             "part of Python that makes environments isn't installed. Install it with sudo apt install "
             "python3-venv, then remove the half-made folder with rm -rf .venv (this deletes only the "
             "environment folder, not your code) and make it again: python3 -m venv .venv.",
     "must": [], "steps": False},
    {"id": "venv_missing", "windows": "'No such file or directory' for .venv/bin/python, .venv/bin/pip or activate",
     "card": "No such file or directory for .venv/bin/python, .venv/bin/pip or .venv/bin/activate: this folder has "
             "no virtual environment yet (or it's in a different folder: check with ls -a). Make one here with "
             "python3 -m venv .venv, then run your program with .venv/bin/python, or switch the environment on "
             "first with source .venv/bin/activate.",
     "must": [], "steps": False},
    {"id": "venv_use", "windows": "using a Python virtual environment (.venv): activate, broken after moving",
     "card": "Using a .venv: switch it on with source .venv/bin/activate (running .venv/bin/activate on its own "
             "says Permission denied: it has to be sourced). The prompt then shows (.venv); deactivate switches "
             "it off. Without activating, use its programs directly: .venv/bin/python and .venv/bin/pip. A .venv "
             "breaks when the project folder is moved or renamed (bad interpreter, or No such file for "
             ".venv/bin/pip): make it again with rm -rf .venv (deletes only the environment, not your code), "
             "python3 -m venv .venv, then reinstall what the project needs, for example .venv/bin/pip install -r "
             "requirements.txt if the project has that file.",
     "must": [], "steps": False},
    {"id": "tkinter", "windows": "getting tkinter (Python's window toolkit): pip install tkinter fails",
     "card": "tkinter, Python's toolkit for windows and buttons, doesn't come from pip: pip install tkinter finds "
             "nothing (and the name is easy to mistype). It comes from the system: sudo apt install python3-tk. "
             "It then works in your existing .venv too, so there's no need to remake it. Check with python3 -c "
             "\"import tkinter\": no message means it's there.",
     "must": [], "steps": False},
    {"id": "dpkg_lock", "windows": "'Could not get lock' when installing or updating with apt",
     "card": "Could not get lock (/var/lib/dpkg/lock-frontend): another program is installing or updating right "
             "now, often {update_manager} in the background. Wait until it finishes, then try again. Don't delete "
             "the lock files: that can break the installation in progress.",
     "must": [], "steps": False},
    {"id": "no_such_file", "windows": "'No such file or directory' in the terminal",
     "card": "No such file or directory: the name is wrong, or you're in a different folder than you think. pwd "
             "shows the folder you're in, ls shows what's in it. Names are case-sensitive: Documents and "
             "documents are different. To run a file in the current folder, start with ./ (for example ./run.sh). "
             "Typing the first letters and pressing Tab completes names that exist.",
     "must": [], "steps": False},
    {"id": "compile_error", "windows": "compiler errors when building a program (gcc, make)",
     "card": "Compiler errors: fix the first error first; later ones often come from it. The place reads "
             "file:line:column, so main.c:7:5 is line 7 of main.c. 'undeclared' (C) or 'was not declared in this "
             "scope' (C++): the name is used before it's declared, or misspelled; declare it first, for example "
             "int count = 0; before using it. 'expected ;' means a missing semicolon on that line or the one "
             "before. make: *** … Error 1 only says that a step failed; the real error is above it.",
     "must": [], "steps": False},
    {"id": "sudo_password", "windows": "sudo asking for a password, or 'is not in the sudoers file'",
     "card": "sudo asks for your own password, the one you log in with. While you type it the terminal shows "
             "stars or nothing at all; that's normal, press Enter when done. 'is not in the sudoers file' means "
             "this account isn't an administrator: ask the person who owns the computer, or use an "
             "administrator's account.",
     "must": [], "steps": False},
]
