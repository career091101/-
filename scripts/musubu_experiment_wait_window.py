#!/usr/bin/env python3
"""Poll during an experiment window: 429 immediate fail, early advance after min_sec."""
from __future__ import annotations

import argparse
import json
import sys
import time

from musubu_experiment_lib import (
    ABORT_FLAG,
    count_http_in_window,
    gate_429_failed,
    max_key_people_page,
    pages_per_hour,
)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--start", type=int, required=True)
    p.add_argument("--page-start", type=int, required=True)
    p.add_argument("--min-sec", type=int, default=1200)
    p.add_argument("--max-sec", type=int, default=3600)
    p.add_argument("--poll-sec", type=int, default=60)
    p.add_argument("--baseline-pph", type=float, required=True)
    p.add_argument("--baseline-interval", type=float, default=1.0)
    p.add_argument("--trial-interval", type=float, required=True)
    p.add_argument("--pph-ratio", type=float, default=0.8)
    args = p.parse_args()

    while True:
        if ABORT_FLAG.is_file():
            now = int(time.time())
            counts = count_http_in_window(args.start, now)
            print(
                json.dumps(
                    {
                        "ended_at": now,
                        "reason": "401_abort",
                        "counts": counts,
                        "elapsed": now - args.start,
                        "page_end": max_key_people_page(),
                    }
                )
            )
            sys.exit(2)

        now = int(time.time())
        elapsed = now - args.start
        counts = count_http_in_window(args.start, now)
        page_end = max_key_people_page()
        pph = pages_per_hour(args.page_start, page_end, max(elapsed, 1))

        if gate_429_failed(counts):
            print(
                json.dumps(
                    {
                        "ended_at": now,
                        "reason": "429_gate",
                        "counts": counts,
                        "elapsed": elapsed,
                        "page_end": page_end,
                        "pages_per_hour": pph,
                    }
                )
            )
            return

        expected = (
            args.baseline_pph
            * (args.baseline_interval / args.trial_interval)
            * args.pph_ratio
        )
        if (
            elapsed >= args.min_sec
            and counts.get("http_429", 0) == 0
            and pph >= expected
        ):
            print(
                json.dumps(
                    {
                        "ended_at": now,
                        "reason": "early_advance",
                        "counts": counts,
                        "elapsed": elapsed,
                        "page_end": page_end,
                        "pages_per_hour": pph,
                        "expected_pph": expected,
                    }
                )
            )
            return

        if elapsed >= args.max_sec:
            print(
                json.dumps(
                    {
                        "ended_at": now,
                        "reason": "max_window",
                        "counts": counts,
                        "elapsed": elapsed,
                        "page_end": page_end,
                        "pages_per_hour": pph,
                        "expected_pph": expected,
                    }
                )
            )
            return

        sleep_for = min(args.poll_sec, args.max_sec - elapsed)
        if sleep_for > 0:
            time.sleep(sleep_for)


if __name__ == "__main__":
    main()
