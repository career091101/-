#!/usr/bin/env bash
# Fetch key_people pages from checkpoint max+1 through END in batches (serial API).
set -euo pipefail
END="${1:-58552}"
BATCH="${2:-170}"
SCRIPT=/workspace/scripts/musubu_collect.py
OUT=/workspace/musubu-data

max_page() {
  python3 << 'PY'
import re
from pathlib import Path
pages = []
for p in Path("/workspace/musubu-data/section_key_people").glob("key_people_page_*.json"):
    if p.name.endswith(".json.b64"):
        continue
    m = re.search(r"_(\d+)\.json$", p.name)
    if m:
        pages.append(int(m.group(1)))
print(max(pages) if pages else 3)
PY
}

start="$(max_page)"
start=$((start + 1))
if [[ "$start" -gt "$END" ]]; then
  echo "already at page $start > END $END"
  exit 0
fi

while [[ "$start" -le "$END" ]]; do
  batch_end=$((start + BATCH - 1))
  [[ "$batch_end" -gt "$END" ]] && batch_end="$END"
  echo "=== key_people pages $start-$batch_end at $(date -Is) ==="
  python3 "$SCRIPT" search_range --resource key_people --page-start "$start" --page-end "$batch_end"
  python3 "$SCRIPT" build_checkpoint
  start=$((batch_end + 1))
done

echo "done through $END at $(date -Is)"
