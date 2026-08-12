from __future__ import annotations

from ashare_data.providers.eastmoney_boards import _map_sector_daily_kline
from ashare_data.services import bars as bars_service


def test_maps_sector_daily_kline_to_canonical_units() -> None:
    row = _map_sector_daily_kline("2026-08-11,100.1,102.2,103.3,99.4,12345,678901.2,0,0,0,0")
    assert row == {
        "trade_date": "2026-08-11",
        "ts": "2026-08-11T15:00:00+08:00",
        "open": 100.1,
        "close": 102.2,
        "high": 103.3,
        "low": 99.4,
        "volume": 12345,
        "amount": 678901.2,
    }


def test_sector_daily_uses_same_bars_interface(monkeypatch) -> None:
    monkeypatch.setattr(
        "ashare_data.providers.eastmoney_boards.fetch_sector_daily",
        lambda sector_id, **kwargs: {
            "sector_id": sector_id,
            "name": "银行Ⅱ",
            "rows": [_map_sector_daily_kline("2026-08-11,100,102,103,99,12345,678901,0,0,0,0")],
        },
    )
    rows, sources, warnings, degraded, provenance = bars_service.get_bars(
        "BK0475", timeframe="1d", limit=120
    )
    assert warnings == []
    assert degraded is False
    assert sources[0].role == "sector_daily"
    assert provenance["sector_name"] == "银行Ⅱ"
    assert rows[0]["symbol"] == "BK0475"
    assert rows[0]["close"] == 102.0
    assert rows[0]["status"] == "final"
    assert rows[0]["source"] == "eastmoney"
    assert rows[0]["adjust"] == "none"
