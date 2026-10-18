#!/usr/bin/env python3
"""Print create_file args as JSON for one musubu .b64 path (stdout)."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

PARENT = "1kR8pPEahMbgj4ErAzHxCqwU85tMPL8Ea"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("b64_path", type=Path)
    args = p.parse_args()
    text = args.b64_path.read_text()
    print(
        json.dumps(
            {
                "title": args.b64_path.name,
                "textContent": text,
                "parentId": PARENT,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
