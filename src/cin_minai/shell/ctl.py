# SPDX-License-Identifier: GPL-3.0-or-later
"""Talk to the shared terminals, and turn terminal sharing on or off (M3, D77).

Every relayed terminal has a control socket, $XDG_RUNTIME_DIR/cinminai/relay-<pid>.sock (user-only); requests are
one JSON line each way (analyzer.py lists them). Sharing is a marked line in the person's ~/.bashrc that sources
start.bash: added when they say yes, removed when they turn it off. Terminals already open keep their state until
they're closed; `ai off` in a terminal stops that one at once.

    python3 -P -m cin_minai.shell.ctl list | status | history [N] | screen | send TEXT | on | off | state
"""

from __future__ import annotations

import glob
import json
import os
import socket
import sys

START = "/usr/share/cinminai/shell/start.bash"
MARK = "# Cin-MinAI terminal sharing (turn off: Cin-MinAI settings, or delete these two lines)"
LINE = f'[ -r {START} ] && . {START}'


def runtime_dir() -> str:
    base = os.environ.get("XDG_RUNTIME_DIR") or f"/tmp/cinminai-{getattr(os, 'getuid', lambda: 0)()}"
    return os.path.join(base, "cinminai")


def sockets() -> list[str]:
    """Control sockets of the open, shared terminals, newest first."""
    return sorted(glob.glob(os.path.join(runtime_dir(), "relay-*.sock")), key=os.path.getmtime, reverse=True)


def request(sock_path: str, req: dict, timeout: float = 3.0) -> dict:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        s.connect(sock_path)
        s.sendall(json.dumps(req).encode() + b"\n")
        data = b""
        while not data.endswith(b"\n"):
            chunk = s.recv(1 << 20)
            if not chunk:
                break
            data += chunk
    return json.loads(data)


def terminals() -> list[dict]:
    """status of every shared terminal that answers; a socket left by a crashed analyzer is removed."""
    out = []
    for path in sockets():
        try:
            st = request(path, {"cmd": "status"}, timeout=1.0)
        except (OSError, ValueError):
            try:
                os.unlink(path)  # nobody listens: stale
            except OSError:
                pass
            continue
        out.append(dict(st, sock=path))
    return out


# --- sharing on/off: the line in ~/.bashrc -----------------------------------------------------------------------
def bashrc(home: str | None = None) -> str:
    return os.path.join(home or os.path.expanduser("~"), ".bashrc")


def enabled(home: str | None = None) -> bool:
    try:
        with open(bashrc(home), encoding="utf-8", errors="replace") as f:
            return any(l.strip() == LINE for l in f)
    except OSError:
        return False


def enable(home: str | None = None) -> bool:
    """Add the sharing line at the top of ~/.bashrc (before anything that might stop for non-interactive shells),
    once. Returns True if it changed the file. New terminals are shared from now on."""
    path = bashrc(home)
    if enabled(home):
        return False
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            old = f.read()
    except FileNotFoundError:
        old = ""
    _write(path, f"{MARK}\n{LINE}\n{old}")
    return True


def disable(home: str | None = None) -> bool:
    """Remove the sharing line (and its comment); everything else in ~/.bashrc stays as it was."""
    path = bashrc(home)
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = f.read().split("\n")
    except FileNotFoundError:
        return False
    kept = [l for l in lines if l.strip() not in (LINE, MARK)]
    if kept == lines:
        return False
    _write(path, "\n".join(kept))
    return True


def _write(path: str, text: str) -> None:
    tmp = path + ".cinminai-tmp"
    mode = os.stat(path).st_mode & 0o777 if os.path.exists(path) else 0o644
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.chmod(tmp, mode)
    os.replace(tmp, path)


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__.strip().splitlines()[-1].strip())
        return 2
    cmd, args = argv[0], argv[1:]
    if cmd == "on":
        print("terminal sharing: on for new terminals" + ("" if enable() else " (it already was)"))
        return 0
    if cmd == "off":
        print("terminal sharing: off for new terminals" + ("" if disable() else " (it already was)"))
        return 0
    if cmd == "state":
        print("on" if enabled() else "off")
        return 0
    if cmd == "list":
        for t in terminals():
            print(f"{t['tty']}  {t['state']:8}  {'shared' if t['ai'] else 'private'}  {t.get('cwd') or ''}")
        return 0
    socks = sockets()
    if not socks:
        print("no shared terminal is open", file=sys.stderr)
        return 1
    req = {"cmd": cmd}
    if cmd == "history":
        req["n"] = int(args[0]) if args else 10
    elif cmd == "send":
        req["text"] = " ".join(args)
    reply = request(socks[0], req)
    print("\n".join(reply["lines"]).rstrip() if cmd == "screen" and "lines" in reply else json.dumps(reply, indent=2))
    return 0 if reply.get("ok", True) and "error" not in reply else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
