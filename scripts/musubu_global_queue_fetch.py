#!/usr/bin/env python3
"""Single-process round-robin fetch for key_people + companies (phase 4)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from musubu_experiment_lib import max_key_people_page  # noqa: E402

COLLECT = Path("/workspace/scripts/musubu_collect.py")
KP_END = 58552
COMP_START = 1834
COMP_END = 10347  # adjust when manifest known


def next_companies_page() -> int | None:
    d = Path("/workspace/musubu-data/section_companies")
    if not d.is_dir():
        return COMP_START
    pages = []
    for p in d.glob("companies_page_*.json"):
        if p.name.endswith(".b64"):
            continue
        pages.append(int(p.name.split("_")[-1].split(".")[0]))
    n = max(pages) + 1 if pages else COMP_START
    return n if n <= COMP_END else None


def main() -> None:
    while True:
        kp = max_key_people_page() + 1
        if kp <= KP_END:
            subprocess.run(
                [
                    sys.executable,
                    str(COLLECT),
                    "search_page",
                    "--resource",
                    "key_people",
                    "--page",
                    str(kp),
                ],
                check=False,
            )
            continue
        cp = next_companies_page()
        if cp is not None:
            subprocess.run(
                [
                    sys.executable,
                    str(COLLECT),
                    "search_page",
                    "--resource",
                    "companies",
                    "--page",
                    str(cp),
                ],
                check=False,
            )
            continue
        break


if __name__ == "__main__":
    main()
