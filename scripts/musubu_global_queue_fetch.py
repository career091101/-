#!/usr/bin/env python3
"""Resident Musubu fetch: one process, reused HTTP + token, O(1) progress jsonl.

Interval from experiment_config.json (EXPERIMENT_INTERVAL_SEC=0.5 for benchmark).
Protected: key_people pages 1–3; companies pages 1–69 and 71–1833 (existing tars).
Companies page 70 is fetched when missing. Packing skips companies 1–1833.
"""
from __future__ import annotations

import fcntl
import json
import gzip
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from musubu_api_client import MusubuApiClient  # noqa: E402
import musubu_collect as mc  # noqa: E402
from musubu_collect import (  # noqa: E402
    effective_interval_sec,
    fetch_search_page_resident,
)
from musubu_experiment_lib import abort_if_401  # noqa: E402

DATA = Path("/workspace/musubu-data")

# resource, first sequential page, explicit extra pages, skip set
RESOURCE_RULES: list[tuple[str, int, list[int], set[int]]] = [
    ("companies", 1834, [70], set(range(1, 70)) | set(range(71, 1834))),
    ("key_people", 4, [], set()),
    ("recruits", 1, [], set()),
    ("departments", 1, [], set()),
    ("offices", 1, [], set()),
    ("stores", 1, [], set()),
    ("facilities", 1, [], set()),
]

COMPANIES_PAGE70_PENDING = DATA / "progress" / "companies_page70_done.flag"
API_LOG = DATA / "experiment_api.log"


def _paused_resources() -> set[str]:
    cfg_path = DATA / "experiment_config.json"
    if not cfg_path.is_file():
        return set()
    try:
        cfg = json.loads(cfg_path.read_text())
        paused = cfg.get("FETCH_PAUSED_RESOURCES") or []
        return {str(x) for x in paused}
    except Exception:
        return set()


def latest_page_statuses(path: Path) -> dict[tuple[str, int], int]:
    """Read only resource/page/status fields; never expose log records."""
    latest: dict[tuple[str, int], int] = {}
    if not path.is_file():
        return latest
    with path.open() as stream:
        for line in stream:
            try:
                rec = json.loads(line)
                resource, page, status = rec.get("resource"), rec.get("page"), rec.get("http_status")
                if isinstance(resource, str) and isinstance(page, int) and isinstance(status, int):
                    latest[(resource, page)] = status
            except (ValueError, TypeError, AttributeError):
                continue
    return latest


def retry_candidates(data_dir: Path, api_log: Path = API_LOG) -> list[tuple[str, int, Path]]:
    latest = latest_page_statuses(api_log)
    candidates: list[tuple[str, int, Path]] = []
    for resource, first, _, skip in RESOURCE_RULES:
        directory = data_dir / f"section_{resource}"
        for (logged_resource, page), status in latest.items():
            if logged_resource != resource or status != 403:
                continue
            if (page < first or page in skip) and not (resource == "companies" and page == 70):
                continue
            path = directory / f"{resource}_page_{page:05d}.json"
            if not path.is_file():
                continue
            try:
                payload = json.loads(gzip.decompress(path.read_bytes()))
            except (OSError, EOFError, ValueError, json.JSONDecodeError):
                continue
            meta = payload.get("meta") if isinstance(payload, dict) else None
            if isinstance(payload, dict) and "error" in payload and not (
                isinstance(meta, dict) and isinstance(meta.get("page"), int) and meta["page"] == page
            ):
                candidates.append((resource, page, path))
    return sorted(candidates)


def quarantine_placeholder(path: Path, data_dir: Path) -> Path:
    directory = data_dir / "quarantine"
    directory.mkdir(parents=True, exist_ok=True)
    base = f"{path.stem}.403-placeholder"
    index = 0
    while True:
        target = directory / f"{base}{f'.{index}' if index else ''}.json.gz"
        try:
            os.link(path, target)
            path.unlink()
            return target
        except FileExistsError:
            index += 1


def saved_pages(resource: str) -> set[int]:
    directory = DATA / f"section_{resource}"
    pages: set[int] = set()
    if not directory.is_dir():
        return pages
    for path in directory.glob(f"{resource}_page_*.json"):
        if ".b64" in path.name:
            continue
        match = re.search(r"_(\d+)\.json$", path.name)
        if match:
            pages.add(int(match.group(1)))
    return pages


def latest_total_pages(resource: str) -> int | None:
    path = DATA / f"manifest_{resource}_pages.json"
    if not path.is_file():
        return None
    try:
        artifacts = json.loads(path.read_text()).get("artifacts") or []
    except Exception:
        return None
    for artifact in reversed(artifacts):
        total = (artifact.get("meta") or {}).get("total_pages")
        if total:
            return int(total)
    return None


def next_companies_page(saved: set[int], excluded: set[int] | None = None) -> int | None:
    excluded = excluded or set()
    if 70 not in saved and 70 not in excluded and not COMPANIES_PAGE70_PENDING.is_file():
        return 70
    total = latest_total_pages("companies")
    if total is not None:
        for candidate in range(1834, total + 1):
            if candidate not in saved and candidate not in excluded:
                return candidate
        return None
    pages = [p for p in saved if p >= 1834]
    candidate = max(pages) + 1 if pages else 1834
    while candidate in excluded:
        candidate += 1
    return candidate


def _inflight_path(resource: str) -> Path:
    return DATA / "progress" / f"{resource}_inflight.json"


def _claim_lock_path(resource: str) -> Path:
    return DATA / "progress" / f"{resource}_claim.lock"


def _load_inflight(resource: str) -> set[int]:
    path = _inflight_path(resource)
    if not path.is_file():
        return set()
    try:
        data = json.loads(path.read_text())
        return {int(x) for x in data}
    except Exception:
        return set()


def _save_inflight(resource: str, pages: set[int]) -> None:
    path = _inflight_path(resource)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sorted(pages)))


def claim_next_page(
    resource: str,
    first: int,
    extras: list[int],
    skip: set[int],
) -> int | None:
    """Reserve the next page under an exclusive lock (safe for parallel workers)."""
    lock_path = _claim_lock_path(resource)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "w") as lockf:
        fcntl.flock(lockf, fcntl.LOCK_EX)
        inflight = _load_inflight(resource)
        page = next_page(resource, first, extras, skip, excluded=inflight)
        if page is not None:
            inflight.add(page)
            _save_inflight(resource, inflight)
        return page


def release_claim(resource: str, page: int) -> None:
    lock_path = _claim_lock_path(resource)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "w") as lockf:
        fcntl.flock(lockf, fcntl.LOCK_EX)
        inflight = _load_inflight(resource)
        inflight.discard(page)
        _save_inflight(resource, inflight)


def next_page(resource: str, first: int, extras: list[int], skip: set[int], excluded: set[int] | None = None) -> int | None:
    excluded = excluded or set()
    saved = saved_pages(resource)
    for p in sorted(extras):
        if p not in saved and p not in skip and p not in excluded:
            return p
    if resource == "companies":
        page = next_companies_page(saved, excluded)
        return page
    pages = [page for page in saved if page >= first and page not in skip and page not in excluded]
    candidate = max(pages) + 1 if pages else first
    while candidate in skip or candidate in excluded:
        candidate += 1
    total = latest_total_pages(resource)
    if total is not None and candidate > total:
        return None
    return candidate


def main() -> None:
    from musubu_collect import effective_api_parallel

    parallel = effective_api_parallel()
    if parallel > 1:
        from musubu_parallel_resource_fetch import main as parallel_main

        parallel_main()
        return
    mc.INTERVAL_SEC = effective_interval_sec()
    print(f"resident fetch interval_sec={mc.INTERVAL_SEC}", flush=True)
    client = MusubuApiClient()
    try:
        attempted: set[tuple[str, int]] = set()
        candidates = retry_candidates(DATA)
        paused = _paused_resources()
        for resource, page, path in candidates:
            if resource in paused:
                continue
            key = (resource, page)
            if key in attempted:
                continue
            attempted.add(key)
            quarantine_placeholder(path, DATA)
            abort_if_401()
            rec = fetch_search_page_resident(
                client, resource, page, DATA, write_b64=False, log_progress=True
            )
            if rec.get("http_status") != 200:
                return
        while True:
            abort_if_401()
            progressed = False
            for resource, first, extras, skip in RESOURCE_RULES:
                if resource in paused:
                    continue
                page = next_page(
                    resource, first, extras, skip,
                    excluded={p for r, p in attempted if r == resource},
                )
                if page is None:
                    continue
                print(f"queue {resource} page {page}", flush=True)
                rec = fetch_search_page_resident(
                    client,
                    resource,
                    page,
                    DATA,
                    write_b64=False,
                    log_progress=True,
                )
                if rec.get("http_status") != 200:
                    return
                if resource == "companies" and page == 70 and rec.get("http_status") == 200:
                    COMPANIES_PAGE70_PENDING.parent.mkdir(parents=True, exist_ok=True)
                    COMPANIES_PAGE70_PENDING.write_text(str(int(time.time())))
                progressed = True
            if not progressed:
                print(
                    "queue idle: every configured section is at its latest total_pages",
                    flush=True,
                )
                break
    finally:
        client.close()


if __name__ == "__main__":
    main()
