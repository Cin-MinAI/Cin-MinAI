#!/usr/bin/env python3
"""Talk to a running relay (M0 spike). Stands in for the daemon.

    relayctl.py [--sock PATH] status | history [N] | screen | send TEXT [--force]

Without --sock: $CINMINAI_SOCK (inside a relayed shell), else the newest relay socket.
"""

from __future__ import annotations

import glob
import json
import os
import socket
import sys


def default_sock() -> str:
    if os.environ.get("CINMINAI_SOCK"):
        return os.environ["CINMINAI_SOCK"]
    base = os.environ.get("XDG_RUNTIME_DIR") or f"/tmp/cinminai-{os.getuid()}"
    socks = sorted(glob.glob(os.path.join(base, "cinminai", "relay-*.sock")), key=os.path.getmtime)
    if not socks:
        sys.exit("relayctl: no running relay")
    return socks[-1]


def request(sock_path: str, req: dict, timeout: float = 5.0) -> dict:
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


def main(argv: list[str]) -> int:
    sock = None
    if argv[:1] == ["--sock"]:
        sock, argv = argv[1], argv[2:]
    if not argv:
        sys.exit(__doc__)
    cmd, args = argv[0], argv[1:]
    if cmd == "history":
        req = {"cmd": "history", "n": int(args[0]) if args else 10}
    elif cmd == "send":
        force = "--force" in args
        req = {"cmd": "send", "text": " ".join(a for a in args if a != "--force"), "force": force}
    else:
        req = {"cmd": cmd}
    reply = request(sock or default_sock(), req)
    if cmd == "screen" and "lines" in reply:
        print("\n".join(reply["lines"]).rstrip())
    else:
        print(json.dumps(reply, indent=2))
    return 0 if reply.get("ok", True) and "error" not in reply else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
