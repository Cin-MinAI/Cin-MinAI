#!/usr/bin/env python3
"""Sandbox spike checks (M0): SPEC §16.1 against sandbox.py, plus indirect paths and function.

    python3 check.py [--stress]      (--stress: fork bomb + memory hog under --limits; test boxes only)

Every probe runs *inside* the sandbox as a small Python/shell snippet. Nothing outside the sandbox
is modified except a temporary workspace and short-lived test listeners, all removed at the end.
"""

from __future__ import annotations

import fcntl
import glob
import os
import pty
import shutil
import socket
import subprocess
import sys
import tempfile
import termios
import textwrap
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import sandbox  # noqa: E402

STRESS = "--stress" in sys.argv
MODES = ["host", "pasta"] if shutil.which("pasta") else ["host"]
WS = tempfile.mkdtemp(prefix="cinminai-ws-")
results: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""), flush=True)


def py(code: str, net: str = "host", timeout: float = 30, **kw) -> subprocess.CompletedProcess:
    return sandbox.run(["python3", "-c", textwrap.dedent(code)], WS, net=net, timeout=timeout, **kw)


def sh(cmd: str, net: str = "host", timeout: float = 30, **kw) -> subprocess.CompletedProcess:
    return sandbox.run(["sh", "-c", cmd], WS, net=net, timeout=timeout, **kw)


def brief(r: subprocess.CompletedProcess) -> str:
    return (r.stdout + r.stderr).strip().replace("\n", " | ")[:140]


# --- host-side test fixtures (all temporary) ----------------------------------------------------

class Listener:
    """A TCP listener on host loopback and a unix socket in $XDG_RUNTIME_DIR (where the relay and
    daemon sockets live), to see whether the sandbox can reach either."""

    def __init__(self) -> None:
        self.tcp = socket.socket()
        self.tcp.bind(("127.0.0.1", 0))
        self.tcp.listen(8)
        self.port = self.tcp.getsockname()[1]
        run_dir = os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir()
        self.unix_path = os.path.join(run_dir, f"cinminai-sbxtest-{os.getpid()}.sock")
        self.unix = socket.socket(socket.AF_UNIX)
        self.unix.bind(self.unix_path)
        self.unix.listen(8)
        self.abstract_name = f"\0cinminai-sbxtest-{os.getpid()}"
        self.abstract = socket.socket(socket.AF_UNIX)
        self.abstract.bind(self.abstract_name)
        self.abstract.listen(8)
        for s in (self.tcp, self.unix, self.abstract):
            threading.Thread(target=self.accept, args=(s,), daemon=True).start()

    @staticmethod
    def accept(s: socket.socket) -> None:
        while True:
            try:
                c, _ = s.accept()
                c.close()
            except OSError:
                return

    def close(self) -> None:
        for s in (self.tcp, self.unix, self.abstract):
            s.close()
        os.unlink(self.unix_path)


CONNECT = """
import socket, sys
def tcp(port):
    try: socket.create_connection(("127.0.0.1", port), timeout=2).close(); return "reachable"
    except OSError as e: return f"blocked ({e.__class__.__name__})"
def unix(path):
    s = socket.socket(socket.AF_UNIX)
    try: s.settimeout(2); s.connect(path); return "reachable"
    except OSError as e: return f"blocked ({e.__class__.__name__})"
"""

X11_PROBE = """
import socket, struct, re
names = [l.split()[-1] for l in open("/proc/net/unix").read().splitlines()[1:] if l.split()[-1].startswith("@")]
print("abstract sockets visible:", len(names))
x = [n for n in names if ".X11-unix" in n]
print("X11 abstract:", x or "none")
for n in x[:1]:
    s = socket.socket(socket.AF_UNIX)
    try:
        s.settimeout(2); s.connect("\\0" + n[1:])
        s.sendall(b"l\\0" + struct.pack("<HHHH", 11, 0, 0, 0) + b"\\0\\0")
        r = s.recv(8)
        print("X11 handshake:", {0: "refused", 1: "ACCEPTED", 2: "needs auth"}.get(r[0], r[:1]))
    except OSError as e:
        print("X11 connect blocked:", e)
"""


def main() -> int:
    # Things the sandbox must not see, planted in the environment it's started from.
    global fake_env
    fake_env = {"DBUS_SESSION_BUS_ADDRESS": os.environ.get("DBUS_SESSION_BUS_ADDRESS", "unix:path=/run/user/1000/bus"),
                "DISPLAY": ":0", "WAYLAND_DISPLAY": "wayland-0", "XAUTHORITY": "/home/x/.Xauthority",
                "SSH_AUTH_SOCK": "/tmp/ssh-x/agent.1", "CINMINAI_SOCK": "/run/user/1000/cinminai/x.sock"}
    os.environ.update(fake_env)
    lis = Listener()
    try:
        security(lis)
        indirect(lis)
        function()
        lifecycle()
        if STRESS:
            stress()
    finally:
        lis.close()
        shutil.rmtree(WS, ignore_errors=True)
    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks pass  (network modes tested: {', '.join(MODES)})")
    return 1 if failed else 0


# --- SPEC §16.1 --------------------------------------------------------------------------------

def security(lis: Listener) -> None:
    print("== SPEC §16.1: the normal AI path cannot …")
    for net in MODES:
        tag = f"[{net}]"
        r = sh("sudo -n true; echo rc=$?; pkexec true 2>&1; echo rc=$?; su -c true root </dev/null 2>&1; echo rc=$?", net)
        rcs = [l for l in r.stdout.split() if l.startswith("rc=")]
        record(f"{tag} acquire sudo / pkexec / su", rcs == ["rc=1"] * 3 or all(x != "rc=0" for x in rcs), brief(r))
        r = py("""
            import os
            st = dict(l.split(":\\t") for l in open("/proc/self/status").read().splitlines() if ":\\t" in l)
            try: os.setuid(0); print("setuid(0) WORKED")
            except OSError as e: print("setuid(0) denied:", e.strerror)  # EINVAL: root is not even mapped
            print("NoNewPrivs", st["NoNewPrivs"], "CapEff", st["CapEff"], "CapBnd", st["CapBnd"])
        """, net)
        record(f"{tag} no privileges at all (no_new_privs, empty capability sets)",
               "denied" in r.stdout and "NoNewPrivs 1" in r.stdout and "CapEff 0000000000000000" in r.stdout, brief(r))

        bus = fake_env["DBUS_SESSION_BUS_ADDRESS"].split("path=")[-1].split(",")[0]
        r = py(CONNECT + f"""
print("system bus", unix("/run/dbus/system_bus_socket"))
print("session bus", unix({bus!r}))
""", net)
        record(f"{tag} reach the system or session D-Bus", r.stdout.count("blocked") == 2, brief(r))
        r = sh("timeout 10 systemctl restart cron 2>&1; echo rc=$?; timeout 10 busctl --user list 2>&1 | head -1; "
               "timeout 10 gdbus call --session --dest org.cinminai.Assistant1 --object-path /org/cinminai/Assistant1 "
               "--method org.cinminai.Assistant1.SetState idle 2>&1 | head -1", net)
        record(f"{tag} systemctl / busctl / gdbus fail fast (no polkit prompt, no daemon)",
               "rc=0" not in r.stdout and "rc=124" not in r.stdout, brief(r))
        r = py(CONNECT + f"print('daemon/relay socket dir', unix({lis.unix_path!r}))", net)
        record(f"{tag} talk to the daemon's approval API (unix sockets in $XDG_RUNTIME_DIR)",
               "blocked" in r.stdout, brief(r))
        r = sh("for f in /usr/share/polkit-1/actions/x.policy /etc/polkit-1/rules.d/00-x.rules "
               "/usr/lib/cinminai/admin-x; do (echo x > $f) 2>&1 | head -1; done", net)
        record(f"{tag} rewrite the admin mechanism or polkit policy",
               sum(r.stdout.count(w) for w in ("Read-only", "ermission", "No such", "nonexistent")) >= 3, brief(r))
        r = py("""
            import glob, os
            blk = [d for d in glob.glob("/dev/*") if os.path.exists(d) and __import__("stat").S_ISBLK(os.stat(d).st_mode)]
            print("block devices:", blk or "none")
            for p in ("/dev/sda", "/dev/nvme0n1", "/dev/mmcblk0"):
                # No O_CREAT: /dev here is a small tmpfs, so a plain open() would just make a file.
                try: os.close(os.open(p, os.O_WRONLY)); print(p, "OPENED")
                except OSError as e: print(p, e.__class__.__name__)
        """, net)
        record(f"{tag} write raw block devices", "OPENED" not in r.stdout and "none" in r.stdout, brief(r))
        r = sh("ls /dev/ttyUSB* /dev/ttyACM* /dev/ttyS* /dev/hidraw* /dev/bus/usb /dev/gpiochip* 2>&1 | head -3", net)
        record(f"{tag} open serial ports or debug probes (none present in /dev)",
               "No such file" in r.stdout and "/dev/tty" not in r.stdout.replace("cannot access '/dev/tty", ""), brief(r))
        r = py("""
            import glob
            targets = glob.glob("/sys/firmware/efi/efivars/*")[:1] + ["/dev/mtd0", "/dev/mem", "/dev/port", "/dev/nvram"]
            for p in targets:
                try: open(p, "r+b"); print(p, "OPENED FOR WRITE")
                except OSError as e: print(p.split("/")[-1][:20], e.__class__.__name__)
        """, net)
        record(f"{tag} flash firmware (efivars read-only; mtd, mem, port absent)", "OPENED" not in r.stdout, brief(r))
        r = py("""
            import glob
            cfg = glob.glob("/sys/bus/pci/devices/*/config")
            print("pci devices:", len(cfg))
            for p in cfg[:3]:
                try: open(p, "r+b"); print(p, "OPENED FOR WRITE")
                except OSError as e: print(e.__class__.__name__)
        """, net)
        record(f"{tag} write PCI configuration", "OPENED" not in r.stdout, brief(r))
        r = sh("for f in /etc/hosts /etc/fstab /usr/bin/cinminai-x /boot/x; do (echo x >> $f) 2>&1 | head -1; done", net)
        record(f"{tag} modify protected system files", "Read-only" in r.stdout and r.returncode == 0, brief(r))
        home = os.path.expanduser("~")
        present = [p for p in (".bashrc", ".ssh", ".config", ".local") if os.path.exists(os.path.join(home, p))]
        r = sh(f"ls -A {home} 2>&1; ls /mnt/c 2>&1 | head -1", net)
        record(f"{tag} read $HOME outside the workspace", not any(p in r.stdout.split() for p in present),
               f"host has {present}; sandbox sees: {brief(r) or 'empty'}")


# --- indirect paths ----------------------------------------------------------------------------

def indirect(lis: Listener) -> None:
    print("== indirect paths")
    for net in MODES + ["none"]:
        tag = f"[{net}]"
        r = py(X11_PROBE, net)
        accepted = "ACCEPTED" in r.stdout
        ok = not accepted if net != "host" else True
        record(f"{tag} X server via abstract socket", ok and (not accepted or net == "host"),
               ("FINDING: sandbox can drive the X server (keystrokes, screen) — " if accepted else "") + brief(r))
        r = py(CONNECT + f"""
print("host loopback tcp", tcp({lis.port}))
print("host abstract unix", unix({lis.abstract_name!r}))
""", net)
        exposed = r.stdout.count("reachable")
        record(f"{tag} host loopback services and abstract sockets",
               exposed == 0 or net == "host",
               ("FINDING (host mode shares them) — " if exposed else "") + brief(r))
    for net in MODES:
        tag = f"[{net}]"
        leaked = [k for k in ("DBUS_SESSION_BUS_ADDRESS", "DISPLAY", "WAYLAND_DISPLAY", "XAUTHORITY",
                              "SSH_AUTH_SOCK", "CINMINAI_SOCK")]
        r = py(f"import os; print([k for k in {leaked!r} if k in os.environ])", net)
        record(f"{tag} environment scrubbed (bus, display, ssh-agent, daemon vars)", r.stdout.strip() == "[]", brief(r))
        r = py(f"""
            import os
            pids = [d for d in os.listdir("/proc") if d.isdigit()]
            try: os.kill({os.getpid()}, 0); print("host pid visible")
            except ProcessLookupError: print("host pid invisible")
            print("processes visible:", len(pids))
        """, net)
        record(f"{tag} host processes invisible (pid namespace)", "invisible" in r.stdout, brief(r))
        # TIOCSTI: push keystrokes into the controlling terminal of whoever launched the sandbox.
        master, slave = pty.openpty()
        r = py("""
            import fcntl, termios
            try: fcntl.ioctl(0, termios.TIOCSTI, b"x"); print("TIOCSTI WORKED")
            except OSError as e: print("TIOCSTI blocked:", e)
        """, net, stdin=slave)
        os.close(slave)
        os.close(master)
        record(f"{tag} inject keystrokes into the user's terminal (TIOCSTI)", "blocked" in r.stdout, brief(r))


# --- function ----------------------------------------------------------------------------------

def function() -> None:
    print("== normal work still works")
    for net in MODES:
        tag = f"[{net}]"
        r = sh("echo hi > f.txt && cat f.txt && mkdir -p d/e && touch d/e/g && ls d/e", net)
        st = os.stat(os.path.join(WS, "f.txt"))
        record(f"{tag} read/write in the workspace; files owned by the user on the host",
               "hi" in r.stdout and st.st_uid == os.getuid(), brief(r))
        r = py("import urllib.request as u; print(u.urlopen('https://deb.debian.org', timeout=15).status)", net)
        record(f"{tag} network for builds (https)", r.stdout.strip() == "200", brief(r))
    r = py("import urllib.request as u; print(u.urlopen('https://deb.debian.org', timeout=5).status)", "none")
    record("[none] network off when a workspace turns it off", r.returncode != 0, brief(r)[-80:])
    r = sh("git init -q r && cd r && echo x > a && git add a && "
           "git -c user.email=a@b -c user.name=t commit -qm t && git log --oneline | wc -l")
    record("git init / commit / log", r.stdout.strip() == "1", brief(r))
    if shutil.which("cc"):
        r = sh("printf '#include <stdio.h>\\nint main(){puts(\"built\");}' > h.c && cc h.c -o h && ./h")
        record("C build and run", "built" in r.stdout, brief(r))
    r = sh("head -1 /proc/cpuinfo; ls /sys/class/net | head -3; cat /sys/class/dmi/id/board_name 2>/dev/null; "
           "dpkg -l | grep -c ^ii")
    record("read /proc, /sys, dpkg database", r.returncode == 0 and r.stdout.strip().split()[-1].isdigit(), brief(r))
    for tool, args in (("lspci", ""), ("lsusb", ""), ("lsblk", "-d -o NAME,SIZE")):
        if shutil.which(tool):
            r = sh(f"{tool} {args} 2>&1 | head -3")
            record(f"(info) {tool}", True, brief(r) or "(no output)")


# --- lifecycle and limits ----------------------------------------------------------------------

def lifecycle() -> None:
    print("== lifecycle")
    t0 = time.monotonic()
    r = sh("sleep 3137 & sleep 3138", timeout=2)
    left = subprocess.run(["pgrep", "-f", "sleep 313[78]"], capture_output=True, text=True).stdout.split()
    record("timeout kills the whole sandbox, background jobs included",
           r.returncode == -9 and not left and time.monotonic() - t0 < 5, f"leftover pids: {left}")
    r = sandbox.run(["true"], WS, limits=True)
    record("(info) resource limits available (systemd --user scope)", True,
           "yes" if r.returncode == 0 else f"no: {brief(r)}")
    try:
        sandbox.bwrap_argv(["true"], os.path.expanduser("~"), "none")
        record("refuses $HOME or system dirs as a workspace", False)
    except ValueError as e:
        record("refuses $HOME or system dirs as a workspace", True, str(e))


def stress() -> None:
    print("== stress (limits)")
    r = sandbox.run(["python3", "-c", textwrap.dedent("""
        import os, time
        n = 0
        try:
            while n < 5000:
                if os.fork() == 0: time.sleep(20); os._exit(0)
                n += 1
        except OSError as e: print("fork stopped at", n, e.__class__.__name__, flush=True)
        os._exit(0)
    """)], WS, limits=True, timeout=40)
    record("fork bomb stopped by TasksMax", "stopped at" in r.stdout, brief(r))
    r = sandbox.run(["python3", "-c", "b = bytearray(3 * 1024**3); print('allocated 3 GiB')"],
                    WS, limits=True, timeout=60)
    record("memory hog killed at MemoryMax (2 GiB)", "allocated" not in r.stdout, f"rc={r.returncode} {brief(r)[:80]}")


if __name__ == "__main__":
    sys.exit(main())
