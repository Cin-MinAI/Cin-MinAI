# SPDX-License-Identifier: GPL-3.0-or-later
"""SANDBOXED lane runner (M3, PLAN D1, SPEC §8.2; from the M0 spike, docs/spikes.md "Sandbox": 50/50 checks).

    python3 -P -m cin_minai.sandbox --workspace DIR [--mount-at PATH] [--net pasta|none] [--limits] [--timeout S] -- CMD

Runs CMD under bubblewrap as the user:
  - own session (no TIOCSTI into the user's terminal), no-new-privs, all capabilities dropped
  - own user/pid/ipc/uts/cgroup namespaces; network per --net
  - /usr, /etc, /var, /sys read-only; fresh /tmp, /run, /home; minimal /dev
  - only the workspace is writable; $HOME is an empty tmpfs
  - scrubbed environment: no D-Bus, X11/Wayland, ssh-agent, or daemon variables
  - --limits: inside a systemd --user scope with memory/task/CPU limits

Network modes:
  none   no network at all
  host   TESTS ONLY — the host's network namespace: shares the host's *abstract* unix sockets,
         incl. the X server (on Mint any process of the user may connect: keylogging, input
         injection, screenshots) and everything listening on 127.0.0.1. Never the default.
  pasta  DEFAULT — a private network namespace with user-mode networking (passt): internet works, host
         loopback services and abstract sockets are out of reach
"""

from __future__ import annotations

import argparse
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import uuid

KEEP_ENV = {"LANG", "LC_ALL", "TERM"}
PATH = "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"


SYSTEM_DIRS = ("/usr", "/etc", "/var", "/sys", "/proc", "/dev", "/run", "/boot", "/bin", "/sbin", "/lib")


PASTA_DNS = "169.254.53.53"  # inside the pasta namespace; pasta forwards it to the host's resolver


def resolv_conf(net: str) -> str:
    """/etc/resolv.conf usually links into /run (systemd-resolved) or /mnt/wsl, which the sandbox
    replaces, so the sandbox gets its own copy."""
    if net == "pasta":
        return f"nameserver {PASTA_DNS}\n"
    try:
        with open("/etc/resolv.conf") as f:
            return f.read()
    except OSError:
        return ""


def valid_place(path: str) -> str:
    """A folder the sandbox may write to: never /, the home folder itself, or a system folder."""
    p = os.path.realpath(path)
    if p == "/" or p == os.path.realpath(os.path.expanduser("~")) or p.startswith(
            tuple(d + "/" for d in SYSTEM_DIRS)) or p in SYSTEM_DIRS:
        raise ValueError(f"not a valid workspace: {p}")
    return p


def bwrap_argv(cmd: list[str], workspace: str, net: str, resolv_path: str | None = None,
               mount_at: str | None = None) -> list[str]:
    """mount_at: show the workspace at another path inside the sandbox (M3's "try it first": a copy of the person's
    folder at its real path, so absolute paths in it — a venv's — still work)."""
    src = valid_place(workspace)
    ws = valid_place(mount_at) if mount_at else src
    home = f"/home/{os.environ.get('USER', 'user')}"
    a = ["bwrap", "--new-session", "--die-with-parent", "--unshare-all", "--cap-drop", "ALL",
         "--hostname", "cinminai-sandbox",
         # Same uid/gid as the user, also under pasta (whose own namespace maps the user to 0).
         "--uid", str(os.getuid()), "--gid", str(os.getgid())]
    if net in ("host", "pasta"):
        a.append("--share-net")  # host: the host's namespace; pasta: the one pasta created
    # Merged-/usr system: /bin, /lib, ... are symlinks into /usr.
    a += ["--ro-bind", "/usr", "/usr"]
    for link in ("bin", "sbin", "lib", "lib32", "lib64", "libx32"):
        target = f"/{link}"
        if os.path.islink(target):
            a += ["--symlink", os.readlink(target), target]
        elif os.path.isdir(target):
            a += ["--ro-bind", target, target]
    a += ["--ro-bind", "/etc", "/etc"]
    resolv_target = os.path.realpath("/etc/resolv.conf")  # follow the symlink (see resolv_conf)
    a += ["--ro-bind", "/var", "/var",
          "--ro-bind", "/sys", "/sys",
          "--proc", "/proc",
          "--dev", "/dev",
          "--tmpfs", "/tmp", "--tmpfs", "/var/tmp",
          "--tmpfs", "/run",            # hides /run/user/$UID (session bus, daemon sockets) and the system bus
          "--tmpfs", "/home", "--dir", home,
          "--tmpfs", "/root", "--tmpfs", "/mnt", "--tmpfs", "/media", "--tmpfs", "/srv", "--tmpfs", "/opt"]
    if resolv_path and net != "none":
        # Where the symlink points: inside /run or /mnt, which are empty tmpfs here.
        a += ["--ro-bind", resolv_path, resolv_target]
    # Mounted last, so it shows through the tmpfs layers above (e.g. a workspace under /home).
    a += ["--bind", src, ws,
          "--chdir", ws, "--clearenv",
          "--setenv", "PATH", PATH, "--setenv", "HOME", home,
          "--setenv", "USER", os.environ.get("USER", "user"),
          "--setenv", "CINMINAI_SANDBOX", "1"]
    for k in KEEP_ENV & os.environ.keys():
        a += ["--setenv", k, os.environ[k]]
    return a + ["--", *cmd]



def sandbox_argv(cmd: list[str], workspace: str, net: str = "pasta", limits: bool = False,
                 resolv_path: str | None = None, mount_at: str | None = None) -> list[str]:
    argv = bwrap_argv(cmd, workspace, net, resolv_path, mount_at)
    if net == "pasta":
        # pasta creates a user + network namespace with a tap device and runs bwrap inside it.
        # -T/-U none: no forwarding from the namespace to host ports; --no-map-gw: the gateway
        # address must not lead to the host's loopback; DNS goes only to the host's resolver.
        argv = ["pasta", "--quiet", "--ipv4-only", "--config-net", "-T", "none", "-U", "none", "--no-map-gw",
                "--dns-forward", PASTA_DNS, "--", *argv]
    if limits and shutil.which("systemd-run"):
        unit = f"cinminai-sbx-{uuid.uuid4().hex[:8]}"
        argv = ["systemd-run", "--user", "--scope", "--quiet", f"--unit={unit}",
                "-p", "MemoryMax=2G", "-p", "MemorySwapMax=0", "-p", "TasksMax=256",
                "-p", "CPUWeight=50", "--", *argv]
    return argv


class Sandbox:
    """argv plus the per-run files it needs (the sandbox's resolv.conf); use as a context manager."""

    def __init__(self, cmd: list[str], workspace: str, net: str = "pasta", limits: bool = False,
                 mount_at: str | None = None):
        self.resolv = tempfile.NamedTemporaryFile("w", prefix="cinminai-resolv-", delete=False)
        self.resolv.write(resolv_conf(net))
        self.resolv.close()
        self.argv = sandbox_argv(cmd, workspace, net, limits, self.resolv.name, mount_at)

    def __enter__(self) -> list[str]:
        return self.argv

    def __exit__(self, *exc) -> None:
        os.unlink(self.resolv.name)


def best_net() -> str:
    """pasta (a private network) when passt is installed; otherwise no network at all — never the host's."""
    return "pasta" if shutil.which("pasta") else "none"


def run(cmd: list[str], workspace: str, net: str = "pasta", limits: bool = False,
        timeout: float = 60, stdin=subprocess.DEVNULL, mount_at: str | None = None) -> subprocess.CompletedProcess:
    """Run cmd in the sandbox; on timeout the whole sandbox (every process in it) is killed."""
    with Sandbox(cmd, workspace, net, limits, mount_at) as argv:
        p = subprocess.Popen(argv, stdin=stdin, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             text=True, start_new_session=True)
        try:
            out, err = p.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(p.pid, signal.SIGKILL)
            out, err = p.communicate()
            return subprocess.CompletedProcess(argv, -9, out, err + "\n[timeout: sandbox killed]")
    return subprocess.CompletedProcess(argv, p.returncode, out, err)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--workspace", required=True)
    ap.add_argument("--mount-at")
    ap.add_argument("--net", choices=["pasta", "none", "host"], default="pasta")
    ap.add_argument("--limits", action="store_true")
    ap.add_argument("--timeout", type=float, default=0)
    ap.add_argument("cmd", nargs=argparse.REMAINDER)
    args = ap.parse_args()
    cmd = args.cmd[1:] if args.cmd[:1] == ["--"] else args.cmd
    if not cmd:
        ap.error("no command")
    if args.timeout:
        r = run(cmd, args.workspace, args.net, args.limits, args.timeout, stdin=None, mount_at=args.mount_at)
        sys.stdout.write(r.stdout)
        sys.stderr.write(r.stderr)
        return r.returncode
    with Sandbox(cmd, args.workspace, args.net, args.limits, args.mount_at) as argv:
        return subprocess.call(argv)


if __name__ == "__main__":
    sys.exit(main())
