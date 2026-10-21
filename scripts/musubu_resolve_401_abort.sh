#!/usr/bin/env bash
# Archive EXPERIMENT_ABORT_401.flag after confirming a live API token works.
set -euo pipefail
ROOT="/workspace/musubu-data"
FLAG="$ROOT/EXPERIMENT_ABORT_401.flag"
cd /workspace/scripts
python3 -c "from musubu_api_client import extract_bearer_token; extract_bearer_token()"
if [[ ! -f "$FLAG" ]]; then
  echo "no abort flag"
  exit 0
fi
STAMP="$(date -u +%Y%m%dT%H%MJST)"
DEST="$ROOT/EXPERIMENT_ABORT_401.resolved-${STAMP}.flag"
mv "$FLAG" "$DEST"
echo "archived to $DEST"
