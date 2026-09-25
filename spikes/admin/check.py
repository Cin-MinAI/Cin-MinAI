#!/usr/bin/env python3
"""Admin mechanism spike checks (M0). Run as a normal user after `sudo ./install.sh --test` (WSL):

    python3 check.py [--skip-idle] [--skip-apt]

Drives org.cinminai.Admin1 through cinminai-admin-demo, the way the daemon will. The test polkit
rule answers from /run/cinminai-polkit-test ("yes" / "no" / "" = fall through to auth_admin);
the real password dialog is checked by hand in the VM.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
DECISION = "/run/cinminai-polkit-test"
AUDIT = "/var/log/cinminai/admin.log"
DEMO = "cinminai-demo.service"
results: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""), flush=True)


def decide(d: str) -> None:
    with open(DECISION, "w") as f:
        f.write(d)


def demo(*args: str, stdin: bytes | None = None, interactive: bool = True) -> subprocess.CompletedProcess:
    argv = ["cinminai-admin-demo", *args] + ([] if interactive else ["--no-interactive"])
    return subprocess.run(argv, input=stdin, capture_output=True, timeout=600)


def out(r: subprocess.CompletedProcess) -> str:
    return (r.stdout + r.stderr).decode(errors="replace").strip().replace("\n", " | ")[:150]


def sh(*cmd: str) -> str:
    return subprocess.run(cmd, capture_output=True, text=True).stdout.strip()


def invocation() -> str:
    return sh("systemctl", "show", "-p", "InvocationID", "--value", DEMO)


def audit() -> list[dict]:
    with open(AUDIT) as f:
        return [json.loads(l) for l in f if l.strip()]


def polkit_checks(since: str) -> int:
    """Checks the test rule has seen since `since` (a count from polkit_count())."""
    return polkit_count() - int(since)


def polkit_count() -> int:
    with open("/run/cinminai-polkit-count") as f:
        return sum(1 for _ in f)


def main() -> int:
    skip_idle, skip_apt = "--skip-idle" in sys.argv, "--skip-apt" in sys.argv
    start = time.strftime("%Y-%m-%d %H:%M:%S")
    time.sleep(1)

    # Policy: every action auth_admin, never auth_admin_keep.
    pk = sh("pkaction", "--verbose", "--action-id", "org.cinminai.admin.restart-service")
    actions = [l.split()[-1] for l in sh("pkaction").splitlines() if l.startswith("org.cinminai.admin.")]
    implicit = {a: sh("pkaction", "--verbose", "--action-id", a) for a in actions}
    record("policy: 5 actions, all auth_admin for the active session, none *_keep",
           len(actions) == 5 and all("implicit active:   auth_admin\n" in v + "\n" and "keep" not in v
                                     for v in implicit.values()), f"{actions}")

    # D-Bus activation.
    subprocess.run(["systemctl", "stop", "cinminai-admin"], capture_output=True)  # may need root; fine if idle
    before = sh("systemctl", "is-active", "cinminai-admin")
    ver = sh("busctl", "--system", "get-property", "org.cinminai.Admin1", "/org/cinminai/Admin1",
             "org.cinminai.Admin1", "Version")
    after = sh("systemctl", "is-active", "cinminai-admin")
    record("D-Bus activation starts the root mechanism on demand", "0.1-spike" in ver and after == "active",
           f"{before} → {after}; Version {ver}")
    pid = sh("systemctl", "show", "-p", "MainPID", "--value", "cinminai-admin")
    uid = sh("ps", "-o", "uid=", "-p", pid)
    record("mechanism runs as root", uid == "0", f"pid {pid} uid {uid}")

    # Authorized / denied / no answer.
    decide("yes")
    inv0 = invocation()
    r = demo("restart", DEMO)
    inv1 = invocation()
    record("authorized: restart really happens", r.returncode == 0 and inv1 != inv0, out(r))
    decide("no")
    r = demo("restart", DEMO)
    record("denied: clean error, service untouched", r.returncode == 2 and invocation() == inv1, out(r))
    decide("")
    r = demo("restart", DEMO, interactive=False)
    record("no answer, non-interactive: not authorized, untouched", r.returncode == 2 and invocation() == inv1, out(r))
    r = demo("restart", DEMO)
    record("no answer, no password agent: not authorized, untouched", r.returncode == 2 and invocation() == inv1, out(r))

    # Every request is checked again (no caching).
    decide("yes")
    t0 = str(polkit_count())
    time.sleep(1)
    for _ in range(3):
        demo("restart", DEMO)
    time.sleep(1)
    n = polkit_checks(t0)
    record("every request asks polkit again (3 requests → 3 checks)", n == 3, f"{n} checks")

    # Refused before polkit is asked.
    t0 = str(polkit_count())
    time.sleep(1)
    bad = [
        ("restart", "x; rm -rf /"), ("restart", "../../etc/passwd"), ("restart", "dbus.service"),
        ("restart", "polkit.service"), ("restart", "systemd-logind.service"), ("restart", "cinminai-admin.service"),
        ("restart", "lightdm.service"), ("install", "foo bar"), ("install", "-y"), ("remove", "sudo"),
        ("remove", "libc6"), ("remove", "cinnamon"), ("write", "/etc/sudoers.d/x"), ("write", "/etc/../etc/shadow"),
        ("write", "/etc/passwd"), ("write", "/etc/polkit-1/rules.d/00-x.rules"), ("write", "/tmp/x"),
        ("write", "etc/x"), ("write", "/etc/profile.d/x.sh"), ("write", "/etc/systemd/system/x.service"),
        ("write", "/etc/apt/sources.list.d/x.list"), ("write", "/etc/cron.d/x"),
    ]
    links = [p for p in ("/etc/resolv.conf", "/etc/mtab", "/etc/localtime") if os.path.islink(p)]
    bad += [("write", links[0])] if links else []
    rejected = []
    for verb, target in bad:
        r = demo(verb, target, stdin=b"x\n")
        rejected.append((verb, target, r.returncode))
    time.sleep(1)
    wrong = [f"{v} {t} → {c}" for v, t, c in rejected if c != 3]
    record(f"{len(bad)} unsafe requests rejected before polkit (injection, protected units/packages/paths, symlink)",
           not wrong and polkit_checks(t0) == 0, "; ".join(wrong) or f"polkit checks: {polkit_checks(t0)}")
    r = demo("write", "/etc/cinminai-test.conf", stdin=b"x" * (1 << 20 + 1))
    r2 = subprocess.run(["cinminai-admin-demo", "write", "/etc/cinminai-test.conf", "--mode", "4755"],
                        input=b"x", capture_output=True)
    record("oversize content and setuid mode rejected", r.returncode == 3 and r2.returncode == 3, out(r2))

    # Writing a file: atomic, mode, backup of the previous version.
    decide("yes")
    r = demo("write", "/etc/cinminai-test.conf", stdin=b"first\n")
    st = os.stat("/etc/cinminai-test.conf")
    ok1 = r.returncode == 0 and open("/etc/cinminai-test.conf").read() == "first\n" and oct(st.st_mode & 0o777) == "0o644"
    r = demo("write", "/etc/cinminai-test.conf", stdin=b"second\n")
    backup = out(r).removeprefix("OK: ")
    record("write_file: content + mode, previous version backed up",
           ok1 and r.returncode == 0 and open("/etc/cinminai-test.conf").read() == "second\n" and "admin-backups" in backup,
           f"backup {backup}")

    # Enable / disable.
    r1 = demo("enable", DEMO)
    e1 = sh("systemctl", "is-enabled", DEMO)
    r2 = demo("disable", DEMO)
    e2 = sh("systemctl", "is-enabled", DEMO)
    record("set_service_enabled", r1.returncode == 0 and r2.returncode == 0 and (e1, e2) == ("enabled", "disabled"),
           f"{e1} → {e2}")

    # Packages (real apt).
    if not skip_apt:
        r = demo("install", "hello")
        installed = "install ok installed" in sh("dpkg-query", "-W", "-f=${Status}", "hello")
        record("install_package (apt, noninteractive)", r.returncode == 0 and installed, out(r)[-100:])
        r = demo("remove", "hello")
        gone = "install ok installed" not in sh("dpkg-query", "-W", "-f=${Status}", "hello")
        record("remove_package", r.returncode == 0 and gone, out(r)[-100:])
        r = demo("install", "no-such-package-cinminai")
        record("apt failure reported as an error, not a hang", r.returncode == 1, out(r)[-100:])

    # Concurrent requests.
    rs: list[subprocess.CompletedProcess] = []
    ts = [threading.Thread(target=lambda: rs.append(demo("restart", DEMO))) for _ in range(3)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    record("concurrent requests all handled", len(rs) == 3 and all(r.returncode == 0 for r in rs))

    # From inside the sandbox: no system bus at all.
    sys.path.insert(0, os.path.join(HERE, "..", "sandbox"))
    import sandbox  # noqa: E402
    ws = tempfile.mkdtemp(prefix="cinminai-ws-")
    inv_before = invocation()
    r = sandbox.run(["cinminai-admin-demo", "restart", DEMO], ws, net="pasta")
    record("the sandbox can't reach the mechanism", r.returncode != 0 and invocation() == inv_before,
           (r.stdout + r.stderr).strip().replace("\n", " | ")[:120])

    # Audit log.
    log = [e for e in audit() if e["ts"] >= start.replace(" ", "T")[:19]]
    decisions = {e["decision"] for e in log}
    mine = all(e["caller"]["uid"] == os.getuid() for e in log)
    attrs = sh("lsattr", AUDIT).split()[0] if sh("lsattr", AUDIT) else "?"
    record("audit log: every request with caller, decision, result",
           {"authorized", "denied", "rejected"} <= decisions and mine and len(log) >= len(bad) + 10,
           f"{len(log)} entries, decisions {sorted(decisions)}")
    record("audit log is append-only (chattr +a)", "a" in attrs, attrs)
    with open(AUDIT) as f:
        sample = [l for l in f][-1].strip()
    print("      last entry:", sample[:220])

    # Idle exit.
    if not skip_idle:
        time.sleep(75)
        record("exits when idle (D-Bus starts it again next time)",
               sh("systemctl", "is-active", "cinminai-admin") != "active")

    decide("")
    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks pass")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
