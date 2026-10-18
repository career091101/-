#!/usr/bin/env python3
"""Upload complete key_people tar.gz archives; only drive_publisher_log.json writer."""
from __future__ import annotations

import fcntl
import hashlib
import json
import sys
import time
from pathlib import Path

ARCHIVES = Path("/workspace/musubu-data/archives/key_people")
MANIFEST = Path("/workspace/musubu-data/manifest_key_people_archives.json")
DRIVE_LOG = Path("/workspace/musubu-data/drive_publisher_log.json")
FOLDER = "1kR8pPEahMbgj4ErAzHxCqwU85tMPL8Ea"
QUEUE = Path("/workspace/musubu-data/publisher_mcp_queue")
STABLE_SEC = 15


def load_drive_log() -> dict:
    if DRIVE_LOG.is_file():
        return json.loads(DRIVE_LOG.read_text())
    return {"schema": "musubu_drive_publisher_log_v1", "folder_id": FOLDER, "uploads": []}


def save_drive_log(data: dict) -> None:
    """Exclusive write. Open append-only so flock is held before truncate."""
    DRIVE_LOG.parent.mkdir(parents=True, exist_ok=True)
    with DRIVE_LOG.open("a+") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.seek(0)
        f.truncate()
        f.write(json.dumps(data, ensure_ascii=False, indent=2))
        f.flush()


def manifest_by_name() -> dict[str, dict]:
    if not MANIFEST.is_file():
        return {}
    arts = json.loads(MANIFEST.read_text()).get("artifacts") or []
    return {a["file"]: a for a in arts if a.get("file")}


def already_handled(name: str, log: dict) -> bool:
    for u in log.get("uploads") or []:
        if u.get("name") != name:
            continue
        if u.get("readback_verified") or u.get("status") == "queued_mcp_binary":
            return True
    return False


def queue_mcp_upload(tar_path: Path, rec: dict) -> None:
    """Queue upload for agent MCP worker (binary tar exceeds MCP 1MB text limit)."""
    QUEUE.mkdir(parents=True, exist_ok=True)
    tar_bytes = tar_path.read_bytes()
    sha = hashlib.sha256(tar_bytes).hexdigest()
    if sha != rec.get("tar_sha256"):
        raise ValueError(f"tar sha mismatch {tar_path.name}")
    job = {
        "title": tar_path.name,
        "parentId": FOLDER,
        "local_path": str(tar_path),
        "tar_sha256": sha,
        "tar_bytes": len(tar_bytes),
        "queued_at_epoch": int(time.time()),
    }
    out = QUEUE / f"{tar_path.name}.json"
    out.write_text(json.dumps(job, indent=2))


def process_one(tar_path: Path, log: dict, by_name: dict[str, dict]) -> bool:
    name = tar_path.name
    if already_handled(name, log):
        return False
    if name not in by_name:
        return False
    rec = by_name[name]
    age = time.time() - tar_path.stat().st_mtime
    if age < STABLE_SEC:
        return False
    queue_mcp_upload(tar_path, rec)
    log.setdefault("uploads", []).append(
        {
            "name": name,
            "tar_sha256": rec.get("tar_sha256"),
            "local_verified": True,
            "readback_verified": False,
            "status": "queued_mcp_binary",
            "queued_at_epoch": int(time.time()),
        }
    )
    return True


def main() -> None:
    interval = float(sys.argv[1]) if len(sys.argv) > 1 else 45.0
    by_name = manifest_by_name()
    while True:
        log = load_drive_log()
        changed = False
        for tar in sorted(ARCHIVES.glob("key_people_pages_*.tar.gz")):
            try:
                if process_one(tar, log, by_name):
                    changed = True
            except Exception as exc:
                log.setdefault("publisher_errors", []).append(
                    {"file": tar.name, "error": str(exc), "ts": int(time.time())}
                )
                changed = True
        if changed:
            save_drive_log(log)
        time.sleep(interval)


if __name__ == "__main__":
    main()
