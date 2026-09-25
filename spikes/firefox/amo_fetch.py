#!/usr/bin/env python3
"""Wait for an uploaded unlisted version to be signed on addons.mozilla.org and download it.

    python3 amo_fetch.py VERSION [OUT_DIR]      (WSL; key from ~/.config/cinminai/amo.env)

`web-ext sign` uploads fine but its status polling failed with "JWT iat (issued at time) is invalid":
the dev PC's clock (Windows, and WSL following it) was 30 s fast. This stamps tokens with AMO's
own time (from its Date header), one fresh token per request. The key is read from the private file
and never printed.
"""

import base64
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.request
import uuid

GUID = "assistant@cinminai.org"
API = "https://addons.mozilla.org/api/v5"


def credentials() -> tuple[str, str]:
    path = os.path.expanduser("~/.config/cinminai/amo.env")
    env = dict(line.split("=", 1) for line in open(path).read().splitlines() if "=" in line)
    return env["WEB_EXT_API_KEY"], env["WEB_EXT_API_SECRET"]


def b64(data: bytes) -> bytes:
    return base64.urlsafe_b64encode(data).rstrip(b"=")


_skew = None


def server_skew() -> float:
    """Seconds to add to our clock to match AMO's (a wrong local clock makes AMO reject tokens)."""
    global _skew
    if _skew is None:
        import email.utils
        import urllib.error
        try:
            with urllib.request.urlopen(urllib.request.Request(API + "/", method="HEAD"), timeout=15) as r:
                headers = r.headers
        except urllib.error.HTTPError as e:  # the API root answers 404, still with a Date header
            headers = e.headers
        server = email.utils.parsedate_to_datetime(headers["Date"]).timestamp()
        _skew = server - time.time()
        if abs(_skew) > 5:
            print(f"note: local clock is off by {-_skew:+.0f} s; using the server's time for tokens", flush=True)
    return _skew


def token(key: str, secret: str) -> str:
    now = int(time.time() + server_skew())
    head = b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    body = b64(json.dumps({"iss": key, "jti": uuid.uuid4().hex, "iat": now, "exp": now + 60}).encode())
    sig = b64(hmac.new(secret.encode(), head + b"." + body, hashlib.sha256).digest())
    return "JWT " + (head + b"." + body + b"." + sig).decode()


def get(url: str, raw: bool = False):
    key, secret = credentials()
    req = urllib.request.Request(url, headers={"Authorization": token(key, secret)})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read() if raw else json.load(r)


def main() -> int:
    version = sys.argv[1]
    out_dir = sys.argv[2] if len(sys.argv) > 2 else os.path.expanduser("~/cinminai-build/firefox/dist")
    for _ in range(45):  # up to ~15 minutes
        versions = get(f"{API}/addons/addon/{GUID}/versions/?filter=all_with_unlisted")["results"]
        v = next((x for x in versions if x["version"] == version), None)
        status = (v or {}).get("file", {}).get("status")
        print(f"{version}: {status or 'not uploaded yet'}", flush=True)
        if status == "public":
            out = os.path.join(out_dir, f"cinminai_assistant-{version}.xpi")
            os.makedirs(out_dir, exist_ok=True)
            with open(out, "wb") as f:
                f.write(get(v["file"]["url"], raw=True))
            print(f"signed: {out} ({os.path.getsize(out)} bytes)")
            return 0
        if status in ("disabled", "rejected"):
            return 1
        time.sleep(20)
    return 1


if __name__ == "__main__":
    sys.exit(main())
