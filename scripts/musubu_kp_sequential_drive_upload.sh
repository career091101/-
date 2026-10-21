#!/usr/bin/env bash
# Upload one or more KP tar parts4k queues to Drive (rclone verify + close).
set -euo pipefail
ROOT="/workspace/musubu-data"
QUEUE_ROOT="$ROOT/mcp_upload_queue"
LOG="${1:-/tmp/kp_sequential_drive_upload.log}"
shift || true
if [[ $# -lt 1 ]]; then
  echo "usage: $0 [logfile] key_people_pages_XXXX-YYYY.tar.gz ..." >&2
  exit 2
fi
exec >>"$LOG" 2>&1
echo "START $(date -Is) tars=$*"
for tar_name in "$@"; do
  qdir="$QUEUE_ROOT/${tar_name}.parts4k"
  if [[ ! -f "$qdir/manifest.json" ]]; then
    arch="$ROOT/archives/key_people/$tar_name"
    [[ -f "$arch" ]] || { echo "missing $arch"; exit 1; }
    python3 /workspace/scripts/musubu_prepare_parts4k_queue.py "$arch"
  fi
  parts="$(python3 -c "import json;print(json.load(open('$qdir/manifest.json'))['part_count'])")"
  echo "=== $tar_name parts=$parts $(date -Is) ==="
  for start in $(seq 1 12 "$parts"); do
    end=$((start + 11))
    [[ "$end" -gt "$parts" ]] && end="$parts"
    python3 /workspace/scripts/musubu_rclone_verify_parts_range.py \
      --queue-dir "$qdir" --start "$start" --end "$end"
  done
  python3 /workspace/scripts/musubu_mcp_close_verified_tar.py --queue-dir "$qdir"
  echo "CLOSED $tar_name $(date -Is)"
done
echo "ALL_DONE $(date -Is)"
