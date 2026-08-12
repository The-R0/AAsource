"""Canonical Reference facts backed by the narrow Eastmoney fact module."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime
from typing import Any

from ashare_data.domain.errors import AshareDataError, ErrorCode
from ashare_data.domain.identifiers import canonicalize_symbol
from ashare_data.domain.models import SourceRef, WarningItem
from ashare_data.services._reference_eastmoney import _get_reference_source

REFERENCE_SCHEMA_VERSION = "1.0"

_REQUIRED_FIELDS = {
    "dragon_tiger": {"symbol", "trade_date"},
    "dragon_tiger_seats": {"symbol", "seat_name"},
    "institutional_dragon_tiger": {"symbol", "trade_date"},
    "block_trades": {"symbol", "trade_date"},
    "money_flow": {"symbol", "trade_date"},
    "shareholders": {"symbol", "shareholder_name"},
    "fund_holdings": {"symbol"},
}

_UNITS = {
    "price": "CNY_per_share",
    "volume": "shares",
    "amount": "CNY",
    "market_cap": "CNY",
    "percent_fields": "percent_points",
}


def _date_text(value: Any) -> str | None:
    if value in (None, "", "-"):
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    return text[:10]


def _wrap(dataset: str, payload: dict[str, Any], query: dict[str, Any]):
    source = dict(payload.get("source") or {})
    provider = str(source.get("provider") or "eastmoney")
    sources = [SourceRef(provider=provider, role=f"reference:{dataset}")]
    if payload.get("status") in {"UNAVAILABLE", "ERROR", "error"} or payload.get("error"):
        warnings = [WarningItem(code="REFERENCE_DEGRADED", message=str(payload.get("error") or payload.get("status")))]
        return None, sources, warnings, True

    records = list(payload.get("records") or [])
    required = _REQUIRED_FIELDS[dataset]
    drifted_records = sum(not required.issubset(record) for record in records)
    warnings: list[WarningItem] = []
    degraded = drifted_records > 0
    if degraded:
        warnings.append(
            WarningItem(
                code="REFERENCE_SCHEMA_DRIFT",
                message=f"{drifted_records} upstream rows miss required canonical fields: {sorted(required)}",
            )
        )
    cache = source.get("cache") or {}
    cache_hit = cache.get("hit")
    if isinstance(cache.get("calls"), list) and cache["calls"]:
        cache_hit = all(bool(call.get("cache", {}).get("hit")) for call in cache["calls"])
    data = {
        "data_class": "reference",
        "dataset": dataset,
        "reference_schema_version": REFERENCE_SCHEMA_VERSION,
        "query": query,
        "record_count": len(records),
        "truncated": bool(payload.get("truncated")),
        "records": records,
        "units": dict(_UNITS),
        "provenance": {
            "provider": provider,
            "adapter_version": source.get("adapter_version"),
            "endpoint": source.get("endpoint"),
            "fetched_at": source.get("fetched_at"),
            "cache_hit": cache_hit,
        },
    }
    return data, sources, warnings, degraded


def _call(dataset: str, query: dict[str, Any], fn: Callable[[], dict[str, Any]]):
    try:
        return _wrap(dataset, fn(), query)
    except Exception as exc:  # reference facts never break the price plane
        sources = [SourceRef(provider="eastmoney", role=f"reference:{dataset}")]
        return None, sources, [WarningItem(code="REFERENCE_DEGRADED", message=str(exc))], True


def reference_status() -> dict[str, Any]:
    """Report Reference Fact readiness without performing remote queries."""
    return _get_reference_source().status()


def dragon_tiger(symbol: str | None = None, trade_date: str = "", limit: int = 100):
    canonical = canonicalize_symbol(symbol) if symbol else None
    query = {"symbol": canonical, "trade_date": _date_text(trade_date), "limit": limit}
    return _call("dragon_tiger", query, lambda: _get_reference_source().dragon_tiger_list(trade_date, canonical, limit))


def dragon_tiger_seats(symbol: str, trade_date: str, limit: int = 20):
    canonical = canonicalize_symbol(symbol)
    query = {"symbol": canonical, "trade_date": _date_text(trade_date), "limit": limit}
    return _call("dragon_tiger_seats", query, lambda: _get_reference_source().dragon_tiger_seats(canonical, trade_date, limit))


def institutional_dragon_tiger(start_date: str, end_date: str, symbol: str | None = None, limit: int = 100):
    canonical = canonicalize_symbol(symbol) if symbol else None
    query = {"symbol": canonical, "start_date": _date_text(start_date), "end_date": _date_text(end_date), "limit": limit}
    return _call(
        "institutional_dragon_tiger",
        query,
        lambda: _get_reference_source().institutional_dragon_tiger(start_date, end_date, canonical, limit),
    )


def block_trades(symbol: str | None = None, start_date: str = "", end_date: str = "", category: str = "A股", limit: int = 100):
    canonical = canonicalize_symbol(symbol) if symbol else None
    query = {"symbol": canonical, "start_date": _date_text(start_date), "end_date": _date_text(end_date), "category": category, "limit": limit}
    return _call(
        "block_trades",
        query,
        lambda: _get_reference_source().block_trades(start_date, end_date, category, canonical, limit),
    )


def money_flow(symbol: str, limit: int = 100):
    canonical = canonicalize_symbol(symbol)
    query = {"symbol": canonical, "limit": limit}
    return _call("money_flow", query, lambda: _get_reference_source().money_flow(canonical, limit))


def shareholders(symbol: str, report_date: str = "", limit: int = 20):
    canonical = canonicalize_symbol(symbol)
    query = {"symbol": canonical, "report_date": _date_text(report_date), "limit": limit}
    return _call("shareholders", query, lambda: _get_reference_source().top_float_shareholders(canonical, report_date, limit))


def fund_holdings(report_date: str = "", symbol: str | None = None, limit: int = 100):
    canonical = canonicalize_symbol(symbol) if symbol else None
    query = {"symbol": canonical, "report_date": _date_text(report_date), "limit": limit}
    return _call("fund_holdings", query, lambda: _get_reference_source().fund_holdings(report_date, canonical, limit))


def dispatch(dataset: str, **kwargs: Any):
    mapping = {
        "dragon-tiger": dragon_tiger,
        "dragon-tiger-seats": dragon_tiger_seats,
        "institutional-dragon-tiger": institutional_dragon_tiger,
        "block-trades": block_trades,
        "money-flow": money_flow,
        "shareholders": shareholders,
        "fund-holdings": fund_holdings,
    }
    fn = mapping.get(dataset)
    if not fn:
        raise AshareDataError(ErrorCode.INVALID_REQUEST, f"Unknown reference dataset: {dataset}")
    return fn(**kwargs)
