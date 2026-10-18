# Musubu experiment summary

- **Confirmed interval (EXPERIMENT_INTERVAL_SEC):** 0.5s
- **Recommended mode:** `global_queue`
- **Recruits total_pages (API):** 207420

## Phases

| Phase | pages/h | interval | 429 | 401 | decision | notes |
|-------|---------|----------|-----|-----|----------|-------|
| 0_baseline | 0.0 |  | 0 | 0 | advance | experiment runner starting; publisher OFF |
| 0_baseline | 1072.0 | 2.2 | 0 | 0 | advance | no publisher uploads |
| 0_baseline | 1060.0 | 2.2 | 0 | 0 | advance | no publisher uploads |
| runner_start | 0.0 |  | 0 | 0 | advance | phase2_sweep_1.0_to_0.5_v1; phase0=1.0s/30m; phase2=0.75,0.5 adaptive window |
| runner_start | 0.0 |  | 0 | 0 | advance | phase2_sweep_1.0_to_0.5_v1; phase0=1.0s/30m; phase2=0.75,0.5 adaptive window |
| 1_publisher_parallel | 0.0 | 2.2 | 0 | 0 | skip | runner died during Phase 1 sleep after 15:37 JST start; no ended_at. Not reconst |
| 1_publisher_parallel | 1528.7 | 1.0 | 0 | 0 | advance | explicit 1.0s remeasure after runner loss; publisher ON; window_end=early_advanc |
| 2a | 1654.6 | 0.75 | 0 | 0 | advance | window_end=early_advance |
| 2b | 1837.0 | 0.5 | 0 | 0 | advance | window_end=max_window |
| 3a | 1766.0 | 0.5 | 0 | 0 | advance | light + key people |
| 3b | 1730.0 | 0.5 | 0 | 0 | advance | companies 1834+ and key people |
| 4_global_queue | 1622.5 | 0.5 | 0 | 0 | advance | recommended_mode=global_queue |
| 5_recruits | 0.0 | 0.5 | 0 | 0 | advance | recruits_total_pages=207420 |

## Publisher

- Phase 0 baseline at **1.0s** (30 min); phase 2 sweeps **0.75s → 0.5s** with min 20 min / max 60 min windows.
- Parallel publisher tmux recommended when fetch pph stays ≥80% of phase-0 baseline (phase 1 gate).
- Large `tar.gz` uploads are queued in `publisher_mcp_queue/` for MCP binary upload + SHA verify.

## Recruits completion estimate

- Pages remaining ≈ `207420` minus local max page; at `0.5`s per page, duration ≈ `(remaining × 0.5) / 3600` hours.

## Phase 5 recruits observation

The `5_recruits` log row records `pages_per_hour=0.0` because `record_phase` measured **key_people** (`page_start=page_end=1`) while that fetch was stopped. Recruits ran for the same 3600s window (2026-10-18 21:47:21–22:47:21 JST). Local `section_recruits/recruits_page_*.json` mtimes in that window are pages **1–1536** (**1536 pages/h**). The row's `http_429=0`, `http_401=0`, `http_5xx=0` come from `experiment_api.log` over that window. Live recruits search during the window returned HTTP 200.

