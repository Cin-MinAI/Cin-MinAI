# SPDX-License-Identifier: GPL-3.0-or-later
"""cinminai-diag — the diagnostics' command (SPEC §20.4). It only reads.

    cinminai-diag [status]            the findings, short
    cinminai-diag report [--json]     the full report (Markdown, or JSON)
    cinminai-diag show CODE           one finding with its fixes
    cinminai-diag guide [CODE]        what the assistant's diagnose tool sees (JSON)
    cinminai-diag capture FILE [NOTE] record this machine's evidence as a test case (SPEC §20.7)
    --fixture FILE                    read a recorded case instead of this machine
"""

from __future__ import annotations

import json
import sys

from . import probes, report, rules
from .source import FixtureSource, LiveSource, Recorder


def main(argv: list[str]) -> int:
    src = LiveSource()
    if "--fixture" in argv:
        i = argv.index("--fixture")
        src = FixtureSource(argv[i + 1])
        argv = argv[:i] + argv[i + 2:]
    as_json = "--json" in argv
    argv = [a for a in argv if a != "--json"]
    cmd = argv[0] if argv else "status"

    if cmd == "capture":
        if len(argv) < 2:
            print("usage: cinminai-diag capture FILE [NOTE]", file=sys.stderr)
            return 2
        rec = Recorder(probes.keep_line)
        probes.collect(rec)
        rec.save(argv[1], " ".join(argv[2:]))
        print(f"recorded {len(rec.cmds)} commands and {len(rec.files)} files to {argv[1]}")
        return 0

    ev = probes.collect(src)
    rep = report.build(ev, rules.evaluate(ev))
    if cmd == "report":
        print(json.dumps(rep, indent=1, ensure_ascii=False) if as_json else report.markdown(rep))
    elif cmd == "guide":
        print(json.dumps(report.guide_view(rep, argv[1] if len(argv) > 1 else None), indent=1, ensure_ascii=False))
    elif cmd == "show":
        f = next((f for f in rep["findings"] if len(argv) > 1 and f["code"] == argv[1].upper()), None)
        if not f:
            print(f"no finding {argv[1] if len(argv) > 1 else '(give a code)'}", file=sys.stderr)
            return 1
        print(json.dumps(f, indent=1, ensure_ascii=False) if as_json else
              report.markdown({**rep, "findings": [f]}).split("## Findings", 1)[1].split("## Recent starts")[0].strip())
    elif cmd == "status":
        if not rep["findings"]:
            print("No faults found.")
        for f in rep["findings"]:
            print(f"{f['code']}  {f['status']:<7}  {f['title']}")
    else:
        print(__doc__, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
