"""Aligned stock-versus-sector intraday facts."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from aasource.domain.errors import AshareDataError, ErrorCode
from aasource.domain.identifiers import canonicalize_symbol
from aasource.domain.models import SourceRef, WarningItem
from aasource.domain.sectors import canonicalize_sector_id
from aasource.services.bars import get_bars
from aasource.services.market import market_limits
from aasource.services.sectors import list_sectors, sector_minute, stock_memberships

SHANGHAI = ZoneInfo("Asia/Shanghai")
CHECKPOINTS = ("09:30", "10:00", "10:30", "11:00", "13:00", "13:30", "14:00", "14:30")


def minute_clock(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    if "T" in text:
        text = text.split("T", 1)[1]
    elif " " in text:
        text = text.split(" ")[-1]
    text = text.replace("+08:00", "").replace("Z", "")
    parts = text.split(":")
    if len(parts) < 2 or not parts[0][-2:].isdigit() or not parts[1][:2].isdigit():
        return None
    return f"{parts[0][-2:].zfill(2)}:{parts[1][:2].zfill(2)}"


def _close(row: dict[str, Any]) -> float | None:
    for key in ("close", "last", "price"):
        value = row.get(key)
        if isinstance(value, (int, float)) and value > 0:
            return float(value)
    return None


def resolve_sector(memberships: list[dict[str, Any]]) -> dict[str, Any] | None:
    for kind in ("industry", "concept"):
        for row in memberships:
            if row.get("relation_type") == kind and row.get("source_id"):
                return row
    return next((row for row in memberships if row.get("source_id")), None)


def _membership_sector_id(value: Any) -> str:
    text = str(value or "").strip().upper()
    if text.isdigit():
        text = f"BK{text.zfill(4)}"
    return canonicalize_sector_id(text)


def previous_close_for_session(bars: list[dict[str, Any]], session: str) -> float | None:
    for row in reversed(bars):
        trade_date = str(row.get("trade_date") or row.get("ts") or "")[:10]
        if trade_date == session and isinstance(row.get("previous_close"), (int, float)):
            return float(row["previous_close"])
    prior = [
        row for row in bars
        if str(row.get("trade_date") or row.get("ts") or "")[:10] < session
        and isinstance(row.get("close"), (int, float))
    ]
    return float(prior[-1]["close"]) if prior else None


def align_relative_points(
    stock_bars: list[dict[str, Any]],
    sector_rows: list[dict[str, Any]],
    stock_previous_close: float | None,
    sector_previous_close: float | None,
) -> list[dict[str, Any]]:
    if not isinstance(stock_previous_close, (int, float)) or not isinstance(sector_previous_close, (int, float)):
        return []
    if stock_previous_close <= 0 or sector_previous_close <= 0:
        return []
    stock = {minute_clock(row.get("ts") or row.get("time")): row for row in stock_bars}
    sector = {minute_clock(row.get("ts") or row.get("time")): row for row in sector_rows}
    points: list[dict[str, Any]] = []
    previous_rs: float | None = None
    for clock in sorted((set(stock) & set(sector)) - {None}):
        stock_close, sector_close = _close(stock[clock]), _close(sector[clock])
        if stock_close is None or sector_close is None:
            continue
        stock_change = round((stock_close / stock_previous_close - 1) * 100, 4)
        sector_change = round((sector_close / sector_previous_close - 1) * 100, 4)
        rs = round(stock_change - sector_change, 4)
        points.append(
            {
                "minute": clock,
                "ts": stock[clock].get("ts") or sector[clock].get("ts") or sector[clock].get("time"),
                "stock_close": stock_close,
                "sector_close": sector_close,
                "stock_change_pct": stock_change,
                "sector_change_pct": sector_change,
                "relative_return_pct": rs,
                "delta_relative_return_pct": None if previous_rs is None else round(rs - previous_rs, 4),
            }
        )
        previous_rs = rs
    return points


def _clock_minutes(clock: str) -> int:
    hour, minute = clock.split(":", 1)
    return int(hour) * 60 + int(minute[:2])


def _extreme(points: list[dict[str, Any]], field: str, kind: str) -> int | None:
    if not points:
        return None
    fn = min if kind == "low" else max
    return fn(range(len(points)), key=lambda index: float(points[index][field]))


def lead_lag(points: list[dict[str, Any]], kind: str, sync_window: int = 5) -> dict[str, Any] | None:
    stock_index = _extreme(points, "stock_change_pct", kind)
    sector_index = _extreme(points, "sector_change_pct", kind)
    if stock_index is None or sector_index is None:
        return None
    stock_minute = points[stock_index]["minute"]
    sector_minute = points[sector_index]["minute"]
    gap = _clock_minutes(sector_minute) - _clock_minutes(stock_minute)
    return {
        "stock_minute": stock_minute,
        "sector_minute": sector_minute,
        "stock_change_pct": points[stock_index]["stock_change_pct"],
        "sector_change_pct": points[sector_index]["sector_change_pct"],
        "stock_lead_minutes": gap,
        "aligned": abs(gap) <= sync_window,
    }


def _local_extrema(points: list[dict[str, Any]], field: str, kind: str, radius: int = 5) -> list[int]:
    if len(points) < radius * 2 + 1:
        return []
    output: list[int] = []
    for index in range(radius, len(points) - radius):
        window = [float(row[field]) for row in points[index - radius : index + radius + 1]]
        value = float(points[index][field])
        if value != (min(window) if kind == "low" else max(window)):
            continue
        if output and index - output[-1] < radius:
            previous = output[-1]
            better = value < float(points[previous][field]) if kind == "low" else value > float(points[previous][field])
            if better:
                output[-1] = index
        else:
            output.append(index)
    return output


def _paired_extrema(points: list[dict[str, Any]], indexes: list[int], kind: str) -> dict[str, Any] | None:
    if len(indexes) < 2:
        return None
    first, second = points[indexes[-2]], points[indexes[-1]]
    low = kind == "low_to_low"
    return {
        "kind": kind,
        "first": first,
        "second": second,
        "delta_relative_return_pct": round(second["relative_return_pct"] - first["relative_return_pct"], 4),
        "sector_extended": second["sector_change_pct"] < first["sector_change_pct"] if low else second["sector_change_pct"] > first["sector_change_pct"],
        "stock_extended": second["stock_change_pct"] < first["stock_change_pct"] if low else second["stock_change_pct"] > first["stock_change_pct"],
    }


def compute_relative_intraday(
    stock_bars: list[dict[str, Any]],
    sector_rows: list[dict[str, Any]],
    *,
    stock_previous_close: float | None,
    sector_previous_close: float | None,
) -> dict[str, Any]:
    points = align_relative_points(stock_bars, sector_rows, stock_previous_close, sector_previous_close)
    if len(points) < 2:
        return {"status": "unavailable", "reason": "need_aligned_stock_and_sector_minutes", "point_count": len(points)}
    latest = points[-1]
    stock_changes = [float(row["stock_change_pct"]) for row in points]
    sector_changes = [float(row["sector_change_pct"]) for row in points]
    low = lead_lag(points, "low")
    high = lead_lag(points, "high")
    low_pair = _paired_extrema(points, _local_extrema(points, "sector_change_pct", "low"), "low_to_low")
    high_pair = _paired_extrema(points, _local_extrema(points, "sector_change_pct", "high"), "high_to_high")
    stock_low, sector_low = min(stock_changes), min(sector_changes)
    by_minute = {row["minute"]: row for row in points}
    checkpoints = [by_minute[item] for item in CHECKPOINTS if item in by_minute]
    if latest["minute"] not in {row["minute"] for row in checkpoints}:
        checkpoints.append(latest)
    return {
        "status": "available",
        "point_count": len(points),
        "first_minute": points[0]["minute"],
        "last_minute": latest["minute"],
        "latest": latest,
        "path": {
            "relative_return_pct": latest["relative_return_pct"],
            "relative_drawdown_pct": round(stock_low - sector_low, 4),
            "relative_rebound_pct": round((stock_changes[-1] - stock_low) - (sector_changes[-1] - sector_low), 4),
            "stock_session_high_pct": max(stock_changes),
            "sector_session_high_pct": max(sector_changes),
        },
        "lead_lag": {"low": low, "high": high},
        "sync": {"low": bool((low or {}).get("aligned")), "high": bool((high or {}).get("aligned"))},
        "divergence": {
            "sector_lower_low_stock_held": bool(low_pair and low_pair["sector_extended"] and not low_pair["stock_extended"]),
            "sector_higher_high_stock_lagged": bool(high_pair and high_pair["sector_extended"] and not high_pair["stock_extended"]),
            "latest_relative_return_positive": latest["relative_return_pct"] > 0,
            "latest_delta_positive": latest["delta_relative_return_pct"] is not None and latest["delta_relative_return_pct"] > 0,
        },
        "low_to_low": low_pair,
        "high_to_high": high_pair,
        "checkpoints": checkpoints,
    }


def _dedupe_sources(sources: list[SourceRef]) -> list[SourceRef]:
    output: list[SourceRef] = []
    seen: set[tuple[str, str]] = set()
    for source in sources:
        key = (source.provider, source.role)
        if key not in seen:
            seen.add(key)
            output.append(source)
    return output


def get_relative_intraday(
    symbol: str,
    *,
    sector_id: str | None = None,
    trade_date: str | None = None,
) -> tuple[dict[str, Any], list[SourceRef], list[WarningItem], bool]:
    canonical = canonicalize_symbol(symbol)
    if trade_date and not sector_id:
        raise AshareDataError(
            ErrorCode.CAPABILITY_NOT_AVAILABLE,
            "a dated relative-intraday request requires an explicit --sector",
            details={"historical_sector_membership": "unavailable", "date_requested": trade_date},
        )
    sources: list[SourceRef] = []
    warnings: list[WarningItem] = []
    degraded = False
    if trade_date:
        session = trade_date
    else:
        limits, limit_sources, limit_warnings, limit_degraded = market_limits()
        sources.extend(limit_sources)
        warnings.extend(limit_warnings)
        degraded = limit_degraded
        session = limits.get("trading_date") or datetime.now(SHANGHAI).date().isoformat()
    membership_basis = "explicit"
    sector_name = None
    sector_kind = "explicit"
    if sector_id:
        board_id = canonicalize_sector_id(sector_id)
    else:
        membership_data, membership_sources, membership_warnings, membership_degraded = stock_memberships([canonical])
        sources.extend(membership_sources)
        warnings.extend(membership_warnings)
        degraded = degraded or membership_degraded
        memberships = list(((membership_data.get("items") or [{}])[0]).get("memberships") or [])
        selected = resolve_sector(memberships)
        if not selected:
            raise AshareDataError(ErrorCode.UNAVAILABLE, f"no current sector membership for {canonical}")
        board_id = _membership_sector_id(selected["source_id"])
        sector_name = selected.get("name")
        sector_kind = selected.get("relation_type")
        membership_basis = "current_snapshot"

    stock_rows, stock_sources, stock_warnings, stock_degraded, _ = get_bars(
        canonical, timeframe="1m", start=session, end=session, limit=400
    )
    board, board_sources, board_warnings, board_degraded = sector_minute(board_id, trading_date=session)
    sources.extend(stock_sources + board_sources)
    warnings.extend(stock_warnings + board_warnings)
    degraded = degraded or stock_degraded or board_degraded
    daily, daily_sources, daily_warnings, daily_degraded, _ = get_bars(
        canonical, timeframe="1d", end=session, limit=3
    )
    sector_daily, sector_daily_sources, sector_daily_warnings, sector_daily_degraded, _ = get_bars(
        board_id, timeframe="1d", end=session, limit=3
    )
    sources.extend(daily_sources + sector_daily_sources)
    warnings.extend(daily_warnings + sector_daily_warnings)
    degraded = degraded or daily_degraded or sector_daily_degraded
    stock_previous_close = previous_close_for_session(daily, session)
    sector_previous_close = previous_close_for_session(sector_daily, session)
    facts = compute_relative_intraday(
        stock_rows,
        list(board.get("rows") or []),
        stock_previous_close=stock_previous_close,
        sector_previous_close=sector_previous_close,
    )
    breadth = None
    if not trade_date:
        boards, breadth_sources, breadth_warnings, breadth_degraded = list_sectors(kind="all", limit=500)
        sources.extend(breadth_sources)
        warnings.extend(breadth_warnings)
        degraded = degraded or breadth_degraded
        breadth = next(
            (row for row in boards.get("sectors") or [] if str(row.get("sector_id") or row.get("board_code")) == board_id),
            None,
        )
    return (
        {
            "purpose": "stock_sector_intraday_relative_facts",
            "judgment_free": True,
            "symbol": canonical,
            "trade_date": session,
            "sector": {"sector_id": board_id, "name": sector_name or board.get("name"), "kind": sector_kind},
            "membership_basis": membership_basis,
            "sector_breadth": breadth,
            **facts,
            "note": "Aligned stock-versus-sector facts; not a buy/sell signal.",
        },
        _dedupe_sources(sources),
        warnings,
        degraded or facts.get("status") != "available",
    )
