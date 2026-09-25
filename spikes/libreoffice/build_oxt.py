#!/usr/bin/env python3
"""Pack extension/ into cinminai-libreoffice.oxt (a zip). Usage: python3 build_oxt.py [OUT]"""

import os
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "extension")


def build(out: str) -> str:
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for root, dirs, files in os.walk(SRC):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for f in files:
                path = os.path.join(root, f)
                z.write(path, os.path.relpath(path, SRC))
    return out


if __name__ == "__main__":
    print(build(sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "cinminai-libreoffice.oxt")))
