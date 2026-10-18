#!/usr/bin/env python3
"""Musubu read-only collector: fetch API pages, gzip locally, emit manifest for Drive upload."""
from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

API_BASE = "https://api.production.musubu.in"
ORIGIN = "https://app.production.musubu.in"
CHROME_LS = Path("/home/ubuntu/.config/google-chrome/Default/Local Storage/leveldb")
DEFAULT_OUT = Path("/workspace/musubu-data")
INTERVAL_SEC = 2.2

SECTION9_GETS: list[tuple[str, str]] = [
    ("master_categories.json", "/api/categories"),
    ("master_second_categories.json", "/api/categories/second_categories"),
    ("master_event_categories.json", "/api/event_categories"),
    ("master_regions.json", "/api/regions"),
    ("master_prefectures.json", "/api/prefectures"),
    ("master_cities.json", "/api/cities"),
    ("master_wards.json", "/api/wards"),
    ("master_banks.json", "/api/banks"),
    ("master_brands.json", "/api/brands"),
    ("master_products.json", "/api/products"),
    ("master_occupations.json", "/api/occupations"),
    ("master_publication_media.json", "/api/publication_media"),
    ("master_recruit_keywords.json", "/api/recruit_keywords"),
    ("master_needs.json", "/api/companies/needs"),
]

SECTION8_GETS: list[tuple[str, str]] = [
    ("target_tiers_info.json", "/api/target_accounts/tiers_info"),
    ("target_lists.json", "/api/target_account_lists"),
    ("target_search_conditions.json", "/api/search_conditions"),
    ("target_company_ids.json", "/api/target_accounts/company_ids"),
]

SEARCH_RESOURCES = {
    "key_people": ("key_people", "/api/key_people/search"),
    "companies": ("companies", "/api/companies/search"),
    "departments": ("departments", "/api/departments/search"),
    "offices": ("offices", "/api/offices/search"),
    "stores": ("stores", "/api/stores/search"),
    "facilities": ("facilities", "/api/facilities/search"),
    "recruits": ("recruits", "/api/recruits/search"),
}


def extract_bearer_token() -> str:
    data = b"".join(p.read_bytes() for p in CHROME_LS.iterdir() if p.is_file())
    m = re.search(
        rb'\{"body":\{"access_token":"(eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+)"',
        data,
    )
    if not m:
        raise SystemExit("Auth0 access_token not found in Chrome local storage")
    return m.group(1).decode()


def api_call(token: str, method: str, path: str, body: dict | None = None) -> tuple[int, Any]:
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        API_BASE + path,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Origin": ORIGIN,
            "Referer": ORIGIN + "/",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read()
            return resp.status, json.loads(raw.decode() or "null")
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            parsed = json.loads(raw.decode() or "null")
        except Exception:
            parsed = {"error": raw[:500].decode("utf-8", "replace")}
        return e.code, parsed


def write_gzip_artifact(out_dir: Path, name: str, payload: Any) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    gz = gzip.compress(raw, compresslevel=6)
    gz_path = out_dir / name
    b64_path = out_dir / (name + ".b64")
    gz_path.write_bytes(gz)
    b64_path.write_text(base64.b64encode(gz).decode("ascii"))
    return {
        "file": name,
        "drive_upload_name": name + ".b64",
        "raw_bytes": len(raw),
        "gzip_bytes": len(gz),
        "raw_sha256": hashlib.sha256(raw).hexdigest(),
        "gzip_sha256": hashlib.sha256(gz).hexdigest(),
        "local_gz_path": str(gz_path),
        "local_b64_path": str(b64_path),
    }


def fetch_section9(token: str, out_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for filename, path in SECTION9_GETS:
        time.sleep(INTERVAL_SEC)
        status, parsed = api_call(token, "GET", path)
        rec = write_gzip_artifact(out_dir / "section9", filename, parsed)
        rec.update({"section": 9, "endpoint": path, "http_status": status})
        records.append(rec)
        print(f"GET {status} {path} -> {filename} gzip={rec['gzip_bytes']}B")
    return records


def fetch_section8(token: str, out_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for filename, path in SECTION8_GETS:
        time.sleep(INTERVAL_SEC)
        status, parsed = api_call(token, "GET", path)
        rec = write_gzip_artifact(out_dir / "section8", filename, parsed)
        rec.update({"section": 8, "endpoint": path, "http_status": status})
        records.append(rec)
        print(f"GET {status} {path} -> {filename}")
    # paginated target_accounts
    page = 1
    per_page = 50
    all_accounts: list[Any] = []
    meta = None
    while True:
        time.sleep(INTERVAL_SEC)
        path = f"/api/target_accounts?page={page}&per_page={per_page}"
        status, parsed = api_call(token, "GET", path)
        if status != 200 or not isinstance(parsed, dict):
            records.append({"section": 8, "endpoint": path, "http_status": status, "error": parsed})
            break
        items = parsed.get("target_accounts") or []
        all_accounts.extend(items)
        meta = parsed.get("meta") or meta
        total_pages = (meta or {}).get("total_pages") or 1
        print(f"GET {status} target_accounts page {page}/{total_pages} items={len(items)}")
        if page >= total_pages:
            payload = {
                "target_accounts": all_accounts,
                "meta": meta,
                "tier_counts": parsed.get("tier_counts"),
                "client_status_counts": parsed.get("client_status_counts"),
            }
            rec = write_gzip_artifact(out_dir / "section8", "target_accounts_all.json", payload)
            rec.update({"section": 8, "endpoint": "/api/target_accounts", "http_status": 200, "pages": page})
            records.append(rec)
            break
        page += 1
    return records


def fetch_search_page(
    token: str,
    resource: str,
    page: int,
    out_dir: Path,
    extra_body: dict | None = None,
) -> dict[str, Any]:
    list_key, path = SEARCH_RESOURCES[resource]
    body: dict[str, Any] = {"page": page}
    if extra_body:
        body.update(extra_body)
    time.sleep(INTERVAL_SEC)
    status, parsed = api_call(token, "POST", path, body)
    name = f"{resource}_page_{page:05d}.json"
    rec = write_gzip_artifact(out_dir / f"section_{resource}", name, parsed)
    meta = parsed.get("meta") if isinstance(parsed, dict) else None
    items = parsed.get(list_key) if isinstance(parsed, dict) else None
    rec.update(
        {
            "section": resource,
            "endpoint": path,
            "http_status": status,
            "page": page,
            "meta": meta,
            "item_count": len(items) if isinstance(items, list) else None,
        }
    )
    print(
        f"POST {status} {path} page={page} items={rec.get('item_count')} "
        f"meta={meta}"
    )
    return rec


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument(
        "action",
        choices=["section9", "section8", "search_page", "checkpoint_manifest"],
    )
    p.add_argument("--resource", choices=list(SEARCH_RESOURCES))
    p.add_argument("--page", type=int)
    args = p.parse_args()
    token = extract_bearer_token()
    args.out.mkdir(parents=True, exist_ok=True)

    manifest: dict[str, Any] = {
        "created_at_epoch": int(time.time()),
        "api_base": API_BASE,
        "interval_sec": INTERVAL_SEC,
        "artifacts": [],
    }

    if args.action == "section9":
        manifest["artifacts"] = fetch_section9(token, args.out)
    elif args.action == "section8":
        manifest["artifacts"] = fetch_section8(token, args.out)
    elif args.action == "search_page":
        if not args.resource or not args.page:
            raise SystemExit("--resource and --page required")
        manifest["artifacts"] = [fetch_search_page(token, args.resource, args.page, args.out)]
    else:
        manifest_path = args.out / "manifest_latest.json"
        if manifest_path.exists():
            print(manifest_path.read_text()[:2000])
            return
        raise SystemExit("no manifest yet")

    manifest_path = args.out / f"manifest_{args.action}.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    print("wrote", manifest_path)


if __name__ == "__main__":
    main()
