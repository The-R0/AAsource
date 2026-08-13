from __future__ import annotations

from datetime import date, timedelta

import pytest


def _daily_bars(count: int = 120) -> list[dict[str, object]]:
    start = date(2026, 1, 1)
    rows: list[dict[str, object]] = []
    for index in range(count):
        close = 10.0 + index * 0.05
        rows.append(
            {
                "trade_date": (start + timedelta(days=index)).isoformat(),
                "open": close - 0.02,
                "high": close + 0.08,
                "low": close - 0.08,
                "close": close,
                "volume": 1_000_000 + index * 1_000,
                "amount": close * (1_000_000 + index * 1_000),
            }
        )
    return rows


@pytest.fixture(autouse=True)
def offline_feature_bars(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = _daily_bars()

    def fake_get_bars(*_args, **_kwargs):
        return rows, [], [], False, {"fixture": "offline_feature_bars"}

    monkeypatch.setattr("ashare_data.features.compute.get_bars", fake_get_bars)
