from __future__ import annotations

import json
import math
from datetime import date

from aasource.agent_cli.serializers import sanitize_for_json
from aasource.domain.calendar import TradingCalendar
from aasource.domain.validators import validate_ohlc
from aasource.services.calendar import calendar_info, previous_trading_day, resolve_trading_dates


def test_trading_calendar_weekday():
    cal = TradingCalendar()
    assert cal.is_trading_day(date(2026, 8, 7)) is True  # Friday
    assert cal.is_trading_day(date(2026, 8, 8)) is False  # Saturday
    assert cal.previous(date(2026, 8, 10)).isoformat() == "2026-08-07"
    sessions = cal.sessions(date(2026, 8, 7))
    names = [s["name"] for s in sessions]
    assert "call_auction" in names
    assert "lunch" in names
    assert calendar_info(date(2026, 8, 7))["is_trading_day"] is True
    assert previous_trading_day(date(2026, 8, 10)).isoformat() == "2026-08-07"


def test_market_date_resolution_prefers_canonical_bars(monkeypatch):
    rows = [{"trade_date": "2026-08-07"}, {"trade_date": "2026-08-10"}]
    monkeypatch.setattr("aasource.services.calendar.get_bars", lambda *_args, **_kwargs: (rows, [], [], False, {}))
    assert resolve_trading_dates(date(2026, 8, 11)) == (
        "2026-08-10",
        "2026-08-07",
        "canonical_bars:SH000001",
    )


def test_market_date_resolution_discloses_calendar_fallback(monkeypatch):
    def unavailable(*_args, **_kwargs):
        raise RuntimeError("offline")

    monkeypatch.setattr("aasource.services.calendar.get_bars", unavailable)
    assert resolve_trading_dates(date(2026, 8, 9)) == (
        "2026-08-07",
        "2026-08-06",
        "calendar_fallback",
    )


def test_sanitize_rejects_nan_inf():
    clean = sanitize_for_json({"a": math.nan, "b": math.inf, "c": -math.inf, "d": 1.5})
    assert clean["a"] is None
    assert clean["b"] is None
    assert clean["c"] is None
    assert clean["d"] == 1.5
    json.dumps(clean, allow_nan=False)


def test_validate_ohlc():
    assert validate_ohlc(10, 11, 9, 10.5) == []
    assert "high_below_body" in validate_ohlc(10, 9, 8, 10)
