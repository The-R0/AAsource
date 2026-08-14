from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from ashare_data.domain.errors import AshareDataError, ErrorCode
from ashare_data.domain.identifiers import canonicalize_symbol
from ashare_data.domain.models import SourceRef, WarningItem
from ashare_data.services.bars import get_bars


def _standard_limit_pct(symbol: str, trade_date: str) -> float:
    code = symbol[2:]
    if symbol.startswith("BJ"):
        return 30.0
    if symbol.startswith("SH688"):
        return 20.0
    if symbol.startswith("SZ") and code.startswith(("300", "301")) and trade_date >= "2020-08-24":
        return 20.0
    return 10.0


def _limit_price(previous_close: float, limit_pct: float) -> float:
    value = Decimal(str(previous_close)) * (Decimal("1") + Decimal(str(limit_pct)) / Decimal("100"))
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _matches_price(value: Any, target: float) -> bool:
    return value is not None and abs(float(value) - target) < 0.0051


def classify_limit_history(symbol: str, bars: list[dict[str, Any]]) -> dict[str, Any]:
    """Classify price-limit touches from canonical daily facts without inventing historical ST identity."""
    symbol = canonicalize_symbol(symbol)
    provisional_bars = [bar for bar in bars if str(bar.get("status") or "final") != "final"]
    bars = [bar for bar in bars if str(bar.get("status") or "final") == "final"]
    events: list[dict[str, Any]] = []
    streak = 0
    streak_is_lower_bound = False
    for index, bar in enumerate(bars):
        trade_date = str(bar.get("trade_date") or bar.get("ts") or "")[:10]
        previous_close = bar.get("previous_close")
        if not trade_date or previous_close in (None, 0) or bar.get("high") is None or bar.get("close") is None:
            streak = 0
            continue
        limit_pct = _standard_limit_pct(symbol, trade_date)
        price = _limit_price(float(previous_close), limit_pct)
        touched = _matches_price(bar.get("high"), price)
        sealed = touched and _matches_price(bar.get("close"), price)
        if sealed:
            streak += 1
            if index == 0:
                streak_is_lower_bound = True
        else:
            streak = 0
            streak_is_lower_bound = False
        if not touched:
            continue
        events.append(
            {
                "trade_date": trade_date,
                "state": "sealed_limit_up" if sealed else "broken_limit_up",
                "limit_pct": limit_pct,
                "limit_price": price,
                "previous_close": previous_close,
                "open": bar.get("open"),
                "high": bar.get("high"),
                "low": bar.get("low"),
                "close": bar.get("close"),
                "volume": bar.get("volume"),
                "amount": bar.get("amount"),
                "streak": streak if sealed else 0,
                "streak_is_lower_bound": bool(streak_is_lower_bound and streak > 0),
                "method": "canonical_daily_price_limit_match",
            }
        )
    sealed = [event for event in events if event["state"] == "sealed_limit_up"]
    broken = [event for event in events if event["state"] == "broken_limit_up"]
    st_history_needed = any(
        _standard_limit_pct(symbol, str(bar.get("trade_date") or bar.get("ts") or "")[:10]) == 10.0
        for bar in bars
        if str(bar.get("trade_date") or bar.get("ts") or "")[:10]
    )
    unavailable = ["historical_st_status", "five_pct_limit_events"] if st_history_needed else []
    provisional_current_event = None
    if provisional_bars:
        current = dict(provisional_bars[-1])
        current["status"] = "final"
        current_result = classify_limit_history(symbol, [current])
        if current_result["events"]:
            provisional_current_event = dict(current_result["events"][0])
            provisional_current_event.pop("streak", None)
            provisional_current_event.pop("streak_is_lower_bound", None)
            provisional_current_event["status"] = "provisional"
    return {
        "symbol": symbol,
        "observation_start": str(bars[0].get("trade_date") or bars[0].get("ts") or "")[:10] if bars else None,
        "observation_end": str(bars[-1].get("trade_date") or bars[-1].get("ts") or "")[:10] if bars else None,
        "bar_count": len(bars),
        "event_count": len(events),
        "sealed_count": len(sealed),
        "broken_count": len(broken),
        "max_streak": max((int(event["streak"]) for event in sealed), default=0),
        "events": events,
        "provisional_current_event": provisional_current_event,
        "provisional_bar_count": len(provisional_bars),
        "unavailable_dimensions": unavailable,
        "method": {
            "id": "canonical_daily_price_limit_match",
            "price_tick": 0.01,
            "rounding": "ROUND_HALF_UP",
            "basis": "previous_close and board/date standard price-limit regime",
            "limitations": ["historical ST identity is unavailable; 5% ST limit events are not inferred"]
            if st_history_needed
            else [],
        },
    }


def get_limit_history(
    symbol: str,
    *,
    start: str | None = None,
    end: str | None = None,
    limit: int = 1200,
) -> tuple[dict[str, Any], list[SourceRef], list[WarningItem], bool, dict[str, Any]]:
    canonical = canonicalize_symbol(symbol)
    bars, sources, warnings, degraded, provenance = get_bars(
        canonical, timeframe="1d", start=start, end=end, limit=limit, adjust="none"
    )
    if not bars:
        raise AshareDataError(ErrorCode.UNAVAILABLE, f"No daily bars for {canonical}")
    data = classify_limit_history(canonical, bars)
    if data["unavailable_dimensions"]:
        warnings = [
            *warnings,
            WarningItem(
                code="HISTORICAL_ST_STATUS_UNAVAILABLE",
                message="5% ST price-limit history is not inferred without point-in-time ST identity",
                symbols=[canonical],
            ),
        ]
        degraded = True
    return data, sources, warnings, degraded, {**provenance, "derivation": data["method"]}
