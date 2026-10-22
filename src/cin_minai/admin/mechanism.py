# SPDX-License-Identifier: GPL-3.0-or-later
"""Root-owned, D-Bus-activated Cin-MinAI ADMIN-lane mechanism."""

from __future__ import annotations

import datetime
import fcntl
import hashlib
import json
import os
import re
import subprocess
import tempfile
import threading
import time
import uuid

from gi.repository import Gio, GLib

from . import updates
from .policy import Reject, check_module, check_package, check_run_argv, check_unit, check_write

NAME = IFACE = "org.cinminai.Admin1"
PATH = "/org/cinminai/Admin1"
ERR = f"{IFACE}.Error"
AUDIT = os.environ.get("CINMINAI_ADMIN_AUDIT", "/var/log/cinminai/admin.log")
BACKUPS = "/var/lib/cinminai/admin-backups"
IDLE_EXIT = int(os.environ.get("CINMINAI_ADMIN_IDLE", "60"))
VERSION = "0.0.1"

XML = f"""<node><interface name="{IFACE}">
  <method name="RestartService"><arg type="s" name="unit" direction="in"/></method>
  <method name="SetServiceEnabled"><arg type="s" name="unit" direction="in"/><arg type="b" name="enabled" direction="in"/></method>
  <method name="InstallPackage"><arg type="s" name="package" direction="in"/><arg type="s" name="log" direction="out"/></method>
  <method name="RemovePackage"><arg type="s" name="package" direction="in"/><arg type="s" name="log" direction="out"/></method>
  <method name="WriteFile"><arg type="s" name="path" direction="in"/><arg type="ay" name="content" direction="in"/><arg type="u" name="mode" direction="in"/><arg type="s" name="backup" direction="out"/></method>
  <method name="LoadModule"><arg type="s" name="module" direction="in"/></method>
  <method name="UnloadModule"><arg type="s" name="module" direction="in"/></method>
  <method name="RunArgv"><arg type="as" name="argv" direction="in"/><arg type="s" name="log" direction="out"/></method>
  <method name="RefreshUpdates"><arg type="s" name="result" direction="out"/></method>
  <method name="InstallUpdates"><arg type="as" name="versions" direction="in"/><arg type="b" name="snapshot" direction="in"/><arg type="s" name="job" direction="in"/><arg type="s" name="result" direction="out"/></method>
  <method name="SetUpdateSettings"><arg type="s" name="settings" direction="in"/><arg type="s" name="result" direction="out"/></method>
  <signal name="UpdateStep"><arg type="s" name="job"/><arg type="s" name="step"/><arg type="s" name="state"/><arg type="s" name="detail"/></signal>
  <property name="Version" type="s" access="read"/>
</interface></node>"""


def run(argv: list[str], timeout: int | None = 900, keep: int | None = 8000) -> str:
    env = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C.UTF-8", "DEBIAN_FRONTEND": "noninteractive"}
    result = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, env=env, shell=False)
    output = result.stdout + result.stderr
    output = output[-keep:] if keep else output
    if result.returncode:
        raise RuntimeError(f"{argv[0]} exited {result.returncode}: {output.strip()[-500:]}")
    return output


def write_file(path: str, content: bytes, mode: int) -> str:
    backup = ""
    if os.path.exists(path):
        os.makedirs(BACKUPS, mode=0o700, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        backup = os.path.join(BACKUPS, f"{stamp}-{uuid.uuid4().hex[:6]}{path.replace('/', '_')}")
        with open(path, "rb") as src, open(backup, "xb") as dst:
            dst.write(src.read())
    fd, temporary = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".cinminai-")
    try:
        os.write(fd, content)
        os.fchmod(fd, mode)
        os.fsync(fd)
        os.close(fd)
        fd = -1
        os.replace(temporary, path)
    except BaseException:
        if fd >= 0:
            os.close(fd)
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise
    return backup


def execute_write(args) -> str:
    # Like RunArgv: the password dialog can sit on screen while things change, so
    # check the path and content again immediately before writing.
    path, content, mode = args
    return write_file(check_write(path, content, mode), content, mode)


def _none(value: object) -> None:
    return None


def prepare_module(args, unloading=False):
    module = check_module(args[0], unloading=unloading)
    return {"module": module}, ["/sbin/modprobe", *(["-r"] if unloading else []), "--", module]


def prepare_run_argv(args):
    argv = check_run_argv(args[0])
    return {"program": argv[0], "target": argv[-1]}, argv


def execute_run_argv(argv):
    # Authentication may sit on screen while hardware is unplugged/replugged.
    # Resolve the target and boot-device set again immediately before execution.
    return run(check_run_argv(argv))


def run_apt(argv: list[str]) -> str:
    # No time limit: a big install on a slow connection can take longer than any
    # limit, and killing apt part-way can leave a half-installed package.
    return run(argv, timeout=None)


def run_apt_whole(argv: list[str]) -> str:
    # The update window reads every line of apt's plan, so nothing is cut.
    return run(argv, timeout=None, keep=None)


JOB_RE = re.compile(r"^[a-z0-9]{1,32}$")
EMIT = [lambda *a: None]  # set when the bus name is owned: the UpdateStep signal


def prepare_install_updates(args):
    versions, snapshot, job = list(args[0]), bool(args[1]), str(args[2])
    if not JOB_RE.fullmatch(job):
        raise Reject("not a job id")
    checked = updates.check_versions(versions, updates.apt_candidates())
    names = [v.split("=", 1)[0] for v in checked]
    shown = ", ".join(names[:6]) + (f" and {len(names) - 6} more" if len(names) > 6 else "")
    return {"count": str(len(checked)), "updates": shown, "snapshot": "yes" if snapshot else "no"}, (checked, snapshot, job)


def execute_install_updates(args):
    versions, snapshot, job = args
    with updates.exclusive():  # one update at a time, the daily timer's included
        # the password dialog may have sat on screen while the lists changed: check again
        versions = updates.check_versions(versions, updates.apt_candidates())
        return json.dumps(updates.install(versions, snapshot, run_apt_whole, lambda *a: EMIT[0](*a), job))


def changelog(item: dict) -> str:
    """A held security update's changelog, for the CVEs it fixes (D89): from the package itself, downloaded by apt into
    its cache (checked against the signed index by apt; it's installed from there later). Ubuntu's changelog server
    often doesn't have a new update's changelog yet; it's asked only when the package carries none of its own."""
    name, version, arch = item["name"], item["version"], item.get("arch", "")
    base = updates.base_name(name)
    text = ""
    try:
        for _ in range(2):  # the package itself, then the one its changelog links to (same source, same version)
            run(["/usr/bin/apt-get", "install", "-y", "--download-only", *updates.APT_OPTS, "--", f"{base}={version}"],
                timeout=600)
            deb = next((os.path.join(updates.ARCHIVES, updates.deb_name(base, version, a)) for a in (arch, "all")
                        if os.path.exists(os.path.join(updates.ARCHIVES, updates.deb_name(base, version, a)))), "")
            text, other = updates.deb_changelog(deb, base) if deb else ("", "")
            if text or not other:
                break
            base = other
    except (RuntimeError, OSError, subprocess.SubprocessError):
        text = ""
    return text or run(["/usr/bin/apt-get", "changelog", f"{updates.base_name(name)}={version}"], timeout=60, keep=None)


def execute_refresh_updates(_args) -> str:
    with updates.exclusive():
        return json.dumps(updates.check(run_apt_whole, changelog))


def prepare_update_settings(args):
    try:
        settings = updates.check_settings(json.loads(args[0]))
    except ValueError:
        raise Reject("not update settings") from None
    own = ", ".join(h["name"] + (f" {h['version']}" if h["version"] else "") for h in settings["own"][:6])
    return ({"days": str(settings["hold_days"]), "auto": "on" if settings["auto"] else "off",
             "own": own or "none", "looked": ", ".join(settings["looked"][-6:]) or "none"}, settings)


def execute_update_settings(settings) -> str:
    # root-owned and readable by all: the window and the daily timer read the same settings
    updates.write_json(updates.SETTINGS, updates.check_settings(settings))
    return json.dumps(settings)


VERBS = {
    "RestartService": ("org.cinminai.admin.restart-service", lambda a: ({"unit": check_unit(a[0])}, ["/usr/bin/systemctl", "restart", "--", a[0]]), lambda a: _none(run(a)), None),
    "SetServiceEnabled": ("org.cinminai.admin.set-service-enabled", lambda a: ({"unit": check_unit(a[0]), "enabled": "yes" if a[1] else "no"}, ["/usr/bin/systemctl", "enable" if a[1] else "disable", "--", a[0]]), lambda a: _none(run(a)), None),
    "InstallPackage": ("org.cinminai.admin.install-package", lambda a: ({"package": check_package(a[0])}, ["/usr/bin/apt-get", "install", "-y", "-o", "Dpkg::Options::=--force-confold", "--", a[0]]), run_apt, "(s)"),
    "RemovePackage": ("org.cinminai.admin.remove-package", lambda a: ({"package": check_package(a[0], True)}, ["/usr/bin/apt-get", "remove", "-y", "--no-auto-remove", "--", a[0]]), run_apt, "(s)"),
    "WriteFile": ("org.cinminai.admin.write-file", lambda a: ({"path": check_write(a[0], bytes(a[1]), a[2]), "size": str(len(a[1])), "mode": oct(a[2])}, [a[0], bytes(a[1]), a[2]]), execute_write, "(s)"),
    "LoadModule": ("org.cinminai.admin.load-module", lambda a: prepare_module(a), lambda a: _none(run(a)), None),
    "UnloadModule": ("org.cinminai.admin.unload-module", lambda a: prepare_module(a, True), lambda a: _none(run(a)), None),
    "RunArgv": ("org.cinminai.admin.run-argv", prepare_run_argv, execute_run_argv, "(s)"),
    # the update window (D29): checking for updates needs no password (Update Manager's doesn't either); installing does
    "RefreshUpdates": ("org.cinminai.admin.refresh-updates", lambda a: ({}, None), execute_refresh_updates, "(s)"),
    "InstallUpdates": ("org.cinminai.admin.install-updates", prepare_install_updates, execute_install_updates, "(s)"),
    # the holds and automatic updates (D89): optional, the person's own; one password to change them
    "SetUpdateSettings": ("org.cinminai.admin.update-settings", prepare_update_settings, execute_update_settings, "(s)"),
}


def append_audit(path: str, record: dict) -> None:
    """Append one fsync'd, hash-chained JSON record while holding a file lock."""
    os.makedirs(os.path.dirname(path), mode=0o750, exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_CLOEXEC | os.O_NOFOLLOW, 0o640)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        with os.fdopen(os.dup(fd), "r", encoding="utf-8") as reader:
            lines = [line for line in reader if line.strip()]
        previous, sequence = "0" * 64, 1
        for line in lines:
            try:
                item = json.loads(line)
                digest = item.pop("hash")
                if item["seq"] != sequence or item["prev"] != previous:
                    raise ValueError("broken sequence")
                canonical_item = json.dumps(item, sort_keys=True, separators=(",", ":")).encode()
                if hashlib.sha256(previous.encode() + canonical_item).hexdigest() != digest:
                    raise ValueError("bad hash")
                previous, sequence = digest, sequence + 1
            except (ValueError, KeyError, TypeError) as exc:
                raise RuntimeError("audit chain is invalid; refusing an unchained append") from exc
        body = {"seq": sequence, "prev": previous, **record}
        canonical = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
        body["hash"] = hashlib.sha256(previous.encode() + canonical).hexdigest()
        os.write(fd, (json.dumps(body, sort_keys=True, separators=(",", ":")) + "\n").encode())
        os.fsync(fd)
    finally:
        os.close(fd)


class Mechanism:
    def __init__(self, loop: GLib.MainLoop) -> None:
        self.loop, self.conn, self.inflight, self.last = loop, None, 0, time.monotonic()
        GLib.timeout_add_seconds(5, self.idle_check)

    def idle_check(self) -> bool:
        if not self.inflight and time.monotonic() - self.last > IDLE_EXIT:
            self.loop.quit()
            return False
        return True

    def audit(self, event: str, **record) -> None:
        append_audit(AUDIT, {"ts": datetime.datetime.now().astimezone().isoformat(timespec="seconds"), "event": event, **record})

    def caller(self, sender: str) -> dict:
        def ask(method: str):
            return self.conn.call_sync("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus", method, GLib.Variant("(s)", (sender,)), None, Gio.DBusCallFlags.NONE, 2000, None).unpack()[0]
        uid, pid = ask("GetConnectionUnixUser"), ask("GetConnectionUnixProcessID")
        try:
            exe = os.readlink(f"/proc/{pid}/exe")
        except OSError:
            exe = "?"
        return {"uid": uid, "pid": pid, "exe": exe}

    def acquired(self, connection, _name) -> None:
        self.conn = connection
        info = Gio.DBusNodeInfo.new_for_xml(XML).interfaces[0]
        connection.register_object(PATH, info, self.call, lambda *_: GLib.Variant("s", VERSION), None)

        def step(*args) -> None:  # from the worker thread: the signal goes out on the main loop
            def send() -> bool:
                connection.emit_signal(None, PATH, IFACE, "UpdateStep", GLib.Variant("(ssss)", args))
                self.last = time.monotonic()
                return False
            GLib.idle_add(send)
        EMIT[0] = step

    def call(self, _connection, sender, _path, _iface, method, params, invocation) -> None:
        self.last = time.monotonic()
        request_id = uuid.uuid4().hex
        args = params.unpack()
        shown = [f"<{len(a)} bytes>" if isinstance(a, (bytes, bytearray)) or
                 (isinstance(a, list) and (not a or isinstance(a[0], int))) else a for a in args]
        base = {"request": request_id, "verb": method, "args": shown, "caller": self.caller(sender)}
        try:
            self.audit("request", **base)
        except Exception as exc:
            invocation.return_dbus_error(f"{ERR}.AuditFailed", f"audit unavailable; request not run: {exc}")
            return
        try:
            action, validate, execute, out_signature = VERBS[method]
            details, safe_args = validate(args)
        except (Reject, KeyError, IndexError, TypeError) as exc:
            try:
                self.audit("rejected", **base, reason=str(exc))
            except Exception:
                pass  # still refuse the request; never turn an audit fault into execution
            invocation.return_dbus_error(f"{ERR}.Rejected", str(exc))
            return
        interactive = bool(invocation.get_message().get_flags() & Gio.DBusMessageFlags.ALLOW_INTERACTIVE_AUTHORIZATION)
        try:
            self.audit("authorization-requested", **base, details=details, interactive=interactive)
        except Exception as exc:
            invocation.return_dbus_error(f"{ERR}.AuditFailed", f"audit unavailable; request not run: {exc}")
            return
        self.inflight += 1
        self.check_auth(sender, action, details, interactive, lambda ok, why: self.after_auth(ok, why, invocation, base, details, execute, safe_args, out_signature))

    def check_auth(self, sender, action, details, interactive, done) -> None:
        subject = ("system-bus-name", {"name": GLib.Variant("s", sender)})
        flags = 1 if interactive else 0
        def reply(bus, result) -> None:
            try:
                authorized, challenge, polkit_details = bus.call_finish(result).unpack()[0]
                reason = "authorized" if authorized else ("dismissed" if polkit_details.get("polkit.dismissed") else ("challenge" if challenge else "denied"))
                done(authorized, reason)
            except GLib.Error as exc:
                done(False, f"polkit error: {exc.message}")
        self.conn.call("org.freedesktop.PolicyKit1", "/org/freedesktop/PolicyKit1/Authority", "org.freedesktop.PolicyKit1.Authority", "CheckAuthorization", GLib.Variant("((sa{sv})sa{ss}us)", (subject, action, details, flags, uuid.uuid4().hex)), GLib.VariantType("((bba{ss}))"), Gio.DBusCallFlags.NONE, 0x7fffffff, None, reply)

    def after_auth(self, ok, reason, invocation, base, details, execute, safe_args, out_signature) -> None:
        if not ok:
            self.inflight -= 1
            try:
                self.audit("authorization-denied", **base, details=details, reason=reason)
            except Exception:
                pass  # denial remains a denial
            name = "Dismissed" if reason == "dismissed" else "NotAuthorized"
            invocation.return_dbus_error(f"{ERR}.{name}", f"not authorized: {reason}")
            return
        try:
            self.audit("authorization-approved", **base, details=details)
        except Exception as exc:
            self.inflight -= 1
            invocation.return_dbus_error(f"{ERR}.AuditFailed", f"audit unavailable; approved request not run: {exc}")
            return
        started = time.monotonic()
        def work() -> None:
            try:
                value, error = execute(safe_args), None
            except Exception as exc:
                value, error = None, str(exc)
            GLib.idle_add(finish, value, error)
        def finish(value, error) -> bool:
            self.inflight -= 1
            self.last = time.monotonic()
            try:
                self.audit("result", **base, details=details, result="error" if error else "ok", error=error, seconds=round(time.monotonic() - started, 2))
            except Exception as exc:
                invocation.return_dbus_error(f"{ERR}.AuditFailed", f"operation finished but its result could not be audited: {exc}")
                return False
            if error:
                invocation.return_dbus_error(f"{ERR}.Failed", error)
            elif out_signature:
                invocation.return_value(GLib.Variant(out_signature, (value or "",)))
            else:
                invocation.return_value(None)
            return False
        threading.Thread(target=work, daemon=True).start()


def main() -> int:
    if os.geteuid() != 0:
        print("cinminai-admin must run as root (D-Bus activated)", file=os.sys.stderr)
        return 1
    os.umask(0o022)
    loop = GLib.MainLoop()
    mechanism = Mechanism(loop)
    Gio.bus_own_name(Gio.BusType.SYSTEM, NAME, Gio.BusNameOwnerFlags.NONE, mechanism.acquired, None, lambda *_: loop.quit())
    loop.run()
    return 0
