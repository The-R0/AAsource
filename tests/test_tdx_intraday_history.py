from __future__ import annotations

import pytest

from ashare_data.domain.errors import AshareDataError, ErrorCode
from ashare_data.providers import tdx as tdx_provider
from ashare_data.services import bars as bars_service


def _raw_minute(day: str, hour: int, minute: int, *, open_: float, high: float, low: float, close: float):
    year, month, date = (int(part) for part in day.split("-"))
    return {
        "year": year,
        "month": month,
        "day": date,
        "hour": hour,
        "minute": minute,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "vol": 100,
        "amount": close * 100,
    }


def test_tdx_pages_back_to_requested_intraday_date(monkeypatch) -> None:
    calls = []

    class FakeApi:
        def __init__(self, **kwargs):
            pass

        def connect(self, *args, **kwargs):
            return self

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get_security_bars(self, category, market, code, offset, count):
            calls.append(offset)
            if offset == 0:
                row = _raw_minute("2026-08-14", 15, 0, open_=8.7, high=8.8, low=8.6, close=8.7)
                return [row] * 800
            if offset == 800:
                return [
                    _raw_minute("2026-07-21", 9, 31, open_=4.89, high=4.93, low=4.78, close=4.78),
                    _raw_minute("2026-07-21", 9, 32, open_=4.78, high=4.90, low=4.78, close=4.88),
                ]
            return []

    monkeypatch.setattr(tdx_provider, "TdxHq_API", FakeApi)
    provider = tdx_provider.TdxProvider([tdx_provider.TdxHost("example.test")])

    rows = provider.fetch_minute_1m("SH600664", trading_date="2026-07-21")

    # One older page is checked because a trading day can straddle page boundaries.
    assert calls == [0, 800, 1600]
    assert [row["ts"].isoformat() for row in rows] == [
        "2026-07-21T09:31:00+08:00",
        "2026-07-21T09:32:00+08:00",
    ]
    assert rows[0]["open"] == 4.89
    assert rows[0]["low"] == 4.78


def test_historical_intraday_bars_are_final_and_resample_to_15m(monkeypatch) -> None:
    class FakeTdx:
        def fetch_minute_1m(self, symbol, trading_date=None):
            assert trading_date == "2026-07-21"
            return [
                {
                    "ts": tdx_provider.datetime(2026, 7, 21, 9, minute, tzinfo=tdx_provider.SHANGHAI),
                    "open": 4.89 if minute == 31 else 4.78,
                    "high": 5.21 if minute == 45 else 4.93,
                    "low": 4.78,
                    "close": 5.21 if minute == 45 else 4.78,
                    "volume": 100,
                    "amount": 500,
                    "volume_unit": "shares",
                    "source": "tdx",
                }
                for minute in range(31, 46)
            ]

    monkeypatch.setattr(bars_service, "get_tdx_provider", lambda: FakeTdx())

    bars, _sources, warnings, degraded, provenance = bars_service.get_bars(
        "SH600664",
        timeframe="15m",
        start="2026-07-21",
        end="2026-07-21",
        limit=16,
    )

    assert len(bars) == 1
    assert bars[0]["ts"] == "2026-07-21T09:45:00+08:00"
    assert bars[0]["open"] == 4.89
    assert bars[0]["low"] == 4.78
    assert bars[0]["close"] == 5.21
    assert bars[0]["status"] == "final"
    assert warnings == []
    assert degraded is False
    assert provenance["requested_trade_date"] == "2026-07-21"


def test_tdx_reports_unavailable_when_history_retention_does_not_reach_date(monkeypatch) -> None:
    class FakeApi:
        def __init__(self, **kwargs):
            pass

        def connect(self, *args, **kwargs):
            return self

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get_security_bars(self, category, market, code, offset, count):
            row = _raw_minute("2026-08-14", 15, 0, open_=8.7, high=8.8, low=8.6, close=8.7)
            return [row] * count

    monkeypatch.setattr(tdx_provider, "TdxHq_API", FakeApi)
    monkeypatch.setattr(tdx_provider, "INTRADAY_MAX_PAGES", 2)
    provider = tdx_provider.TdxProvider([tdx_provider.TdxHost("example.test")])

    with pytest.raises(AshareDataError) as caught:
        provider.fetch_minute_1m("SH600664", trading_date="2020-01-02")

    assert caught.value.code == ErrorCode.UNAVAILABLE
    assert caught.value.details["trade_date"] == "2020-01-02"
