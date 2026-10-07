# SPDX-License-Identifier: GPL-3.0-or-later
"""D84 coverage, step 2: match the inventory against the help cards (training/kb) by label key and by name.

    python3 -I training/kb/coverage_match.py . inventory.json match.json

A name match (marked *) can be a passing mention: read those cards before counting them (docs/d84-coverage.md).
"""
import importlib.util
import json
import re
import sys

repo, inv_path, out_path = sys.argv[1:4]
labels = json.load(open(f"{repo}/training/eval/guide/labels.json", encoding="utf-8"))["labels"]
english = {k: (v.get("en") if isinstance(v, dict) else v) for k, v in labels.items()}

cards = []
for mod in ("transition", "lessons", "terminal"):
    spec = importlib.util.spec_from_file_location(mod, f"{repo}/training/kb/{mod}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    for t in m.TOPICS:
        cards.append({"set": mod, "id": t["id"], "card": t.get("card", ""), "windows": t.get("windows", ""),
                      "keys": set(re.findall(r"\{([a-z_]+)\}", t.get("card", "")))})

inv = json.load(open(inv_path, encoding="utf-8"))
items = [a for a in inv["apps"] if not a["hidden"]]


def norm(s):
    return re.sub(r"[^a-z0-9 ]", " ", s.lower()).strip()


rows = []
for a in sorted(items, key=lambda a: (a["where"], a["name"].lower())):
    keys = {k for k, v in english.items() if v and norm(v) == norm(a["name"])}
    by_key = [c["id"] for c in cards if c["keys"] & keys]
    name = norm(a["name"])
    by_name = [c["id"] for c in cards if c["id"] not in by_key and name and
               re.search(r"\b" + re.escape(name) + r"\b", norm(c["card"]))]
    rows.append({"where": a["where"], "name": a["name"], "file": a["file"], "label_keys": sorted(keys),
                 "cards_by_key": by_key, "cards_by_name": by_name})

json.dump({"cards": len(cards), "label_keys": len(english), "rows": rows}, open(out_path, "w", encoding="utf-8"),
          indent=1, ensure_ascii=False)
covered = sum(1 for r in rows if r["cards_by_key"] or r["cards_by_name"])
print(f"cards {len(cards)}, items {len(rows)}, named by some card {covered}, by none {len(rows) - covered}")
for r in rows:
    hit = ",".join(r["cards_by_key"] + [x + "*" for x in r["cards_by_name"]])
    print(f"{r['where']:<8} {r['name']:<32} {('key:' + ','.join(r['label_keys'])) if r['label_keys'] else '-':<28} {hit[:70]}")
