#!/usr/bin/env bash
# Restart the single-flight fetch queue when no collector is running.
set -euo pipefail
# shellcheck source=musubu_env.sh
source "$(dirname "${BASH_SOURCE[0]}")/musubu_env.sh"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/musubu-data"
ABORT_FLAG="$ROOT/EXPERIMENT_ABORT_401.flag"
while true; do
  if [[ -f "$ABORT_FLAG" ]]; then
    echo "[$(musubu_now)] fetch paused — $ABORT_FLAG present (restore token, then musubu_resolve_401_abort.sh)"
    sleep 300
    continue
  fi
  if ! pgrep -f "musubu_global_queue_fetch.py" >/dev/null 2>&1; then
    echo "[$(musubu_now)] fetch idle — restarting autorun"
    tmux -f /exec-daemon/tmux.portal.conf send-keys -t musubu-kp-fetch:0.0 \
      'python3 /workspace/scripts/musubu_global_queue_fetch.py' C-m 2>/dev/null || \
      tmux -f /exec-daemon/tmux.portal.conf new-session -d -s musubu-kp-fetch -c /workspace -- \
        python3 /workspace/scripts/musubu_global_queue_fetch.py
  fi
  sleep 60
done
