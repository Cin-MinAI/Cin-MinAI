#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""LibreOffice end to end (PLAN D20, SPEC §7.6–7.8): the extension from src/libreoffice-extension/ inside a real,
headless LibreOffice with a throwaway profile (the user's own LibreOffice and profile are never touched),
driven by the daemon's own code (src/cin_minai/daemon/office.py, guide.py). Linux with LibreOffice and
python3-uno; no model needed.

    python3 tests/integration/check_libreoffice.py        (from the repo root)
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "distro", "packages", "cinminai-daemon"))

import uno  # noqa: E402  (python3-uno)

from cin_minai.daemon.guide import Guide  # noqa: E402
from cin_minai.daemon.helpcards import HelpIndex  # noqa: E402
from cin_minai.daemon.office import Office, OfficeError, dbus_call  # noqa: E402
from cin_minai.daemon.tools import Tools  # noqa: E402
import gen_data  # noqa: E402

results: list[tuple[str, bool, str]] = []


def record(name: str, ok, detail: str = "") -> None:
    results.append((name, bool(ok), detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""), flush=True)


def build_oxt(out: str) -> str:
    src = os.path.join(ROOT, "src", "libreoffice-extension")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for root, dirs, files in os.walk(src):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for f in files:
                z.write(os.path.join(root, f), os.path.relpath(os.path.join(root, f), src))
    return out


class HeadlessOffice:
    def __init__(self, oxt: str) -> None:
        self.profile = tempfile.mkdtemp(prefix="cinminai-lo-check-")
        env = f"-env:UserInstallation=file://{self.profile}"
        r = subprocess.run(["unopkg", "add", "--suppress-license", env, oxt], capture_output=True, text=True, timeout=180)
        if r.returncode:
            raise RuntimeError(f"unopkg add failed: {r.stdout}{r.stderr}")
        pipe = f"cinminai_check_{os.getpid()}"
        self.proc = subprocess.Popen(["soffice", "--headless", "--invisible", env, "--norestore", "--nologo",
                                      "--nodefault", "--nolockcheck", f"--accept=pipe,name={pipe};urp;StarOffice.ComponentContext"],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        local = uno.getComponentContext()
        resolver = local.ServiceManager.createInstanceWithContext("com.sun.star.bridge.UnoUrlResolver", local)
        for _ in range(150):
            try:
                self.ctx = resolver.resolve(f"uno:pipe,name={pipe};urp;StarOffice.ComponentContext")
                break
            except Exception:
                time.sleep(0.2)
        else:
            raise RuntimeError("LibreOffice didn't come up")
        self.smgr = self.ctx.ServiceManager
        self.desktop = self.smgr.createInstanceWithContext("com.sun.star.frame.Desktop", self.ctx)

    def dispatch(self, doc, url: str) -> None:
        helper = self.smgr.createInstanceWithContext("com.sun.star.frame.DispatchHelper", self.ctx)
        helper.executeDispatch(doc.getCurrentController().getFrame(), url, "", 0, ())

    def close(self) -> None:
        try:
            self.desktop.terminate()
        except Exception:
            pass
        try:
            self.proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        shutil.rmtree(self.profile, ignore_errors=True)


def eval_module():
    saved, sys.argv = sys.argv, ["run_eval.py"]
    spec = importlib.util.spec_from_file_location("run_eval", os.path.join(ROOT, "training", "eval", "guide", "run_eval.py"))
    r = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(r)
    sys.argv = saved
    r.PROMPT = "v2"
    return r


def fill(sheet, values) -> None:
    for r, row in enumerate(values):
        for c, v in enumerate(row):
            cell = sheet.getCellByPosition(c, r)
            cell.setString(v) if isinstance(v, str) else cell.setValue(v)


def guide_run(R, office, o) -> None:
    """--guide: the real model (the daemon's config) answers the eval's questions on the expenses sheet; its
    proposals are applied and checked against the eval's expectation (training/eval/guide/tasks.py)."""
    import re
    import threading
    from cin_minai.daemon import config
    from cin_minai.inference.llamacpp import LlamaCppBackend

    cfg = config.load()
    backend = LlamaCppBackend(cfg["inference"], lambda m: None)
    data = gen_data.build(ROOT)
    h = data["help.json"]
    g = Guide(backend, data["guide.json"], HelpIndex(h), Tools(h["labels"], h["desktop"], "en"), cfg["guide"], o)

    def matches(expect: dict, tool: str, args: dict) -> bool:
        if expect["tool"] != tool:
            return False
        for k, want in expect.get("args", {}).items():
            got = json.dumps(args.get(k), ensure_ascii=False) if not isinstance(args.get(k), str) else args.get(k)
            if isinstance(want, str) and want.startswith("~"):
                if not re.search(want[1:], str(got).replace('"', "'") if k == "cells" else str(got), re.I):
                    return False
            elif want != args.get(k):
                return False
        return True

    try:
        for tid in ("O03", "O01", "O04", "O05", "O06"):
            task = next(t for t in R.TASKS if t["id"] == tid)
            doc = office.desktop.loadComponentFromURL("private:factory/scalc", "_blank", 0, ())
            sheet = doc.getSheets().getByIndex(0)
            fill(sheet, task["ctx"]["data"]["values"])
            doc.getCurrentController().select(sheet.getCellRangeByName("A1"))
            office.dispatch(doc, "org.cinminai.lo:share")
            g.reset()
            t0 = time.monotonic()
            try:
                out = g.turn(task["q"]["en"], lambda t: None, lambda *a: None, threading.Event())
            except Exception as e:  # what the user sees as the error line
                record(f"guide {tid}: {task['q']['en']}", False, f"{type(e).__name__}: {e}")
                office.dispatch(doc, "org.cinminai.lo:unshare")
                doc.close(True)
                continue
            dt = time.monotonic() - t0
            ok = any(matches(e, out["tool"], out["args"]) for e in task["expect"])
            detail = f"{out['tool']} {json.dumps(out['args'], ensure_ascii=False)[:90]} ({dt:.1f} s)"
            if out.get("proposal"):
                res = o.decide(out["proposal"], True)
                used = sheet.getCellRangeByName("A1:C9")
                cells = [[c for c in row] for row in used.getFormulaArray()]
                changed = [f"{chr(65 + c)}{r + 1}={v}" for r, row in enumerate(cells) for c, v in enumerate(row)
                           if v and (r >= len(task["ctx"]["data"]["values"]) or c >= 2)]
                detail += f" → applied: {', '.join(changed)}" if res.get("applied") else " → not applied"
            else:
                detail += f" → \"{out['reply'][:80]}\""
            record(f"guide {tid}: {task['q']['en']}", ok, detail)
            office.dispatch(doc, "org.cinminai.lo:unshare")
            doc.close(True)
    finally:
        backend.unload()


def main() -> int:
    R = eval_module()
    task = next(t for t in R.TASKS if t["id"] == "O03")  # "Add up everything I spent and put the total in B8."
    office = HeadlessOffice(build_oxt(os.path.join(tempfile.gettempdir(), "cinminai-check.oxt")))
    try:
        doc = office.desktop.loadComponentFromURL("private:factory/scalc", "_blank", 0, ())
        sheet = doc.getSheets().getByIndex(0)
        for r, row in enumerate(task["ctx"]["data"]["values"]):
            for c, v in enumerate(row):
                cell = sheet.getCellByPosition(c, r)
                cell.setString(v) if isinstance(v, str) else cell.setValue(v)
        doc.getCurrentController().select(sheet.getCellRangeByName("A1"))
        office.dispatch(doc, "org.cinminai.lo:start")  # headless: no visible window to start the service
        o = Office(dbus_call())
        for _ in range(50):
            if o.documents():
                break
            time.sleep(0.1)
        record("the extension answers on D-Bus", bool(o.documents()))
        record("nothing is shared before the menu click", o.current() is None)
        office.dispatch(doc, "org.cinminai.lo:share")  # what Assistant → Share does
        cur = o.current()
        record("Assistant → Share: the daemon sees the sheet", cur and cur["type"] == "calc", json.dumps(cur))

        data = gen_data.build(ROOT)
        h = data["help.json"]
        g = Guide(None, data["guide.json"], HelpIndex(h), Tools(h["labels"], h["desktop"], "en"), {}, o)
        _, system, schema = g.document()
        trained = R.system_prompt(task)
        record("the prompt from a real LibreOffice is the trained one, exactly", system == trained,
               "" if system == trained else f"daemon: {system[system.find('Document context'):][:300]!r}")

        pv = o.preview(cur, "set_formula", {"cell": "B8", "formula": "=SUM(B2:B7)"})
        record("set_formula previews, the sheet is unchanged", pv["after"] == [["=SUM(B2:B7)"]]
               and sheet.getCellRangeByName("B8").getFormula() == "", pv.get("summary", ""))
        res = o.decide(pv["id"], True)
        b8 = sheet.getCellRangeByName("B8")
        record("Apply: B8 holds the formula and the right total", res.get("applied") and b8.getFormula() == "=SUM(B2:B7)"
               and abs(b8.getValue() - 2456.6) < 1e-9, f"{b8.getFormula()} = {b8.getValue()}; undo: {res.get('undo')}")
        doc.getUndoManager().undo()
        record("one undo reverts it", sheet.getCellRangeByName("B8").getFormula() == "")

        pv = o.preview(cur, "write_range", {"range": "A8:B8", "cells": [["Total", "=SUM(B2:B7)"]]})
        sheet.getCellRangeByName("A8").setString("someone typed here")
        try:
            o.decide(pv["id"], True)
            record("a preview made stale by typing is refused", False)
        except OfficeError as e:
            record("a preview made stale by typing is refused", "changed since the preview" in str(e), str(e))
        office.dispatch(doc, "org.cinminai.lo:unshare")
        record("Assistant → Stop sharing: the daemon sees no document", o.current() is None)
        try:
            o.read(cur, "read_range", {"range": "A1:B2"})
            record("an unshared sheet refuses reads", False)
        except OfficeError as e:
            record("an unshared sheet refuses reads", "isn't shared" in str(e), str(e))
        doc.close(True)

        # new spreadsheets (sheets.py): the totals are right, as opened (no forced recalculation)
        from cin_minai.daemon import sheets
        import datetime as dt
        folder = tempfile.mkdtemp(prefix="cinminai-sheets-")
        made = sheets.make(folder, "Monthly expenses", ["Date", "Item", "Amount"],
                           [["2026-09-02", "Rent", "900"], ["2026-09-15", "Groceries", "84.20"],
                            ["2026-10-01", "Rent", "900"], ["2026-09-30", "Phone", "$35.00"]], "by_month",
                           today=dt.date(2026, 9, 30))
        url = uno.systemPathToFileUrl(made["file"])
        s = office.desktop.loadComponentFromURL(url, "_blank", 0, ())
        t = s.getSheets().getByName("Totals by month")
        sep, octo, year = (t.getCellRangeByName(c).getValue() for c in ("B10", "B11", "B14"))
        record("by_month totals right as opened (Sep 1019.2, Oct 900, year 1919.2)",
               abs(sep - 1019.2) < 1e-9 and abs(octo - 900) < 1e-9 and abs(year - 1919.2) < 1e-9,
               f"Sep {sep}, Oct {octo}, year {year}; {t.getCellRangeByName('A10').getString()}")
        e = s.getSheets().getByName("Entries")
        e.getCellRangeByName("A6").setValue(e.getCellRangeByName("A2").getValue() + 40)  # a new row, typed in
        e.getCellRangeByName("C6").setValue(50)
        record("a row typed in later counts in its month", abs(t.getCellRangeByName("B11").getValue() - 950) < 1e-9,
               f"Oct {t.getCellRangeByName('B11').getValue()} ({e.getCellRangeByName('A6').getString()})")
        s.close(True)
        made = sheets.make(folder, "Garden club", ["Name", "Amount"], [["Ann", "20"], ["Bob", "15.50"]], "sum")
        s = office.desktop.loadComponentFromURL(uno.systemPathToFileUrl(made["file"]), "_blank", 0, ())
        sh = s.getSheets().getByIndex(0)
        record("sum total right as opened (35.5)", abs(sh.getCellRangeByName("D2").getValue() - 35.5) < 1e-9,
               f"{sh.getCellRangeByName('D1').getString()} {sh.getCellRangeByName('D2').getValue()}")
        s.close(True)
        shutil.rmtree(folder, ignore_errors=True)

        if "--guide" in sys.argv:
            guide_run(R, office, o)
    finally:
        office.close()
    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks pass")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
