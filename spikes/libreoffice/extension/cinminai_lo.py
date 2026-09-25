"""Cin-MinAI LibreOffice extension (M0 spike, SPEC §7.6–7.8).

- ProtocolHandler for `org.cinminai.lo:*` URLs (the Assistant menu, Addons.xcu).
- Job on `onFirstVisibleTask` (Jobs.xcu) so the D-Bus service is up once LibreOffice shows a window.
- D-Bus service `org.cinminai.LibreOffice1` on the session bus, run on its own thread with its own
  GLib main context (LibreOffice's GTK main loop is never touched). The daemon calls it to use the
  toolkit (cinminai_tools) on documents the user shared.

Sharing is switched only from the menu (the user's action); there is deliberately no D-Bus method
for it, so no other program can grant itself access to a document.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import traceback

import uno
import unohelper
from com.sun.star.frame import XDispatch, XDispatchProvider
from com.sun.star.lang import XInitialization, XServiceInfo
from com.sun.star.task import XJob

import cinminai_tools as T  # noqa: E402  (./pythonpath, next to this file, is on sys.path)

IMPL = "org.cinminai.lo.ProtocolHandler"
PROTOCOL = "org.cinminai.lo:"
BUS_NAME = "org.cinminai.LibreOffice1"
OBJ_PATH = "/org/cinminai/LibreOffice1"
IFACE = "org.cinminai.LibreOffice1"

XML = f"""
<node>
  <interface name="{IFACE}">
    <method name="ListDocuments"><arg type="s" name="json" direction="out"/></method>
    <method name="Read">
      <arg type="s" name="doc" direction="in"/><arg type="s" name="tool" direction="in"/>
      <arg type="s" name="args" direction="in"/><arg type="s" name="json" direction="out"/>
    </method>
    <method name="Preview">
      <arg type="s" name="doc" direction="in"/><arg type="s" name="tool" direction="in"/>
      <arg type="s" name="args" direction="in"/><arg type="s" name="json" direction="out"/>
    </method>
    <method name="Apply">
      <arg type="s" name="doc" direction="in"/><arg type="s" name="tool" direction="in"/>
      <arg type="s" name="args" direction="in"/><arg type="s" name="snapshot" direction="in"/>
      <arg type="s" name="json" direction="out"/>
    </method>
    <signal name="Shared"><arg type="s" name="doc"/><arg type="s" name="title"/><arg type="b" name="shared"/></signal>
    <signal name="Asked"><arg type="s" name="doc"/><arg type="s" name="action"/><arg type="s" name="context"/></signal>
  </interface>
</node>
"""


def log(msg: str) -> None:
    try:
        with open(os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "cinminai-lo.log"), "a") as f:
            f.write(msg + "\n")
    except OSError:
        pass


class Service:
    """The D-Bus side. One per LibreOffice process."""

    instance: "Service | None" = None

    def __init__(self, ctx) -> None:
        self.ctx = ctx
        self.shared: set[str] = set()
        self.conn = None
        self.ready = threading.Event()
        threading.Thread(target=self.run, name="cinminai-dbus", daemon=True).start()
        self.ready.wait(5)

    @classmethod
    def get(cls, ctx) -> "Service":
        if cls.instance is None:
            cls.instance = Service(ctx)
        return cls.instance

    # --- documents ---
    def desktop(self):
        return self.ctx.ServiceManager.createInstanceWithContext("com.sun.star.frame.Desktop", self.ctx)

    def documents(self) -> dict:
        docs = {}
        enum = self.desktop().getComponents().createEnumeration()
        while enum.hasMoreElements():
            d = enum.nextElement()
            if hasattr(d, "RuntimeUID") and T.kind(d) != "other":
                docs[d.RuntimeUID] = d
        return docs

    def doc(self, uid: str, need_shared: bool = True):
        d = self.documents().get(uid)
        if d is None:
            raise T.ToolError(f"no open document {uid!r}")
        if need_shared and uid not in self.shared:
            raise T.ToolError("this document isn't shared with the assistant (Assistant → Share)")
        return d

    def set_shared(self, d, shared: bool) -> None:
        uid = d.RuntimeUID
        (self.shared.add if shared else self.shared.discard)(uid)
        self.emit("Shared", "(ssb)", uid, T.title(d), shared)

    # --- D-Bus (runs on our thread) ---
    def run(self) -> None:
        from gi.repository import Gio, GLib
        self.Gio, self.GLib = Gio, GLib
        ctx = GLib.MainContext.new()
        ctx.push_thread_default()  # our own main context: LibreOffice's is never used
        loop = GLib.MainLoop.new(ctx, False)

        def acquired(conn, name) -> None:
            self.conn = conn
            info = Gio.DBusNodeInfo.new_for_xml(XML).interfaces[0]
            conn.register_object(OBJ_PATH, info, self.call, None, None)
            self.ready.set()
            log(f"owned {name}")

        Gio.bus_own_name(Gio.BusType.SESSION, BUS_NAME, Gio.BusNameOwnerFlags.NONE, acquired, None,
                         lambda *a: (log("name lost"), self.ready.set()))
        loop.run()

    def emit(self, signal: str, fmt: str, *args) -> None:
        if self.conn:
            self.conn.emit_signal(None, OBJ_PATH, IFACE, signal, self.GLib.Variant(fmt, args))

    def call(self, conn, sender, path, iface, method, params, inv) -> None:
        GLib = self.GLib
        try:
            a = params.unpack()
            if method == "ListDocuments":
                out = [{"id": uid, "title": T.title(d), "type": T.kind(d), "shared": uid in self.shared}
                       for uid, d in self.documents().items()]
            elif method == "Read":
                out = T.read(self.doc(a[0]), a[1], json.loads(a[2] or "{}"))
            elif method == "Preview":
                out = T.preview(self.doc(a[0]), a[1], json.loads(a[2] or "{}"))
            elif method == "Apply":
                out = T.apply(self.doc(a[0]), a[1], json.loads(a[2] or "{}"), a[3])
            else:
                raise T.ToolError(f"unknown method {method}")
            inv.return_value(GLib.Variant("(s)", (json.dumps(out, default=str),)))
        except T.ToolError as e:
            inv.return_dbus_error(f"{IFACE}.Error.Tool", str(e))
        except (KeyError, ValueError, TypeError) as e:
            inv.return_dbus_error(f"{IFACE}.Error.BadArgs", f"{e.__class__.__name__}: {e}")
        except Exception as e:  # never let a tool failure take LibreOffice down
            log(traceback.format_exc())
            inv.return_dbus_error(f"{IFACE}.Error.Internal", repr(e))


class Handler(unohelper.Base, XDispatchProvider, XDispatch, XInitialization, XServiceInfo, XJob):
    def __init__(self, ctx, *args) -> None:
        self.ctx = ctx
        self.frame = None

    # XInitialization: LibreOffice passes the frame the menu belongs to.
    def initialize(self, args) -> None:
        if args:
            self.frame = args[0]

    # XJob (onFirstVisibleTask): start the D-Bus service with LibreOffice.
    def execute(self, args):
        Service.get(self.ctx)
        return None

    # XDispatchProvider
    def queryDispatch(self, url, target, flags):
        return self if url.Protocol == PROTOCOL else None

    def queryDispatches(self, requests):
        return tuple(self.queryDispatch(r.FeatureURL, r.FrameName, r.SearchFlags) for r in requests)

    # XDispatch
    def dispatch(self, url, args) -> None:
        svc = Service.get(self.ctx)
        action = url.Path
        if action == "start" or self.frame is None:
            return
        doc = self.frame.getController().getModel()
        try:
            if action == "share":
                svc.set_shared(doc, True)
            elif action == "unshare":
                svc.set_shared(doc, False)
            elif action in ("ask-selection", "rewrite-selection", "explain-formula", "summarize"):
                svc.set_shared(doc, True)  # asking about a document shares it (SPEC §7.6)
                try:
                    context = json.dumps(T.read(doc, "get_selection", {}), default=str)[:4000]
                except T.ToolError:
                    context = ""
                svc.emit("Asked", "(sss)", doc.RuntimeUID, action, context)
        except Exception:
            log(traceback.format_exc())

    def addStatusListener(self, listener, url) -> None:
        pass

    def removeStatusListener(self, listener, url) -> None:
        pass

    # XServiceInfo
    def getImplementationName(self) -> str:
        return IMPL

    def supportsService(self, name: str) -> bool:
        return name in self.getSupportedServiceNames()

    def getSupportedServiceNames(self):
        return ("com.sun.star.frame.ProtocolHandler", "com.sun.star.task.Job")


g_ImplementationHelper = unohelper.ImplementationHelper()
g_ImplementationHelper.addImplementation(Handler, IMPL, ("com.sun.star.frame.ProtocolHandler", "com.sun.star.task.Job"))
