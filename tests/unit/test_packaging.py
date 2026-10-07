# SPDX-License-Identifier: GPL-3.0-or-later
"""Every cin_minai module the shipped code imports is shipped by some package.

M4's actions/ was imported by the daemon for two commits but copied by no build.sh: an installed daemon would not have
started. This reads the package build scripts and the imports, so the next one fails here instead of on a machine."""

import os
import re
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SRC = os.path.join(ROOT, "src", "cin_minai")
PACKAGES = os.path.join(ROOT, "distro", "packages")
IMPORT = re.compile(r"^\s*(?:from|import)\s+cin_minai\.([a-z_]+)", re.M)


def shipped() -> set[str]:
    out = set()
    for name in os.listdir(PACKAGES):
        path = os.path.join(PACKAGES, name, "build.sh")
        if not os.path.exists(path):
            continue
        text = open(path, encoding="utf-8").read()
        out.update(re.findall(r'src/cin_minai/([a-z_]+)"? "\$py/"', text))
        for loop in re.findall(r"for pkg in ([a-z_ ]+); do\s+cp -r \"\$repo/src/cin_minai/\$pkg\"", text):
            out.update(loop.split())
    return out


class ShippedImports(unittest.TestCase):
    def test_every_imported_module_is_in_a_package(self):
        have = shipped()
        self.assertIn("daemon", have)           # the reader of build.sh still works
        missing = {}
        for module in sorted(have):
            for folder, _, files in os.walk(os.path.join(SRC, module)):
                for f in files:
                    if f.endswith(".py"):
                        path = os.path.join(folder, f)
                        for wanted in IMPORT.findall(open(path, encoding="utf-8").read()):
                            if wanted not in have and os.path.isdir(os.path.join(SRC, wanted)):
                                missing.setdefault(wanted, os.path.relpath(path, ROOT))
        self.assertEqual(missing, {}, "imported but no package ships it (module: first importer)")


if __name__ == "__main__":
    unittest.main()
