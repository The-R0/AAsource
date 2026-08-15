from __future__ import annotations

import pandas as pd

from ashare_data.features.relative import (
    _sector_rank,
    _sector_relative_return,
    build_sector_relative_context,
)


def test_sector_context_preserves_multiple_memberships_and_temporal_basis() -> None:
    stock = pd.DataFrame(
        {
            "trade_date": ["2026-08-11", "2026-08-12", "2026-08-13"],
            "close": [10.0, 11.0, 12.0],
        }
    )

    def memberships(_symbol):
        return {
            "memberships": [
                {"source_id": "BK0001", "name": "行业A", "relation_type": "industry", "rank": 1},
                {"source_id": "BK0002", "name": "概念B", "relation_type": "concept", "precise": True},
                {"source_id": "BK9999", "name": "标签", "relation_type": "tag"},
            ]
        }

    def bars(sector_id, **_kwargs):
        closes = [100.0, 102.0, 104.0] if sector_id == "BK0001" else [200.0, 201.0, 202.0]
        rows = [
            {"trade_date": day, "close": close, "status": "final"}
            for day, close in zip(stock["trade_date"], closes)
        ]
        return rows, [], [], False, {}

    def members(_sector_id, **_kwargs):
        return [
            {"symbol": "SH600001", "change_pct": 3.0, "amount": 20.0, "turnover_rate": 2.0},
            {"symbol": "SH600002", "change_pct": 5.0, "amount": 10.0, "turnover_rate": 4.0},
        ]

    context = build_sector_relative_context(
        "SH600001",
        stock,
        membership_fetcher=memberships,
        sector_bars_fetcher=bars,
        member_fetcher=members,
        retrieved_at="2026-08-14T15:01:00+08:00",
    )
    stock.attrs["sector_relative_context"] = context
    relative = _sector_relative_return(stock, {"window": 2})
    amount_rank = _sector_rank(stock, {"feature_id": "sector_amount_rank"})

    assert {item["sector_id"] for item in relative["items"]} == {"BK0001", "BK0002"}
    assert all(item["period_start"] == "2026-08-11" for item in relative["items"])
    assert all(item["historical_membership_asserted"] is False for item in relative["items"])
    assert {item["rank"] for item in amount_rank["items"]} == {1}
    assert amount_rank["temporal_basis"] == "current_member_cross_section"
