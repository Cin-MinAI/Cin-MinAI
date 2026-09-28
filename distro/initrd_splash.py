#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""The live USB's boot splash (boot check 1, 2026-09-28: the live boot showed Mint's logo; the installed
system and the shutdown screen already show ours, from the live filesystem).

casper/initrd.lz is a chain of cpio archives (newc): uncompressed early ones (CPU microcode), then the main
one, compressed. Plymouth in the main one shows the theme `usr/share/plymouth/themes/default.plymouth`
points to. This swaps in our theme — the same files cinminai-branding installs — and changes nothing else:
every other member is copied byte for byte, the early archives aren't touched, and the main archive is
recompressed with the same compressor.

    initrd_splash.py list INITRD                       (the archives and the plymouth files in them)
    initrd_splash.py rebrand INITRD ROOTFS OUT         (ROOTFS: the live filesystem with our packages)
"""

from __future__ import annotations

import os
import stat
import subprocess
import sys

MAGIC = {b"\x28\xb5\x2f\xfd": ["zstd", "-q", "-d", "-c"], b"\xfd7zXZ": ["xz", "-d", "-c"],
         b"\x1f\x8b": ["gzip", "-d", "-c"], b"\x04\x22\x4d\x18": ["lz4", "-d", "-c"]}
PACK = {"zstd": ["zstd", "-q", "-19", "-T0", "-c"], "xz": ["xz", "--check=crc32", "-9", "-c"],
        "gzip": ["gzip", "-9", "-n", "-c"], "lz4": ["lz4", "-l", "-9", "-c"]}
THEMES = "usr/share/plymouth/themes"


def parse(data: bytes, pos: int = 0) -> tuple[list[dict], int]:
    """Members of one newc archive starting at pos; returns (members, end offset incl. padding)."""
    out = []
    while True:
        if data[pos:pos + 6] not in (b"070701", b"070702"):
            raise ValueError(f"no cpio header at {pos}")
        f = [int(data[pos + 6 + 8 * i: pos + 14 + 8 * i], 16) for i in range(13)]
        namesize, filesize = f[11], f[6]
        name = data[pos + 110: pos + 110 + namesize - 1].decode()
        dpos = (pos + 110 + namesize + 3) & ~3
        body = data[dpos: dpos + filesize]
        end = (dpos + filesize + 3) & ~3
        out.append({"name": name, "mode": f[1], "fields": f, "data": body, "raw": data[pos:end]})
        pos = end
        if name == "TRAILER!!!":
            while pos < len(data) and data[pos] == 0:
                pos += 1  # padding between archives
            return out, pos


def segments(data: bytes):
    """[(kind, payload)]: kind "cpio" (uncompressed archive bytes) or a compressor name (compressed tail)."""
    pos, segs = 0, []
    while pos < len(data):
        if data[pos:pos + 6] in (b"070701", b"070702"):
            _, end = parse(data, pos)
            segs.append(("cpio", data[pos:end]))
            pos = end
            continue
        for magic, cmd in MAGIC.items():
            if data[pos:pos + len(magic)] == magic:
                segs.append((cmd[0], data[pos:]))
                return segs
        raise ValueError(f"unknown data at {pos}")
    return segs


def decompress(kind: str, blob: bytes) -> bytes:
    cmd = next(c for m, c in MAGIC.items() if c[0] == kind)
    return subprocess.run(cmd, input=blob, capture_output=True, check=True).stdout


def header(name: str, mode: int, filesize: int, ino: int, mtime: int, nlink: int = 1) -> bytes:
    f = [ino, mode, 0, 0, nlink, mtime, filesize, 0, 0, 0, 0, len(name) + 1, 0]
    h = b"070701" + b"".join(b"%08X" % v for v in f) + name.encode() + b"\0"
    return h + b"\0" * (-len(h) % 4)


def member(name: str, mode: int, body: bytes, ino: int, mtime: int) -> bytes:
    return header(name, mode, len(body), ino, mtime) + body + b"\0" * (-len(body) % 4)


def list_cmd(path: str) -> None:
    data = open(path, "rb").read()
    for kind, blob in segments(data):
        raw = blob if kind == "cpio" else decompress(kind, blob)
        members, _ = parse(raw)
        print(f"{kind}: {len(blob)} bytes, {len(members)} members")
        for m in members:
            if "plymouth" in m["name"]:
                t = "link" if stat.S_ISLNK(m["mode"]) else "dir" if stat.S_ISDIR(m["mode"]) else "file"
                extra = f" -> {m['data'].decode()}" if t == "link" else ""
                print(f"   {t:4} {m['name']}{extra}")


def rebrand(path: str, rootfs: str, out: str) -> None:
    data = open(path, "rb").read()
    segs = segments(data)
    kind, blob = segs[-1]
    if kind == "cpio":
        raise SystemExit("the main archive isn't compressed: unexpected layout")
    members, _ = parse(decompress(kind, blob))
    names = {m["name"] for m in members}
    # our theme as the live filesystem selects it (cinminai-branding sets the alternative); the link is
    # absolute, so it's read, not followed (following it would look on the build machine)
    chosen = os.readlink(os.path.join(rootfs, "etc/alternatives/default.plymouth"))
    if chosen != f"/{THEMES}/cinminai/cinminai.plymouth":
        raise SystemExit(f"the live filesystem's splash is {chosen!r}, not ours (is cinminai-branding installed?)")
    theme_file = os.path.join(rootfs, chosen.lstrip("/"))
    theme_dir, theme = os.path.dirname(theme_file), "cinminai"
    mtime = int(os.environ.get("SOURCE_DATE_EPOCH", "0"))
    ino = max(m["fields"][0] for m in members) + 1
    new, replaced = [], False
    for m in members:
        n = m["name"]
        if n == "TRAILER!!!":
            # our theme's files, then the trailer
            new.append(member(f"{THEMES}/cinminai", stat.S_IFDIR | 0o755, b"", ino, mtime)); ino += 1
            for fn in sorted(os.listdir(theme_dir)):
                p = os.path.join(theme_dir, fn)
                if os.path.isfile(p) and f"{THEMES}/cinminai/{fn}" not in names:
                    new.append(member(f"{THEMES}/cinminai/{fn}", stat.S_IFREG | 0o644, open(p, "rb").read(), ino, mtime))
                    ino += 1
            new.append(m["raw"])
            continue
        if n == f"{THEMES}/default.plymouth":
            # the default theme: a link (or a copy) to the theme's .plymouth file
            link = f"/{THEMES}/cinminai/cinminai.plymouth"
            if stat.S_ISLNK(m["mode"]):
                new.append(member(n, stat.S_IFLNK | 0o777, link.encode(), m["fields"][0], mtime))
            else:
                new.append(member(n, stat.S_IFREG | 0o644, open(theme_file, "rb").read(), m["fields"][0], mtime))
            replaced = True
            continue
        new.append(m["raw"])
    if not replaced:
        raise SystemExit(f"no {THEMES}/default.plymouth in the initrd: nothing to rebrand")
    main = b"".join(new)
    packed = subprocess.run(PACK[kind], input=main, capture_output=True, check=True).stdout
    with open(out, "wb") as f:
        for k, b in segs[:-1]:
            f.write(b)
        f.write(packed)
    print(f"{out}: {theme} splash; main archive {len(blob)} -> {len(packed)} bytes ({kind})")


if __name__ == "__main__":
    if sys.argv[1:2] == ["list"]:
        list_cmd(sys.argv[2])
    elif sys.argv[1:2] == ["rebrand"]:
        rebrand(*sys.argv[2:5])
    else:
        sys.exit(__doc__)
