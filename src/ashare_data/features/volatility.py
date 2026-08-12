from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from ashare_data.features.registry import FeatureDefinition, register


def _true_range(frame: pd.DataFrame) -> pd.Series:
    high = frame["high"]
    low = frame["low"]
    close = frame["close"]
    prev_close = close.shift(1)
    return pd.concat([(high - low), (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)


def _atr(frame: pd.DataFrame, params: dict[str, Any]) -> float | None:
    window = int(params.get("window", 14))
    if len(frame) < window + 1:
        return None
    return float(_true_range(frame).tail(window).mean())


def _volatility(frame: pd.DataFrame, params: dict[str, Any]) -> float | None:
    window = int(params.get("window", 20))
    if len(frame) < window + 1:
        return None
    rets = frame["close"].pct_change().dropna()
    if len(rets) < window:
        return None
    return float(rets.tail(window).std(ddof=0) * np.sqrt(window) * 100.0)


def _amplitude(frame: pd.DataFrame, params: dict[str, Any]) -> float | None:
    if len(frame) < 1:
        return None
    row = frame.iloc[-1]
    prev = float(row["pre_close"]) if "pre_close" in frame.columns and pd.notna(row.get("pre_close")) else float(frame["close"].iloc[-2]) if len(frame) > 1 else None
    base = prev if prev and prev > 0 else float(row["open"]) if float(row["open"] or 0) > 0 else None
    if base is None or base == 0:
        return None
    return (float(row["high"]) - float(row["low"])) / base * 100.0


def _average_amplitude(frame: pd.DataFrame, params: dict[str, Any]) -> float | None:
    window = int(params.get("window", 20))
    if len(frame) < window + 1:
        return None
    values = []
    for i in range(len(frame) - window, len(frame)):
        part = frame.iloc[: i + 1]
        amp = _amplitude(part, {})
        if amp is not None:
            values.append(amp)
    if len(values) < window:
        return None
    return float(sum(values[-window:]) / window)


def _atr_percentile(frame: pd.DataFrame, params: dict[str, Any]) -> float | None:
    window = int(params.get("window", 60))
    atr_window = int(params.get("atr_window", 14))
    if len(frame) < window + atr_window:
        return None
    tr = _true_range(frame)
    atr_series = tr.rolling(atr_window).mean().dropna()
    if len(atr_series) < window:
        return None
    part = atr_series.tail(window)
    last = float(part.iloc[-1])
    return float((part <= last).mean() * 100.0)


def register_volatility_features() -> None:
    register(FeatureDefinition("atr", 1, ("high", "low", "close"), ("window",), _atr))
    register(FeatureDefinition("volatility", 1, ("close",), ("window",), _volatility))
    register(FeatureDefinition("amplitude", 1, ("high", "low"), (), _amplitude))
    register(FeatureDefinition("average_amplitude", 1, ("high", "low", "close"), ("window",), _average_amplitude))
    register(FeatureDefinition("atr_percentile", 1, ("high", "low", "close"), ("window",), _atr_percentile))
