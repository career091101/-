#!/usr/bin/env python3
"""One Musubu search request at a time across sections 1–7.

Interval comes from musubu_collect (experiment_config.json, default 2.2s).
Protected ranges are never requested: key_people pages 1–3 and companies
pages 1–1833. Companies page 70 stays the documented gap.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from musubu_collect import maybe_pack_complete_key_people_chunks  # noqa: E402

COLLECT = Path("/workspace/scripts/musubu_collect.py")
DATA = Path("/workspace/musubu-data")

# resource, first page this queue may request, pages to skip
RESOURCES: list[tuple[str, int, set[int]]] = [
    ("key_people", 4, set()),
    ("companies", 1834, {70}),
    ("recruits", 1, set()),
    ("departments", 1, set()),
    ("offices", 1, set()),
    ("stores", 1, set()),
    ("facilities", 1, set()),
]


def saved_pages(resource: str) -> list[int]:
    directory = DATA / f"section_{resource}"
    pages: list[int] = []
    if not directory.is_dir():
        return pages
    for path in directory.glob(f"{resource}_page_*.json"):
        if path.name.endswith(".b64"):
            continue
        match = re.search(r"_(\d+)\.json$", path.name)
        if match:
            pages.append(int(match.group(1)))
    return pages


def latest_total_pages(resource: str) -> int | None:
    path = DATA / f"manifest_{resource}_pages.json"
    if not path.is_file():
        return None
    artifacts = json.loads(path.read_text()).get("artifacts") or []
    for artifact in reversed(artifacts):
        total = (artifact.get("meta") or {}).get("total_pages")
        if total:
            return int(total)
    return None


def next_page(resource: str, first: int, skip: set[int]) -> int | None:
    pages = [page for page in saved_pages(resource) if page >= first and page not in skip]
    candidate = max(pages) + 1 if pages else first
    while candidate in skip:
        candidate += 1
    total = latest_total_pages(resource)
    if total is not None and candidate > total:
        return None
    return candidate


def fetch_page(resource: str, page: int) -> None:
    subprocess.run(
        [
            sys.executable,
            str(COLLECT),
            "search_page",
            "--resource",
            resource,
            "--page",
            str(page),
        ],
        check=False,
    )


def main() -> None:
    while True:
        progressed = False
        for resource, first, skip in RESOURCES:
            page = next_page(resource, first, skip)
            if page is None:
                continue
            print(f"queue {resource} page {page}", flush=True)
            fetch_page(resource, page)
            progressed = True
            if resource == "key_people":
                packed = maybe_pack_complete_key_people_chunks(page, DATA)
                if packed:
                    print(
                        "packed",
                        ", ".join(item["file"] for item in packed),
                        flush=True,
                    )
        if not progressed:
            print("queue idle: every configured section is at its latest total_pages", flush=True)
            break


if __name__ == "__main__":
    main()
