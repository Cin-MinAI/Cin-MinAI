# SPDX-License-Identifier: GPL-3.0-or-later
"""Determinism and strict parsing for the ISO package inventory."""

import importlib.util
import os
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SPEC = importlib.util.spec_from_file_location("iso_package_inventory", os.path.join(ROOT, "distro", "iso-package-inventory.py"))
inventory_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(inventory_module)


class InventoryTests(unittest.TestCase):
    def test_packages_are_sorted_and_versions_preserved_exactly(self):
        result = inventory_module.inventory(b"zlib1g:amd64\t1:3.0-1\napt\t2.7.14build2\n", "fixture")
        self.assertIn("# Packages: 2", result)
        self.assertLess(result.index("apt\t2.7.14build2"), result.index("zlib1g:amd64\t1:3.0-1"))

    def test_bad_or_duplicate_manifest_is_rejected(self):
        for data in (b"not-a-row\n", b"apt\t1\napt\t2\n"):
            with self.subTest(data=data), self.assertRaises(ValueError):
                inventory_module.inventory(data, "fixture")


if __name__ == "__main__":
    unittest.main()
