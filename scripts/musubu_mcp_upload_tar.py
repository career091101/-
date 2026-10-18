#!/usr/bin/env python3
"""Split large tar.gz into MCP-sized base64 parts; print upload plan JSON."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path

MAX_B64 = 900_000
PARENT = "1kR8pPEahMbgj4ErAzHxCqwU85tMPL8Ea"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("tar_path", type=Path)
    args = p.parse_args()
    tar_bytes = args.tar_path.read_bytes()
    sha = hashlib.sha256(tar_bytes).hexdigest()
    b64 = base64.b64encode(tar_bytes).decode("ascii")
    parts: list[dict] = []
    for i in range(0, len(b64), MAX_B64):
        chunk = b64[i : i + MAX_B64]
        idx = i // MAX_B64 + 1
        title = f"{args.tar_path.name}.b64.part{idx:02d}"
        parts.append(
            {
                "title": title,
                "parentId": PARENT,
                "text_chars": len(chunk),
                "part_index": idx,
                "textContent": chunk,
            }
        )
    print(
        json.dumps(
            {
                "source_tar": str(args.tar_path),
                "tar_sha256": sha,
                "tar_bytes": len(tar_bytes),
                "part_count": len(parts),
                "parts": parts,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
