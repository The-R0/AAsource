from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

SHANGHAI = ZoneInfo("Asia/Shanghai")

SessionName = Literal[
    "call_auction",
    "silent",
    "continuous_am",
    "lunch",
    "continuous_pm",
    "closing_auction",
]


@dataclass(frozen=True)
class SessionWindow:
    name: SessionName
    start: time
    end: time
    generates_bars: bool


# SSE/SZSE regular session template (excludes holidays — see TradingCalendar).
SESSION_TEMPLATE: tuple[SessionWindow, ...] = (
    SessionWindow("call_auction", time(9, 15), time(9, 25), True),
    SessionWindow("silent", time(9, 25), time(9, 30), False),
    SessionWindow("continuous_am", time(9, 30), time(11, 30), True),
    SessionWindow("lunch", time(11, 30), time(13, 0), False),
    SessionWindow("continuous_pm", time(13, 0), time(14, 57), True),
    SessionWindow("closing_auction", time(14, 57), time(15, 0), True),
)


class TradingCalendar:
    """Exchange trading-day helpers.

    v1 uses weekday + optional holiday set. Full exchange holiday feed can replace
    `holidays` without changing call sites.
    """

    def __init__(self, holidays: set[date] | None = None, makeups: set[date] | None = None):
        self.holidays = holidays or set()
        self.makeups = makeups or set()  # weekend makeup trading days

    def is_trading_day(self, day: date) -> bool:
        if day in self.makeups:
            return True
        if day in self.holidays:
            return False
        return day.weekday() < 5

    def previous(self, day: date, *, n: int = 1) -> date:
        if n < 1:
            raise ValueError("n must be >= 1")
        cur = day
        left = n
        while left > 0:
            cur -= timedelta(days=1)
            if self.is_trading_day(cur):
                left -= 1
        return cur

    def next(self, day: date, *, n: int = 1) -> date:
        if n < 1:
            raise ValueError("n must be >= 1")
        cur = day
        left = n
        while left > 0:
            cur += timedelta(days=1)
            if self.is_trading_day(cur):
                left -= 1
        return cur

    def sessions(self, day: date) -> list[dict[str, object]]:
        if not self.is_trading_day(day):
            return []
        out: list[dict[str, object]] = []
        for window in SESSION_TEMPLATE:
            out.append(
                {
                    "name": window.name,
                    "start": datetime.combine(day, window.start, tzinfo=SHANGHAI).isoformat(timespec="seconds"),
                    "end": datetime.combine(day, window.end, tzinfo=SHANGHAI).isoformat(timespec="seconds"),
                    "generates_bars": window.generates_bars,
                }
            )
        return out

    def trade_date_for(self, moment: datetime | None = None) -> date | None:
        """Map a timestamp to the A-share trade_date, or None if outside a trading day."""
        moment = moment or datetime.now(SHANGHAI)
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=SHANGHAI)
        else:
            moment = moment.astimezone(SHANGHAI)
        day = moment.date()
        if not self.is_trading_day(day):
            return None
        # Pre-open before 09:15 belongs to prior logic as "not yet today's session"
        if moment.timetz().replace(tzinfo=None) < time(9, 15):
            return None
        return day


_DEFAULT = TradingCalendar()


def get_trading_calendar() -> TradingCalendar:
    return _DEFAULT
