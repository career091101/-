#!/usr/bin/env python3
"""Split tar.gz into 4000-char b64 parts + manifest for MCP Drive upload."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path

PARENT = "1kR8pPEahMbgj4ErAzHxCqwU85tMPL8Ea"
PART_SIZE = 4000
QUEUE = Path("/workspace/musubu-data/mcp_upload_queue")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("tar_path", type=Path)
    args = p.parse_args()
    tar_bytes = args.tar_path.read_bytes()
    tar_sha = hashlib.sha256(tar_bytes).hexdigest()
    b64 = base64.b64encode(tar_bytes).decode("ascii")
    b64_sha = hashlib.sha256(b64.encode()).hexdigest()
    out_dir = QUEUE / f"{args.tar_path.name}.parts4k"
    out_dir.mkdir(parents=True, exist_ok=True)
    parts_meta: list[dict] = []
    for idx, start in enumerate(range(0, len(b64), PART_SIZE), start=1):
        chunk = b64[start : start + PART_SIZE]
        part_path = out_dir / f"part{idx:04d}.txt"
        part_path.write_text(chunk)
        parts_meta.append(
            {
                "index": idx,
                "title": f"{args.tar_path.name}.b64.part{idx:04d}",
                "text_chars": len(chunk),
                "sha256": hashlib.sha256(chunk.encode()).hexdigest(),
                "local_part_path": str(part_path),
            }
        )
    manifest = {
        "schema": "musubu_tar_b64_parts4k_v1",
        "final_name": args.tar_path.name,
        "parentId": PARENT,
        "tar_sha256": tar_sha,
        "tar_bytes": len(tar_bytes),
        "b64_chars": len(b64),
        "b64_sha256": b64_sha,
        "part_size": PART_SIZE,
        "part_count": len(parts_meta),
        "parts": parts_meta,
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(
        json.dumps(
            {
                "queue_dir": str(out_dir),
                "part_count": len(parts_meta),
                "tar_sha256": tar_sha,
            }
        )
    )


if __name__ == "__main__":
    main()
