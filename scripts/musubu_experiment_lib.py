#!/usr/bin/env python3
"""Shared helpers for Musubu parallelization experiment."""
from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")


def now_jst_iso() -> str:
    return datetime.now(JST).isoformat(timespec="seconds")

DATA = Path("/workspace/musubu-data")
LOG_PATH = DATA / "experiment_log.json"
STATE_PATH = DATA / "experiment_state.json"
CONFIG_PATH = DATA / "experiment_config.json"
API_LOG = DATA / "experiment_api.log"
ABORT_FLAG = DATA / "EXPERIMENT_ABORT_401.flag"
DRIVE_LOG = DATA / "drive_publisher_log.json"
KP_DIR = DATA / "section_key_people"


def max_key_people_page() -> int:
    pages: list[int] = []
    for p in KP_DIR.glob("key_people_page_*.json"):
        if p.name.endswith(".json.b64"):
            continue
        m = re.search(r"_(\d+)\.json$", p.name)
        if m:
            pages.append(int(m.group(1)))
    return max(pages) if pages else 0


def load_json(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))


def append_experiment_log(entry: dict[str, Any]) -> None:
    log: list[dict[str, Any]] = load_json(LOG_PATH, [])
    log.append(entry)
    save_json(LOG_PATH, log)


def set_experiment_phase(phase: str, extra: dict[str, Any] | None = None) -> None:
    state = load_json(STATE_PATH, {})
    state["experiment_phase"] = phase
    state["updated_at_epoch"] = int(time.time())
    state["updated_at_jst"] = now_jst_iso()
    if extra:
        state.update(extra)
    save_json(STATE_PATH, state)
    try:
        import subprocess

        subprocess.run(
            ["python3", "/workspace/scripts/musubu_collect.py", "build_checkpoint"],
            check=False,
            timeout=120,
        )
    except Exception:
        pass


def get_interval_sec() -> float:
    cfg = load_json(CONFIG_PATH, {})
    if "EXPERIMENT_INTERVAL_SEC" in cfg:
        return float(cfg["EXPERIMENT_INTERVAL_SEC"])
    env = os.environ.get("EXPERIMENT_INTERVAL_SEC")
    if env:
        return float(env)
    return 2.2


def set_interval_sec(value: float) -> None:
    cfg = load_json(CONFIG_PATH, {})
    cfg["EXPERIMENT_INTERVAL_SEC"] = value
    save_json(CONFIG_PATH, cfg)
    os.environ["EXPERIMENT_INTERVAL_SEC"] = str(value)
    state = load_json(STATE_PATH, {})
    state["EXPERIMENT_INTERVAL_SEC"] = value
    state["updated_at_epoch"] = int(time.time())
    state["updated_at_jst"] = now_jst_iso()
    save_json(STATE_PATH, state)


def count_http_in_window(start_epoch: int, end_epoch: int) -> dict[str, int]:
    counts = {"http_429": 0, "http_401": 0, "http_5xx": 0}
    if not API_LOG.is_file():
        return counts
    for line in API_LOG.read_text().splitlines():
        try:
            rec = json.loads(line)
        except Exception:
            continue
        ts = rec.get("ts")
        if ts is None or ts < start_epoch or ts > end_epoch:
            continue
        code = rec.get("http_status")
        if code == 429:
            counts["http_429"] += 1
        elif code == 401:
            counts["http_401"] += 1
        elif isinstance(code, int) and code >= 500:
            counts["http_5xx"] += 1
    return counts


def pages_per_hour(start_page: int, end_page: int, elapsed_sec: float) -> float:
    if elapsed_sec <= 0:
        return 0.0
    return max(0, end_page - start_page) * 3600.0 / elapsed_sec


def gate_429_failed(counts: dict[str, int]) -> bool:
    return counts.get("http_429", 0) >= 2


def abort_if_401() -> None:
    if ABORT_FLAG.is_file():
        raise SystemExit("experiment aborted: HTTP 401")


def log_api_call(
    *,
    method: str,
    path: str,
    http_status: int,
    resource: str | None = None,
    page: int | None = None,
) -> None:
    rec = {
        "ts": int(time.time()),
        "method": method,
        "path": path,
        "http_status": http_status,
        "resource": resource,
        "page": page,
    }
    with API_LOG.open("a") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    if http_status == 401:
        ABORT_FLAG.write_text(json.dumps(rec, indent=2))
        raise SystemExit("HTTP 401 — fetch stopped")
