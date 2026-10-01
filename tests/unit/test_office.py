# SPDX-License-Identifier: GPL-3.0-or-later
"""LibreOffice in the daemon (src/cin_minai/daemon/office.py, guide.py; PLAN D20, SPEC §7.6–7.8) against a
fake extension: the document prompt must be exactly the one the guide was trained and measured with
(training/eval/guide/run_eval.py, prompt v2), edits only ever become previews, and Apply carries the
preview's snapshot.

    python3 -m unittest tests.unit.test_office -v        (from the repo root)
"""

import importlib.util
import json
import os
import sys
import threading
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "distro", "packages", "cinminai-daemon"))

from cin_minai.daemon.guide import Guide  # noqa: E402
from cin_minai.daemon.helpcards import HelpIndex  # noqa: E402
from cin_minai.daemon.office import Office, OfficeError, compact, short_selection  # noqa: E402
from tests.unit.test_guide import DATA, FakeTools, Scripted  # noqa: E402

_saved, sys.argv = sys.argv, ["run_eval.py"]
_spec = importlib.util.spec_from_file_location("run_eval", os.path.join(ROOT, "training", "eval", "guide", "run_eval.py"))
R = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(R)
sys.argv = _saved
R.PROMPT = "v2"
TASKS = {t["id"]: t for t in R.TASKS}


class FakeLO:
    """The extension's D-Bus methods over in-memory documents shaped like the eval's."""

    def __init__(self):
        self.docs, self.calls = {}, []

    def add_calc(self, uid, title, values, order=1, sheet="Sheet1", selection="Sheet1.A1:A1"):
        self.docs[uid] = {"type": "calc", "title": title, "order": order, "sheet": sheet, "selection": selection,
                          "values": [[float(v) if isinstance(v, int) else v for v in r] for r in values]}

    def add_writer(self, uid, title, paragraphs, selection, outline, order=1):
        self.docs[uid] = {"type": "writer", "title": title, "order": order, "paragraphs": paragraphs,
                          "selection": selection, "outline": outline}

    def add_impress(self, uid, slides, order=1):
        self.docs[uid] = {"type": "impress", "title": "Slides", "order": order, "slides": slides}

    def __call__(self, method, *args):
        self.calls.append((method, args))
        if method == "ListDocuments":
            out = [{"id": u, "title": d["title"], "type": d["type"], "shared": d["order"] > 0, "shared_order": d["order"]}
                   for u, d in self.docs.items()]
            return json.dumps(sorted(out, key=lambda d: d["shared_order"]))
        d = self.docs[args[0]]
        tool, a = args[1], json.loads(args[2])
        if method == "Read":
            return json.dumps(self.read(d, tool, a))
        if method == "Preview":
            if tool == "set_formula" and not str(a.get("cell", "")).strip():
                raise OfficeError("set_formula takes one cell (e.g. B9)")
            return json.dumps({"before": [[""]], "after": [[a.get("formula", "")]], "snapshot": "snap1",
                               "summary": f"Set {a.get('cell')} to {a.get('formula')}"})
        if method == "Apply":
            if args[3] != "snap1":
                raise OfficeError("the document changed since the preview")
            return json.dumps({"applied": True, "undo": f"Assistant: {tool}"})
        raise OfficeError(method)

    def read(self, d, tool, a):
        if tool == "doc_info":
            if d["type"] == "calc":
                return {"type": "calc", "title": d["title"], "modified": False, "sheets": [d["sheet"]],
                        "active_sheet": d["sheet"], "selection": d["selection"]}
            if d["type"] == "writer":
                return {"type": "writer", "title": d["title"], "modified": False, "paragraphs": d["paragraphs"]}
            return {"type": "impress", "title": d["title"], "modified": False, "slides": len(d["slides"])}
        if tool == "used_range":
            v = d["values"]
            return {"sheet": d["sheet"], "range": f"A1:{chr(64 + len(v[0]))}{len(v)}"}
        if tool == "read_range":
            return {"values": d["values"]}
        if tool == "get_selection":
            return {"text": d["selection"]}
        if tool == "outline":
            return {"headings": d["outline"]}
        if tool == "slide_text":
            return d["slides"][a["slide"] - 1]
        raise OfficeError(f"unknown tool {tool}")


def guide_with(lo, replies):
    b = Scripted(replies)
    h = DATA["help.json"]
    g = Guide(b, DATA["guide.json"], HelpIndex(h), FakeTools(h["labels"], h["desktop"], "en"),
              {"history_chars": 12000, "cpu_history_chars": 3000}, Office(lo))
    return g, b


def run(g, text):
    out, actions = [], []
    res = g.turn(text, out.append, lambda *a: actions.append(a), threading.Event())
    return res, "".join(out), actions


def lo_like(task_id):
    """A fake LibreOffice holding the eval task's document, shared."""
    t, lo = TASKS[task_id], FakeLO()
    ctx = t["ctx"]
    if t["doc"] == "calc":
        lo.add_calc("d1", "Budget.ods", ctx["data"]["values"], sheet=ctx["document"]["active"],
                    selection=f"{ctx['document']['active']}.{ctx['document']['selection']}:{ctx['document']['selection']}")
    elif t["doc"] == "writer":
        lo.add_writer("d1", ctx["document"]["title"], ctx["document"]["paragraphs"], ctx["selection"], ctx["outline"])
    else:
        lo.add_impress("d1", ctx["slides"])
    return t, lo


class TrainedPrompt(unittest.TestCase):
    """The daemon's document prompt is the eval's prompt, character for character."""

    def test_calc_writer_impress(self):
        for tid in ("O01", "O02", next(i for i, t in TASKS.items() if t.get("doc") == "writer")):
            t, lo = lo_like(tid)
            g, _ = guide_with(lo, [])
            doc, system, schema = g.document()
            self.assertEqual(system, R.system_prompt(t), tid)
            self.assertEqual(schema, R.schema(t["doc"]), tid)

    def test_no_document_is_the_plain_prompt(self):
        g, _ = guide_with(FakeLO(), [])
        self.assertEqual(g.document()[1:], (DATA["guide.json"]["system"], DATA["guide.json"]["schema"]))

    def test_libreoffice_not_running_is_no_document(self):
        def down(*a):
            raise OfficeError("org.cinminai.LibreOffice1 is not running")
        g, _ = guide_with(down, [])
        self.assertIsNone(g.document()[0])

    def test_newest_shared_wins_and_forget(self):
        lo = FakeLO()
        lo.add_calc("old", "Old.ods", [["a"]], order=1)
        lo.add_calc("new", "New.ods", [["b"]], order=2)
        lo.add_calc("unshared", "Other.ods", [["c"]], order=0)
        o = Office(lo)
        self.assertEqual(o.current()["id"], "new")
        o.forget("new")
        self.assertEqual(o.current()["id"], "old")


class Edits(unittest.TestCase):
    def test_edit_becomes_a_preview_never_a_change(self):
        _, lo = lo_like("O03")
        call = json.dumps({"tool": "set_formula", "args": {"cell": "B8", "formula": "=SUM(B2:B7)"}})
        g, b = guide_with(lo, [call])
        res, text, actions = run(g, "Add up everything I spent and put the total in B8.")
        self.assertEqual(len(b.sent), 1)  # no second model call: the reply is the preview's own words
        self.assertIn("Set B8 to =SUM(B2:B7)", text)
        self.assertIn("Apply", text)
        self.assertNotIn("Apply", [m for m, _ in lo.calls])
        proposal = [a for a in actions if a[2] == "proposal"]
        self.assertEqual(len(proposal), 1)
        pid = json.loads(proposal[0][3])["id"]
        self.assertEqual(res["proposal"], pid)
        # the user clicks Apply: the preview's snapshot goes with it
        self.assertTrue(g.office.decide(pid, True)["applied"])
        self.assertEqual(lo.calls[-1][1][3], "snap1")
        with self.assertRaises(OfficeError):
            g.office.decide(pid, True)  # once only

    def test_discard_changes_nothing(self):
        _, lo = lo_like("O03")
        g, _ = guide_with(lo, [json.dumps({"tool": "set_formula", "args": {"cell": "B8", "formula": "=SUM(B2:B7)"}})])
        res, _, _ = run(g, "total in B8")
        self.assertEqual(g.office.decide(res["proposal"], False), {"applied": False})
        self.assertNotIn("Apply", [m for m, _ in lo.calls])

    def test_refused_call_gets_one_corrected_try(self):
        _, lo = lo_like("O03")
        bad = json.dumps({"tool": "set_formula", "args": {"cell": " ", "formula": "=SUM(B2:B7)"}})
        good = json.dumps({"tool": "set_formula", "args": {"cell": "B8", "formula": "=SUM(B2:B7)"}})
        g, b = guide_with(lo, [bad, good])
        res, _, _ = run(g, "total in B8")
        self.assertIn("proposal", res)
        self.assertIn("That call failed: set_formula takes one cell", b.sent[1]["messages"][-1]["content"])

    def test_read_tool_result_goes_back_like_a_system_check(self):
        _, lo = lo_like("O03")
        g, b = guide_with(lo, [json.dumps({"tool": "read_range", "args": {"range": "A1:B3"}}), "January was 412.5."])
        res, text, _ = run(g, "What did I spend in January?")
        self.assertEqual(text.strip().endswith("412.5."), True)
        self.assertTrue(b.sent[1]["messages"][-1]["content"].startswith("Result of read_range:"))


class Helpers(unittest.TestCase):
    def test_numbers_and_selection_as_trained(self):
        self.assertEqual(compact([[388.0, 412.5, "x"]]), [[388, 412.5, "x"]])
        self.assertEqual(short_selection("Sheet1.B8:B8"), "B8")
        self.assertEqual(short_selection("Sheet1.A1:C3"), "A1:C3")


if __name__ == "__main__":
    unittest.main()
