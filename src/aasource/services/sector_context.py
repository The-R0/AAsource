"""One-stop current sector facts without strategy labels."""

from __future__ import annotations

import statistics
from typing import Any

from aasource.domain.errors import AshareDataError, ErrorCode
from aasource.domain.models import SourceRef, WarningItem
from aasource.domain.sectors import canonicalize_sector_id, is_sector_id
from aasource.services.bars import get_bars
from aasource.services.market import market_limits, market_snapshot
from aasource.services.sectors import sector_members, sector_minute, sector_rankings, sector_resolve

MAX_MEMBER_PREVIEW = 40
MEMBER_POOL_LIMIT = 8


def _pct(numerator: Any, denominator: Any) -> float | None:
    if not isinstance(numerator, (int, float)) or not isinstance(denominator, (int, float)) or denominator == 0:
        return None
    return round(float(numerator) / float(denominator) * 100, 4)


def window_returns(bars: list[dict[str, Any]], windows: tuple[int, ...] = (1, 3, 5, 20)) -> dict[str, Any]:
    closes = [float(row["close"]) for row in bars if isinstance(row.get("close"), (int, float))]
    output: dict[str, Any] = {}
    for window in windows:
        if len(closes) <= window:
            output[f"{window}d"] = {"status": "partial", "observations": max(0, len(closes) - 1)}
        else:
            output[f"{window}d"] = {
                "status": "available",
                "observations": window,
                "change_pct": _pct(closes[-1] - closes[-window - 1], closes[-window - 1]),
            }
    return output


def relative_windows(sector: dict[str, Any], benchmark: dict[str, Any]) -> dict[str, float]:
    output: dict[str, float] = {}
    for key, row in sector.items():
        left, right = row.get("change_pct"), (benchmark.get(key) or {}).get("change_pct")
        if isinstance(left, (int, float)) and isinstance(right, (int, float)):
            output[key] = round(float(left) - float(right), 4)
    return output


def return_distribution(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"count": 0}
    ordered = sorted(values)

    def percentile(position: float) -> float:
        index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * position)))
        return ordered[index]

    return {
        "count": len(ordered),
        "up": sum(value > 0 for value in ordered),
        "down": sum(value < 0 for value in ordered),
        "flat": sum(value == 0 for value in ordered),
        "median": statistics.median(ordered),
        "stdev": statistics.pstdev(ordered) if len(ordered) > 1 else 0.0,
        "p10": percentile(0.10),
        "p90": percentile(0.90),
        "min": ordered[0],
        "max": ordered[-1],
    }


def amount_concentration(members: list[dict[str, Any]]) -> dict[str, Any]:
    amounts = sorted(
        (float(row["amount"]) for row in members if isinstance(row.get("amount"), (int, float))),
        reverse=True,
    )
    total = sum(amounts)
    if not total:
        return {"status": "unavailable"}
    return {
        "status": "available",
        "total_amount": total,
        "top1_share_pct": _pct(amounts[0], total),
        "top5_share_pct": _pct(sum(amounts[:5]), total),
    }


def slim_member(row: dict[str, Any], sector_change: float | None) -> dict[str, Any]:
    change = row.get("change_pct")
    last = row.get("last") or row.get("price")
    high = row.get("high")
    result = {
        key: row.get(key)
        for key in (
            "symbol", "name", "change_pct", "open_change_pct", "amount", "volume_ratio",
            "turnover_rate", "today_state", "streak", "first_limit_time",
        )
        if row.get(key) is not None
    }
    result["relative_sector_pct"] = (
        round(float(change) - float(sector_change), 4)
        if isinstance(change, (int, float)) and isinstance(sector_change, (int, float)) else None
    )
    result["at_session_high"] = bool(
        isinstance(last, (int, float)) and isinstance(high, (int, float)) and high > 0 and last >= high * 0.999
    )
    return result


def member_fact_pools(
    members: list[dict[str, Any]], sector_change: float | None, limit: int = MEMBER_POOL_LIMIT
) -> dict[str, Any]:
    def take(field: str, reverse: bool = True) -> list[dict[str, Any]]:
        rows = [row for row in members if row.get(field) is not None]
        rows.sort(key=lambda row: row[field], reverse=reverse)
        return [slim_member(row, sector_change) for row in rows[:limit]]

    relative = [row for row in members if slim_member(row, sector_change).get("relative_sector_pct") is not None]
    relative.sort(key=lambda row: slim_member(row, sector_change)["relative_sector_pct"], reverse=True)
    first_limit = [row for row in members if row.get("first_limit_time")]
    first_limit.sort(key=lambda row: str(row["first_limit_time"]))
    return {
        "amount_front": take("amount"),
        "return_front": take("change_pct"),
        "turnover_front": take("turnover_rate"),
        "volume_ratio_front": take("volume_ratio"),
        "earliest_limit": [slim_member(row, sector_change) for row in first_limit[:limit]],
        "held_vs_sector": [slim_member(row, sector_change) for row in relative[:limit]],
        "lagged_vs_sector": [slim_member(row, sector_change) for row in reversed(relative[-limit:])],
        "session_high": [slim_member(row, sector_change) for row in members if slim_member(row, sector_change)["at_session_high"]][:limit],
        "note": "Ranked fact pools only; not leaders, cores, or candidates.",
    }


def minute_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    usable = [row for row in rows if isinstance(row.get("close") or row.get("last") or row.get("price"), (int, float))]
    if not usable:
        return {"status": "unavailable", "reason": "no_sector_minutes"}

    def close(row: dict[str, Any]) -> float:
        return float(row.get("close") or row.get("last") or row.get("price"))

    high, low = max(usable, key=close), min(usable, key=close)
    return {
        "status": "available",
        "point_count": len(usable),
        "first_ts": usable[0].get("ts") or usable[0].get("time"),
        "last_ts": usable[-1].get("ts") or usable[-1].get("time"),
        "last_close": close(usable[-1]),
        "session_high": {"value": close(high), "ts": high.get("ts") or high.get("time")},
        "session_low": {"value": close(low), "ts": low.get("ts") or low.get("time")},
    }


def _limit_events(limits: dict[str, Any]) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for pool, state in (("limit_up", "limit_up"), ("broken_limit", "broken_limit"), ("limit_down", "limit_down")):
        for row in (limits.get(pool) or {}).get("rows") or []:
            symbol = row.get("symbol")
            if symbol:
                output[str(symbol)] = {
                    "today_state": state,
                    "streak": row.get("streak"),
                    "first_limit_time": row.get("first_limit_time"),
                }
    return output


def _dedupe_sources(sources: list[SourceRef]) -> list[SourceRef]:
    output: list[SourceRef] = []
    seen: set[tuple[str, str]] = set()
    for source in sources:
        key = (source.provider, source.role)
        if key not in seen:
            seen.add(key)
            output.append(source)
    return output


def get_sector_context(
    sector: str, *, member_limit: int = 20
) -> tuple[dict[str, Any], list[SourceRef], list[WarningItem], bool]:
    if not 1 <= int(member_limit) <= MAX_MEMBER_PREVIEW:
        raise AshareDataError(ErrorCode.INVALID_REQUEST, f"member_limit must be between 1 and {MAX_MEMBER_PREVIEW}")
    resolved: dict[str, Any] = {}
    if is_sector_id(sector):
        sector_id = canonicalize_sector_id(sector)
    else:
        resolved_data, resolve_sources, resolve_warnings, resolve_degraded = sector_resolve(sector)
        resolved = resolved_data.get("sector") or {}
        if not resolved:
            raise AshareDataError(ErrorCode.SYMBOL_NOT_FOUND, f"sector not found: {sector}")
        sector_id = canonicalize_sector_id(str(resolved.get("sector_id") or resolved.get("board_code")))

    sources: list[SourceRef] = []
    warnings: list[WarningItem] = []
    degraded = False
    if not is_sector_id(sector):
        sources.extend(resolve_sources)
        warnings.extend(resolve_warnings)
        degraded = resolve_degraded

    industries, src, warn, deg = sector_rankings(kind="industry", limit=500)
    sources.extend(src)
    warnings.extend(warn)
    degraded = degraded or deg
    concepts, src, warn, deg = sector_rankings(kind="concept", limit=500)
    sources.extend(src)
    warnings.extend(warn)
    degraded = degraded or deg
    all_rankings = list(industries.get("rankings") or []) + list(concepts.get("rankings") or [])
    ranking = next(
        (row for row in all_rankings if str(row.get("sector_id") or row.get("board_code")) == sector_id),
        resolved,
    )
    kind_rows = list(industries.get("rankings") or []) if ranking.get("kind") == "industry" else list(concepts.get("rankings") or [])
    rank = next((index for index, row in enumerate(kind_rows, 1) if str(row.get("sector_id") or row.get("board_code")) == sector_id), None)

    members_data, src, warn, deg = sector_members(sector_id, limit=500)
    sources.extend(src)
    warnings.extend(warn)
    degraded = degraded or deg
    limits, src, warn, deg = market_limits()
    sources.extend(src)
    warnings.extend(warn)
    degraded = degraded or deg
    try:
        market, src, warn, deg = market_snapshot()
        sources.extend(src)
        warnings.extend(warn)
        degraded = degraded or deg
    except AshareDataError as exc:
        market = {}
        warnings.append(WarningItem(code="SECTOR_CONTEXT_MARKET_UNAVAILABLE", message=str(exc)))
        degraded = True
    try:
        board_bars, src, warn, deg, _ = get_bars(sector_id, timeframe="1d", limit=30)
        sources.extend(src)
        warnings.extend(warn)
        degraded = degraded or deg
    except AshareDataError as exc:
        board_bars = []
        warnings.append(WarningItem(code="SECTOR_CONTEXT_BOARD_BARS_UNAVAILABLE", message=str(exc)))
        degraded = True
    try:
        benchmark_bars, src, warn, deg, _ = get_bars("SH000001", timeframe="1d", limit=30)
        sources.extend(src)
        warnings.extend(warn)
        degraded = degraded or deg
    except AshareDataError as exc:
        benchmark_bars = []
        warnings.append(WarningItem(code="SECTOR_CONTEXT_BENCHMARK_UNAVAILABLE", message=str(exc)))
        degraded = True
    try:
        minute, src, warn, deg = sector_minute(sector_id)
        sources.extend(src)
        warnings.extend(warn)
        degraded = degraded or deg
    except AshareDataError as exc:
        minute = {"rows": []}
        warnings.append(WarningItem(code="SECTOR_CONTEXT_MINUTE_UNAVAILABLE", message=str(exc)))
        degraded = True

    events = _limit_events(limits)
    members: list[dict[str, Any]] = []
    for row in members_data.get("members") or []:
        previous_close = row.get("previous_close")
        open_price = row.get("open")
        members.append(
            {
                **row,
                **events.get(str(row.get("symbol")), {"today_state": "none"}),
                "open_change_pct": _pct(
                    float(open_price) - float(previous_close)
                    if isinstance(open_price, (int, float)) and isinstance(previous_close, (int, float)) else None,
                    previous_close,
                ),
            }
        )
    member_symbols = {str(row.get("symbol")) for row in members}
    limit_up = [row for symbol, row in events.items() if symbol in member_symbols and row["today_state"] == "limit_up"]
    broken = [row for symbol, row in events.items() if symbol in member_symbols and row["today_state"] == "broken_limit"]
    changes = [float(row["change_pct"]) for row in members if isinstance(row.get("change_pct"), (int, float))]
    board_windows = window_returns(board_bars)
    benchmark_windows = window_returns(benchmark_bars)
    board_change = ranking.get("change_pct")
    return (
        {
            "purpose": "agent_sector_evidence_pack",
            "judgment_free": True,
            "temporal_scope": "current_session",
            "historical_replay": False,
            "sector_id": sector_id,
            "name": ranking.get("name") or ranking.get("board_name"),
            "kind": ranking.get("kind"),
            "trade_date": limits.get("trading_date"),
            "snapshot": {
                **{key: ranking.get(key) for key in ("change_pct", "amount", "turnover_rate", "main_net_flow", "up_count", "down_count", "breadth")},
                "rank": rank,
                "rank_pct": round(rank / len(kind_rows), 4) if rank and kind_rows else None,
                "member_count": len(members),
                "limit_up_count": len(limit_up),
                "broken_limit_count": len(broken),
            },
            "windows": {
                "sector": board_windows,
                "shanghai": benchmark_windows,
                "vs_shanghai": relative_windows(board_windows, benchmark_windows),
            },
            "minute": minute_summary(list(minute.get("rows") or [])),
            "internal": {
                "distribution": return_distribution(changes),
                "amount_concentration": amount_concentration(members),
            },
            "member_facts": member_fact_pools(members, board_change),
            "members_preview": [slim_member(row, board_change) for row in members[:member_limit]],
            "market_width": market.get("market_width"),
            "truncated": len(members) > member_limit,
            "note": "Current sector facts only; no leader labels, scores, or trade decisions.",
        },
        _dedupe_sources(sources),
        warnings,
        degraded,
    )
