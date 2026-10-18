#!/usr/bin/env python3
"""Verify Drive download_file JSON: base64 outer -> .b64 text -> gzip sha256."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sys
from pathlib import Path


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("drive_download_json", help="Path to download_file JSON or raw base64 field")
    p.add_argument("--expected-gzip-sha256", required=True)
    args = p.parse_args()
    arg = args.drive_download_json
    raw = Path(arg).read_text() if not arg.strip().startswith("{") else arg

    if raw.strip().startswith("{"):
        data = json.loads(raw)
        outer = data["base64"]
    else:
        outer = raw.strip()
    text = base64.b64decode(outer).decode("ascii")
    gz = base64.b64decode(text)
    got = hashlib.sha256(gz).hexdigest()
    ok = got == args.expected_gzip_sha256
    print("gzip_sha256", got, "OK" if ok else "MISMATCH")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
