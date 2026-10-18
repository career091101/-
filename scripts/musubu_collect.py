#!/usr/bin/env python3
"""Musubu read-only collector: fetch API pages, gzip locally, emit manifest for Drive upload."""
from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import json
import re
import tarfile
import time
import urllib.error
import urllib.request
from io import BytesIO
from pathlib import Path
from typing import Any

API_BASE = "https://api.production.musubu.in"
ORIGIN = "https://app.production.musubu.in"
CHROME_LS = Path("/home/ubuntu/.config/google-chrome/Default/Local Storage/leveldb")
DEFAULT_OUT = Path("/workspace/musubu-data")
INTERVAL_SEC = 2.2
# Align with companies archives on Drive (~200 search pages per tar.gz).
SEARCH_TAR_PAGE_SIZE = 200
KEY_PEOPLE_FIRST_PACK_PAGE = 4  # pages 1–3 remain separate .json.gz on Drive

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


def append_artifact_manifest(out_dir: Path, manifest_name: str, rec: dict[str, Any]) -> None:
    path = out_dir / manifest_name
    entries: list[dict[str, Any]] = []
    if path.exists():
        entries = json.loads(path.read_text()).get("artifacts") or []
    page = rec.get("page")
    page_start = rec.get("page_start")
    if page is not None:
        entries = [e for e in entries if e.get("page") != page]
    elif page_start is not None:
        entries = [
            e
            for e in entries
            if not (e.get("page_start") == page_start and e.get("page_end") == rec.get("page_end"))
        ]
    entries.append(rec)
    entries.sort(key=lambda e: (e.get("page") or 0))
    payload = {
        "updated_at_epoch": int(time.time()),
        "api_base": API_BASE,
        "interval_sec": INTERVAL_SEC,
        "artifacts": entries,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))


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


def chunk_page_end(first_page: int, chunk_size: int, chunk_index: int) -> int:
    """chunk_index 0 => first_page .. first_page+chunk_size-1."""
    return first_page + (chunk_index + 1) * chunk_size - 1


def pack_search_pages_tar(
    resource: str,
    page_start: int,
    page_end: int,
    out_dir: Path,
) -> dict[str, Any]:
    if resource != "key_people":
        raise SystemExit("pack_tar currently implemented for key_people only")
    section_dir = out_dir / f"section_{resource}"
    archive_dir = out_dir / "archives" / resource
    archive_dir.mkdir(parents=True, exist_ok=True)
    members: list[dict[str, Any]] = []
    buf = BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for page in range(page_start, page_end + 1):
            name = f"{resource}_page_{page:05d}.json"
            gz_path = section_dir / name
            if not gz_path.is_file():
                raise SystemExit(f"missing page file: {gz_path}")
            gz_bytes = gz_path.read_bytes()
            ti = tarfile.TarInfo(name=name)
            ti.size = len(gz_bytes)
            tar.addfile(ti, BytesIO(gz_bytes))
            members.append(
                {
                    "page": page,
                    "member": name,
                    "gzip_bytes": len(gz_bytes),
                    "gzip_sha256": hashlib.sha256(gz_bytes).hexdigest(),
                }
            )
    tar_bytes = buf.getvalue()
    tar_name = f"{resource}_pages_{page_start:05d}-{page_end:05d}.tar.gz"
    tar_path = archive_dir / tar_name
    tar_path.write_bytes(tar_bytes)
    b64_path = tar_path.with_suffix(tar_path.suffix + ".b64")
    if len(tar_bytes) <= 950_000:
        b64_path.write_text(base64.b64encode(tar_bytes).decode("ascii"))
    elif b64_path.exists():
        b64_path.unlink()
    rec = {
        "file": tar_name,
        "drive_upload_name": tar_name if len(tar_bytes) > 950_000 else tar_name + ".b64",
        "format": "tar.gz_members_are_gzip_json",
        "page_start": page_start,
        "page_end": page_end,
        "page_count": page_end - page_start + 1,
        "tar_bytes": len(tar_bytes),
        "tar_sha256": hashlib.sha256(tar_bytes).hexdigest(),
        "local_tar_path": str(tar_path),
        "local_b64_path": str(b64_path) if b64_path.exists() else None,
        "members": members,
        "section": resource,
    }
    append_artifact_manifest(out_dir, f"manifest_{resource}_archives.json", rec)
    print(f"packed {tar_name} pages={rec['page_count']} tar_bytes={len(tar_bytes)}")
    return rec


def maybe_pack_complete_key_people_chunks(page_end: int, out_dir: Path) -> list[dict[str, Any]]:
    packed: list[dict[str, Any]] = []
    first = KEY_PEOPLE_FIRST_PACK_PAGE
    size = SEARCH_TAR_PAGE_SIZE
    if page_end < first:
        return packed
    last_complete_end = first + ((page_end - first + 1) // size) * size - 1
    chunk_idx = 0
    while True:
        start = first + chunk_idx * size
        end = chunk_page_end(first, size, chunk_idx)
        if end > last_complete_end:
            break
        manifest_path = out_dir / "manifest_key_people_archives.json"
        if manifest_path.exists():
            existing = {
                (a.get("page_start"), a.get("page_end"))
                for a in json.loads(manifest_path.read_text()).get("artifacts") or []
            }
            if (start, end) in existing:
                chunk_idx += 1
                continue
        packed.append(pack_search_pages_tar("key_people", start, end, out_dir))
        chunk_idx += 1
    return packed


def fetch_search_range(
    token: str,
    resource: str,
    page_start: int,
    page_end: int,
    out_dir: Path,
    auto_pack: bool = True,
) -> list[dict[str, Any]]:
    manifest_name = f"manifest_{resource}_pages.json"
    records: list[dict[str, Any]] = []
    for page in range(page_start, page_end + 1):
        rec = fetch_search_page(token, resource, page, out_dir)
        append_artifact_manifest(out_dir, manifest_name, rec)
        records.append(rec)
    if auto_pack and resource == "key_people":
        maybe_pack_complete_key_people_chunks(page_end, out_dir)
    return records


def build_checkpoint(out_dir: Path) -> dict[str, Any]:
    artifacts: list[dict[str, Any]] = []
    for name in ("manifest_section9.json", "manifest_section8.json"):
        p = out_dir / name
        if p.exists():
            artifacts.extend(json.loads(p.read_text()).get("artifacts") or [])
    kp = out_dir / "manifest_key_people_pages.json"
    if kp.exists():
        artifacts.extend(json.loads(kp.read_text()).get("artifacts") or [])
    kp_arch = out_dir / "manifest_key_people_archives.json"
    if kp_arch.exists():
        artifacts.extend(json.loads(kp_arch.read_text()).get("artifacts") or [])
    seen_kp_pages: set[int] = {
        a["page"] for a in artifacts if a.get("section") == "key_people" and a.get("page")
    }
    for gz in sorted((out_dir / "section_key_people").glob("key_people_page_*.json")):
        if gz.name.endswith(".b64"):
            continue
        page = int(gz.name.split("_")[-1].split(".")[0])
        if page in seen_kp_pages:
            continue
        b64 = gz.with_suffix(gz.suffix + ".b64")
        if not b64.exists():
            continue
        gz_bytes = gz.read_bytes()
        artifacts.append(
            {
                "file": gz.name,
                "drive_upload_name": gz.name + ".b64",
                "gzip_bytes": len(gz_bytes),
                "gzip_sha256": hashlib.sha256(gz_bytes).hexdigest(),
                "local_gz_path": str(gz),
                "local_b64_path": str(b64),
                "section": "key_people",
                "page": page,
            }
        )
        seen_kp_pages.add(page)
    kp_pages = sorted(seen_kp_pages)
    out_path = out_dir / "musubu_cursor_checkpoint_20261018.json"
    prior: dict[str, Any] = {}
    if out_path.exists():
        try:
            prior = json.loads(out_path.read_text())
        except Exception:
            prior = {}
    checkpoint = {
        "schema": "musubu_cursor_checkpoint_v1",
        "status": "in_progress",
        "drive_folder_id": "1kR8pPEahMbgj4ErAzHxCqwU85tMPL8Ea",
        "agent": "cursor",
        "updated_at_epoch": int(time.time()),
        "sections_completed_partial": {
            "9": "fetched_local_section9",
            "8": "fetched_local_section8",
            "2_key_people_pages_saved_locally": kp_pages,
            "2_key_people_pages_protected_on_drive": [1, 2, 3],
            "1_companies_protected_pages": "1-1833 except missing 70",
        },
        "packaging_policy": {
            "search_tar_page_size": SEARCH_TAR_PAGE_SIZE,
            "key_people_first_pack_page": KEY_PEOPLE_FIRST_PACK_PAGE,
            "archive_pattern": "{resource}_pages_{start:05d}-{end:05d}.tar.gz",
            "note": "pages 1-3 stay as legacy .json.gz on Drive; page 4+ pack every 200 pages",
        },
        "next_steps": [
            "upload tar.gz archives (and small .b64) verify tar_sha256",
            "continue key_people pagination through 58552",
            "companies page 70 then 1834+",
            "sections 3-7 search pagination",
        ],
        "artifact_count": len(artifacts),
        "artifacts": artifacts,
        "drive_uploads_verified": prior.get("drive_uploads_verified") or [],
        "2_key_people_pages_on_drive_b64": prior.get("2_key_people_pages_on_drive_b64") or [],
    }
    out_path.write_text(json.dumps(checkpoint, ensure_ascii=False, indent=2))
    print("wrote", out_path, "artifacts=", len(artifacts), "key_people_pages=", len(kp_pages))
    return checkpoint


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument(
        "action",
        choices=[
            "section9",
            "section8",
            "search_page",
            "search_range",
            "pack_tar",
            "build_checkpoint",
            "checkpoint_manifest",
        ],
    )
    p.add_argument(
        "--no-auto-pack",
        action="store_true",
        help="search_range: do not create 200-page tar.gz archives",
    )
    p.add_argument("--resource", choices=list(SEARCH_RESOURCES))
    p.add_argument("--page", type=int)
    p.add_argument("--page-start", type=int)
    p.add_argument("--page-end", type=int)
    args = p.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    if args.action == "build_checkpoint":
        build_checkpoint(args.out)
        return
    if args.action == "pack_tar":
        if not args.resource or args.page_start is None or args.page_end is None:
            raise SystemExit("--resource --page-start --page-end required")
        pack_search_pages_tar(args.resource, args.page_start, args.page_end, args.out)
        build_checkpoint(args.out)
        return

    token = extract_bearer_token()

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
        rec = fetch_search_page(token, args.resource, args.page, args.out)
        append_artifact_manifest(args.out, f"manifest_{args.resource}_pages.json", rec)
        manifest["artifacts"] = [rec]
    elif args.action == "search_range":
        if not args.resource or args.page_start is None or args.page_end is None:
            raise SystemExit("--resource --page-start --page-end required")
        manifest["artifacts"] = fetch_search_range(
            token,
            args.resource,
            args.page_start,
            args.page_end,
            args.out,
            auto_pack=not args.no_auto_pack,
        )
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
