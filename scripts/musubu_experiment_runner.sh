#!/usr/bin/env bash
# Musubu staged parallelization experiment (phases 0–5).
set -euo pipefail
# shellcheck source=musubu_env.sh
source "$(dirname "${BASH_SOURCE[0]}")/musubu_env.sh"

ROOT=/workspace/musubu-data
LIB=/workspace/scripts/musubu_experiment_lib.py
RUNNER_LOG="$ROOT/experiment_runner.log"
PHASE0_SEC=1800
PHASE0_INTERVAL=1.0
PHASE1_SEC=3600
PHASE2_MIN_SEC=1200
PHASE2_MAX_SEC=3600
PHASE2_POLL_SEC=60
# Phase 2 sweep: 1.0s baseline (phases 0–1) then 0.75s → 0.5s
PHASE2_INTERVALS=(0.75 0.5)
PHASE2_LABELS=(a b)
PHASE3_SEC=3600
PHASE4_SEC=3600
PHASE5_SEC=3600

log() { echo "[$(musubu_now)] $*" | tee -a "$RUNNER_LOG"; }

export PYTHONPATH="/workspace/scripts${PYTHONPATH:+:$PYTHONPATH}"
py() { python3 "$@"; }

py - <<'PY'
from musubu_experiment_lib import append_experiment_log
append_experiment_log({
  "phase": "runner_start",
  "decision": "advance",
  "notes": "phase2_sweep_1.0_to_0.5_v1; phase0=1.0s/30m; phase2=0.75,0.5 adaptive window",
})
PY

max_page() {
  py - <<'PY'
from musubu_experiment_lib import max_key_people_page
print(max_key_people_page())
PY
}

append_phase() {
  py - "$@" <<'PY'
import json, sys, time
from pathlib import Path
from musubu_experiment_lib import append_experiment_log, count_http_in_window, pages_per_hour

entry = json.loads(sys.argv[1])
append_experiment_log(entry)
PY
}

record_phase() {
  local phase="$1" started="$2" ended="$3" pstart="$4" pend="$5" interval="$6" api_par="$7" pub_par="$8" decision="$9" notes="${10}"
  local elapsed=$((ended - started))
  local pph
  pph=$(python3 - <<PY
from musubu_experiment_lib import pages_per_hour
print(pages_per_hour($pstart, $pend, $elapsed))
PY
)
  local counts
  counts=$(python3 - <<PY
import json
from musubu_experiment_lib import count_http_in_window
print(json.dumps(count_http_in_window($started, $ended)))
PY
)
  py - <<PY
import json, time
from musubu_experiment_lib import append_experiment_log
counts = json.loads('''$counts''')
append_experiment_log({
  "phase": "$phase",
  "started_at": $started,
  "ended_at": $ended,
  "resource(s)": ["key_people"],
  "page_start": $pstart,
  "page_end": $pend,
  "pages_per_hour": float('$pph'),
  "api_parallel": $api_par,
  "interval_sec": $interval,
  "publisher_parallel": $pub_par,
  "http_429": counts.get("http_429", 0),
  "http_401": counts.get("http_401", 0),
  "http_5xx": counts.get("http_5xx", 0),
  "uploads_ok": 0,
  "decision": "$decision",
  "notes": """$notes""",
})
PY
}

ensure_fetch() {
  if tmux -f /exec-daemon/tmux.portal.conf has-session -t musubu-kp-fetch 2>/dev/null; then
    return 0
  fi
  tmux -f /exec-daemon/tmux.portal.conf new-session -d -s musubu-kp-fetch -c /workspace \
    -- bash /workspace/scripts/musubu_kp_autorun.sh 58552 170
}

stop_publisher() {
  tmux -f /exec-daemon/tmux.portal.conf kill-session -t musubu-publisher 2>/dev/null || true
}

start_publisher() {
  stop_publisher
  tmux -f /exec-daemon/tmux.portal.conf new-session -d -s musubu-publisher -c /workspace \
    -- python3 /workspace/scripts/musubu_publisher_daemon.py 45
}

set_interval() {
  py - <<PY
from musubu_experiment_lib import set_interval_sec
set_interval_sec($1)
PY
}

abort_check() {
  if [[ -f "$ROOT/EXPERIMENT_ABORT_401.flag" ]]; then
    log "ABORT: HTTP 401"
    exit 2
  fi
}

# --- Phase 0 (1.0s baseline, 30 min) ---
log "Phase 0 start interval=${PHASE0_INTERVAL}s window=${PHASE0_SEC}s (sweep 1.0->0.5)"
py - <<PY
from musubu_experiment_lib import set_experiment_phase, set_interval_sec
set_interval_sec($PHASE0_INTERVAL)
set_experiment_phase("0_baseline", {
  "EXPERIMENT_INTERVAL_SEC": $PHASE0_INTERVAL,
  "interval_sweep_plan": "1.0_baseline_then_0.75_0.5",
  "runner_schema": "phase2_sweep_1.0_to_0.5_v1",
})
PY
stop_publisher
ensure_fetch
t0=$(date +%s)
p0=$(max_page)
log "Phase 0 baseline max_page=$p0"
sleep "$PHASE0_SEC"
abort_check
t1=$(date +%s)
p1=$(max_page)
record_phase "0_baseline" "$t0" "$t1" "$p0" "$p1" "$PHASE0_INTERVAL" 1 0 "advance" "no publisher uploads; 1.0s baseline for 0.5s sweep"
BASELINE_PPH=$(python3 - <<PY
from musubu_experiment_lib import pages_per_hour
print(pages_per_hour($p0, $p1, $t1 - $t0))
PY
)
BASELINE_INTERVAL=$PHASE0_INTERVAL
log "Phase 0 pages_per_hour=$BASELINE_PPH (baseline interval=${BASELINE_INTERVAL}s)"

# --- Phase 1 ---
log "Phase 1 start (publisher ON, interval=${PHASE0_INTERVAL}s)"
set_interval "$PHASE0_INTERVAL"
py - <<PY
from musubu_experiment_lib import set_experiment_phase
set_experiment_phase("1_publisher_parallel", {"EXPERIMENT_INTERVAL_SEC": $PHASE0_INTERVAL})
PY
start_publisher
t0=$(date +%s)
p0=$(max_page)
sleep "$PHASE1_SEC"
abort_check
t1=$(date +%s)
p1=$(max_page)
pph=$(python3 - <<PY
from musubu_experiment_lib import pages_per_hour
print(pages_per_hour($p0, $p1, $t1 - $t0))
PY
)
threshold=$(python3 - <<PY
print(float('$BASELINE_PPH') * 0.8)
PY
)
decision="advance"
notes="publisher parallel ON"
gate_fail=$(python3 - <<PY
print(1 if float('$pph') < float('$threshold') else 0)
PY
)
if [[ "$gate_fail" == "1" ]]; then
  decision="rollback"
  notes="fetch pph below 80% baseline (${pph} < ${threshold}); stopping publisher"
  stop_publisher
fi
record_phase "1_publisher_parallel" "$t0" "$t1" "$p0" "$p1" "$PHASE0_INTERVAL" 1 1 "$decision" "$notes"
PUBLISHER_ON=1
if [[ "$decision" == "rollback" ]]; then
  PUBLISHER_ON=0
  log "Phase 1 failed gate; retry publisher once"
  start_publisher
  sleep 600
  stop_publisher
  start_publisher
fi

# --- Phase 2 interval exploration (1.0 confirmed → try 0.75 → 0.5) ---
CONFIRMED=$PHASE0_INTERVAL
try_interval() {
  local label="$1" sec="$2"
  log "Phase 2${label} interval=${sec}s min=${PHASE2_MIN_SEC}s max=${PHASE2_MAX_SEC}s poll=${PHASE2_POLL_SEC}s"
  set_interval "$sec"
  py - <<PY
from musubu_experiment_lib import set_experiment_phase
set_experiment_phase("2${label}", {"EXPERIMENT_INTERVAL_SEC": $sec, "interval_sweep_target": 0.5})
PY
  [[ "$PUBLISHER_ON" == 1 ]] && start_publisher || stop_publisher
  t0=$(date +%s)
  p0=$(max_page)
  WIN_FILE="$ROOT/experiment_last_window.json"
  if ! python3 /workspace/scripts/musubu_experiment_wait_window.py \
    --start "$t0" --page-start "$p0" \
    --min-sec "$PHASE2_MIN_SEC" --max-sec "$PHASE2_MAX_SEC" --poll-sec "$PHASE2_POLL_SEC" \
    --baseline-pph "$BASELINE_PPH" --baseline-interval "$BASELINE_INTERVAL" --trial-interval "$sec" \
    >"$WIN_FILE"; then
    abort_check
    return 2
  fi
  abort_check
  t1=$(python3 -c "import json; print(json.load(open('$WIN_FILE'))['ended_at'])")
  p1=$(python3 -c "import json; print(json.load(open('$WIN_FILE')).get('page_end', 0))")
  reason=$(python3 -c "import json; print(json.load(open('$WIN_FILE')).get('reason', ''))")
  failed=$(python3 -c "import json; from musubu_experiment_lib import gate_429_failed; c=json.load(open('$WIN_FILE')).get('counts') or {}; print(gate_429_failed(c))")
  decision="advance"
  notes="window_end=$reason"
  if [[ "$failed" == "True" ]]; then
    decision="rollback"
    notes="429 gate failed at ${sec}s ($reason)"
  fi
  record_phase "2${label}" "$t0" "$t1" "$p0" "$p1" "$sec" 1 "$PUBLISHER_ON" "$decision" "$notes"
  if [[ "$failed" == "True" ]]; then
    return 1
  fi
  CONFIRMED=$sec
  return 0
}

py - <<'PY'
from musubu_experiment_lib import set_experiment_phase
set_experiment_phase("2_interval_sweep", {"interval_sweep_plan": "0.75_then_0.5", "confirmed_start": 1.0})
PY
for i in "${!PHASE2_INTERVALS[@]}"; do
  sec="${PHASE2_INTERVALS[$i]}"
  label="${PHASE2_LABELS[$i]}"
  if try_interval "$label" "$sec"; then
    continue
  fi
  set_interval "$CONFIRMED"
  log "Phase 2${label} failed at ${sec}s; CONFIRMED=${CONFIRMED}s"
  break
done
py - <<PY
from musubu_experiment_lib import set_experiment_phase
set_experiment_phase("2_done", {"EXPERIMENT_INTERVAL_SEC": $CONFIRMED, "interval_sweep_confirmed": $CONFIRMED})
PY
log "EXPERIMENT_INTERVAL_SEC=$CONFIRMED (fastest passing interval toward 0.5s floor)"

stop_worker_b() {
  tmux -f /exec-daemon/tmux.portal.conf kill-session -t musubu-fetch-light 2>/dev/null || true
}

start_worker_b_light() {
  stop_worker_b
  tmux -f /exec-daemon/tmux.portal.conf new-session -d -s musubu-fetch-light -c /workspace -- \
    bash -lc 'for r in departments offices stores facilities; do bash /workspace/scripts/musubu_fetch_worker.sh "$r" 1 30 || true; done; python3 /workspace/scripts/musubu_collect.py build_checkpoint'
}

start_worker_b_companies() {
  stop_worker_b
  tmux -f /exec-daemon/tmux.portal.conf new-session -d -s musubu-fetch-light -c /workspace -- \
    bash /workspace/scripts/musubu_fetch_worker.sh companies 1834 2033
}

run_timed_phase() {
  local phase="$1" window="$2" api_par="$3" pub_par="$4" notes="$5"
  t0=$(date +%s)
  p0=$(max_page)
  sleep "$window"
  abort_check
  t1=$(date +%s)
  p1=$(max_page)
  record_phase "$phase" "$t0" "$t1" "$p0" "$p1" "$CONFIRMED" "$api_par" "$pub_par" "advance" "$notes"
  echo "$pph"
}

SKIP_PHASE4=0
PHASE3B_PPH=0

# --- Phase 3a ---
log "Phase 3a start"
py - <<'PY'
from musubu_experiment_lib import set_experiment_phase
set_experiment_phase("3a_light_and_kp")
PY
ensure_fetch
start_worker_b_light
t0=$(date +%s)
p0=$(max_page)
sleep "$PHASE3_SEC"
abort_check
t1=$(date +%s)
p1=$(max_page)
counts=$(python3 - <<PY
import json
from musubu_experiment_lib import count_http_in_window, gate_429_failed
c = count_http_in_window($t0, $t1)
c["failed"] = gate_429_failed(c)
print(json.dumps(c))
PY
)
failed_3a=$(python3 -c "import json; print(json.loads('''$counts''').get('failed'))")
if [[ "$failed_3a" == "True" ]]; then
  stop_worker_b
  record_phase "3a" "$t0" "$t1" "$p0" "$p1" "$CONFIRMED" 2 "$PUBLISHER_ON" "rollback" "429 gate; worker B stopped"
  SKIP_PHASE4=1
else
  record_phase "3a" "$t0" "$t1" "$p0" "$p1" "$CONFIRMED" 2 "$PUBLISHER_ON" "advance" "light + key people"
  # --- Phase 3b ---
  log "Phase 3b start"
  py - <<'PY'
from musubu_experiment_lib import set_experiment_phase
set_experiment_phase("3b_companies_and_kp")
PY
  start_worker_b_companies
  t0=$(date +%s)
  p0=$(max_page)
  sleep "$PHASE3_SEC"
  abort_check
  t1=$(date +%s)
  p1=$(max_page)
  counts=$(python3 - <<PY
import json
from musubu_experiment_lib import count_http_in_window, gate_429_failed
c = count_http_in_window($t0, $t1)
c["failed"] = gate_429_failed(c)
print(json.dumps(c))
PY
)
  PHASE3B_PPH=$(python3 - <<PY
from musubu_experiment_lib import pages_per_hour
print(pages_per_hour($p0, $p1, $t1 - $t0))
PY
)
  failed_3b=$(python3 -c "import json; print(json.loads('''$counts''').get('failed'))")
  if [[ "$failed_3b" == "True" ]]; then
    stop_worker_b
    record_phase "3b" "$t0" "$t1" "$p0" "$p1" "$CONFIRMED" 2 "$PUBLISHER_ON" "rollback" "429 gate; worker B stopped"
    SKIP_PHASE4=1
  else
    record_phase "3b" "$t0" "$t1" "$p0" "$p1" "$CONFIRMED" 2 "$PUBLISHER_ON" "advance" "companies 1834+ and key people"
  fi
fi

# --- Phase 4 (optional) ---
RECOMMENDED="single_or_2worker_B_off"
if [[ "$SKIP_PHASE4" == 0 ]]; then
  log "Phase 4 global queue"
  py - <<'PY'
from musubu_experiment_lib import set_experiment_phase
set_experiment_phase("4_global_queue")
PY
  stop_worker_b
  tmux -f /exec-daemon/tmux.portal.conf kill-session -t musubu-kp-fetch 2>/dev/null || true
  tmux -f /exec-daemon/tmux.portal.conf new-session -d -s musubu-kp-fetch -c /workspace -- \
    python3 /workspace/scripts/musubu_global_queue_fetch.py
  t0=$(date +%s)
  p0=$(max_page)
  sleep "$PHASE4_SEC"
  abort_check
  t1=$(date +%s)
  p1=$(max_page)
  pph4=$(python3 - <<PY
from musubu_experiment_lib import pages_per_hour
print(pages_per_hour($p0, $p1, $t1 - $t0))
PY
)
  counts=$(python3 - <<PY
import json
from musubu_experiment_lib import count_http_in_window, gate_429_failed
c = count_http_in_window($t0, $t1)
c["failed"] = gate_429_failed(c)
print(json.dumps(c))
PY
)
  failed_4=$(python3 -c "import json; print(json.loads('''$counts''').get('failed'))")
  pph4_ok=$(python3 -c "print(1 if float('$pph4') >= float('$PHASE3B_PPH') * 0.8 else 0)")
  if [[ "$failed_4" == "False" && "$pph4_ok" == "1" ]]; then
    RECOMMENDED="global_queue"
  fi
  record_phase "4_global_queue" "$t0" "$t1" "$p0" "$p1" "$CONFIRMED" 1 "$PUBLISHER_ON" "advance" "recommended_mode=$RECOMMENDED"
else
  append_phase() { :; }
  py - <<PY
from musubu_experiment_lib import append_experiment_log
append_experiment_log({"phase": "4_skipped", "decision": "advance", "notes": "3b failed or 3a 429"})
PY
fi

# --- Phase 5 recruits ---
log "Phase 5 recruits"
py - <<'PY'
from musubu_experiment_lib import set_experiment_phase
set_experiment_phase("5_recruits")
PY
stop_worker_b
python3 /workspace/scripts/musubu_collect.py search_page --resource recruits --page 1 || true
RECRUIT_TOTAL=$(python3 - <<'PY'
import json
from pathlib import Path
p = Path("/workspace/musubu-data/manifest_recruits_pages.json")
if p.exists():
    arts = json.loads(p.read_text()).get("artifacts") or []
    if arts:
        meta = arts[-1].get("meta") or {}
        print(meta.get("total_pages") or 0)
    else:
        print(0)
else:
    print(0)
PY
)
tmux -f /exec-daemon/tmux.portal.conf kill-session -t musubu-recruits-fetch 2>/dev/null || true
tmux -f /exec-daemon/tmux.portal.conf new-session -d -s musubu-recruits-fetch -c /workspace -- \
  bash /workspace/scripts/musubu_recruits_autorun.sh "$RECRUIT_TOTAL" 100
t0=$(date +%s)
sleep "$PHASE5_SEC"
abort_check
t1=$(date +%s)
record_phase "5_recruits" "$t0" "$t1" 1 1 "$CONFIRMED" 1 "$PUBLISHER_ON" "advance" "recruits_total_pages=$RECRUIT_TOTAL"

python3 /workspace/scripts/musubu_write_experiment_summary.py "$RECOMMENDED" "$CONFIRMED" "$RECRUIT_TOTAL" || true

py - <<PY
from musubu_experiment_lib import set_experiment_phase
set_experiment_phase("post_experiment_collect", {
  "EXPERIMENT_INTERVAL_SEC": $CONFIRMED,
  "recommended_mode": "$RECOMMENDED",
  "recruits_total_pages": $RECRUIT_TOTAL,
})
PY

if [[ "$RECOMMENDED" == "global_queue" ]]; then
  tmux -f /exec-daemon/tmux.portal.conf kill-session -t musubu-kp-fetch 2>/dev/null || true
  tmux -f /exec-daemon/tmux.portal.conf new-session -d -s musubu-kp-fetch -c /workspace -- \
    python3 /workspace/scripts/musubu_global_queue_fetch.py
else
  ensure_fetch
fi
[[ "$PUBLISHER_ON" == 1 ]] && start_publisher || true
log "Experiment complete; GOAL collection continues (recommended_mode=$RECOMMENDED)"
