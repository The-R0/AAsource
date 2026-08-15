from __future__ import annotations

from ashare_data.providers.eastmoney import _normalize_row


def test_limit_pool_keeps_direct_seal_and_turnover_facts() -> None:
    row = _normalize_row(
        {
            "c": "000936",
            "n": "华西股份",
            "lbc": 3,
            "fbt": 92500,
            "lbt": 105703,
            "zbc": 7,
            "fund": 43942490,
            "hs": 15.4514,
            "zttj": {"days": 3, "ct": 3},
        }
    )

    assert row["first_limit_time"] == 92500
    assert row["last_limit_time"] == 105703
    assert row["break_count"] == 7
    assert row["streak"] == 3
    assert row["seal_order_amount"] == 43942490.0
    assert row["turnover_rate"] == 15.4514
    assert row["raw"]["zttj"] == {"days": 3, "ct": 3}
