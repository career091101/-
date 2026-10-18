#!/usr/bin/env bash
set -euo pipefail
END="${1:-0}"
BATCH="${2:-100}"
SCRIPT=/workspace/scripts/musubu_collect.py
DIR=/workspace/musubu-data/section_recruits

max_page() {
  python3 << 'PY'
import re
from pathlib import Path
pages = []
for p in Path("/workspace/musubu-data/section_recruits").glob("recruits_page_*.json"):
    if p.name.endswith(".json.b64"):
        continue
    m = re.search(r"_(\d+)\.json$", p.name)
    if m:
        pages.append(int(m.group(1)))
print(max(pages) if pages else 1)
PY
}

if [[ "$END" == "0" ]]; then
  python3 "$SCRIPT" search_page --resource recruits --page 1 || true
  END=$(python3 - <<'PY'
import json
from pathlib import Path
p = Path("/workspace/musubu-data/manifest_recruits_pages.json")
if p.exists():
    arts = json.loads(p.read_text()).get("artifacts") or []
    if arts:
        print((arts[-1].get("meta") or {}).get("total_pages") or 1)
        raise SystemExit
print(1)
PY
)
fi

start="$(max_page)"
start=$((start + 1))
while [[ "$start" -le "$END" ]]; do
  end=$((start + BATCH - 1))
  [[ "$end" -gt "$END" ]] && end="$END"
  python3 "$SCRIPT" search_range --resource recruits --page-start "$start" --page-end "$end"
  python3 "$SCRIPT" build_checkpoint
  start=$((end + 1))
done
