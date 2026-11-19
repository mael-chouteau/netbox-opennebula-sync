"""Minimal NetBox REST client with idempotent helpers."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from .config import NetBoxConfig

log = logging.getLogger(__name__)


class NetBoxClient:
    def __init__(self, cfg: NetBoxConfig, dry_run: bool = False):
        self.cfg = cfg
        self.dry_run = dry_run
        self.stats = {"created": 0, "updated": 0, "skipped": 0, "errors": 0}
        token = cfg.token
        auth = f"Bearer {token}" if token.startswith("nbt_") else f"Token {token}"
        headers = {
            "Authorization": auth,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if cfg.host_header:
            headers["Host"] = cfg.host_header
            headers["X-Forwarded-Proto"] = "https"
        proxies = cfg.socks_proxy
        # httpx uses proxy= for all schemes when a string is given
        self._client = httpx.Client(
            base_url=cfg.url.rstrip("/") + "/",
            headers=headers,
            verify=cfg.verify_ssl,
            timeout=cfg.timeout,
            proxy=proxies,
            follow_redirects=True,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> NetBoxClient:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        if not path.startswith("api/"):
            path = "api/" + path.lstrip("/")
        resp = self._client.request(method, path, **kwargs)
        return resp

    def get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        resp = self.request("GET", path, params=params)
        if resp.status_code >= 400:
            raise RuntimeError(f"GET {path} HTTP {resp.status_code}: {resp.text[:500]}")
        return resp.json()

    def find_one(self, path: str, params: dict[str, Any]) -> dict[str, Any] | None:
        data = self.get_json(path, {**params, "limit": 1})
        results = data.get("results") or []
        return results[0] if results else None

    def _rewrite_next(self, next_url: str | None) -> str | None:
        """Map absolute NetBox pagination URLs back onto our base_url (e.g. 127.0.0.1:8001)."""
        if not next_url:
            return None
        if next_url.startswith("http://") or next_url.startswith("https://"):
            from urllib.parse import urlparse

            parsed = urlparse(next_url)
            path = parsed.path or "/"
            if parsed.query:
                path = f"{path}?{parsed.query}"
            return path.lstrip("/")
        return next_url

    def list_all(self, path: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        params = dict(params or {})
        params.setdefault("limit", 100)
        out: list[dict[str, Any]] = []
        next_url: str | None = path
        first = True
        while next_url:
            if first:
                data = self.get_json(next_url, params)
                first = False
            else:
                resp = self._client.get(next_url)
                if resp.status_code >= 400:
                    raise RuntimeError(f"GET {next_url} HTTP {resp.status_code}")
                data = resp.json()
            out.extend(data.get("results") or [])
            next_url = self._rewrite_next(data.get("next"))
        return out

    def ensure(
        self,
        kind: str,
        path: str,
        lookup: dict[str, Any],
        payload: dict[str, Any],
        update_fields: list[str] | None = None,
    ) -> dict[str, Any] | None:
        existing = self.find_one(path, lookup)
        if existing:
            if update_fields:
                patch = {
                    k: payload[k]
                    for k in update_fields
                    if k in payload and _needs_update(existing.get(k), payload[k])
                }
                if patch:
                    return self._write("PATCH", kind, f"{path}{existing['id']}/", patch, existing)
            self.stats["skipped"] += 1
            log.debug("skip %s %s id=%s", kind, lookup, existing.get("id"))
            return existing
        return self._write("POST", kind, path, payload, None)

    def _write(
        self,
        method: str,
        kind: str,
        path: str,
        payload: dict[str, Any],
        existing: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        label = payload.get("name") or payload.get("address") or payload.get("slug") or path
        if self.dry_run:
            action = "update" if existing else "create"
            log.info("[dry-run] %s %s %s", action, kind, label)
            if existing:
                self.stats["updated"] += 1
                return existing
            self.stats["created"] += 1
            # Synthetic object so dry-run can walk the full reconcile chain
            stub = dict(payload)
            stub.setdefault("id", -abs(hash((kind, str(label)))) % 10_000_000 or 1)
            stub.setdefault("name", label)
            return stub
        resp = self.request(method, path, json=payload)
        if resp.status_code in (200, 201):
            data = resp.json()
            if existing:
                self.stats["updated"] += 1
                log.info("updated %s %s id=%s", kind, label, data.get("id"))
            else:
                self.stats["created"] += 1
                log.info("created %s %s id=%s", kind, label, data.get("id"))
            return data
        self.stats["errors"] += 1
        log.error(
            "%s %s %s HTTP %s: %s",
            method,
            kind,
            label,
            resp.status_code,
            resp.text[:500],
        )
        return existing

    def delete(self, path: str, obj_id: int) -> bool:
        if self.dry_run:
            log.info("[dry-run] delete %s%s", path, obj_id)
            return True
        resp = self.request("DELETE", f"{path}{obj_id}/")
        if resp.status_code in (200, 204):
            return True
        log.error("DELETE %s%s HTTP %s: %s", path, obj_id, resp.status_code, resp.text[:300])
        return False

    def ping(self) -> dict[str, Any]:
        return self.get_json("api/status/")


def _needs_update(current: Any, desired: Any) -> bool:
    if isinstance(desired, dict) and "id" in desired:
        if isinstance(current, dict):
            return current.get("id") != desired.get("id")
        return current != desired.get("id")
    if isinstance(desired, list):
        # tags / simple lists
        if isinstance(current, list):
            cur_ids = [
                (x.get("id") if isinstance(x, dict) else x) for x in current
            ]
            des_ids = [
                (x.get("id") if isinstance(x, dict) else x) for x in desired
            ]
            return cur_ids != des_ids
        return True
    if isinstance(current, dict) and "value" in current:
        return current.get("value") != desired
    if isinstance(current, dict) and "id" in current and not isinstance(desired, dict):
        return current.get("id") != desired
    return current != desired


def slugify(name: str) -> str:
    import unicodedata

    nfkd = unicodedata.normalize("NFKD", name)
    ascii_ = "".join(c for c in nfkd if not unicodedata.combining(c))
    out = []
    for c in ascii_.lower():
        if c.isalnum():
            out.append(c)
        elif c in " '._/" or c.isspace():
            out.append("-")
    return "-".join(p for p in "".join(out).split("-") if p) or "item"
