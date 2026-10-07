# SPDX-License-Identifier: GPL-3.0-or-later
"""Admin actions on the one path (M4 slice 3; PLAN D85, SPEC §8.4).

The eight verbs of the root mechanism (org.cinminai.Admin1, package cinminai-admin) as action kinds. They are
irreversible here, so the walls make every one ask: the person allows the card, then the mechanism asks polkit for the
administrator password — the assistant is not the admin. Cancelling the password is a denial (Declined), not a
failure. The mechanism checks everything again on its side; nothing here is trusted by it.

    from cin_minai.actions import admin
    admin.register(actions)
    actions.propose("admin.install_package", {"package": "gimp"}, reason="you asked for a photo editor")
"""

from __future__ import annotations

from typing import Any, Callable

from .core import ActionError, Actions, Declined, Kind

NAME = IFACE = "org.cinminai.Admin1"
PATH = "/org/cinminai/Admin1"
ERR = f"{IFACE}.Error."
NO_TIMEOUT = 0x7fffffff     # the password dialog and apt can both take as long as they take


class Unavailable(ActionError):
    """The admin mechanism isn't installed or didn't start."""


def _bus_call(method: str, signature: str, values: tuple, reply: str | None) -> Any:
    from gi.repository import Gio, GLib
    bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
    try:
        out = bus.call_sync(NAME, PATH, IFACE, method, GLib.Variant(signature, values),
                            GLib.VariantType(reply) if reply else None,
                            Gio.DBusCallFlags.ALLOW_INTERACTIVE_AUTHORIZATION, NO_TIMEOUT, None)
    except GLib.Error as e:
        remote = Gio.DBusError.get_remote_error(e) or ""
        # e.message is "GDBus.Error:<remote>: <reason>" (strip_remote_error edits a copy in PyGObject, not e)
        raise _error(remote, _reason(e.message, remote)) from None
    return out.unpack()[0] if reply else None


def _reason(message: str, remote: str) -> str:
    prefix = f"GDBus.Error:{remote}: "
    return message[len(prefix):] if remote and message.startswith(prefix) else message


def _error(remote: str, message: str) -> ActionError:
    if remote in (ERR + "Dismissed", ERR + "NotAuthorized"):
        return Declined("the password wasn't given, so nothing was changed")
    if remote == ERR + "Rejected":
        return ActionError(f"the system refused it: {message}")
    if remote in ("org.freedesktop.DBus.Error.ServiceUnknown", "org.freedesktop.DBus.Error.Spawn.ChildExited",
                  "org.freedesktop.DBus.Error.NameHasNoOwner"):
        return Unavailable("the admin helper (cinminai-admin) isn't installed or didn't start")
    return ActionError(message)


# name: (D-Bus method, signature, args -> values, reply, plain-words summary, destructive)
VERBS: dict[str, tuple[str, str, Callable[[dict], tuple], str | None, Callable[[dict], str], bool]] = {
    "admin.install_package": ("InstallPackage", "(s)", lambda a: (a["package"],), "(s)",
                              lambda a: f"install the program “{a['package']}”", False),
    "admin.remove_package": ("RemovePackage", "(s)", lambda a: (a["package"],), "(s)",
                             lambda a: f"remove the program “{a['package']}”", False),
    "admin.restart_service": ("RestartService", "(s)", lambda a: (a["unit"],), None,
                              lambda a: f"restart the system service {a['unit']}", False),
    "admin.set_service_enabled": ("SetServiceEnabled", "(sb)", lambda a: (a["unit"], bool(a["enabled"])), None,
                                  lambda a: f"{'switch on' if a['enabled'] else 'switch off'} the system service "
                                            f"{a['unit']} at start-up", False),
    "admin.write_file": ("WriteFile", "(sayu)",
                         lambda a: (a["path"], a["content"].encode("utf-8"), int(a.get("mode", 0o644))), "(s)",
                         lambda a: f"write the system setting file {a['path']}", False),
    "admin.load_module": ("LoadModule", "(s)", lambda a: (a["module"],), None,
                          lambda a: f"load the driver {a['module']}", False),
    "admin.unload_module": ("UnloadModule", "(s)", lambda a: (a["module"],), None,
                            lambda a: f"unload the driver {a['module']}", False),
    "admin.run": ("RunArgv", "(as)", lambda a: (list(a["argv"]),), "(s)",
                  lambda a: f"run {a['argv'][0].rsplit('/', 1)[-1]} on {a['argv'][-1]}", True),
}


def _kind(name: str, call: Callable[..., Any]) -> Kind:
    method, signature, values, reply, summary, destructive = VERBS[name]
    return Kind(name, "admin", False, summary=summary, destructive=destructive,
                realize=lambda a: call(method, signature, values(a), reply))


def register(actions: Actions, call: Callable[..., Any] = _bus_call) -> None:
    for name in VERBS:
        actions.register(_kind(name, call))
