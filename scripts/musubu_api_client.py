#!/usr/bin/env python3
"""Reused HTTPS connection + in-memory Auth0 token for Musubu API."""
from __future__ import annotations

import base64
import json
import re
import time
import urllib.error
from musubu_request_gate import GatedHTTPSConnection as HTTPSConnection
from pathlib import Path
from typing import Any

API_HOST = "api.production.musubu.in"
API_BASE = f"https://{API_HOST}"
ORIGIN = "https://app.production.musubu.in"
CHROME_LS = Path("/home/ubuntu/.config/google-chrome/Default/Local Storage/leveldb")


def _jwt_exp_epoch(token: str) -> int | None:
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload))
        exp = data.get("exp")
        return int(exp) if exp is not None else None
    except Exception:
        return None


def extract_bearer_token() -> str:
    data = b"".join(p.read_bytes() for p in CHROME_LS.iterdir() if p.is_file())
    candidates = re.findall(
        rb'\{"body":\{"access_token":"(eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+)"',
        data,
    )
    now = int(time.time())
    eligible: list[tuple[int, bytes]] = []
    for token in candidates:
        exp = _jwt_exp_epoch(token.decode())
        if exp is not None and exp > now + 120:
            eligible.append((exp, token))
    if not eligible:
        raise RuntimeError("No unexpired Auth0 access_token found in Chrome local storage")
    return max(eligible, key=lambda item: item[0])[1].decode()


class MusubuApiClient:
    def __init__(self) -> None:
        self._token: str | None = None
        self._token_exp: int | None = None
        self._conn: HTTPSConnection | None = None

    def _ensure_token(self) -> str:
        now = int(time.time())
        if self._token and self._token_exp and now < self._token_exp - 120:
            return self._token
        self._token = extract_bearer_token()
        self._token_exp = _jwt_exp_epoch(self._token)
        return self._token

    def _connection(self) -> HTTPSConnection:
        if self._conn is None:
            self._conn = HTTPSConnection(API_HOST, timeout=120)
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None

    def request(
        self,
        method: str,
        path: str,
        body: dict | None = None,
        *,
        resource: str | None = None,
        page: int | None = None,
    ) -> tuple[int, Any]:
        from musubu_experiment_lib import log_api_call

        token = self._ensure_token()
        data = None if body is None else json.dumps(body).encode()
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Origin": ORIGIN,
            "Referer": ORIGIN + "/",
            "Connection": "keep-alive",
            "User-Agent": "Python-urllib/3.12",
        }
        conn = self._connection()
        try:
            conn.request(method, path, body=data, headers=headers)
            resp = conn.getresponse()
            raw = resp.read()
            status = resp.status
            try:
                parsed = json.loads(raw.decode() or "null")
            except Exception:
                parsed = {"error": raw[:500].decode("utf-8", "replace")}
            log_api_call(
                method=method,
                path=path,
                http_status=status,
                resource=resource,
                page=page,
            )
            if status == 401:
                self._token = None
                self._token_exp = None
            return status, parsed
        except (ConnectionError, OSError, urllib.error.HTTPError) as exc:
            self.close()
            if isinstance(exc, urllib.error.HTTPError):
                raw = exc.read()
                try:
                    parsed = json.loads(raw.decode() or "null")
                except Exception:
                    parsed = {"error": str(exc)}
                log_api_call(
                    method=method,
                    path=path,
                    http_status=exc.code,
                    resource=resource,
                    page=page,
                )
                return exc.code, parsed
            raise
