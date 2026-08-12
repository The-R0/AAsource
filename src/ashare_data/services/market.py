"""Canonical Runtime snapshot facts for full-market Agent queries."""

from __future__ import annotations

import threading
import time
from datetime import date, datetime, time as clock_time
from typing import Any
from zoneinfo import ZoneInfo

import requests

from ashare_data.domain.errors import AshareDataError, ErrorCode
from ashare_data.domain.identifiers import canonicalize_symbol
from ashare_data.domain.models import SourceRef, WarningItem
from ashare_data.normalize.quotes import quote_from_tencent_row
from ashare_data.providers.eastmoney import EastmoneyProviderError, get_eastmoney_provider
from ashare_data.providers.eastmoney_boards import fetch_board_rankings, fetch_stock_signal_rows
from ashare_data.providers.tdx import get_tdx_provider
from ashare_data.providers.tencent import get_tencent_provider
from ashare_data.services.calendar import resolve_trading_dates

SHANGHAI = ZoneInfo("Asia/Shanghai")
MIN_QUOTE_COVERAGE = 0.75
_snapshot_lock = threading.Lock()
_snapshot: dict[str, Any] | None = None


def _is_market_open() -> bool:
    now = datetime.now(SHANGHAI)
    return now.weekday() < 5 and clock_time(9, 15) <= now.time() <= clock_time(15, 5)


def _snapshot_ttl() -> float:
    return 3.0 if _is_market_open() else 300.0


def _canonical_quotes(rows: list[dict[str, Any]], *, retrieved_at: str) -> list[dict[str, Any]]:
    """Keep vendor rows inside the module; only canonical Quote fields cross its seam."""
    facts: list[dict[str, Any]] = []
    for row in rows:
        fact = quote_from_tencent_row(row, as_of=retrieved_at).to_dict()
        fact.pop("raw", None)
        fact["source_time"] = fact["as_of"]
        fact["retrieved_at"] = retrieved_at
        facts.append(fact)
    return facts


def _source_time(quotes: list[dict[str, Any]]) -> str | None:
    values = [str(row["source_time"]) for row in quotes if row.get("source_time")]
    return max(values) if values else None


def summarize_market(quotes: list[dict[str, Any]]) -> dict[str, Any]:
    valid = [row for row in quotes if row.get("change_pct") is not None]
    up = sum(float(row["change_pct"]) > 0 for row in valid)
    down = sum(float(row["change_pct"]) < 0 for row in valid)
    return {
        "total": len(valid),
        "up": up,
        "down": down,
        "flat": len(valid) - up - down,
        "up_ratio": round(up / len(valid), 4) if valid else None,
        "amount": sum(float(row.get("amount") or 0) for row in valid),
    }


def _refresh_snapshot() -> dict[str, Any]:
    started = time.perf_counter()
    retrieved_at = datetime.now(SHANGHAI).isoformat(timespec="seconds")
    master = get_tdx_provider().fetch_security_master()
    symbols = [
        canonicalize_symbol(f"{row.get('exchange') or ''}{row.get('code') or ''}")
        for row in master.get("symbols") or []
    ]
    if not symbols:
        raise AshareDataError(ErrorCode.UNAVAILABLE, "security master is empty")
    raw_rows = get_tencent_provider().fetch_quote_rows(symbols)
    quotes = _canonical_quotes(raw_rows, retrieved_at=retrieved_at)
    required = int(len(symbols) * MIN_QUOTE_COVERAGE)
    if len(quotes) < required:
        raise AshareDataError(
            ErrorCode.PROVIDER_FAILURE,
            f"Tencent quote coverage too small: {len(quotes)}/{len(symbols)}",
            retryable=True,
        )
    return {
        "quotes": quotes,
        "source_time": _source_time(quotes),
        "retrieved_at": retrieved_at,
        "refresh_duration_ms": round((time.perf_counter() - started) * 1_000, 1),
        "universe": {
            "status": master.get("status"),
            "source": master.get("source"),
            "scope": master.get("scope"),
            "count": master.get("count"),
        },
        "expires_at_monotonic": time.monotonic() + _snapshot_ttl(),
    }


def _market_snapshot() -> dict[str, Any]:
    global _snapshot
    with _snapshot_lock:
        if _snapshot is None or time.monotonic() >= float(_snapshot["expires_at_monotonic"]):
            _snapshot = _refresh_snapshot()
        return _snapshot


def reset_runtime_snapshot() -> None:
    """Drop reconstructable process state; primarily useful for deterministic tests."""
    global _snapshot
    with _snapshot_lock:
        _snapshot = None


def market_snapshot() -> tuple[dict[str, Any], list[SourceRef], list[WarningItem], bool]:
    snapshot = _market_snapshot()
    width = summarize_market(snapshot["quotes"])
    degraded = snapshot["universe"].get("status") != "PASS"
    data = {
        "market_width": width,
        "breadth": {
            "up": width["up"],
            "down": width["down"],
            "flat": width["flat"],
            "total": width["total"],
            "amount": width["amount"],
            "limit_up": None,
            "limit_down": None,
        },
        "quote_count": len(snapshot["quotes"]),
        "source_time": snapshot["source_time"],
        "retrieved_at": snapshot["retrieved_at"],
        "refresh_duration_ms": snapshot["refresh_duration_ms"],
        "universe": snapshot["universe"],
    }
    warnings = [WarningItem(code="SNAPSHOT_DEGRADED")] if degraded else []
    sources = [
        SourceRef(provider="tdx", role="security_master"),
        SourceRef(provider="tencent", role="realtime_snapshot"),
    ]
    return data, sources, warnings, degraded


def market_cross_section() -> tuple[dict[str, Any], list[SourceRef], list[WarningItem], bool]:
    snapshot = _market_snapshot()
    degraded = snapshot["universe"].get("status") != "PASS"
    data = {
        "quotes": list(snapshot["quotes"]),
        "quote_count": len(snapshot["quotes"]),
        "market_width": summarize_market(snapshot["quotes"]),
        "source_time": snapshot["source_time"],
        "retrieved_at": snapshot["retrieved_at"],
        "universe": snapshot["universe"],
    }
    warnings = [WarningItem(code="CROSS_SECTION_DEGRADED")] if degraded else []
    sources = [
        SourceRef(provider="tdx", role="security_master"),
        SourceRef(provider="tencent", role="realtime_cross_section"),
    ]
    return data, sources, warnings, degraded


def _percentiles(rows: list[dict[str, Any]], field: str) -> dict[str, float]:
    values = sorted(
        (float(row[field]), str(row["symbol"]))
        for row in rows
        if row.get(field) is not None and row.get("symbol")
    )
    size = len(values)
    return {
        symbol: round((index + 1) * 100 / size, 2)
        for index, (_value, symbol) in enumerate(values)
    } if size else {}


def _prior_four_day_return(change_5d: Any, change_1d: Any) -> float | None:
    if change_5d is None or change_1d is None or float(change_1d) <= -100:
        return None
    return round(((1 + float(change_5d) / 100) / (1 + float(change_1d) / 100) - 1) * 100, 4)


def _limit_activity_by_symbol(limit_data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    activity: dict[str, dict[str, Any]] = {}
    observation_days = 1 + int(limit_data.get("previous_limit_up") is not None)

    def mark(pool: str, state: str) -> None:
        for row in (limit_data.get(pool) or {}).get("rows") or []:
            symbol = row.get("symbol")
            if not symbol:
                continue
            item = activity.setdefault(
                symbol,
                {"active": True, "today_state": None, "previous_limit_up": False, "streak": 0},
            )
            if pool == "previous_limit_up":
                item["previous_limit_up"] = True
            else:
                item["today_state"] = state
                item["streak"] = max(int(item["streak"]), int(row.get("streak") or 0))

    mark("limit_up", "limit_up")
    mark("broken_limit", "broken_limit")
    mark("limit_down", "limit_down")
    mark("previous_limit_up", "limit_up")
    for item in activity.values():
        item["observation_days"] = observation_days
    return activity


def market_stock_signals() -> tuple[dict[str, Any], list[SourceRef], list[WarningItem], bool]:
    """Full-A stock-discovery facts; partial dimensions stay null per item, never fabricated."""
    snapshot = _market_snapshot()
    warnings: list[WarningItem] = []
    degraded = snapshot["universe"].get("status") != "PASS"
    supplemental: list[dict[str, Any]] = []
    industries: list[dict[str, Any]] = []
    try:
        supplemental = fetch_stock_signal_rows()
        industries = fetch_board_rankings("industry", limit=500)
    except (EastmoneyProviderError, requests.RequestException, OSError, ValueError) as exc:
        degraded = True
        warnings.append(WarningItem(code="STOCK_SIGNALS_SUPPLEMENT_FAILED", message=str(exc)))
    try:
        limits, _limit_sources, limit_warnings, limit_degraded = market_limits()
        warnings.extend(limit_warnings)
        degraded = degraded or limit_degraded
    except AshareDataError as exc:
        limits = {}
        degraded = True
        warnings.append(WarningItem(code="STOCK_SIGNALS_LIMITS_FAILED", message=str(exc)))

    by_symbol = {str(row["symbol"]): row for row in supplemental if row.get("symbol")}
    industry_change = {
        str(row.get("name")): row.get("change_pct") for row in industries if row.get("name")
    }
    limit_activity = _limit_activity_by_symbol(limits)
    limit_observation_days = 1 + int(limits.get("previous_limit_up") is not None)
    rows: list[dict[str, Any]] = []
    for quote in snapshot["quotes"]:
        symbol = str(quote["symbol"])
        extra = by_symbol.get(symbol, {})
        industry = extra.get("industry")
        sector_change = industry_change.get(str(industry)) if industry else None
        change = quote.get("change_pct")
        divergence = float(change) - float(sector_change) if change is not None and sector_change is not None else None
        rows.append(
            {
                **quote,
                "volume_ratio": extra.get("volume_ratio"),
                "amount_expansion_basis": "intraday_volume_ratio_proxy" if extra.get("volume_ratio") is not None else None,
                "change_speed": extra.get("change_speed"),
                "change_pct_5d": extra.get("change_pct_5d"),
                "change_pct_60d": extra.get("change_pct_60d"),
                "change_pct_ytd": extra.get("change_pct_ytd"),
                "persistence_return_4d_pct": _prior_four_day_return(extra.get("change_pct_5d"), change),
                "industry": industry,
                "industry_change_pct": sector_change,
                "sector_divergence_pct": round(divergence, 4) if divergence is not None else None,
                "limit_activity": limit_activity.get(symbol, {"active": False, "observation_days": limit_observation_days}),
            }
        )
    percentile_fields = {
        "return_pctile": "change_pct",
        "amount_pctile": "amount",
        "turnover_pctile": "turnover_rate",
        "amount_expansion_pctile": "volume_ratio",
        "sector_divergence_pctile": "sector_divergence_pct",
        "persistence_pctile": "persistence_return_4d_pct",
    }
    for output, field in percentile_fields.items():
        ranks = _percentiles(rows, field)
        for row in rows:
            row[output] = ranks.get(str(row["symbol"]))
    coverage = {
        output: sum(row.get(output) is not None for row in rows)
        for output in percentile_fields
    }
    coverage["limit_activity"] = sum(bool(row["limit_activity"].get("active")) for row in rows)
    return (
        {
            "stocks": rows,
            "count": len(rows),
            "source_time": snapshot["source_time"],
            "retrieved_at": snapshot["retrieved_at"],
            "dimensions": list(percentile_fields) + ["limit_activity"],
            "dimension_coverage": coverage,
            "limit_activity_observation_days": limit_observation_days,
        },
        [
            SourceRef(provider="tdx", role="security_master"),
            SourceRef(provider="tencent", role="realtime_cross_section"),
            SourceRef(provider="eastmoney", role="stock_discovery_supplement"),
        ],
        warnings,
        degraded,
    )


def market_movers(sort_by: str = "change_pct", limit: int = 50, descending: bool = True):
    if sort_by not in {"change_pct", "amount", "turnover_rate", "code", "symbol"}:
        raise AshareDataError(ErrorCode.INVALID_REQUEST, f"unsupported sort_by: {sort_by}")
    if not 1 <= limit <= 500:
        raise AshareDataError(ErrorCode.INVALID_REQUEST, "limit must be between 1 and 500")
    snapshot = _market_snapshot()
    sort_key = "symbol" if sort_by == "code" else sort_by
    rows = [row for row in snapshot["quotes"] if row.get(sort_key) is not None]
    rows.sort(key=lambda row: row[sort_key], reverse=descending)
    degraded = snapshot["universe"].get("status") != "PASS"
    warnings = [WarningItem(code="MOVERS_DEGRADED")] if degraded else []
    data = {
        "movers": rows[:limit],
        "sort_by": sort_by,
        "descending": descending,
        "source_time": snapshot["source_time"],
        "retrieved_at": snapshot["retrieved_at"],
        "universe": snapshot["universe"],
    }
    return data, [SourceRef(provider="tencent", role="realtime_movers")], warnings, degraded


def market_breadth():
    data, sources, warnings, degraded = market_snapshot()
    return {"breadth": data.get("breadth"), "as_of_source": data.get("source_time")}, sources, warnings, degraded


def _source_date_from_stamp(source_time: Any) -> date | None:
    text = str(source_time or "")
    digits = text.replace("-", "")[:8]
    if len(digits) == 8 and digits.isdigit():
        try:
            return date(int(digits[:4]), int(digits[4:6]), int(digits[6:8]))
        except ValueError:
            return None
    return None


def _audit_date_effect(current_pool: dict[str, Any], historical_pool: dict[str, Any]) -> dict[str, Any]:
    current_codes = {str(row.get("code") or "") for row in current_pool.get("rows") or []}
    historical_codes = {str(row.get("code") or "") for row in historical_pool.get("rows") or []}
    current_codes.discard("")
    historical_codes.discard("")
    observable_difference = current_pool.get("count") != historical_pool.get("count") or current_codes != historical_codes
    return {
        "current_requested_date": current_pool.get("requested_date"),
        "historical_requested_date": historical_pool.get("requested_date"),
        "current_qdate": current_pool.get("qdate"),
        "historical_qdate": historical_pool.get("qdate"),
        "current_count": len(current_codes),
        "historical_count": len(historical_codes),
        "intersection_count": len(current_codes & historical_codes),
        "symmetric_difference_count": len(current_codes ^ historical_codes),
        "date_parameter_effective": bool(
            current_pool.get("requested_date") != historical_pool.get("requested_date") and observable_difference
        ),
    }


def _canonical_limit_pool(pool: dict[str, Any] | None) -> dict[str, Any] | None:
    if pool is None:
        return None
    return {
        **pool,
        "rows": [
            {key: value for key, value in row.items() if key != "raw"}
            for row in pool.get("rows") or []
        ],
    }


def market_limits(*, trade_date: str | None = None):
    warnings: list[WarningItem] = []
    degraded = False
    provider = get_eastmoney_provider()
    errors: dict[str, str] = {}
    candidate = date.fromisoformat(trade_date) if trade_date else datetime.now(SHANGHAI).date()
    if not trade_date:
        try:
            stamped = _source_date_from_stamp(_market_snapshot().get("source_time"))
            if stamped is not None:
                candidate = stamped
        except Exception:
            pass
    trading_date, previous_trading_date, calendar_basis = resolve_trading_dates(candidate)

    def safe_fetch(kind: str, day: str) -> dict[str, Any] | None:
        nonlocal degraded
        try:
            return provider.fetch_limit_pool(kind, day)
        except (EastmoneyProviderError, requests.RequestException, OSError, ValueError) as exc:
            errors[f"{kind}:{day}"] = str(exc)
            degraded = True
            warnings.append(WarningItem(code="LIMIT_POOL_FETCH_FAILED", message=f"{kind}@{day}: {exc}"))
            return None

    limit_up = _canonical_limit_pool(safe_fetch("limit_up", trading_date))
    limit_down = _canonical_limit_pool(safe_fetch("limit_down", trading_date))
    broken_limit = _canonical_limit_pool(safe_fetch("broken_limit", trading_date))
    previous_limit_up = _canonical_limit_pool(safe_fetch("limit_up", previous_trading_date))
    pool_date_effect_audit = None
    if limit_up and previous_limit_up:
        pool_date_effect_audit = _audit_date_effect(limit_up, previous_limit_up)
        if previous_limit_up.get("provider_qdate_differs") and not pool_date_effect_audit["date_parameter_effective"]:
            errors["previous_limit_up"] = "historical limit-up pool rejected: requested-date effect could not be proven"
            warnings.append(WarningItem(code="PREVIOUS_LIMIT_UP_REJECTED", message=errors["previous_limit_up"]))
            previous_limit_up = None
            degraded = True

    up_rows = list((limit_up or {}).get("rows") or [])
    sealed_count = int((limit_up or {}).get("count")) if limit_up else None
    broken_count = int((broken_limit or {}).get("count")) if broken_limit else None
    max_streak = max((int(row.get("streak") or 0) for row in up_rows), default=0) if limit_up else None
    data = {
        "trading_date": trading_date,
        "previous_trading_date": previous_trading_date,
        "calendar_basis": calendar_basis,
        "limit_up": limit_up,
        "limit_down": limit_down,
        "broken_limit": broken_limit,
        "previous_limit_up": previous_limit_up,
        "sealed_count": sealed_count,
        "broken_count": broken_count,
        "max_streak": max_streak,
        "summary": {
            "limit_up_count": int((limit_up or {}).get("count")) if limit_up else None,
            "limit_down_count": int((limit_down or {}).get("count")) if limit_down else None,
            "sealed_count": sealed_count,
            "broken_count": broken_count,
            "max_streak": max_streak,
        },
        "audit": {"pool_date_effect_audit": pool_date_effect_audit, "errors": errors, "candidate_date": candidate.isoformat()},
    }
    sources = [SourceRef(provider="eastmoney", role="topic_limit_pools")]
    if calendar_basis.startswith("canonical_bars"):
        sources.append(SourceRef(provider="tdx", role="calendar_via_bars"))
    return data, sources, warnings, degraded
