#!/usr/bin/env python3
"""Upload parts4k range via rclone + SHA readback; write verified_batch JSON.

Uses conservative Drive API pacing to avoid rateLimitExceeded.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

REMOTE = "musubu-drive"
PARENT_DEFAULT = "1kR8pPEahMbgj4ErAzHxCqwU85tMPL8Ea"
LOCK = Path("/tmp/musubu_rclone_verify_parts.lock")
RCLONE_BASE = [
    "rclone",
    "--log-level",
    "ERROR",
    "--drive-pacer-min-sleep",
    "3s",
    "--drive-pacer-burst",
    "1",
    "--retries",
    "5",
    "--low-level-retries",
    "10",
]


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def part_entry(manifest: dict, index: int) -> dict:
    for p in manifest["parts"]:
        if p["index"] == index:
            return p
    raise SystemExit(f"part {index} not in manifest")


def rclone(*args: str, timeout: int = 180) -> bytes:
    return subprocess.check_output(
        [*RCLONE_BASE, *args],
        stderr=subprocess.STDOUT,
        timeout=timeout,
    )


def drive_file_id(title: str, parent: str) -> str | None:
    proc = subprocess.run(
        [
            *RCLONE_BASE,
            "lsf",
            f"--drive-root-folder-id={parent}",
            "--files-only",
            "--format",
            "i",
            f"{REMOTE}:{title}",
        ],
        capture_output=True,
        timeout=120,
    )
    if proc.returncode != 0:
        return None
    out = proc.stdout.decode().strip()
    return out or None


def upload_and_id(local: Path, title: str, parent: str) -> str:
    existing = drive_file_id(title, parent)
    if existing:
        time.sleep(1)
        return existing
    rclone(
        "copyto",
        str(local),
        f"{REMOTE}:{title}",
        f"--drive-root-folder-id={parent}",
        timeout=300,
    )
    time.sleep(2)
    file_id = drive_file_id(title, parent)
    if not file_id:
        raise SystemExit(f"no file id after upload {title}")
    return file_id


def readback_text(title: str, parent: str) -> str:
    time.sleep(2)
    last: Exception | None = None
    for attempt in range(5):
        try:
            fd, name = tempfile.mkstemp(prefix="musubu_rb_")
            os.close(fd)
            tmp_path = Path(name)
            try:
                rclone(
                    "copyto",
                    f"{REMOTE}:{title}",
                    str(tmp_path),
                    f"--drive-root-folder-id={parent}",
                    timeout=300,
                )
                return tmp_path.read_text()
            finally:
                tmp_path.unlink(missing_ok=True)
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, OSError) as exc:
            last = exc
            time.sleep(5 + attempt * 3)
    raise SystemExit(f"readback failed for {title}: {last}")


def incremental_path(queue_dir: Path) -> Path:
    return queue_dir / ".verified_incremental.jsonl"


def append_incremental(queue_dir: Path, row: dict) -> None:
    path = incremental_path(queue_dir)
    with path.open("a") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


def load_verified_rows(queue_dir: Path) -> dict[int, dict]:
    by_idx: dict[int, dict] = {}
    inc = incremental_path(queue_dir)
    if inc.is_file():
        for line in inc.read_text().splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            by_idx[int(row["index"])] = row
    for vb in queue_dir.glob("verified_batch_*.json"):
        for row in json.loads(vb.read_text()):
            by_idx[int(row["index"])] = row
    return by_idx


def load_verified_indices(queue_dir: Path) -> set[int]:
    return set(load_verified_rows(queue_dir))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--queue-dir", type=Path, required=True)
    ap.add_argument("--start", type=int, required=True)
    ap.add_argument("--end", type=int, required=True)
    ap.add_argument("--parent-id", default=PARENT_DEFAULT)
    ap.add_argument("--skip-existing", action="store_true", default=True)
    args = ap.parse_args()

    LOCK.parent.mkdir(parents=True, exist_ok=True)
    with LOCK.open("w") as lockf:
        fcntl.flock(lockf, fcntl.LOCK_EX | fcntl.LOCK_NB)

        manifest = json.loads((args.queue_dir / "manifest.json").read_text())
        already = load_verified_indices(args.queue_dir) if args.skip_existing else set()
        rows: list[dict] = []
        for index in range(args.start, args.end + 1):
            if index in already:
                print(f"skip verified {index}", flush=True)
                continue
            p = part_entry(manifest, index)
            local = Path(p["local_part_path"])
            text = local.read_text()
            expected = p["sha256"]
            if sha256_text(text) != expected:
                raise SystemExit(f"local sha mismatch {index}")
            file_id = upload_and_id(local, p["title"], args.parent_id)
            rb = readback_text(p["title"], args.parent_id)
            if sha256_text(rb) != expected:
                raise SystemExit(f"readback sha mismatch {index}")
            row = {
                "index": index,
                "title": p["title"],
                "file_id": file_id,
                "sha256": expected,
                "readback_verified": True,
            }
            append_incremental(args.queue_dir, row)
            rows.append(row)
            print(f"ok {index} {file_id}", flush=True)
            time.sleep(1)

        if not rows:
            print("no new rows", flush=True)
            return

        out = args.queue_dir / f"verified_batch_{args.start:04d}_{args.end:04d}.json"
        if out.is_file():
            existing = json.loads(out.read_text())
            by_idx = {int(r["index"]): r for r in existing}
            for r in rows:
                by_idx[int(r["index"])] = r
            merged = [by_idx[i] for i in sorted(by_idx)]
            out.write_text(json.dumps(merged, indent=2) + "\n")
        else:
            out.write_text(json.dumps(rows, indent=2) + "\n")
        print(f"DONE {out} ({len(rows)} new)", flush=True)


if __name__ == "__main__":
    main()
