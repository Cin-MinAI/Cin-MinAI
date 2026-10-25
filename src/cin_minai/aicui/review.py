# SPDX-License-Identifier: GPL-3.0-or-later
"""Reviews by another model (PLAN D94), AICUI's Review button:

    python3 -P -m cin_minai.aicui.review FOLDER [--out FILE]

A model other than the one that wrote the code reads the project three times, each time for what breaks from one side
(Ian, 2026-10-24): **from the beginning** (from the start command forward: what runs as each file loads, each view as
it's built), **from the end** (the person's goal, followed backwards link by link to the start) and **in operation**
(every control the person can use; twice, out of order, away and back). Measured on a 1080 Ti with the 35B-A3B, the
three passes merged found 6, 10.5 and 10 of 16 known defects (one pass three times: ~8.5) — and each set carried about
four claims that weren't true (made-up crashes, a "done" verdict).

So every claim is checked in code where a check can exist, before the person sees it: the quoted line is where it says,
a "syntax error" against the compiler, a name "not imported" against the file, a missing library against the project's
own Python, a crash at startup against starting the program for five seconds (sandboxed, on a virtual screen). A claim
a check contradicts is dropped and counted; one a check reproduces is "checked"; the rest are "not checked". The person
reads the list and sends the ones they tick to the coder (the Review window in app.py). The model is the Models view's
Review job (daemon/jobs.py): ours is the 35B-A3B, the person may choose another; the guide doesn't review.
"""

from __future__ import annotations

import argparse
import ast
import dataclasses
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import threading
import time

from .project import Goals, entry_point, tree, venv_python

THINK = 4096            # tokens of thinking per pass (unbounded, the reviews never got written: measured 2026-10-24)
ANSWER = 9000           # the thinking and the answer together
CHARS_PER_TOKEN = 3.0   # code with line numbers, as the 35B's tokenizer counted test runs (9.8K tokens, ~30K chars)
BUDGET_MESSAGE = " That is enough thinking; time to write the answer."
SAMPLING = {"temperature": 0.6, "top_p": 0.95}
START_SECONDS = 5
REVIEWS = os.path.join(".cinminai", "reviews")
CODE = {".py", ".pyw", ".js", ".mjs", ".ts", ".tsx", ".jsx", ".html", ".htm", ".css", ".sh", ".c", ".h", ".cc",
        ".cpp", ".hpp", ".cxx", ".rs", ".go", ".java", ".kt", ".cs", ".lua", ".rb", ".php", ".swift", ".dart", ".gd"}

RULES = ("Write each defect as one block, exactly like this:\n"
         "### file:line\n"
         "quote: the line itself, copied exactly\n"
         "wrong: what is wrong\n"
         "sees: what the person sees\n\n"
         "Worst first. A crash only if you can name the line that raises it; if the code checks first (hasattr, try, "
         "if), it does not crash. Read what the code does, not what its names suggest. End with one line: the "
         "verdict, done or not done.\n\n")
PASSES = [
    ("beginning", "From the beginning",
     "Review the code below for what breaks, starting from the beginning. Follow the program from {start} forward: "
     "the imports, the code that runs when each file loads, the window or first screen, and each part as it is built "
     "(its constructor and what it sets up). List every defect on that path. "),
    ("end", "From the end",
     "Review the code below for what breaks, starting from the end. The person's goal is what they asked for, above. "
     "Work backwards: what must the code do for the last step of it? Then the step before it, and so on back to "
     "starting the program. At each link, say whether the code makes it, and where the chain breaks. "),
    ("operation", "In operation",
     "Review the code below for what breaks in operation. The program is running and the person uses it. Follow "
     "everything they can do: every button, menu entry, field, list and command. Then what happens when they do it "
     "twice, in a different order, or go somewhere else and come back. List every defect. "),
]


# --- what is read --------------------------------------------------------------------------------------------
def asked(root: str, limit: int = 2500) -> str:
    """What the person asked for: the project's first request in their words, and the session goals."""
    parts = []
    try:
        with open(os.path.join(root, "original-request.txt"), encoding="utf-8") as f:
            parts.append(f.read().strip())
    except OSError:
        pass
    goals = [g["text"] for g in Goals(root).load() if g.get("text")]
    if goals:
        parts.append("Its goals: " + "; ".join(goals))
    return ("\n".join(parts) or "(not written down: judge from the code what it is meant to do)")[:limit]


def changed_files(root: str) -> list[str]:
    """Files AICUI's changelog has changes for, the latest first."""
    seen = []
    try:
        with open(os.path.join(root, ".cinminai", "changelog.jsonl"), encoding="utf-8") as f:
            rows = [json.loads(line) for line in f if line.strip()]
    except (OSError, ValueError):
        return []
    for r in reversed(rows):
        rel = r.get("file", "")
        if rel and rel not in seen and not r.get("undone"):
            seen.append(rel)
    return seen


def writers(root: str, files: list[str]) -> dict[str, int]:
    """Which models wrote these files, by changes (the changelog's "model" field)."""
    out: dict[str, int] = {}
    try:
        with open(os.path.join(root, ".cinminai", "changelog.jsonl"), encoding="utf-8") as f:
            for line in f:
                r = json.loads(line) if line.strip() else {}
                if r.get("file") in files and not r.get("undone"):
                    out[r.get("model", "")] = out.get(r.get("model", ""), 0) + 1
    except (OSError, ValueError):
        pass
    return out


def same_model(a: str, b: str) -> bool:
    """The changelog's model label and a model's name, compared without their notes ("(experts in RAM)", "(cloud)")."""
    norm = lambda s: re.sub(r"\s*\(.*?\)", "", s or "").strip().lower()
    return bool(norm(a)) and norm(a) == norm(b)


def code_files(root: str) -> list[str]:
    """The project's own code: kept pages and fetched material left out, the start file first, then what AICUI
    changed (latest first), then the rest by name."""
    from .agent import kept_material
    files = [rel for rel, is_dir, _ in tree(root) if not is_dir and os.path.splitext(rel)[1].lower() in CODE
             and not kept_material(rel, root)]
    entry = entry_point(root)
    order = ([entry] if entry in files else []) + [f for f in changed_files(root) if f in files]
    return list(dict.fromkeys(order + sorted(files)))


def numbered(root: str, rel: str) -> str:
    try:
        with open(os.path.join(root, rel), encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()
    except OSError:
        return ""
    return f"=== {rel} ===\n" + "\n".join(f"{i:4} {line}" for i, line in enumerate(lines, 1))


def pick(root: str, budget_chars: int) -> tuple[list[str], list[str], str]:
    """(files shown, files left out, the code as the model reads it): whole files, in code_files' order, up to the
    budget."""
    shown, left, parts, used = [], [], [], 0
    for rel in code_files(root):
        text = numbered(root, rel)
        if text and used + len(text) <= budget_chars:
            shown.append(rel)
            parts.append(text)
            used += len(text) + 2
        elif text:
            left.append(rel)
    return shown, left, "\n\n".join(parts)


def prompt(key: str, want: str, code: str, start: str, left: list[str] = ()) -> str:
    ask = next(p for k, _, p in PASSES if k == key)
    # the files that didn't fit are named: told nothing, the 35B called gui/deck_builder.py "not provided" (2026-10-25)
    rest = (f"Also in the project, not shown here for room: {', '.join(left)}. They exist: don't report them as "
            "missing.\n\n") if left else ""
    return (f"The person asked for: {want}\n\nThe project starts with: {start}. Another model wrote this code.\n\n"
            + rest + ask.format(start=start) + RULES + code)


# --- what came back --------------------------------------------------------------------------------------------
HEAD = re.compile(r"^\s*#{2,4}\s*\**\s*`?([\w./\\-]+\.\w+)`?\s*[:,]?\s*(?:line\s*)?`?(\d+)?", re.I)
FIELD = re.compile(r"^\s*[-*]?\s*\**(quote|wrong|sees)\**\s*:\s*\**\s*(.*)$", re.I)
VERDICT = re.compile(r"verdict\W{0,6}\s*(not done|done)", re.I)


def parse(text: str, key: str) -> list[dict]:
    """The blocks: {"file", "line", "quote", "wrong", "sees", "passes"}; a block needs a file and what's wrong."""
    out, cur, field = [], None, None
    for raw in text.splitlines():
        m = HEAD.match(raw)
        if m:
            if cur and cur.get("wrong"):
                out.append(cur)
            cur, field = {"file": m.group(1).replace("\\", "/"), "line": int(m.group(2) or 0), "quote": "",
                          "wrong": "", "sees": "", "passes": [key]}, None
            continue
        if cur is None:
            continue
        f = FIELD.match(raw)
        if f:
            field = f.group(1).lower()
            cur[field] = f.group(2).strip()
        elif field and raw.strip() and not raw.lstrip().startswith("#"):
            joint = "\n" if field == "quote" else " "  # a quote of two lines stays two lines: each is a file's line
            cur[field] = (cur[field] + joint + raw.strip()).strip()
    if cur and cur.get("wrong"):
        out.append(cur)
    for c in out:
        c["quote"] = c["quote"].strip().strip("`").strip('"').strip()
    return out


PER_PASS = 15     # findings a pass may give, worst first (measured passes gave ~10; past that, lists of lines)
MIN_WRONG = 30    # characters a finding's "wrong" needs: "No", "Y=780.", "Fixed." aren't findings


def kept(found: list[dict]) -> list[dict]:
    """A pass's findings that say something, at most PER_PASS of them, in the order given (worst first)."""
    return [f for f in found if len(f["wrong"].strip()) >= MIN_WRONG][:PER_PASS]


def verdict(text: str) -> str:
    found = VERDICT.findall(text)
    return found[-1].lower() if found else ""


def words(s: str) -> set:
    return {w for w in re.findall(r"[a-z_][a-z0-9_]{3,}", (s or "").lower())}


def alike(a: dict, b: dict) -> bool:
    """The same defect said twice: the same file, near lines, and mostly the same words (fewer when the quote is the
    same line)."""
    if os.path.basename(a["file"]) != os.path.basename(b["file"]) or abs(a["line"] - b["line"]) > 3:
        return False
    wa, wb = words(a["wrong"]), words(b["wrong"])
    if not (wa and wb):
        return False
    share = len(wa & wb) / min(len(wa), len(wb))
    qa, qb = squash(a["quote"]), squash(b["quote"])
    same_line = bool(qa and qb and (qa in qb or qb in qa))  # one line can hold two defects: the words decide
    return share >= (0.3 if same_line else 0.45)


def merge(found: list[list[dict]]) -> list[dict]:
    out: list[dict] = []
    for one in found:
        for f in one:
            twin = next((o for o in out if alike(o, f)), None)
            if twin is None:
                out.append(dict(f))
                continue
            twin["passes"] = list(dict.fromkeys(twin["passes"] + f["passes"]))
            for k in ("wrong", "sees", "quote"):
                if len(f[k]) > len(twin[k]):
                    twin[k] = f[k]
    return out


# --- the checks ------------------------------------------------------------------------------------------------
def squash(s: str) -> str:
    return re.sub(r"\s+", "", (s or "").strip("`'\" ")).lower()


IF = re.compile(r"\b(if|when|unless|could|may|might|would|should|potential(ly)?|risk)\b", re.I)
SYNTAX = re.compile(r"syntax\s*error|missing (colon|bracket|brace|parenthes\w*|paren|quote)|extra (closing )?"
                    r"(parenthes\w*|bracket)|unterminated|indentation\s*error|unbalanced|unclosed", re.I)
# only the negative: "`on_click` is defined as an empty method" is a true finding a name check would have dropped
NAME = re.compile(r"NameError|\b(isn't|is not|not|never|wasn't|was not)\s+(been\s+)?(imported|defined)\b|undefined "
                  r"name|not in scope", re.I)
MODULE = re.compile(r"ModuleNotFoundError|ImportError|(isn't|is not|not) installed|missing (library|dependency|"
                    r"package|module)", re.I)
# a claim that the whole program doesn't start, named as such: launch, startup, import, before any window. Not "the
# game never starts" or "Start never opens the board": that's one button (2026-10-24: Start Game's real bug was dropped
# because the program itself started)
START = re.compile(r"\b(crash\w*|fails?|exits?|terminat\w*|dies)\b[^.]{0,40}\b(on|at|during|upon)\s+"
                   r"(startup|start-up|launch|import)\b|\b(crash\w*|exits?|terminat\w*)\s+(immediately|instantly|"
                   r"right away)\s+(on|at|when)\s+(startup|launch|start-up)\b|before any (ui|window|gui|screen)", re.I)
TICKS = re.compile(r"`([A-Za-z_][\w.]*)`")
PIP_NAMES = {"pillow": "PIL", "pyyaml": "yaml", "opencv-python": "cv2", "scikit-learn": "sklearn",
             "beautifulsoup4": "bs4"}


def where(root: str, shown: list[str], rel: str) -> str:
    """The file a finding names, as a path in the project ("" when it isn't one): its path, or a shown file's name."""
    rel = rel.lstrip("./")
    if os.path.isfile(os.path.join(root, rel)):
        return rel
    same = [s for s in shown if os.path.basename(s) == os.path.basename(rel) or s.endswith("/" + rel)]
    return same[0] if len(same) == 1 else ""


def place(root: str, shown: list[str], f: dict) -> str:
    """"" when the finding's place holds (its line fixed when the quote is elsewhere), else why it doesn't."""
    rel = where(root, shown, f["file"])
    if not rel:
        return f"there's no file {f['file']} in the project"
    f["file"] = rel
    with open(os.path.join(root, rel), encoding="utf-8", errors="replace") as fh:
        lines = fh.read().splitlines()
    first = next((line for line in f["quote"].replace("\\n", "\n").splitlines() if line.strip()), "")
    q = squash(first.split(" / ")[0])[:60].rstrip(".")
    if q:
        hits = [i for i, line in enumerate(lines, 1) if q in squash(line)]
        if not hits:
            return f"the quoted line isn't in {rel}"
        if not any(abs(h - f["line"]) <= 5 for h in hits):
            f["line"] = min(hits, key=lambda h: abs(h - f["line"]))
    elif f["line"] > len(lines):
        return f"{rel} has {len(lines)} lines, not {f['line']}"
    return ""


def defined_names(source: str) -> dict[str, int]:
    """Every name a Python file imports, defines or assigns, with the first line that does."""
    out: dict[str, int] = {}
    try:
        tree_ = ast.parse(source)
    except SyntaxError:
        return out
    for n in ast.walk(tree_):
        names = []
        if isinstance(n, (ast.Import, ast.ImportFrom)):
            names = [(a.asname or a.name).split(".")[0] for a in n.names]
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names = [n.name]
        elif isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
            names = [n.id]
        elif isinstance(n, ast.arg):
            names = [n.arg]
        for name in names:
            out.setdefault(name, getattr(n, "lineno", 0))
    return out


def set_attributes(source: str) -> dict[str, int]:
    """Every attribute a Python file sets (self.x = …, obj.x += …), with the first line that does."""
    out: dict[str, int] = {}
    try:
        tree_ = ast.parse(source)
    except SyntaxError:
        return out
    for n in ast.walk(tree_):
        if isinstance(n, ast.Attribute) and isinstance(n.ctx, ast.Store):
            out.setdefault(n.attr, n.lineno)
    return out


def imported(source: str) -> set[str]:
    """The modules a Python file imports, as written (gui.deck_builder, PIL)."""
    try:
        tree_ = ast.parse(source)
    except SyntaxError:
        return set()
    out = set()
    for n in ast.walk(tree_):
        if isinstance(n, ast.Import):
            out |= {a.name for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.module and not n.level:
            out.add(n.module)
    return out


def subject(claim: str, m: re.Match) -> str:
    """The name a "not defined" claim is about: the last one named before it in its sentence, else the first after
    (2026-10-25: "`self.detail_name` is never defined … the widget is `self.card_name_label`" was checked against
    `self`, and dropped)."""
    head = claim[:m.start()]
    cut = max(head.rfind(". "), head.rfind("\n"))
    before = TICKS.findall(head[cut + 1:])
    if before:
        return before[-1]
    after = TICKS.findall(re.split(r"\.\s|\n", claim[m.end():], maxsplit=1)[0])
    return after[0] if after else ""


def project_module(root: str, module: str) -> str:
    """The project's own file for a module (gui.deck_builder → gui/deck_builder.py), "" when it isn't one."""
    rel = module.replace(".", "/")
    for cand in (rel + ".py", rel + "/__init__.py"):
        if os.path.isfile(os.path.join(root, cand)):
            return cand
    return rel if os.path.isdir(os.path.join(root, rel)) else ""


def sandboxed(root: str, command: str, timeout: int) -> tuple[int | None, str]:
    """A command in the project, the way the coder's checks run it: the project's Python first, a virtual screen,
    no network, the person's keys walled off (agent.py execute)."""
    from . import look
    from .agent import secret_walls, with_screen, without_secrets
    py = venv_python(root)
    venv = os.path.dirname(os.path.dirname(py)) if py != "python3" else ""
    prefix = f"export VIRTUAL_ENV={shlex.quote(venv)} PATH={shlex.quote(venv + '/bin')}:$PATH; " if venv else ""
    argv = ["bash", "-lc", prefix + (with_screen(command, look.screen_of()) if shutil.which("Xvfb") else command)]
    env = dict(os.environ)
    if shutil.which("bwrap"):
        argv = ["bwrap", "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc", "--tmpfs", "/tmp",
                *secret_walls(), "--bind", root, root, "--unshare-net", "--die-with-parent", "--chdir", root, *argv]
        env = without_secrets(env)
    env.update(SDL_VIDEODRIVER="dummy", SDL_AUDIODRIVER="dummy", PYGAME_HIDE_SUPPORT_PROMPT="1",
               PYTHONDONTWRITEBYTECODE="1")
    try:
        p = subprocess.run(argv, cwd=root, capture_output=True, text=True, env=env, timeout=timeout,
                           start_new_session=True)
    except (OSError, subprocess.TimeoutExpired) as e:
        return None, str(e)
    return p.returncode, (p.stdout + p.stderr).strip()


def start(root: str) -> dict | None:
    """The program started the way the person starts it, for a few seconds: {"entry", "started", "out"}."""
    entry = entry_point(root)
    if not entry or entry.endswith((".html", ".htm")):
        return None
    how = f"./{shlex.quote(entry)}" if entry.endswith(".sh") else f"python3 {shlex.quote(entry)}"
    code, out = sandboxed(root, f"timeout {START_SECONDS} {how}", START_SECONDS + 40)
    return {"entry": entry, "started": code in (0, 124), "code": code, "out": (out or "")[-1500:]}


def importable(root: str, module: str) -> bool | None:
    code, _ = sandboxed(root, f"python3 -c {shlex.quote('import ' + module)}", 40)
    return None if code is None else code == 0


def check(root: str, shown: list[str], f: dict, started: dict | None) -> tuple[str, str]:
    """("checked" | "not checked" | "wrong", why) for one finding."""
    bad = place(root, shown, f)
    if bad.startswith("there's no file") or " has " in bad:  # a file or line that doesn't exist: made up
        return "wrong", bad
    if bad:  # a quote not found: kept for the person to judge (2026-10-24: "the project requires a C++ engine",
        return "not checked", bad + " (it may be about something missing)"  # true, has no line to quote)
    claim = f"{f['wrong']} {f['sees']}"
    full = os.path.join(root, f["file"])
    with open(full, encoding="utf-8", errors="replace") as fh:
        source = fh.read()
    py = full.endswith((".py", ".pyw"))
    if SYNTAX.search(claim):
        if py:
            try:
                ast.parse(source)
                return "wrong", f"{f['file']} compiles: Python reads it without a syntax error"
            except SyntaxError as e:
                return "checked", f"Python: {e.msg}, line {e.lineno}"
        if full.endswith(".json"):
            try:
                json.loads(source)
                return "wrong", f"{f['file']} reads as JSON without an error"
            except ValueError as e:
                return "checked", f"JSON: {e}"
    m = NAME.search(claim) if py else None
    name = subject(claim, m) if m else ""
    if "." in name:  # self.x: never dropped, what runs first decides (2026-10-25: `self.player_lp_label` is set only
        # in a method nobody calls, as the claim said); where the file sets it, for the person to judge
        attr = name.rsplit(".", 1)[1]
        sets = {**set_attributes(source), **{k: v for k, v in defined_names(source).items() if k == attr}}
        return "not checked", (f"{f['file']} sets `{attr}` on line {sets[attr]}" if attr in sets
                               else f"nothing in {f['file']} sets `{attr}`")
    if name:
        names = defined_names(source)
        if name in names and len(name) > 1:
            return "wrong", f"`{name}` is imported or defined in {f['file']} (line {names[name]})"
    if MODULE.search(claim):
        # only modules the file imports: `DeckBuilderScreen` is a class, and `import DeckBuilderScreen` failing made
        # a made-up "not provided" the review's first checked finding (2026-10-25)
        uses = imported(source) if py else set()
        bases = {u.split(".")[0] for u in uses}
        mine = ""
        for name in TICKS.findall(claim) + re.findall(r"\b(Pillow|PIL|pygame|numpy|requests|yaml)\b", claim):
            if name in uses and project_module(root, name):
                mine = mine or project_module(root, name)
                continue
            module = PIP_NAMES.get(name.lower(), name).split(".")[0]
            if module not in bases or not re.fullmatch(r"[A-Za-z_]\w*", module) or project_module(root, module):
                continue
            ok = importable(root, module)
            if ok:
                return "wrong", f"{module} is installed in the project's Python"
            if ok is False:
                return "checked", f"`import {module}` fails in the project's Python"
        if mine:
            return "wrong", f"{mine} is in the project"
    if started is not None and START.search(claim) and not IF.search(claim):
        if started["started"]:
            return "wrong", f"{started['entry']} started and ran for {START_SECONDS} seconds without stopping"
        return "checked", f"{started['entry']} stopped at once (exit {started['code']})"
    return "not checked", ""


# --- the model -------------------------------------------------------------------------------------------------
def reviewer_plan():
    """(store, plan) for the Review job: the person's choice in the Models view, else ours."""
    from cin_minai.daemon import jobs
    from cin_minai.daemon.models import ModelStore
    from cin_minai.inference import matcher
    store = ModelStore()
    machine = matcher.read_machine(models_dir=store.root)
    chosen = store.in_use("review")
    pick = ({"model": chosen["model"], "file": chosen["file"]} if chosen and store.has(chosen["file"])
            else jobs.ours(store, "review", machine))
    if not pick or pick["file"] == matcher.CATALOG["help"][0].file:
        raise SystemExit("No model for reviewing code runs on this computer: Models → Reviewing offers one "
                         "(ours is Qwen3.6-35B-A3B).")
    # planned for the card as it is now: the matcher counts our own servers as free (a model switch unloads them),
    # but the guide and the coder stay loaded beside a review (2026-10-24: planned with the guide's 3 GB counted
    # free, the 24K review didn't fit and the server came up at 4K)
    ours = matcher.own_server_mib()
    now = dataclasses.replace(machine, cards=[{**c, "free_mib": max(0, c["free_mib"] - ours)}
                                              if c.get("api", "").startswith("CUDA") else c for c in machine.cards])
    plan = jobs.job_plan(jobs.entry(store, pick["file"]), now, "review",
                         why="your choice" if chosen else "our pick")
    if not plan:
        raise SystemExit(f"{pick['model']} doesn't fit beside what's loaded now: close the AI's terminal or Stop "
                         "everything first, then Review.")
    return store, plan


def reviewer_backend(log=None):
    from cin_minai.daemon import config
    from cin_minai.daemon.models import backend_cfg
    from cin_minai.inference.llamacpp import LlamaCppBackend
    store, plan = reviewer_plan()
    cfg = backend_cfg(config.load()["inference"], plan, store.path(plan["file"]))
    cfg.update(socket_name="llama-review.sock", reasoning="on", reasoning_budget=THINK,
               reasoning_budget_message=BUDGET_MESSAGE, request_timeout_s=3600, fallback_context=0)
    return LlamaCppBackend(cfg, log or (lambda m: None)), plan


def whole(backend, messages, *, max_tokens=ANSWER, think=True, sampling=None, cancel=None) -> tuple[str, dict]:
    """One request, answered whole (not streamed): llama.cpp's thinking budget ends the thinking in time only then.
    Streamed, the 35B thought through all 9,000 tokens, the budget's message came at the very end and no answer was
    written (2026-10-24, three passes of six minutes each, empty); the same request whole thought ~4K and answered."""
    from cin_minai.inference.llamacpp import UnixHTTPConnection
    backend.load()
    body = {"model": backend.model_name(), "messages": messages, "stream": False, "max_tokens": max_tokens,
            "cache_prompt": True, "chat_template_kwargs": {"enable_thinking": bool(think)}, **(sampling or {})}
    conn = UnixHTTPConnection(backend.sock, float(backend.cfg.get("request_timeout_s", 3600)))
    try:
        conn.request("POST", "/v1/chat/completions", body=json.dumps(body).encode(),
                     headers={"Content-Type": "application/json"})
        r = conn.getresponse()
        raw = r.read()
        if r.status != 200:
            raise RuntimeError(f"the reviewer's model answered {r.status}: {raw[:300].decode(errors='replace')}")
        got = json.loads(raw)
    finally:
        conn.close()
    return (got["choices"][0]["message"].get("content") or ""), got.get("timings", {})


def loaded_whole(backend, plan: dict) -> None:
    """The review's context or none: a server that fell back to a smaller one can't read the code (it said "room for
    4096" and stopped, 2026-10-24)."""
    backend.load()
    got = backend.profile.context if backend.profile is not None else 0
    if got < int(plan.get("context") or 0):
        backend.unload()
        raise SystemExit(f"The card is too full for a review right now (room for {got // 1024}K of the "
                         f"{int(plan['context']) // 1024}K it needs): close the AI's terminal or Stop everything "
                         "first, then Review.")


def minutes(plan: dict, chars: int) -> int:
    """About how long the three passes take with this plan (its estimated writing speed; reading at ~8x that)."""
    speed = plan.get("tok_s") or 15
    tok_s = float(min(speed) if isinstance(speed, (list, tuple)) else speed)  # a measured range: its low end
    per_pass = (ANSWER * 0.6) / tok_s + (chars / CHARS_PER_TOKEN) / (tok_s * 8)
    return max(1, round(3 * per_pass / 60))


def budget(plan: dict) -> int:
    """Characters of code the review's context holds beside the instructions and the answer."""
    return int(max(4000, (int(plan.get("context") or 16384) - ANSWER - 900) * CHARS_PER_TOKEN))


def run(root: str, chat, plan: dict, say=print, cancel: threading.Event | None = None) -> dict:
    """The three passes, merged, checked. chat(messages, **kw) -> (text, timings) — the reviewer's backend."""
    root = os.path.abspath(root)
    shown, left, code = pick(root, budget(plan))
    want, entry = asked(root), entry_point(root) or "(no start file)"
    result = {"made": time.strftime("%Y-%m-%dT%H:%M:%S"), "model": plan.get("model", ""), "files": shown,
              "left_out": left, "passes": {}, "findings": [], "dropped": [], "verdicts": {}}
    found = []
    for i, (key, title, _) in enumerate(PASSES, 1):
        if cancel is not None and cancel.is_set():
            break
        say(f"Review {i} of 3: {title.lower()}…")
        t = time.time()
        asked_ = prompt(key, want, code, entry, left)
        # as measured: thinking and answer together within ANSWER. Given the context's whole rest (~11K), the 35B
        # went line by line ("Defines class.", "Stores root.") and ended in fragments ("Y=780.", "No"): 88 and 72 items
        room = int(plan.get("context") or 16384) - int(len(asked_) / CHARS_PER_TOKEN) - 300
        text, _ = chat([{"role": "user", "content": asked_}], max_tokens=max(1000, min(ANSWER, room)), think=True,
                       sampling=SAMPLING, cancel=cancel)
        result["passes"][key] = {"seconds": round(time.time() - t), "text": text}
        result["verdicts"][key] = verdict(text)
        found.append(kept(parse(text, key)))
    say("Checking what the review says…")
    started = start(root)
    result["start"] = started
    for f in merge(found):
        state, why = check(root, shown, f, started)
        f["state"], f["why"] = state, why
        (result["dropped"] if state == "wrong" else result["findings"]).append(f)
    # said unless a finding was confirmed by this start (2026-10-25: a "fails on startup" checked by something else
    # hid that run.sh stopped at once)
    stopped = f"{started['entry']} stopped at once" if started else ""
    if started and not started["started"] and not any(f["why"].startswith(stopped) for f in result["findings"]):
        result["findings"].insert(0, {"file": started["entry"], "line": 0, "quote": "", "passes": ["start"],
                                      "wrong": f"it stops as soon as it starts (exit {started['code']})",
                                      "sees": started["out"][-400:], "state": "checked",
                                      "why": f"started for {START_SECONDS} s by the review"})
    rank = {"checked": 0, "not checked": 1}
    # a program that stops at once first: nothing else can be tried until it starts
    result["findings"].sort(key=lambda f: (f["passes"] != ["start"], rank.get(f["state"], 2), -len(f["passes"])))
    return result


def save(root: str, result: dict, out: str = "") -> str:
    path = out or os.path.join(root, REVIEWS, time.strftime("%Y%m%d-%H%M%S") + ".json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    os.replace(path + ".tmp", path)
    return path


def handover(findings: list[dict]) -> str:
    """The ticked findings as the coder's next request."""
    items = [f"{f['file']}:{f['line']} — {f['wrong']}" + (f" (the person sees: {f['sees']})" if f.get("sees") else "")
             + (f" [checked: {f['why']}]" if f.get("state") == "checked" else "") for f in findings]
    return ("A review by another model found these. Check each one in the code first (a review can be wrong); fix "
            "the real ones, one cause at a time, and say which you fixed and which weren't real: "
            + " | ".join(items))


def main(argv=None) -> int:
    from cin_minai.inference import reach
    reach.install()
    ap = argparse.ArgumentParser(prog="cinminai-review", description="AICUI's Review: three passes by another model.")
    ap.add_argument("folder")
    ap.add_argument("--out", default="", help="where the result goes (default .cinminai/reviews/<time>.json)")
    a = ap.parse_args(argv)
    root = os.path.abspath(a.folder)
    say = lambda s: print(s, flush=True)
    try:
        backend, plan = reviewer_backend()
        loaded_whole(backend, plan)
    except SystemExit as e:
        say(f"ERROR {e}")
        return 2
    say(f"Reviewer: {plan.get('model', '')} ({plan.get('mode', '')})")
    try:
        result = run(root, lambda messages, **kw: whole(backend, messages, **kw), plan, say)
    except Exception as e:  # the model stopped, the card was full…: said, not a traceback
        say(f"ERROR the review stopped: {e}")
        return 1
    finally:
        backend.unload()
    path = save(root, result, a.out)
    say(f"DONE {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
