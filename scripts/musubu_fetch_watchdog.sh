#!/usr/bin/env bash
# Restart key_people autorun if musubu_collect is not running.
set -euo pipefail
# shellcheck source=musubu_env.sh
source "$(dirname "${BASH_SOURCE[0]}")/musubu_env.sh"
while true; do
  if ! pgrep -f "musubu_collect.py search" >/dev/null 2>&1; then
    echo "[$(musubu_now)] fetch idle — restarting autorun"
    tmux -f /exec-daemon/tmux.portal.conf send-keys -t musubu-kp-fetch:0.0 \
      'bash /workspace/scripts/musubu_kp_autorun.sh 58552 170' C-m 2>/dev/null || \
      tmux -f /exec-daemon/tmux.portal.conf new-session -d -s musubu-kp-fetch -c /workspace -- \
        bash /workspace/scripts/musubu_kp_autorun.sh 58552 170
  fi
  sleep 60
done
