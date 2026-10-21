#!/usr/bin/env bash
# Serial search_range for one resource; skips pages that already exist on disk.
set -euo pipefail
RESOURCE="${1:?resource}"
START="${2:?start}"
END="${3:?end}"
SCRIPT=/workspace/scripts/musubu_collect.py
DIR="/workspace/musubu-data/section_${RESOURCE}"

missing_start=""
missing_end=""
for ((p=START; p<=END; p++)); do
  f="$DIR/${RESOURCE}_page_$(printf '%05d' "$p").json"
  if [[ ! -f "$f" ]]; then
    if [[ -z "$missing_start" ]]; then
      missing_start=$p
      missing_end=$p
    else
      missing_end=$p
    fi
  else
    if [[ -n "$missing_start" ]]; then
      python3 "$SCRIPT" search_range --resource "$RESOURCE" --page-start "$missing_start" --page-end "$missing_end"
      missing_start=""
      missing_end=""
    fi
  fi
done
if [[ -n "$missing_start" ]]; then
  python3 "$SCRIPT" search_range --resource "$RESOURCE" --page-start "$missing_start" --page-end "$missing_end"
fi
