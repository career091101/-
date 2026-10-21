#!/usr/bin/env python3
"""Parallel resident workers (default 7 @ 0.5s), companies-priority slot plan.

Each worker uses claim_next_page() so multiple companies workers do not collide.
"""
from __future__ import annotations

import json
import multiprocessing as mp
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import musubu_collect as mc  # noqa: E402
from musubu_api_client import MusubuApiClient  # noqa: E402
from musubu_collect import (  # noqa: E402
    effective_api_parallel,
    effective_interval_sec,
    effective_worker_plan,
    fetch_search_page_resident,
)
from musubu_experiment_lib import abort_if_401  # noqa: E402
from musubu_global_queue_fetch import (  # noqa: E402
    COMPANIES_PAGE70_PENDING,
    DATA,
    RESOURCE_RULES,
    claim_next_page,
    quarantine_placeholder,
    release_claim,
    retry_candidates,
)

RESOURCE_RULES_BY_NAME = {
    name: (first, extras, skip) for name, first, extras, skip in RESOURCE_RULES
}

IDLE_SLEEP_SEC = 30.0


def _paused_resources() -> set[str]:
    cfg_path = DATA / "experiment_config.json"
    if not cfg_path.is_file():
        return set()
    try:
        cfg = json.loads(cfg_path.read_text())
        paused = cfg.get("FETCH_PAUSED_RESOURCES") or []
        return {str(x) for x in paused}
    except Exception:
        return set()


def _worker(resource: str, worker_id: int) -> None:
    if resource in _paused_resources():
        print(f"[{resource}#{worker_id}] paused — exiting", flush=True)
        return
    rules = RESOURCE_RULES_BY_NAME
    if resource not in rules:
        print(f"[worker-{worker_id}] unknown resource {resource}", flush=True)
        return
    first, extras, skip = rules[resource]
    mc.INTERVAL_SEC = effective_interval_sec()
    client = MusubuApiClient()
    try:
        for res, page, path in retry_candidates(DATA):
            if res != resource:
                continue
            quarantine_placeholder(path, DATA)
            abort_if_401()
            rec = fetch_search_page_resident(
                client, resource, page, DATA, write_b64=False, log_progress=True
            )
            if rec.get("http_status") != 200:
                return
        while True:
            abort_if_401()
            page = claim_next_page(resource, first, extras, skip)
            if page is None:
                time.sleep(IDLE_SLEEP_SEC)
                continue
            print(f"[{resource}#{worker_id}] page {page}", flush=True)
            try:
                rec = fetch_search_page_resident(
                    client,
                    resource,
                    page,
                    DATA,
                    write_b64=False,
                    log_progress=True,
                )
            finally:
                release_claim(resource, page)
            if rec.get("http_status") != 200:
                return
            if resource == "companies" and page == 70 and rec.get("http_status") == 200:
                COMPANIES_PAGE70_PENDING.parent.mkdir(parents=True, exist_ok=True)
                COMPANIES_PAGE70_PENDING.write_text(str(int(time.time())))
    finally:
        client.close()


def main() -> None:
    parallel = effective_api_parallel()
    plan = effective_worker_plan()
    mc.INTERVAL_SEC = effective_interval_sec()
    print(
        f"parallel_resource_fetch workers={len(plan)} plan={plan} "
        f"interval_sec={mc.INTERVAL_SEC} api_parallel={parallel}",
        flush=True,
    )
    ctx = mp.get_context("spawn")
    processes: list[mp.Process] = []
    for index, resource in enumerate(plan):
        proc = ctx.Process(
            target=_worker,
            args=(resource, index),
            name=f"musubu-fetch-{resource}-{index}",
            daemon=False,
        )
        proc.start()
        processes.append(proc)
    for proc in processes:
        proc.join()
    print("parallel_resource_fetch: all workers exited", flush=True)


if __name__ == "__main__":
    main()
