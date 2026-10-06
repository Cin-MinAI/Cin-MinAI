#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Run the real sandbox probes, then the mechanism/browser negative tests."""

import os
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def main() -> int:
    environment = {**os.environ, "PYTHONPATH": os.path.join(ROOT, "src")}
    commands = [
        [sys.executable, os.path.join(ROOT, "tests", "sandbox", "check_sandbox.py")],
        [sys.executable, "-m", "unittest", "discover", "-s", os.path.join(ROOT, "tests", "security"), "-p", "test_*.py"],
    ]
    for command in commands:
        result = subprocess.run(command, cwd=ROOT, env=environment, check=False)
        if result.returncode:
            return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
