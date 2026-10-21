#!/usr/bin/env python3
"""O(1) fetch progress: append-only jsonl per resource."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

DATA = Path("/workspace/musubu-data")
PROGRESS_DIR = DATA / "progress"


def progress_path(resource: str) -> Path:
    return PROGRESS_DIR / f"{resource}.jsonl"


def append_page_progress(resource: str, rec: dict[str, Any]) -> None:
    PROGRESS_DIR.mkdir(parents=True, exist_ok=True)
    line = {
        "ts": int(time.time()),
        "kind": "page",
        "resource": resource,
        "page": rec.get("page"),
        "http_status": rec.get("http_status"),
        "gzip_sha256": rec.get("gzip_sha256"),
        "item_count": rec.get("item_count"),
        "meta": rec.get("meta"),
    }
    with progress_path(resource).open("a") as f:
        f.write(json.dumps(line, ensure_ascii=False) + "\n")


def append_archive_progress(resource: str, rec: dict[str, Any]) -> None:
    PROGRESS_DIR.mkdir(parents=True, exist_ok=True)
    line = {
        "ts": int(time.time()),
        "kind": "archive",
        "resource": resource,
        "file": rec.get("file"),
        "page_start": rec.get("page_start"),
        "page_end": rec.get("page_end"),
        "tar_sha256": rec.get("tar_sha256"),
    }
    with progress_path(resource).open("a") as f:
        f.write(json.dumps(line, ensure_ascii=False) + "\n")


def max_page_from_progress(resource: str) -> int | None:
    path = progress_path(resource)
    if not path.is_file():
        return None
    best: int | None = None
    for line in path.read_text().splitlines():
        try:
            rec = json.loads(line)
        except Exception:
            continue
        if rec.get("kind") != "page" or rec.get("http_status") != 200:
            continue
        page = rec.get("page")
        if isinstance(page, int):
            best = page if best is None else max(best, page)
    return best
