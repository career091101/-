#!/usr/bin/env python3
"""Queue complete search tar.gz archives for upload; only drive_publisher_log.json writer."""
from __future__ import annotations

import fcntl
import hashlib
import json
import sys
import time
from pathlib import Path

DATA = Path("/workspace/musubu-data")
ARCHIVES_ROOT = DATA / "archives"
DRIVE_LOG = DATA / "drive_publisher_log.json"
FOLDER = "1kR8pPEahMbgj4ErAzHxCqwU85tMPL8Ea"
QUEUE = DATA / "publisher_mcp_queue"
STABLE_SEC = 15
SEARCH_RESOURCES = (
    "key_people",
    "companies",
    "recruits",
    "departments",
    "offices",
    "stores",
    "facilities",
)


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
    by_name: dict[str, dict] = {}
    for resource in SEARCH_RESOURCES:
        manifest = DATA / f"manifest_{resource}_archives.json"
        if not manifest.is_file():
            continue
        try:
            arts = json.loads(manifest.read_text()).get("artifacts") or []
        except Exception:
            continue
        for a in arts:
            if a.get("file"):
                by_name[a["file"]] = a
    return by_name


def already_handled(name: str, log: dict) -> bool:
    for u in log.get("uploads") or []:
        if u.get("name") != name:
            continue
        if u.get("readback_verified") or u.get("status") in (
            "queued_mcp_binary",
            "queued_rclone",
            "verified",
        ):
            return True
    return False


def queue_mcp_upload(tar_path: Path, rec: dict) -> None:
    """Queue upload for agent MCP worker or rclone helper (binary tar)."""
    QUEUE.mkdir(parents=True, exist_ok=True)
    tar_bytes = tar_path.read_bytes()
    sha = hashlib.sha256(tar_bytes).hexdigest()
    expected = rec.get("tar_sha256") or sha
    if sha != expected:
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
    rec = by_name.get(name)
    if not rec:
        tar_bytes = tar_path.read_bytes()
        rec = {
            "file": name,
            "tar_sha256": hashlib.sha256(tar_bytes).hexdigest(),
            "tar_bytes": len(tar_bytes),
        }
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
    while True:
        by_name = manifest_by_name()
        log = load_drive_log()
        changed = False
        for resource in SEARCH_RESOURCES:
            archive_dir = ARCHIVES_ROOT / resource
            if not archive_dir.is_dir():
                continue
            for tar in sorted(archive_dir.glob(f"{resource}_pages_*.tar.gz")):
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
