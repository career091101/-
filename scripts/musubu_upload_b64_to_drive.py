#!/usr/bin/env python3
"""Print JSON lines {title, textContent, gzip_sha256} for each .b64 under musubu-data."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path("/workspace/musubu-data")
FOLDER_NOTE = "1kR8pPEahMbgj4ErAzHxCqwU85tMPL8Ea"


def main() -> None:
    paths = sorted(ROOT.rglob("*.b64"))
    if len(sys.argv) > 1:
        want = set(sys.argv[1:])
        paths = [p for p in paths if p.name in want or p.stem in want]
    for p in paths:
        text = p.read_text()
        gz = __import__("base64").b64decode(text)
        rec = {
            "title": p.name,
            "parentId": FOLDER_NOTE,
            "gzip_sha256": hashlib.sha256(gz).hexdigest(),
            "text_chars": len(text),
        }
        if len(text) > 950_000:
            print(json.dumps({**rec, "error": "too_large_for_mcp"}), flush=True)
            continue
        print(json.dumps({**rec, "textContent": text}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
