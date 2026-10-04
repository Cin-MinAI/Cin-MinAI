# SPDX-License-Identifier: GPL-3.0-or-later
"""What the assistant sees of the terminals the person shares (M3, SPEC §6, §11.4, §11.5, §12.3; D77).

Not a tool the model picks: the state lives outside the model and only what's relevant is handed to it (§11.5).
When a message is about the terminal ("why didn't this work?", "what does this error mean?"), the newest shared
terminal's last commands go in front of it: the command line, where it ran, how it ended, and the lines of its
output that matter (§11.4: never a 50,000-line log). Credentials are redacted first (§12.3); commands typed at a
password prompt or hidden with a leading space were never captured (the relay).
"""

from __future__ import annotations

import os
import re
import shlex
import time

RECENT = 15 * 60          # a command older than this isn't "this"
MAX_COMMANDS = 3          # the last few, newest last
MAX_OUTPUT = 1500         # characters of output per command after filtering
SHORT_LINES = 30          # output this short goes in whole

# --- when is a message about the terminal? -------------------------------------------------------------------------
# Words that name it, in the six languages (D25); and short questions that point at something just seen.
NAMES = re.compile(r"\b(terminal|command|commande|comando|befehl|kommando|bash|shell|prompt|output|error|errors?|"
                   r"erreur|fehler|erro|traceback|exit code|stack trace)\b|ターミナル|端末|コマンド|エラー", re.I)
POINTING = re.compile(r"\b(this|that|it|esto|eso|isso|isto|ça|cela|das|dies)\b|これ|それ|この|その", re.I)
TROUBLE = re.compile(r"\b(why|what happened|what does .* mean|didn'?t work|doesn'?t work|not working|failed|fails|"
                     r"wrong|broke|broken|fix|help|por ?qué|no funciona|falló|por que|não funciona|falhou|"
                     r"pourquoi|marche pas|échoué|warum|funktioniert nicht|geht nicht|fehlgeschlagen)\b|なぜ|動かない|失敗", re.I)


def about_terminal(text: str, commands: list[dict], now: float | None = None) -> bool:
    """Is this message about what just happened in the terminal? It names the terminal or an error; or it's a short
    question pointing at something ("why didn't this work?") right after a command failed."""
    if not commands:
        return False
    now = now or time.time()
    last = commands[-1]
    recent = now - (last.get("end") or last.get("start") or 0) <= RECENT
    if not recent:
        return False
    if NAMES.search(text):
        return True
    failed = last.get("exit") not in (0, None)
    short = len(text) <= 160
    return failed and short and bool(TROUBLE.search(text) or POINTING.search(text))


# --- redaction (§12.3) ---------------------------------------------------------------------------------------------
_REDACT = [
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?(-----END [A-Z ]*PRIVATE KEY-----|$)"), "[private key removed]"),
    (re.compile(r"(?i)\b((?:password|passwd|pwd|token|secret|api[_-]?key|access[_-]?key)\s*[=:]\s*)(\"[^\"]*\"|'[^']*'|\S+)"),
     r"\1[removed]"),
    (re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9._~+/=-]{12,}"), r"\1 [removed]"),
    (re.compile(r"\b(AKIA|ASIA)[A-Z0-9]{16}\b"), "[cloud key removed]"),
    (re.compile(r"\b(ghp_|gho_|github_pat_|hf_|sk-|xox[bp]-)[A-Za-z0-9_-]{16,}"), "[token removed]"),
    (re.compile(r"(\b[a-z][a-z0-9+.-]*://)[^/\s:@]+:[^/\s@]+@"), r"\1[removed]@"),
]


def redact(text: str) -> str:
    for pat, repl in _REDACT:
        text = pat.sub(repl, text)
    return text


# --- the lines that matter (§11.4) ---------------------------------------------------------------------------------
ERROR = re.compile(r"(?i)\b(error|fatal|failed|failure|exception|panic|segmentation fault|core dumped|denied|"
                   r"not found|no such file|cannot|can't|could not|couldn't|undefined reference|unresolved|"
                   r"refused|timed out|E:|ERR!)")
WARNING = re.compile(r"(?i)\bwarn(ing)?\b|\bW:")
FILE_LINE = re.compile(r"[\w./-]+\.\w+:\d+(:\d+)?")
SUMMARY = re.compile(r"(?i)\b\d+ (passed|failed|errors?|warnings?|skipped)\b|^(FAILED|OK|PASSED)\b|tests? (ran|run)")


def extract(output: str, limit: int = MAX_OUTPUT) -> str:
    """Short output whole; long output reduced to what a person debugging it would look at: the first and last error
    and the warnings next to them, file:line references, the end of the last traceback, a test summary, and the last
    lines. Left-out stretches are marked."""
    lines = output.splitlines()
    if len(lines) <= SHORT_LINES and len(output) <= limit:
        return output.strip("\n")
    keep: set[int] = set()
    errors = [i for i, l in enumerate(lines) if ERROR.search(l)]
    for i in errors[:1] + errors[-1:]:
        keep.update(range(max(0, i - 1), min(len(lines), i + 3)))
    for i in errors:
        if FILE_LINE.search(lines[i]):
            keep.add(i)
    for i, l in enumerate(lines):
        if (WARNING.search(l) and any(abs(i - e) <= 2 for e in errors)) or SUMMARY.search(l):
            keep.add(i)
    tb = max((i for i, l in enumerate(lines) if l.startswith("Traceback")), default=None)
    if tb is not None:
        keep.update(range(max(tb, len(lines) - 8), len(lines)))
    keep.update(range(max(0, len(lines) - 5), len(lines)))
    out, prev = [], -1
    for i in sorted(keep):
        if i != prev + 1:
            out.append(f"… ({i - prev - 1} lines left out)" if prev >= 0 else f"… ({i} lines left out)")
        out.append(lines[i])
        prev = i
    text = "\n".join(out)
    if len(text) > limit:  # still too long: keep the start (first error) and the end
        text = text[: limit // 3] + "\n…\n" + text[-(limit * 2 // 3):]
    return text


# --- what the model is shown ---------------------------------------------------------------------------------------
EXIT_WORDS = {0: "worked", 1: "failed", 2: "failed (wrong usage)", 126: "couldn't run (not executable)",
              127: "failed: command not found", 130: "stopped with Ctrl+C"}


def ended(code) -> str:
    if code is None:
        return "still running, or its end wasn't seen"
    return EXIT_WORDS.get(code, f"failed (exit code {code})" if code else "worked")


def home_short(path: str | None) -> str:
    if not path:
        return "?"
    home = os.path.expanduser("~")
    return "~" + path[len(home):] if path == home or path.startswith(home + "/") else path


def context(commands: list[dict]) -> str:
    """The block put in front of the person's message: the last commands, newest last."""
    # "look it up first": measured 2026-10-04, the guide answered `cd Documents/Taxes 2025` from memory with a wrong
    # fix; the help has a card for every classic terminal error (training/kb/terminal.py)
    parts = ["[The person's shared terminal: what they ran, newest last. You can't run anything in it; suggest "
             "commands for them to run. Look the error up in the built-in help before answering; checking the "
             "computer won't show a terminal error.]"]
    for c in commands[-MAX_COMMANDS:]:
        if not c.get("cmd"):
            continue  # hidden (leading space): never shown
        parts.append(f"$ {redact(c['cmd'])}    (in {home_short(c.get('cwd'))}: {ended(c.get('exit'))})")
        out = c.get("output") or ""
        if c.get("fullscreen"):
            out = "(a full-screen program; its screen isn't kept)"
        elif c.get("secret") and out:
            out = out.strip("\n")  # what came after the password prompt; the password itself was never captured
        out = extract(redact(out))
        if c.get("truncated"):
            out += "\n(part of this output was too fast to keep)"
        if out.strip():
            parts.append(out)
    return "\n".join(parts)


def lookup_hint(commands: list[dict], limit: int = 200) -> str:
    """The failed command and its first error lines, added to the guide's help lookup (the daemon knows them; the
    model's own query is often generic — measured on the test SSD 2026-10-04: `pip install tinkter` looked up "how
    to install Python packages in Linux Mint" and missed the tkinter card)."""
    shown = [c for c in commands if c.get("cmd")]
    if not shown:
        return ""
    last = next((c for c in reversed(shown) if c.get("exit") not in (0, None)), shown[-1])
    lines = [l.strip() for l in (last.get("output") or "").splitlines() if l.strip()]
    errors = [l for l in lines if ERROR.search(l)] or lines[-1:]
    return redact(f"{last['cmd']} {' '.join(errors[:2])}")[:limit]


def latest(n: int = MAX_COMMANDS) -> list[dict]:
    """The newest shared terminal's last commands ([] when nothing is shared or nothing has run). Never raises:
    reading the terminals must never take an answer down."""
    try:
        return _latest(n)
    except Exception:
        return []


LAST = {"sock": None}  # the terminal the assistant last read: "To terminal" sends there


def _latest(n: int) -> list[dict]:
    try:
        from cin_minai.shell import ctl
    except ImportError:
        return []  # cinminai-shell isn't installed
    best, best_t, best_sock = [], 0.0, None
    for t in ctl.terminals():
        if not t.get("ai"):
            continue  # `ai off` in that terminal
        try:
            cmds = ctl.request(t["sock"], {"cmd": "history", "n": n}, timeout=1.0).get("commands", [])
        except (OSError, ValueError):
            continue
        when = max((c.get("end") or c.get("start") or 0 for c in cmds), default=0)
        if when > best_t:
            best, best_t, best_sock = cmds, when, t["sock"]
    LAST["sock"] = best_sock
    return best


# --- try it first (M3 slice 4): the command on a copy of the terminal's folder, in the sandbox -----------------------
TRY_MAX_BYTES = 500 << 20    # a bigger folder isn't copied: say so instead
TRY_TIMEOUT = 180


def _active_venv(sock: str, cwd: str) -> str | None:
    """The venv activated in that terminal, read from its prompt: "(.venv) user@host:…$" (activate exports
    VIRTUAL_ENV in the shell, where /proc can't see it; the prompt shows it)."""
    from cin_minai.shell import ctl
    lines = [l for l in ctl.request(sock, {"cmd": "screen"}, timeout=1.0).get("lines", []) if l.strip()]
    m = re.match(r"\(([^)\s]+)\) ", lines[-1].lstrip("◆ ")) if lines else None
    if m:
        venv = os.path.join(cwd, m.group(1))
        if os.path.isfile(os.path.join(venv, "bin", "activate")):
            return venv
    return None


def _snapshot(root: str) -> dict:
    out = {}
    for dirpath, dirs, files in os.walk(root):
        for f in files:
            p = os.path.join(dirpath, f)
            try:
                st = os.lstat(p)
            except OSError:
                continue
            out[os.path.relpath(p, root)] = (st.st_size, int(st.st_mtime))
    return out


def try_first(command: str, timeout: int = TRY_TIMEOUT) -> dict:
    """Run a command the assistant suggested on a throwaway copy of the terminal's folder, in the sandbox (PLAN D1,
    SPEC §8.2: no root, no D-Bus, no X server, only a private network), and say what happened. The copy is mounted at
    the folder's real path, so absolute paths in it (a venv's) still work; the person's folder isn't touched."""
    import shutil
    import tempfile
    try:
        from cin_minai import sandbox
    except ImportError:
        return {"ok": False, "error": "The sandbox isn't installed (the cinminai-sandbox package)."}
    started = time.time()
    if re.match(r"\s*(sudo|pkexec|su)\b", command):
        return {"ok": False, "error": "It needs your password, so it can't be tried in the sandbox: it would change "
                                      "the system itself. Run it in the terminal if it's what you want."}
    try:
        from cin_minai.shell import ctl
        sock = LAST["sock"] if LAST["sock"] and os.path.exists(LAST["sock"]) else next(iter(ctl.sockets()), None)
        cwd = ctl.request(sock, {"cmd": "status"}, timeout=1.0).get("cwd") if sock else None
    except Exception:
        sock = cwd = None
    if not cwd or not os.path.isdir(cwd):
        return {"ok": False, "error": "There's no shared terminal to take the folder from."}
    if os.path.realpath(cwd) == os.path.realpath(os.path.expanduser("~")):
        return {"ok": False, "error": "Your terminal is in your home folder; trying a command works in a project "
                                      "folder (cd into it first)."}
    try:
        sandbox.valid_place(cwd)
    except ValueError:
        return {"ok": False, "error": "That folder can't be tried in the sandbox."}
    before = _snapshot(cwd)
    size = sum(s for s, _ in before.values())
    if size > TRY_MAX_BYTES:
        return {"ok": False, "error": f"The folder is too big to copy for a try ({size >> 20} MB)."}
    venv = None
    try:
        venv = _active_venv(sock, cwd)
    except Exception:
        pass
    work = tempfile.mkdtemp(prefix="cinminai-try-")
    try:
        copy = os.path.join(work, "folder")
        shutil.copytree(cwd, copy, symlinks=True)
        prefix = f"export VIRTUAL_ENV={shlex.quote(venv)} PATH={shlex.quote(venv + '/bin')}:$PATH; " if venv else ""
        net = sandbox.best_net()
        r = sandbox.run(["bash", "-c", prefix + command], copy, net=net, limits=True, timeout=timeout, mount_at=cwd)
        after = _snapshot(copy)
        made = sorted(p for p in after if p not in before)
        changed = sorted(p for p in after if p in before and after[p] != before[p])
        gone = sorted(p for p in before if p not in after)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    # pasta's own note when the host's resolver is a local stub (systemd-resolved); names still resolve (checked)
    noise = re.compile(r"^Couldn't get any nameserver address$", re.M)
    out = extract(redact(noise.sub("", (r.stdout or "") + (r.stderr or ""))).strip())
    return {"ok": True, "exit": r.returncode, "output": out, "net": net, "venv": bool(venv), "folder": cwd,
            "timed_out": r.returncode == -9, "made": _summary(made), "changed": _summary(changed),
            "deleted": _summary(gone), "seconds": round(time.time() - started, 1)}


def _summary(paths: list[str], limit: int = 6) -> dict:
    """{"count", "top": the first few top-level names} — a new .venv is one line, not 1,500 files."""
    tops = []
    for p in paths:
        t = p.split(os.sep)[0]
        if t not in tops:
            tops.append(t)
    return {"count": len(paths), "top": tops[:limit]}


def send(text: str) -> dict:
    """Put a command at the prompt of the terminal the assistant last read, as if typed — never with Enter (SPEC §6.1:
    the person runs it). The relay refuses at a password prompt, while a program runs, or with `ai off`."""
    try:
        from cin_minai.shell import ctl
        sock = LAST["sock"] if LAST["sock"] and os.path.exists(LAST["sock"]) else next(iter(ctl.sockets()), None)
        if not sock:
            return {"ok": False, "error": "No shared terminal is open."}
        return ctl.request(sock, {"cmd": "send", "text": text})
    except Exception as e:
        return {"ok": False, "error": f"Couldn't reach the terminal ({type(e).__name__})."}
