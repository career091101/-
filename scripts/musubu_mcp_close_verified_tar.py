#!/usr/bin/env python3
"""Close a parts4k upload: merge verified_batch JSON, verify local concat, patch drive log."""
from __future__ import annotations

import argparse
import base64
import fcntl
import hashlib
import json
from pathlib import Path

DRIVE_LOG = Path("/workspace/musubu-data/drive_publisher_log.json")


def load_all_rows(queue_dir: Path) -> dict[int, dict]:
    by_idx: dict[int, dict] = {}
    for vb in sorted(queue_dir.glob("verified_batch_*.json")):
        for row in json.loads(vb.read_text()):
            by_idx[int(row["index"])] = row
    return by_idx


def verify_local_concat(manifest: dict) -> None:
    parts = manifest["parts"]
    b64 = "".join(Path(p["local_part_path"]).read_text() for p in parts)
    if hashlib.sha256(b64.encode()).hexdigest() != manifest["b64_sha256"]:
        raise SystemExit("STOP: b64 concat sha mismatch")
    tar = base64.b64decode(b64)
    if hashlib.sha256(tar).hexdigest() != manifest["tar_sha256"]:
        raise SystemExit("STOP: tar sha mismatch after b64 decode")


def patch_drive_log(tar_name: str, manifest: dict, by_idx: dict[int, dict]) -> None:
    expected = manifest["part_count"]
    if len(by_idx) != expected:
        raise SystemExit(f"STOP: expected {expected} parts, got {len(by_idx)}")
    for i in range(1, expected + 1):
        row = by_idx[i]
        if not row.get("readback_verified"):
            raise SystemExit(f"STOP: part {i} not readback_verified")
        want = next(p["sha256"] for p in manifest["parts"] if p["index"] == i)
        if row.get("sha256") != want:
            raise SystemExit(f"STOP: part {i} sha mismatch in verified batch")

    mcp_parts = [
        {
            "index": i,
            "title": by_idx[i]["title"],
            "file_id": by_idx[i]["file_id"],
        }
        for i in range(1, expected + 1)
    ]

    DRIVE_LOG.parent.mkdir(parents=True, exist_ok=True)
    with DRIVE_LOG.open("a+") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.seek(0)
        log = json.loads(f.read() or "{}")
        uploads = log.setdefault("uploads", [])
        rec = None
        for u in uploads:
            if u.get("name") == tar_name:
                rec = u
                break
        if rec is None:
            rec = {"name": tar_name}
            uploads.append(rec)
        rec.update(
            {
                "tar_sha256": manifest["tar_sha256"],
                "tar_bytes": manifest["tar_bytes"],
                "text_sha256": manifest["b64_sha256"],
                "part_count": expected,
                "local_verified": True,
                "readback_verified": True,
                "status": "verified_b64_parts",
                "mcp_b64_parts": mcp_parts,
                "note": (
                    f"{expected} Drive text parts. Local concatenation matches "
                    f"tar SHA256 {manifest['tar_sha256']} ({manifest['tar_bytes']} bytes) "
                    f"and text SHA256 {manifest['b64_sha256']}. "
                    "Each verified_batch entry has readback_verified true."
                ),
            }
        )
        f.seek(0)
        f.truncate()
        f.write(json.dumps(log, ensure_ascii=False, indent=2))
        f.write("\n")
        f.flush()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--queue-dir", type=Path, required=True)
    args = ap.parse_args()
    queue_dir = args.queue_dir.resolve()
    manifest = json.loads((queue_dir / "manifest.json").read_text())
    tar_name = manifest["final_name"]
    by_idx = load_all_rows(queue_dir)
    verify_local_concat(manifest)
    patch_drive_log(tar_name, manifest, by_idx)
    print("CLOSED", tar_name, "parts", len(by_idx), "status=verified_b64_parts")


if __name__ == "__main__":
    main()
