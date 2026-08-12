from __future__ import annotations

from ashare_data.services import market


def test_stock_signals_derive_all_requested_dimensions(monkeypatch) -> None:
    monkeypatch.setattr(
        market,
        "_market_snapshot",
        lambda: {
            "quotes": [
                {"symbol": "SH600001", "change_pct": 10.0, "amount": 100.0, "turnover_rate": 8.0},
                {"symbol": "SZ000002", "change_pct": 1.0, "amount": 200.0, "turnover_rate": 2.0},
            ],
            "source_time": "2026-08-11T10:00:00+08:00",
            "retrieved_at": "2026-08-11T10:00:01+08:00",
            "universe": {"status": "PASS"},
        },
    )
    monkeypatch.setattr(
        market,
        "fetch_stock_signal_rows",
        lambda: [
            {"symbol": "SH600001", "volume_ratio": 3.0, "change_pct_5d": 20.0, "industry": "测试行业"},
            {"symbol": "SZ000002", "volume_ratio": 1.0, "change_pct_5d": 2.0, "industry": "测试行业"},
        ],
    )
    monkeypatch.setattr(market, "fetch_board_rankings", lambda *_args, **_kwargs: [{"name": "测试行业", "change_pct": 2.0}])
    monkeypatch.setattr(
        market,
        "market_limits",
        lambda: (
            {"limit_up": {"rows": [{"symbol": "SH600001", "streak": 2}]}, "broken_limit": None, "limit_down": None, "previous_limit_up": {"rows": []}},
            [],
            [],
            False,
        ),
    )

    data, _sources, _warnings, degraded = market.market_stock_signals()
    first = data["stocks"][0]

    assert degraded is False
    assert first["amount_expansion_pctile"] == 100.0
    assert first["sector_divergence_pct"] == 8.0
    assert first["persistence_return_4d_pct"] is not None
    assert first["limit_activity"]["today_state"] == "limit_up"
    assert data["dimension_coverage"]["sector_divergence_pctile"] == 2
