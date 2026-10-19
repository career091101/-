#!/usr/bin/env python3
"""Pack complete 200-page search chunks off the fetch hot path."""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from musubu_collect import (  # noqa: E402
    SEARCH_TAR_PAGE_SIZE,
    first_pack_page_for_resource,
    maybe_pack_complete_search_chunks,
)

DATA = Path("/workspace/musubu-data")
RESOURCES = (
    "key_people",
    "companies",
    "recruits",
    "departments",
    "offices",
    "stores",
    "facilities",
)


def max_saved_page(resource: str) -> int:
    d = DATA / f"section_{resource}"
    best = 0
    if not d.is_dir():
        return 0
    for path in d.glob(f"{resource}_page_*.json"):
        if ".b64" in path.name:
            continue
        m = re.search(r"_(\d+)\.json$", path.name)
        if m:
            best = max(best, int(m.group(1)))
    return best


def main() -> None:
    interval = float(sys.argv[1]) if len(sys.argv) > 1 else 30.0
    while True:
        for resource in RESOURCES:
            page_end = max_saved_page(resource)
            first = first_pack_page_for_resource(resource)
            if page_end < first:
                continue
            try:
                packed = maybe_pack_complete_search_chunks(resource, page_end, DATA)
                if packed:
                    print(
                        json.dumps(
                            {
                                "ts": int(time.time()),
                                "resource": resource,
                                "packed": [p["file"] for p in packed],
                            }
                        ),
                        flush=True,
                    )
            except Exception as exc:
                print(
                    json.dumps(
                        {
                            "ts": int(time.time()),
                            "resource": resource,
                            "error": str(exc),
                        }
                    ),
                    flush=True,
                )
        time.sleep(interval)


if __name__ == "__main__":
    main()
