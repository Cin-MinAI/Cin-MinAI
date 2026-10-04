#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Have Mozilla sign the Cin-MinAI Firefox extension (D14): pack src/cin_minai/firefox/extension, upload it to
addons.mozilla.org as an unlisted version (signed, not listed in the store), wait for the signature, download it.

    python3 distro/firefox-sign.py            (WSL; key from ~/.config/cinminai/amo.env, never printed)

Output: $WORK/firefox/assistant-VERSION.xpi (config.env's WORK), which cinminai-firefox packages. A version that's
already signed is downloaded again instead of uploaded. Tokens use AMO's clock: this PC's runs ~30 s fast, and AMO
rejects tokens from the future (the spike's lesson, spikes/firefox/amo_fetch.py).
"""

import base64
import email.utils
import hashlib
import hmac
import io
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
import zipfile

GUID = "assistant@cinminai.org"
API = "https://addons.mozilla.org/api/v5"
HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..", "src", "cin_minai", "firefox", "extension")
OUT = os.path.join(os.environ.get("WORK") or os.path.expanduser("~/cinminai-build"), "firefox")
_skew = None


def credentials() -> tuple[str, str]:
    path = os.path.expanduser("~/.config/cinminai/amo.env")
    env = dict(line.split("=", 1) for line in open(path).read().splitlines() if "=" in line)
    return env["WEB_EXT_API_KEY"].strip(), env["WEB_EXT_API_SECRET"].strip()


def b64(data: bytes) -> bytes:
    return base64.urlsafe_b64encode(data).rstrip(b"=")


def skew() -> float:
    global _skew
    if _skew is None:
        try:
            with urllib.request.urlopen(urllib.request.Request(API + "/", method="HEAD"), timeout=15) as r:
                headers = r.headers
        except urllib.error.HTTPError as e:
            headers = e.headers
        _skew = email.utils.parsedate_to_datetime(headers["Date"]).timestamp() - time.time()
    return _skew


def auth() -> str:
    key, secret = credentials()
    now = int(time.time() + skew())
    head = b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    body = b64(json.dumps({"iss": key, "jti": uuid.uuid4().hex, "iat": now, "exp": now + 60}).encode())
    sig = b64(hmac.new(secret.encode(), head + b"." + body, hashlib.sha256).digest())
    return "JWT " + (head + b"." + body + b"." + sig).decode()


def call(url: str, data: bytes | None = None, ctype: str | None = None, raw: bool = False):
    req = urllib.request.Request(url, data=data, headers={"Authorization": auth(), **({"Content-Type": ctype}
                                                                                       if ctype else {})})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            body = r.read()
    except urllib.error.HTTPError as e:
        sys.exit(f"AMO said {e.code} for {url.split('?')[0]}: {e.read()[:600].decode(errors='replace')}")
    return body if raw else json.loads(body or b"{}")


def pack() -> tuple[str, bytes]:
    """The extension as a zip, files in a fixed order with a fixed date (the same bytes from the same source)."""
    with open(os.path.join(SRC, "manifest.json"), encoding="utf-8") as f:
        version = json.load(f)["version"]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name in sorted(os.listdir(SRC)):
            info = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            with open(os.path.join(SRC, name), "rb") as f:
                z.writestr(info, f.read())
    return version, buf.getvalue()


def multipart(fields: dict, filename: str, data: bytes) -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    out = b""
    for k, v in fields.items():
        out += f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
    out += (f'--{boundary}\r\nContent-Disposition: form-data; name="upload"; filename="{filename}"\r\n'
            "Content-Type: application/zip\r\n\r\n").encode() + data + f"\r\n--{boundary}--\r\n".encode()
    return out, f"multipart/form-data; boundary={boundary}"


def existing(version: str) -> dict | None:
    versions = call(f"{API}/addons/addon/{GUID}/versions/?filter=all_with_unlisted")["results"]
    return next((v for v in versions if v["version"] == version), None)


def main() -> int:
    version, data = pack()
    out = os.path.join(OUT, f"assistant-{version}.xpi")
    v = existing(version)
    if v is None:
        print(f"uploading {GUID} {version} (unlisted) …", flush=True)
        body, ctype = multipart({"channel": "unlisted"}, f"assistant-{version}.zip", data)
        up = call(f"{API}/addons/upload/", body, ctype)
        for _ in range(60):
            if up.get("processed"):
                break
            time.sleep(5)
            up = call(f"{API}/addons/upload/{up['uuid']}/")
        if not up.get("valid"):
            print(json.dumps(up.get("validation", {}).get("messages", up), indent=1)[:4000])
            return 1
        warnings = [m["message"] for m in up.get("validation", {}).get("messages", []) if m.get("type") == "warning"]
        for w in warnings:
            print("  AMO warning:", w)
        call(f"{API}/addons/addon/{GUID}/versions/", json.dumps({"upload": up["uuid"]}).encode(), "application/json")
    for _ in range(60):  # signing usually takes a minute or two; up to ~20 min
        v = existing(version)
        status = (v or {}).get("file", {}).get("status")
        print(f"{version}: {status or 'waiting'}", flush=True)
        if status == "public":
            os.makedirs(OUT, exist_ok=True)
            with open(out, "wb") as f:
                f.write(call(v["file"]["url"], raw=True))
            print(f"signed: {out} ({os.path.getsize(out)} bytes)")
            return 0
        if status in ("disabled", "rejected"):
            return 1
        time.sleep(20)
    return 1


if __name__ == "__main__":
    sys.exit(main())
