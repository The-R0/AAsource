from __future__ import annotations

from typing import Any

import pandas as pd

from ashare_data.features.registry import FeatureDefinition, register


def _frame_return_pct(frame: pd.DataFrame, window: int) -> float | None:
    if len(frame) <= window:
        return None
    last = float(frame["close"].iloc[-1])
    prev = float(frame["close"].iloc[-1 - window])
    if prev == 0:
        return None
    return (last / prev - 1.0) * 100.0


def _relative_return_index(frame: pd.DataFrame, params: dict[str, Any]) -> float | None:
    window = int(params.get("window", 5))
    benchmark = str(params.get("benchmark", "SH000300"))
    stock_ret = _frame_return_pct(frame, window)
    if stock_ret is None:
        return None
    from ashare_data.services.bars import get_bars

    try:
        rows, _sources, _warnings, _degraded, _provenance = get_bars(
            benchmark,
            timeframe="1d",
            limit=max(window + 5, 80),
            adjust="none",
        )
    except Exception:
        return None
    bench = pd.DataFrame(rows)
    bench_ret = _frame_return_pct(bench, window)
    if bench_ret is None:
        return None
    return stock_ret - bench_ret


def _unavailable(_frame: pd.DataFrame, _params: dict[str, Any]) -> float | None:
    """Sector-relative metrics await canonical sector membership — stay null."""
    return None


def register_relative_features() -> None:
    register(
        FeatureDefinition(
            "relative_return_index",
            1,
            ("close",),
            ("window", "benchmark"),
            _relative_return_index,
        )
    )
    register(FeatureDefinition("relative_return_sector", 1, ("close",), ("window",), _unavailable))
    register(FeatureDefinition("sector_return_rank", 1, (), (), _unavailable))
    register(FeatureDefinition("sector_amount_rank", 1, (), (), _unavailable))
    register(FeatureDefinition("sector_turnover_rank", 1, (), (), _unavailable))
