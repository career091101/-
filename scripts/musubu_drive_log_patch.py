#!/usr/bin/env python3
"""Patch drive_publisher_log.json with upload/verify records (publisher log is shared)."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

DRIVE_LOG = Path("/workspace/musubu-data/drive_publisher_log.json")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--name", required=True, help="Drive file title e.g. master_banks.json.b64")
    p.add_argument("--file-id", required=True)
    p.add_argument("--gzip-sha256", required=True)
    p.add_argument("--readback-verified", action="store_true")
    args = p.parse_args()

    log = json.loads(DRIVE_LOG.read_text()) if DRIVE_LOG.is_file() else {
        "schema": "musubu_drive_publisher_log_v1",
        "folder_id": "1kR8pPEahMbgj4ErAzHxCqwU85tMPL8Ea",
        "uploads": [],
    }
    uploads = log.setdefault("uploads", [])
    rec = None
    for u in uploads:
        if u.get("name") == args.name:
            rec = u
            break
    if rec is None:
        rec = {"name": args.name}
        uploads.append(rec)
    rec["file_id"] = args.file_id
    rec["gzip_sha256"] = args.gzip_sha256
    if args.readback_verified:
        rec["readback_verified"] = True

    pending = log.get("pending_b64_under_50kb") or []
    pending_large = log.get("pending_large") or []
    if args.name in pending:
        pending.remove(args.name)
    if args.name in pending_large:
        pending_large.remove(args.name)
    log["pending_b64_under_50kb"] = pending
    log["pending_large"] = pending_large

    DRIVE_LOG.write_text(json.dumps(log, ensure_ascii=False, indent=2) + "\n")
    print("patched", args.name, "verified=", args.readback_verified)


if __name__ == "__main__":
    main()
