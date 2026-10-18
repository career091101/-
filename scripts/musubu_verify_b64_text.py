#!/usr/bin/env python3
"""Verify plain .b64 text (e.g. from Drive read_file) against expected gzip sha256."""
from __future__ import annotations

import argparse
import base64
import hashlib
import sys
from pathlib import Path


def gzip_sha_from_b64_text(text: str) -> str:
    gz = base64.b64decode(text.strip())
    return hashlib.sha256(gz).hexdigest()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("b64_text_path", type=Path, help="File containing Drive readback .b64 text")
    p.add_argument("--expected-gzip-sha256", required=True)
    args = p.parse_args()
    got = gzip_sha_from_b64_text(args.b64_text_path.read_text())
    ok = got == args.expected_gzip_sha256
    print("gzip_sha256", got, "OK" if ok else "MISMATCH")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
