#!/usr/bin/env python3
"""Resident Musubu fetch: one process, reused HTTP + token, O(1) progress jsonl.

Interval from experiment_config.json (EXPERIMENT_INTERVAL_SEC=0.5 for benchmark).
Protected: key_people pages 1–3; companies pages 1–69 and 71–1833 (existing tars).
Companies page 70 is fetched when missing. Packing skips companies 1–1833.
"""
from __future__ import annotations

import json
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
    ("key_people", 4, [], set()),
    ("companies", 1834, [70], set(range(1, 70)) | set(range(71, 1834))),
    ("recruits", 1, [], set()),
    ("departments", 1, [], set()),
    ("offices", 1, [], set()),
    ("stores", 1, [], set()),
    ("facilities", 1, [], set()),
]

COMPANIES_PAGE70_PENDING = DATA / "progress" / "companies_page70_done.flag"


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


def next_companies_page(saved: set[int]) -> int | None:
    if 70 not in saved and not COMPANIES_PAGE70_PENDING.is_file():
        return 70
    pages = [p for p in saved if p >= 1834]
    candidate = max(pages) + 1 if pages else 1834
    total = latest_total_pages("companies")
    if total is not None and candidate > total:
        return None
    return candidate


def next_page(resource: str, first: int, extras: list[int], skip: set[int]) -> int | None:
    saved = saved_pages(resource)
    for p in sorted(extras):
        if p not in saved and p not in skip:
            return p
    if resource == "companies":
        return next_companies_page(saved)
    pages = [page for page in saved if page >= first and page not in skip]
    candidate = max(pages) + 1 if pages else first
    while candidate in skip:
        candidate += 1
    total = latest_total_pages(resource)
    if total is not None and candidate > total:
        return None
    return candidate


def main() -> None:
    mc.INTERVAL_SEC = effective_interval_sec()
    print(f"resident fetch interval_sec={mc.INTERVAL_SEC}", flush=True)
    client = MusubuApiClient()
    try:
        while True:
            abort_if_401()
            progressed = False
            for resource, first, extras, skip in RESOURCE_RULES:
                page = next_page(resource, first, extras, skip)
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
