#!/usr/bin/env python3
"""Local tar audit + upload preflight gates before Drive MCP upload."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

DATA = Path("/workspace/musubu-data")
MCP_QUEUE = DATA / "mcp_upload_queue"
DRIVE_LOG = DATA / "drive_publisher_log.json"
PUBLISHER_QUEUE = DATA / "publisher_mcp_queue"

COMPANIES_PROTECTED_PACK_UNTIL = 1833
SEARCH_TAR_PAGE_SIZE = 200

TAR_RE = re.compile(
    r"^(?P<resource>[a-z_]+)_pages_(?P<start>\d+)-(?P<end>\d+)\.tar\.gz$"
)
MEMBER_RE = re.compile(
    r"^(?P<resource>[a-z_]+)_page_(?P<page>\d+)\.json(?:\.gz)?$"
)

IN_FLIGHT_LOG_STATUSES = frozenset(
    {
        "pending",
        "uploading",
        "queued_mcp_binary",
        "queued_rclone",
        "verified_b64_parts_partial",
    }
)


def parse_tar_name(name: str) -> tuple[str, int, int]:
    m = TAR_RE.match(name)
    if not m:
        raise SystemExit(f"STOP: unrecognized tar name: {name!r}")
    return m.group("resource"), int(m.group("start")), int(m.group("end"))


def is_protected_drive_name(name: str) -> bool:
    if re.match(r"key_people_page_0000[1-3]\.json\.gz$", name):
        return True
    m = TAR_RE.match(name)
    if m and m.group("resource") == "companies":
        end = int(m.group("end"))
        if end <= COMPANIES_PROTECTED_PACK_UNTIL:
            return True
    return False


def expected_pages(
    resource: str, page_start: int, page_end: int
) -> list[int]:
    pages = list(range(page_start, page_end + 1))
    if resource == "companies" and page_start <= 70 <= page_end:
        pages = [p for p in pages if p != 70]
    return pages


def tar_is_stable(path: Path, stable_sec: float) -> bool:
    st = path.stat()
    age = time.time() - st.st_mtime
    if age < stable_sec:
        return False
    time.sleep(0.05)
    st2 = path.stat()
    return st.st_size == st2.st_size and st.st_mtime == st2.st_mtime


def audit_tar_members(
    path: Path,
    resource: str,
    bad: list[dict[str, Any]],
    pages: list[int],
) -> None:
    import tarfile

    with tarfile.open(path, "r:gz") as tar:
        for m in tar.getmembers():
            if not m.isfile():
                continue
            z = MEMBER_RE.search(m.name)
            if not z:
                bad.append({"member": m.name, "reason": "name_pattern"})
                continue
            if z.group("resource") != resource:
                bad.append(
                    {
                        "member": m.name,
                        "reason": "resource_mismatch",
                        "expected": resource,
                    }
                )
                continue
            f = tar.extractfile(m)
            if f is None:
                bad.append({"member": m.name, "reason": "not_extractable"})
                continue
            n = int(z.group("page"))
            raw = f.read()
            if raw[:2] == b"\x1f\x8b":
                try:
                    raw = gzip.decompress(raw)
                except OSError as exc:
                    bad.append(
                        {
                            "member": m.name,
                            "reason": "gzip_error",
                            "page": n,
                            "error": str(exc),
                        }
                    )
                    continue
            try:
                json.loads(raw)
            except json.JSONDecodeError as exc:
                bad.append(
                    {
                        "member": m.name,
                        "reason": "invalid_json",
                        "page": n,
                        "error": str(exc),
                    }
                )
                continue
            pages.append(n)


def collect_queue_reasons(target: str) -> list[str]:
    queued: list[str] = []
    parts4k = MCP_QUEUE / f"{target}.parts4k"
    if parts4k.is_dir():
        queued.append(f"parts4k:{parts4k.relative_to(DATA)}")
    pub_job = PUBLISHER_QUEUE / f"{target}.json"
    if pub_job.is_file():
        queued.append(f"publisher_mcp_queue:{pub_job.name}")
    if DRIVE_LOG.is_file():
        try:
            log = json.loads(DRIVE_LOG.read_text())
        except json.JSONDecodeError:
            log = {}
        for entry in log.get("uploads") or []:
            if entry.get("name") != target:
                continue
            status = entry.get("status")
            if status in IN_FLIGHT_LOG_STATUSES:
                queued.append(f"drive_log:{status}")
    return queued


def run_drive_name_check(name: str, cmd: str | None) -> subprocess.CompletedProcess[str]:
    if not cmd:
        return subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
    return subprocess.run(
        cmd.format(name=name),
        shell=True,
        check=False,
        capture_output=True,
        text=True,
    )


def main() -> None:
    ap = argparse.ArgumentParser(description="Musubu tar upload preflight")
    ap.add_argument("tar_path", type=Path, help="Local .tar.gz path")
    ap.add_argument("--resource", help="Override resource (default: from filename)")
    ap.add_argument("--page-start", type=int)
    ap.add_argument("--page-end", type=int)
    ap.add_argument(
        "--stable-sec",
        type=float,
        default=15.0,
        help="Require mtime age and unchanged size (default: 15)",
    )
    ap.add_argument(
        "--drive-check-cmd",
        help='Shell command; use {name} placeholder. stdout: one Drive title per line.',
    )
    ap.add_argument("--skip-drive", action="store_true")
    ap.add_argument("--skip-queue", action="store_true")
    args = ap.parse_args()

    p = args.tar_path.resolve()
    if not p.is_file():
        raise SystemExit(f"STOP: missing tar: {p}")

    resource, page_start, page_end = parse_tar_name(p.name)
    if args.resource:
        resource = args.resource
    if args.page_start is not None:
        page_start = args.page_start
    if args.page_end is not None:
        page_end = args.page_end

    if is_protected_drive_name(p.name):
        raise SystemExit(f"STOP: protected Drive asset {p.name!r}")

    bad: list[dict[str, Any]] = []
    pages: list[int] = []
    audit_tar_members(p, resource, bad, pages)

    expected = expected_pages(resource, page_start, page_end)
    stable = tar_is_stable(p, args.stable_sec)
    st = p.stat()
    sha = hashlib.sha256(p.read_bytes()).hexdigest()
    exact = sorted(pages) == expected and not bad

    print(
        "LOCAL",
        p.name,
        "SIZE",
        st.st_size,
        "SHA256",
        sha,
        "MEMBERS",
        len(pages),
        "UNIQUE",
        len(set(pages)),
        "RANGE",
        (min(pages), max(pages)) if pages else None,
        "BAD",
        len(bad),
        "STABLE",
        stable,
        "EXACT_200",
        exact,
    )

    if bad:
        raise SystemExit(f"STOP: local tar audit failed: {bad[:3]!r}")
    if not stable:
        raise SystemExit("STOP: tar not stable (still being written?)")
    if not exact:
        raise SystemExit(
            f"STOP: page set mismatch expected={len(expected)} got={len(pages)}"
        )

    if not args.skip_drive and args.drive_check_cmd:
        r = run_drive_name_check(p.name, args.drive_check_cmd)
        if r.returncode:
            raise SystemExit(
                f"STOP: Drive check failed (exit {r.returncode}): {r.stderr.strip()!r}"
            )
        existing = {ln.strip() for ln in r.stdout.splitlines() if ln.strip()}
        if p.name in existing:
            raise SystemExit("STOP: Drive check failed or name exists")

    if not args.skip_queue:
        queued = collect_queue_reasons(p.name)
        if queued:
            raise SystemExit(f"STOP: target appears in upload queue: {queued}")

    print("PREFLIGHT_PASS")


if __name__ == "__main__":
    main()
