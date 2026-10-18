#!/usr/bin/env python3
"""Report pages/hour and error counts from experiment_api.log for a time window."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from musubu_experiment_lib import API_LOG, count_http_in_window, now_jst_iso  # noqa: E402


def count_pages_200(start_epoch: int, end_epoch: int) -> int:
    n = 0
    if not API_LOG.is_file():
        return 0
    for line in API_LOG.read_text().splitlines():
        try:
            rec = json.loads(line)
        except Exception:
            continue
        ts = rec.get("ts")
        if ts is None or ts < start_epoch or ts > end_epoch:
            continue
        if rec.get("http_status") != 200:
            continue
        if rec.get("page") is None:
            continue
        if rec.get("method") != "POST":
            continue
        n += 1
    return n


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--start-epoch", type=int, required=True)
    p.add_argument("--end-epoch", type=int, required=True)
    args = p.parse_args()
    elapsed = max(1, args.end_epoch - args.start_epoch)
    pages = count_pages_200(args.start_epoch, args.end_epoch)
    pph = pages * 3600.0 / elapsed
    errs = count_http_in_window(args.start_epoch, args.end_epoch)
    out = {
        "report_jst": now_jst_iso(),
        "start_epoch": args.start_epoch,
        "end_epoch": args.end_epoch,
        "elapsed_sec": elapsed,
        "http_200_search_pages": pages,
        "pages_per_hour": round(pph, 1),
        **errs,
    }
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
