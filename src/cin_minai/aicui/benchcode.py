# SPDX-License-Identifier: GPL-3.0-or-later
"""The Benchmark's coding run: how much load a model carries as a junior in the development cycle (Ian, 2026-10-15:
"We go by lines of code expressed, held, re-expressed, and continued efficiently. We want to know how much load it can
carry in the development cycle").

One project grows in stages — about 100 lines, then +200 holding those (300), +400 (700), +800 (1,500), +1,600 (3,100)…
until a stage fails; if the first fails, 50 lines instead. The project is the package ledger/: one module per record
type, each with the same ten functions, laid out as stubs with their specifics as a senior gives them; a stage adds
record types (expressed), keeps every earlier test passing (held), changes two earlier functions (re-expressed) and
adds a report that calls every module so far (continued). The tests come from a reference implementation, so they're
exact, and we run them — never the model's word. Each stage is a fresh task (the junior protocol, rule A41)."""

from __future__ import annotations

import math
import os
import re
import subprocess
import sys

TARGETS = (100, 300, 700, 1500, 3100, 6300, 12700)   # lines held after each stage: +200, +400, +800, +1,600…
FIRST_FALLBACK = 50                                    # when the first stage fails: a smaller first step

NOUNS = ("book", "track", "order", "player", "parcel", "recipe", "ticket", "sensor", "invoice", "course", "plant", "trip",
         "device", "account", "shipment", "lesson", "booking", "asset", "chore", "ride", "meal", "tool", "vehicle",
         "fixture", "song", "film", "part", "crate", "room", "permit", "sample", "batch", "claim", "lead", "show",
         "gift", "voucher", "card", "bin", "slot", "kit", "route", "cargo", "lot", "unit", "bill", "pack", "fund",
         "deck", "spool")
ADJ = ("", "spare", "local", "daily", "bulk", "fresh", "prime")
KEYS = ("title", "name", "code", "label", "ref", "tag")
NUMS = ("count", "pages", "seats", "units", "qty", "stock")
DECS = ("price", "weight", "rate", "cost", "score", "volume")
CATS = ("genre", "kind", "zone", "group", "grade", "category")


def entity(i: int) -> dict:
    """Record type i: its name and its four fields (the key text, a whole number, a decimal, a category)."""
    noun, adj = NOUNS[i % len(NOUNS)], ADJ[(i // len(NOUNS)) % len(ADJ)]
    return {"e": f"{adj}_{noun}" if adj else noun, "k": KEYS[i % 6], "n": NUMS[(i // 6) % 6],
            "x": DECS[(i + 3) % 6], "c": CATS[(i // 2) % 6]}


# the reference: each function, version 1 (and 2 where a stage changes it)
REF = {
    "make": '''def make_{e}({k}, {n}, {x}, {c}):
    if not str({k}).strip():
        raise ValueError("{k} is empty")
    if {n} < 0 or {x} < 0:
        raise ValueError("negative")
    return {{"{k}": str({k}).strip(), "{n}": int({n}), "{x}": float({x}), "{c}": str({c})}}
''',
    "key": '''def {e}_key(item):
    return item["{k}"].strip().lower()
''',
    "total": '''def {e}_total(items):
    return round(sum(i["{n}"] * i["{x}"] for i in items), 2)
''',
    "total2": '''def {e}_total(items):
    return round(sum(i["{n}"] * i["{x}"] for i in items if i["{n}"] >= 3), 1)
''',
    "group": '''def {e}_by_{c}(items):
    out = {{}}
    for i in items:
        out.setdefault(i["{c}"], []).append({e}_key(i))
    return {{g: sorted(keys) for g, keys in out.items()}}
''',
    "top": '''def {e}_top(items, count):
    ranked = sorted(items, key=lambda i: (-i["{x}"], {e}_key(i)))
    return [{e}_key(i) for i in ranked[:count]]
''',
    "find": '''def {e}_find(items, key):
    for i in items:
        if {e}_key(i) == key.strip().lower():
            return i
    return None
''',
    "update": '''def {e}_update(item, field, value):
    data = dict(item)
    data[field] = value
    return make_{e}(data["{k}"], data["{n}"], data["{x}"], data["{c}"])
''',
    "summary": '''def {e}_summary(item):
    return f"{{item['{k}']}} ({{item['{c}']}}): {{item['{n}']}} x {{item['{x}']:.2f}}"
''',
    "summary2": '''def {e}_summary(item):
    return f"{{item['{k}']}} [{{item['{c}']}}] {{item['{n}']}}@{{item['{x}']:.2f}}"
''',
    "from_line": '''def {e}_from_line(line):
    {k}, {n}, {x}, {c} = line.split("|")
    return make_{e}({k}, int({n}), float({x}), {c})
''',
    "to_line": '''def {e}_to_line(item):
    return "|".join([item["{k}"], str(item["{n}"]), str(item["{x}"]), item["{c}"]])
''',
}
FUNCS = ("make", "key", "total", "group", "top", "find", "update", "summary", "from_line", "to_line")
SPECS = {  # the same ten for every record type E with fields k (key text), n (whole number), x (decimal), c (category)
    "make": ("make_E(k, n, x, c)", "a dict of the four fields (k stripped, n int, x float, c str); ValueError if k is "
             "empty after stripping, or n or x is negative"),
    "key": ("E_key(item)", "item's k, stripped and lowercased"),
    "total": ("E_total(items)", "the sum of n * x over the items, rounded to 2 decimals"),
    "group": ("E_by_c(items)", "a dict from each c to the sorted list of E_key of its items"),
    "top": ("E_top(items, count)", "the E_key of the count items with the highest x, ties by E_key ascending"),
    "find": ("E_find(items, key)", "the first item whose E_key equals key stripped and lowercased, else None"),
    "update": ("E_update(item, field, value)", "a new record with that field set to value, made (and checked) by "
               "make_E"),
    "summary": ("E_summary(item)", "the text f\"{k} ({c}): {n} x {x:.2f}\" with the item's values"),
    "from_line": ("E_from_line(line)", "the record from 'k|n|x|c' (n as int, x as float), made by make_E"),
    "to_line": ("E_to_line(item)", "'k|n|x|c' joined with '|': k, str(n), str(x), c"),
}
CHANGES = {
    "summary2": "now returns f\"{k} [{c}] {n}@{x:.2f}\" (square brackets around c, no colon, '@' between n and x)",
    "total2": "now sums only the items whose n is at least 3, rounded to 1 decimal",
}


def code(ent: dict, fn: str) -> str:
    return REF[fn].format(**ent)


def name_of(ent: dict, fn: str) -> str:
    return {"make": f"make_{ent['e']}", "group": f"{ent['e']}_by_{ent['c']}"}.get(fn, f"{ent['e']}_{fn}")


def body_lines(text: str) -> int:
    """Lines of code written: not blank, comments, docstrings, def lines or the stubs' raise."""
    n, in_doc = 0, False
    for line in text.splitlines():
        s = line.strip()
        if s.startswith('"""'):
            in_doc = not (s.count('"""') >= 2) and not in_doc
            continue
        if in_doc or not s or s.startswith(("#", "def ", "import ", "from ")) or "NotImplementedError" in s:
            continue
        n += 1
    return n


PER_ENTITY = sum(body_lines(code(entity(0), f)) for f in FUNCS)   # ~30 lines a record type


class Project:
    """The growing project on disk, and the reference state its tests are made from."""

    def __init__(self, root: str) -> None:
        self.root, self.ents, self.version, self.stage, self.reports = root, [], {}, 0, []
        self.changed_now: set = set()   # (record type, function) changed in this stage
        self.kinds: dict = {}           # test name -> new / held / changed / report, this stage
        os.makedirs(os.path.join(root, "ledger"), exist_ok=True)
        open(os.path.join(root, "ledger", "__init__.py"), "a").close()

    def lines(self) -> int:
        d = os.path.join(self.root, "ledger")
        return sum(body_lines(open(os.path.join(d, f), encoding="utf-8").read())
                   for f in sorted(os.listdir(d)) if f.endswith(".py"))

    def grow(self, target: int) -> str:
        """The next stage, laid out (stubs, tests) for `target` lines in all; the task, as a senior gives it."""
        self.stage += 1
        s = self.stage
        have = len(self.ents)
        want = max(have + 1, math.ceil(target / PER_ENTITY))
        new = [dict(entity(i), stage=s) for i in range(have, want)]
        changed = []
        self.changed_now = set()
        if have:  # re-expressed: two earlier functions change
            for j, (fn, v2) in enumerate((("summary", "summary2"), ("total", "total2"))):
                old = self.ents[(s * 3 + j) % have]
                if self.version.get((old["e"], fn)) != v2:
                    self.version[(old["e"], fn)] = v2
                    changed.append((old, fn, v2))
                    self.changed_now.add((old["e"], fn))
        self.ents += new
        for ent in new:
            with open(os.path.join(self.root, "ledger", f"{ent['e']}.py"), "w", encoding="utf-8") as f:
                f.write(f'"""Records of {ent["e"].replace("_", " ")}."""\n')
                for fn in FUNCS:
                    sig, what = SPECS[fn]
                    sig = sig.replace("E_by_c", name_of(ent, "group")).replace("make_E", f"make_{ent['e']}").replace(
                        "E_", f"{ent['e']}_")
                    for field in "knxc":
                        sig = re.sub(rf"\b{field}\b", ent[field], sig)
                    f.write(f"\n\ndef {sig}:\n    \"\"\"{what}\"\"\"\n    raise NotImplementedError  # TODO\n")
        self.reports.append(s)
        with open(os.path.join(self.root, "ledger", "reports.py"), "a", encoding="utf-8") as f:
            f.write(f"\n\ndef report_s{s}(data):\n    \"\"\"Every record type so far, to its total.\"\"\"\n"
                    "    raise NotImplementedError  # TODO\n")
        self.write_tests()
        listing = "\n".join(f"- ledger/{e['e']}.py: k = {e['k']}, n = {e['n']}, x = {e['x']}, c = {e['c']}"
                            for e in new)
        specs = "\n".join(f"- {sig}: {what}" for sig, what in (SPECS[fn] for fn in FUNCS))
        changes = "\n".join(f"- {name_of(old, fn)} in ledger/{old['e']}.py {CHANGES[v2].replace('{k}', old['k'])}"
                            .replace("{c}", old["c"]).replace("{n}", old["n"]).replace("{x}", old["x"])
                            for old, fn, v2 in changed)
        earlier = ", ".join(f"ledger/{e['e']}.py" for e in self.ents if e["stage"] < s)
        return (f"Stage {s} of the package ledger/ (one module per record type; ledger/reports.py for reports).\n"
                + (f"Already there, and it must keep working: {earlier}. Read what you need of it.\n" if earlier else "")
                + f"New record types, each laid out as stubs in its own module (its fields: k is the key text, n a "
                  f"whole number, x a decimal, c a category):\n{listing}\n"
                  f"Each record type has the same ten functions — E is the type's name, k/n/x/c its fields:\n{specs}\n"
                + (f"Change these existing functions:\n{changes}\n" if changes else "")
                + f"In ledger/reports.py, fill report_s{s}(data): data maps a record type's name ('{new[0]['e']}', "
                  f"…) to a list of its records; return a dict from every record type so far ({len(self.ents)} of "
                  f"them) to its E_total of that list (an empty list when the type is missing), using each module's "
                  f"own E_total. Earlier report_s functions stay as they are.\n"
                  "Use only Python's standard library. The tests are in test_ledger.py (don't change it): run "
                  "`python3 -m unittest test_ledger` and fix what fails, then answer with what you did.")

    def fill_reference(self) -> None:
        """The reference answer written into the project (for our own tests: every stage must be passable)."""
        for ent in self.ents:
            src = f'"""Records of {ent["e"]}."""\n\n\n' + "\n\n".join(
                code(ent, self.version.get((ent["e"], fn), fn)) for fn in FUNCS)
            with open(os.path.join(self.root, "ledger", f"{ent['e']}.py"), "w", encoding="utf-8") as f:
                f.write(src)
        out = ["from ledger import " + ", ".join(e["e"] for e in self.ents) + "\n"]
        for s in self.reports:
            upto = [e["e"] for e in self.ents if e["stage"] <= s]
            out.append(f"\ndef report_s{s}(data):\n    return {{"
                       + ", ".join(f"'{e}': {e}.{e}_total(data.get('{e}', []))" for e in upto) + "}\n")
        with open(os.path.join(self.root, "ledger", "reports.py"), "w", encoding="utf-8") as f:
            f.write("\n".join(out))

    def reference(self) -> dict:
        """The reference modules, executed: name -> namespace."""
        spaces = {}
        for ent in self.ents:
            ns: dict = {}
            src = "".join(code(ent, self.version.get((ent["e"], fn), fn)) for fn in FUNCS)
            exec(compile(src, f"ref_{ent['e']}", "exec"), ns)
            spaces[ent["e"]] = ns
        return spaces

    def write_tests(self) -> None:
        ref = self.reference()
        self.kinds = {}
        lines = ["import unittest\n", "from ledger import reports"]
        lines += [f"from ledger import {e['e']}" for e in self.ents]
        lines += ["\n\nclass Ledger(unittest.TestCase):"]
        for ent in self.ents:
            e, ns = ent["e"], ref[ent["e"]]
            k, c = ent["k"], ent["c"]
            items = [ns[f"make_{e}"](f" {e.title()}-{i} ", n, x, g)
                     for i, (n, x, g) in enumerate(((3, 2.5, "a"), (2, 10.0, "b"), (5, 2.5, "a")))]
            lit = repr(items)
            calls = {
                "make": (f"{e}.make_{e}(' {e.title()}-0 ', 3, 2.5, 'a')", repr(items[0])),
                "key": (f"{e}.{e}_key({repr(items[0])})", repr(ns[f"{e}_key"](items[0]))),
                "total": (f"{e}.{e}_total({lit})", repr(ns[f"{e}_total"](items))),
                "group": (f"{e}.{name_of(ent, 'group')}({lit})", repr(ns[name_of(ent, 'group')](items))),
                "top": (f"{e}.{e}_top({lit}, 2)", repr(ns[f"{e}_top"](items, 2))),
                "find": (f"{e}.{e}_find({lit}, ' {e.upper()}-2')", repr(ns[f"{e}_find"](items, f" {e.upper()}-2"))),
                "update": (f"{e}.{e}_update({repr(items[0])}, {repr(ent['n'])}, 7)",
                           repr(ns[f"{e}_update"](items[0], ent["n"], 7))),
                "summary": (f"{e}.{e}_summary({repr(items[0])})", repr(ns[f"{e}_summary"](items[0]))),
                "from_line": (f"{e}.{e}_from_line('Kit-9|4|1.5|z')", repr(ns[f"{e}_from_line"]("Kit-9|4|1.5|z"))),
                "to_line": (f"{e}.{e}_to_line({repr(items[2])})", repr(ns[f"{e}_to_line"](items[2]))),
            }
            kind = "new" if ent["stage"] == self.stage else "held"
            for fn in FUNCS:
                name = f"test_s{ent['stage']}_{e}_{fn}"
                self.kinds[name] = "changed" if (e, fn) in self.changed_now else kind
                call, want = calls[fn]
                lines.append(f"    def {name}(self):\n"
                             f"        self.assertEqual({call}, {want})")
            self.kinds[f"test_s{ent['stage']}_{e}_make_checks"] = kind
            lines.append(f"    def test_s{ent['stage']}_{e}_make_checks(self):\n"
                         f"        with self.assertRaises(ValueError):\n"
                         f"            {e}.make_{e}('  ', 1, 1.0, 'a')\n"
                         f"        with self.assertRaises(ValueError):\n"
                         f"            {e}.make_{e}('x', -1, 1.0, 'a')")
        for s in self.reports:
            upto = [e for e in self.ents if e["stage"] <= s]
            data = {e["e"]: [ref[e["e"]][f"make_{e['e']}"]("A", 2, 1.25, "g")] for e in upto[::2]}
            want = {e["e"]: ref[e["e"]][f"{e['e']}_total"](data.get(e["e"], [])) for e in upto}
            ripple = any((e["e"], "total") in self.changed_now for e in upto)  # its totals changed this stage
            self.kinds[f"test_s{s}_report"] = "report" if s == self.stage else "changed" if ripple else "held"
            lines.append(f"    def test_s{s}_report(self):\n        self.assertEqual(reports.report_s{s}({data!r}), "
                         f"{want!r})")
        lines.append("\n\nif __name__ == '__main__':\n    unittest.main()\n")
        with open(os.path.join(self.root, "test_ledger.py"), "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

    def check(self) -> dict:
        """The tests, run by us: how many passed of each kind this stage (new, held, changed, report)."""
        try:
            r = subprocess.run([sys.executable, "-m", "unittest", "-v", "test_ledger"], cwd=self.root,
                               capture_output=True, text=True, timeout=300)
            out = r.stderr + r.stdout
        except subprocess.TimeoutExpired:
            return {"ok": False, "why": "the tests didn't finish in 5 minutes"}
        res = {}
        for m in re.finditer(r"^(test_\w+) \(.*?\) \.\.\. (ok|FAIL|ERROR)", out, re.M):
            name, verdict = m.group(1), m.group(2)
            got = res.setdefault(self.kinds.get(name, "held"), [0, 0])
            got[0] += verdict == "ok"
            got[1] += 1
        if not res:  # it didn't even import
            tail = out.strip().splitlines()
            return {"ok": False, "why": (tail[-1] if tail else "the tests didn't run")[:200]}
        ok = all(p == t for p, t in res.values())
        return {"ok": ok, **{k: f"{p}/{t}" for k, (p, t) in res.items()},
                "why": "" if ok else next((ln for ln in out.splitlines() if ln.startswith(("FAIL:", "ERROR:"))), "")}
