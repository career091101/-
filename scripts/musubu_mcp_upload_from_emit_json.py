#!/usr/bin/env python3
"""Emit one Google-drive create_file handoff from musubu_mcp_batch_upload_verify --emit-create.

Agent: CallDynamicTool(Google-drive, create_file, arguments=<printed JSON minus wrapper>)
Then read_file; record with musubu_mcp_batch_upload_verify --record-create / --save-readback.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

DEFAULT_QUEUE = Path(
    "/workspace/musubu-data/mcp_upload_queue/key_people_pages_01004-01203.tar.gz.parts4k"
)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--queue-dir", type=Path, default=DEFAULT_QUEUE)
    ap.add_argument("--index", type=int, required=True)
    ap.add_argument("--start", type=int, help="batch start (default: index)")
    ap.add_argument("--end", type=int, help="batch end (default: index)")
    args = ap.parse_args()
    start = args.start if args.start is not None else args.index
    end = args.end if args.end is not None else args.index
    out = subprocess.check_output(
        [
            sys.executable,
            str(Path(__file__).resolve().parent / "musubu_mcp_batch_upload_verify.py"),
            "--queue-dir",
            str(args.queue_dir),
            "--start",
            str(start),
            "--end",
            str(end),
            "--emit-create",
            str(args.index),
        ],
        text=True,
    )
    payload = json.loads(out)
    print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    main()
