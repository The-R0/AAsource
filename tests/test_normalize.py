from __future__ import annotations

import pytest

from ashare_data.normalize import ex_reference, normalize_daily


def test_cash_dividend_adjustment_is_causal() -> None:
    rows = [
        {"year": 2024, "month": 1, "day": 2, "open": 10, "high": 11, "low": 9, "close": 10, "vol": 100, "amount": 1000},
        {"year": 2024, "month": 1, "day": 3, "open": 9, "high": 10, "low": 8, "close": 9, "vol": 100, "amount": 900},
    ]
    actions = [{"category": 1, "year": 2024, "month": 1, "day": 3, "fenhong": 10}]

    frame = normalize_daily("SH600000", rows, actions)

    assert ex_reference(10, actions) == 9
    assert frame.loc[0, "adjust_factor"] == pytest.approx(0.9)
    assert frame.loc[1, "adjust_factor"] == 1
    assert frame.loc[1, "pre_close"] == 10


def test_invalid_ohlc_is_rejected() -> None:
    rows = [{"year": 2024, "month": 1, "day": 2, "open": 10, "high": 9, "low": 8, "close": 10}]
    with pytest.raises(ValueError, match="invalid OHLC"):
        normalize_daily("SH600000", rows, [])
