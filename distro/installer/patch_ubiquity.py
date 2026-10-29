#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Hook cinminai_installer.py (PLAN D47) into Mint's installer in an ISO's root file system:

    python3 patch_ubiquity.py ROOTFS        (build-iso.sh runs it in step 3)

Each change is an exact replacement that must match once: when an installer update moves the code, the build stops
here instead of shipping an installer we haven't read. Every hook is wrapped so a fault in ours leaves Mint's own
behaviour, never a broken page.
"""

from __future__ import annotations

import os
import shutil
import sys

PARTMAN = "usr/lib/ubiquity/plugins/ubi-partman.py"
MODULE = "usr/lib/ubiquity/ubiquity/cinminai.py"

CHANGES = [
    # the heading is kept so our lines can follow it once the options are named
    ("""    def set_autopartition_heading(self, heading):
        self.part_ask_heading.set_label(heading)

    def plugin_set_online_state(self, state):""",
     """    def set_autopartition_heading(self, heading):
        self.part_ask_heading.set_label(heading)
        self._cinminai_heading = heading

    def _cinminai_advice(self):
        # Cin-MinAI (D47): a drive of its own recommended, encryption suggested, under the heading
        try:
            from ubiquity import cinminai
            heading = getattr(self, '_cinminai_heading', None) or self.part_ask_heading.get_label()
            crypto = ''
            if self.use_crypto.get_visible():
                crypto = self.use_crypto.get_label() or ''
            self.part_ask_heading.set_label(
                heading + '\\n\\n' + cinminai.advice(self.use_device.get_label() or '', crypto))
        except Exception:
            pass

    def plugin_set_online_state(self, state):"""),
    # Erase disk ticked when a drive holds no other system (Mint ticks the first option offered: alongside)
    ("""        # Process the default selection
        self.part_ask_option_changed(None)

        # Make sure we're on the autopartitioning page.
        self.current_page = self.page_ask
""",
     """        try:  # Cin-MinAI (D47): with a drive that holds no other system, Erase disk is ticked
            from ubiquity import cinminai
            disks = (extra_options.get('use_device') or [None, {}])[1]
            if ('use_device' in options and self.use_device.get_sensitive() and cinminai.free_drive(
                    [(k, v[0]) for k, v in disks.items()], misc.os_prober()[0]) is not None):
                self.use_device.set_active(True)
        except Exception:
            pass
        self._cinminai_advice()

        # Process the default selection
        self.part_ask_option_changed(None)

        # Make sure we're on the autopartitioning page.
        self.current_page = self.page_ask
"""),
    # ...and that drive is the one offered first on the next page (Mint offers the first drive)
    ("""            if use_device:
                for disk in disks:
                    m.append([disk, ''])
                self.part_auto_select_drive.set_active(0)
""",
     """            if use_device:
                for disk in disks:
                    m.append([disk, ''])
                first = 0
                try:  # Cin-MinAI (D47): the drive that holds no other system first
                    from ubiquity import cinminai
                    free = cinminai.free_drive([(k, v[0]) for k, v in disks.items()], misc.os_prober()[0])
                    first = free if free is not None else 0
                except Exception:
                    pass
                self.part_auto_select_drive.set_active(first)
"""),
    # Something else: the start-up files follow the drive holding / (Mint defaults to the first drive)
    ("""        if grub_bootdev and grub_bootdev in paths:
            default = grub_bootdev
        else:
            default = misc.grub_default()
""",
     """        root = None
        if not self.is_bootdev_preseeded():
            try:  # Cin-MinAI (D47): the bootloader on the drive being installed, unless the person chose another
                from ubiquity import cinminai
                root = cinminai.root_disk(self.partition_cache, misc.partition_to_disk)
            except Exception:
                root = None
        auto = getattr(self, '_cinminai_auto', None)
        if root and root in paths and (not grub_bootdev or grub_bootdev == auto or grub_bootdev not in paths):
            default = root
            self._cinminai_auto = root
        elif grub_bootdev and grub_bootdev in paths:
            default = grub_bootdev
        else:
            default = misc.grub_default()
"""),
]


def patch(text: str) -> str:
    for old, new in CHANGES:
        n = text.count(old)
        if n != 1:
            raise SystemExit(f"patch_ubiquity: expected 1 match, found {n}, for:\n{old[:200]}")
        text = text.replace(old, new)
    return text


def main(rootfs: str) -> int:
    path = os.path.join(rootfs, PARTMAN)
    with open(path, encoding="utf-8") as f:
        text = f.read()
    if "Cin-MinAI (D47)" in text:
        print("patch_ubiquity: already patched")
    else:
        with open(path, "w", encoding="utf-8") as f:
            f.write(patch(text))
    shutil.copyfile(os.path.join(os.path.dirname(os.path.abspath(__file__)), "cinminai_installer.py"),
                    os.path.join(rootfs, MODULE))
    print("patch_ubiquity: D47 hooks in ubi-partman.py, ubiquity/cinminai.py installed")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
