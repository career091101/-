#!/usr/bin/env python3
"""Verify concatenated .b64 part texts decode to expected tar sha256."""
from __future__ import annotations

import argparse
import base64
import hashlib
import sys
from pathlib import Path


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("part_files", nargs="+", type=Path, help="Ordered part text files")
    p.add_argument("--expected-tar-sha256", required=True)
    args = p.parse_args()
    b64 = "".join(pf.read_text().strip() for pf in args.part_files)
    tar = base64.b64decode(b64)
    got = hashlib.sha256(tar).hexdigest()
    ok = got == args.expected_tar_sha256
    print("tar_sha256", got, "bytes", len(tar), "OK" if ok else "MISMATCH")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
