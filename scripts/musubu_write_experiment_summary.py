#!/usr/bin/env python3
"""Write musubu-data/experiment_summary.md from experiment_log.json."""
from __future__ import annotations

import json
import sys
from pathlib import Path

LOG = Path("/workspace/musubu-data/experiment_log.json")
OUT = Path("/workspace/musubu-data/experiment_summary.md")


def main() -> None:
    recommended = sys.argv[1] if len(sys.argv) > 1 else "unknown"
    interval = sys.argv[2] if len(sys.argv) > 2 else "2.2"
    recruits_total = sys.argv[3] if len(sys.argv) > 3 else "?"
    entries = json.loads(LOG.read_text()) if LOG.is_file() else []
    lines = [
        "# Musubu experiment summary",
        "",
        f"- **Confirmed interval (EXPERIMENT_INTERVAL_SEC):** {interval}s",
        f"- **Recommended mode:** `{recommended}`",
        f"- **Recruits total_pages (API):** {recruits_total}",
        "",
        "## Phases",
        "",
        "| Phase | pages/h | interval | 429 | 401 | decision | notes |",
        "|-------|---------|----------|-----|-----|----------|-------|",
    ]
    for e in entries:
        if not isinstance(e, dict) or "phase" not in e:
            continue
        lines.append(
            "| {phase} | {pph:.1f} | {iv} | {a429} | {a401} | {dec} | {notes} |".format(
                phase=e.get("phase"),
                pph=float(e.get("pages_per_hour") or 0),
                iv=e.get("interval_sec", ""),
                a429=e.get("http_429", 0),
                a401=e.get("http_401", 0),
                dec=e.get("decision", ""),
                notes=(e.get("notes") or "")[:80].replace("|", "/"),
            )
        )
    lines.extend(
        [
            "",
            "## Publisher",
            "",
            "- Parallel publisher tmux recommended when fetch pph stays ≥80% of baseline (phase 1 gate).",
            "- Large `tar.gz` uploads are queued in `publisher_mcp_queue/` for MCP binary upload + SHA verify.",
            "",
            "## Recruits completion estimate",
            "",
            f"- Pages remaining ≈ `{recruits_total}` minus local max page; at `{interval}`s per page, "
            f"duration ≈ `(remaining × {interval}) / 3600` hours.",
            "",
        ]
    )
    OUT.write_text("\n".join(lines) + "\n")
    print("wrote", OUT)


if __name__ == "__main__":
    main()
