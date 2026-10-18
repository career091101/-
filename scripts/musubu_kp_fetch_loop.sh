#!/usr/bin/env bash
# Continuous key_people fetch: 2.2s interval, one page at a time.
set -euo pipefail
START=${1:-1}
END=${2:-999999}
SCRIPT=/workspace/scripts/musubu_collect.py
for ((p=START; p<=END; p++)); do
  if ! python3 "$SCRIPT" search_page --resource key_people --page "$p"; then
    echo "failed page $p at $(date -Is)" >&2
    exit 1
  fi
  python3 "$SCRIPT" build_checkpoint >/dev/null
done
