from __future__ import annotations

import pandas as pd

from ashare_data.features.intraday import (
    _intraday_high_time,
    _intraday_low_time,
    _last_30m_return,
    _max_drawdown_from_high,
)


def test_intraday_structure_uses_first_extreme_and_explicit_30m_basis() -> None:
    frame = pd.DataFrame(
        {
            "ts": [f"2026-08-14T{9 + (index + 30) // 60:02d}:{(index + 30) % 60:02d}:00+08:00" for index in range(31)],
            "high": [10.0, 12.0, 12.0] + [11.0] * 28,
            "low": [9.0, 8.0, 8.0] + [9.0] * 28,
            "close": [10.0, 12.0, 9.0] + [11.0] * 27 + [11.0],
        }
    )

    assert _intraday_high_time(frame, {}) == frame.loc[1, "ts"]
    assert _intraday_low_time(frame, {}) == frame.loc[1, "ts"]
    assert round(_max_drawdown_from_high(frame, {}), 4) == -25.0
    assert round(_last_30m_return(frame, {}), 4) == 10.0
