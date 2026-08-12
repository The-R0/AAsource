"""Eastmoney public topic-pool provider (limit-up / limit-down / broken)."""

from __future__ import annotations

import math
from typing import Any

import requests

from ashare_data.domain.identifiers import canonicalize_symbol

UT = "7eea3edcaed734bea9cbfc24409ed989"
TOPIC_BASE = "https://push2ex.eastmoney.com"
TOPIC_ENDPOINTS = {
    "limit_up": "getTopicZTPool",
    "limit_down": "getTopicDTPool",
    "broken_limit": "getTopicZBPool",
}


class EastmoneyProviderError(RuntimeError):
    pass


def _number(value: Any) -> float | None:
    if value in (None, "", "-"):
        return None
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def _get_json(url: str, params: dict[str, Any], *, timeout: float = 20.0) -> dict[str, Any]:
    response = requests.get(url, params=params, timeout=timeout)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise EastmoneyProviderError(f"non-object JSON from {url}")
    return payload


def _normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    code = str(row.get("c") or row.get("code") or "").zfill(6)[-6:]
    symbol = None
    try:
        symbol = canonicalize_symbol(code) if code else None
    except Exception:
        symbol = None
    return {
        "symbol": symbol,
        "code": code,
        "name": row.get("n") or row.get("name"),
        "streak": int(_number(row.get("lbc")) or 0),
        "industry": row.get("hybk") or row.get("industry"),
        "first_limit_time": row.get("fbt"),
        "last_limit_time": row.get("lbt"),
        "break_count": int(_number(row.get("zbc")) or 0),
        "amount": _number(row.get("amount") or row.get("cje")),
        "change_pct": _number(row.get("zdp") or row.get("change_pct")),
        "raw": {
            "c": row.get("c"),
            "n": row.get("n"),
            "lbc": row.get("lbc"),
            "hybk": row.get("hybk"),
            "fbt": row.get("fbt"),
            "lbt": row.get("lbt"),
            "zbc": row.get("zbc"),
        },
    }


def fetch_topic_pool(kind: str, trading_date: str, *, page_size: int = 100) -> dict[str, Any]:
    """Fetch all pages for a public Eastmoney limit topic pool."""
    if kind not in TOPIC_ENDPOINTS:
        raise ValueError(f"unsupported pool kind: {kind}")
    endpoint = TOPIC_ENDPOINTS[kind]
    # ZB (broken) pool rejects fund sort; use first-board-time for up/broken.
    sort = "fund:asc" if kind == "limit_down" else "fbt:asc"
    requested = trading_date.replace("-", "")

    def fetch(page: int) -> dict[str, Any]:
        return _get_json(
            f"{TOPIC_BASE}/{endpoint}",
            {
                "ut": UT,
                "dpt": "wz.ztzt",
                "Pageindex": page,
                "pagesize": page_size,
                "sort": sort,
                "date": requested,
            },
            timeout=20,
        )

    first = fetch(0)
    data = first.get("data") if isinstance(first.get("data"), dict) else None
    if data is None:
        raise EastmoneyProviderError(f"{endpoint} returned no data for {trading_date}")
    qdate = str(data.get("qdate") or "")
    total = int(_number(data.get("tc")) or 0)
    rows = [row for row in data.get("pool") or [] if isinstance(row, dict)]
    pages = math.ceil(total / page_size) if total else 0
    for page in range(1, pages):
        payload = fetch(page)
        page_data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        rows.extend(row for row in page_data.get("pool") or [] if isinstance(row, dict))
    by_code: dict[str, dict[str, Any]] = {}
    for row in rows:
        item = _normalize_row(row)
        if item["code"]:
            by_code[item["code"]] = item
    if total and len(by_code) != total:
        raise EastmoneyProviderError(f"{endpoint} incomplete: fetched {len(by_code)}/{total} rows")
    return {
        "kind": kind,
        "qdate": qdate or requested,
        "requested_date": requested,
        "provider_qdate_differs": bool(qdate and qdate != requested),
        "count": total if total else len(by_code),
        "rows": list(by_code.values()),
        "endpoint": endpoint,
        "provider": "eastmoney",
    }


class EastmoneyProvider:
    name = "eastmoney"

    def status(self) -> dict[str, Any]:
        try:
            # lightweight probe — empty date may fail; use today stamp later in service
            return {"provider": self.name, "status": "ok"}
        except Exception as exc:  # noqa: BLE001
            return {"provider": self.name, "status": "degraded", "error": str(exc)}

    def fetch_limit_pool(self, kind: str, trading_date: str) -> dict[str, Any]:
        return fetch_topic_pool(kind, trading_date)


def get_eastmoney_provider() -> EastmoneyProvider:
    return EastmoneyProvider()
