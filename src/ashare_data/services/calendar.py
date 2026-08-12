from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from ashare_data.domain.calendar import get_trading_calendar
from ashare_data.services.bars import get_bars

SHANGHAI = ZoneInfo("Asia/Shanghai")


def is_trading_day(day: date | None = None) -> bool:
    cal = get_trading_calendar()
    return cal.is_trading_day(day or datetime.now(SHANGHAI).date())


def previous_trading_day(day: date | None = None, n: int = 1) -> date:
    cal = get_trading_calendar()
    return cal.previous(day or datetime.now(SHANGHAI).date(), n=n)


def next_trading_day(day: date | None = None, n: int = 1) -> date:
    cal = get_trading_calendar()
    return cal.next(day or datetime.now(SHANGHAI).date(), n=n)


def sessions(day: date | None = None) -> list[dict[str, Any]]:
    cal = get_trading_calendar()
    return cal.sessions(day or datetime.now(SHANGHAI).date())


def calendar_info(day: date | None = None) -> dict[str, Any]:
    cal = get_trading_calendar()
    today = day or datetime.now(SHANGHAI).date()
    return {
        "trade_date": today.isoformat(),
        "is_trading_day": cal.is_trading_day(today),
        "previous_trading_day": cal.previous(today).isoformat() if cal.is_trading_day(today) or today.weekday() < 7 else None,
        "next_trading_day": cal.next(today).isoformat(),
        "sessions": cal.sessions(today),
        "temporal_scope": "current",
        "calendar_version": 1,
        "note": "v1 weekday calendar; holiday set can be injected without API change.",
    }


def resolve_trading_dates(candidate: date) -> tuple[str, str, str]:
    """Resolve current/previous dates from canonical market evidence, with an explicit fallback."""
    try:
        bars, _sources, _warnings, _degraded, _meta = get_bars(
            "SH000001",
            timeframe="1d",
            start=(candidate - timedelta(days=45)).isoformat(),
            end=candidate.isoformat(),
            limit=60,
            adjust="none",
        )
        dates = sorted(
            {
                date.fromisoformat(str(row.get("trade_date") or row.get("date") or "")[:10])
                for row in bars
                if str(row.get("trade_date") or row.get("date") or "")[:10]
            }
        )
        eligible = [value for value in dates if value <= candidate]
        if len(eligible) >= 2:
            return eligible[-1].isoformat(), eligible[-2].isoformat(), "canonical_bars:SH000001"
    except Exception:
        pass
    calendar = get_trading_calendar()
    current = candidate
    while not calendar.is_trading_day(current):
        current -= timedelta(days=1)
    return current.isoformat(), calendar.previous(current).isoformat(), "calendar_fallback"
