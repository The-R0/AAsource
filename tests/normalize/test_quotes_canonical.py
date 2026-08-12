from __future__ import annotations

from ashare_data.normalize.quotes import quote_from_tencent_row


def test_quote_volume_shares_not_lots():
    q = quote_from_tencent_row(
        {
            "code": "600519",
            "name": "贵州茅台",
            "price": 100.0,
            "previous_close": 99.0,
            "open": 99.5,
            "high": 101.0,
            "low": 98.0,
            "change": 1.0,
            "change_pct": 1.01,
            "volume_lots": 10.0,
            "amount": 100000.0,
            "turnover_rate": 0.1,
            "source_time": "20260808100000",
        },
        as_of="2026-08-08T10:00:00+08:00",
    )
    assert q.symbol == "SH600519"
    assert q.volume == 1000
    assert q.raw["volume_lots"] == 10.0
