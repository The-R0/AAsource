from __future__ import annotations

from typing import Any

import pandas as pd

from ashare_data.features.registry import FeatureDefinition, register


def _ma(frame: pd.DataFrame, params: dict[str, Any]) -> float | None:
    window = int(params.get("window", 20))
    if len(frame) < window:
        return None
    return float(frame["close"].tail(window).mean())


def _ema(frame: pd.DataFrame, params: dict[str, Any]) -> float | None:
    window = int(params.get("window", 20))
    if len(frame) < window:
        return None
    return float(frame["close"].ewm(span=window, adjust=False).mean().iloc[-1])


def _return(frame: pd.DataFrame, params: dict[str, Any]) -> float | None:
    """Return over `window` sessions as percent points (2.31 = +2.31%)."""
    window = int(params.get("window", 5))
    if len(frame) <= window:
        return None
    last = float(frame["close"].iloc[-1])
    prev = float(frame["close"].iloc[-1 - window])
    if prev == 0:
        return None
    return (last / prev - 1.0) * 100.0


def _rolling_high(frame: pd.DataFrame, params: dict[str, Any]) -> float | None:
    window = int(params.get("window", 20))
    if len(frame) < window:
        return None
    return float(frame["high"].tail(window).max())


def _rolling_low(frame: pd.DataFrame, params: dict[str, Any]) -> float | None:
    window = int(params.get("window", 20))
    if len(frame) < window:
        return None
    return float(frame["low"].tail(window).min())


def _distance_to_ma(frame: pd.DataFrame, params: dict[str, Any]) -> float | None:
    window = int(params.get("window", 20))
    ma = _ma(frame, params)
    if ma is None or ma == 0:
        return None
    return (float(frame["close"].iloc[-1]) / ma - 1.0) * 100.0


def _distance_to_high(frame: pd.DataFrame, params: dict[str, Any]) -> float | None:
    high = _rolling_high(frame, params)
    if high is None or high == 0:
        return None
    return (float(frame["close"].iloc[-1]) / high - 1.0) * 100.0


def _breakout_pct(frame: pd.DataFrame, params: dict[str, Any]) -> float | None:
    """Positive when close breaks prior N-day high (excluding today)."""
    window = int(params.get("window", 20))
    if len(frame) < window + 1:
        return None
    prior_high = float(frame["high"].iloc[-(window + 1) : -1].max())
    if prior_high == 0:
        return None
    return (float(frame["close"].iloc[-1]) / prior_high - 1.0) * 100.0


def register_trend_features() -> None:
    register(FeatureDefinition("ma", 1, ("close",), ("window",), _ma))
    register(FeatureDefinition("ema", 1, ("close",), ("window",), _ema))
    register(FeatureDefinition("return", 1, ("close",), ("window",), _return))
    register(FeatureDefinition("rolling_high", 1, ("high",), ("window",), _rolling_high))
    register(FeatureDefinition("rolling_low", 1, ("low",), ("window",), _rolling_low))
    register(FeatureDefinition("distance_to_ma", 1, ("close",), ("window",), _distance_to_ma))
    register(FeatureDefinition("distance_to_high", 1, ("close", "high"), ("window",), _distance_to_high))
    register(FeatureDefinition("breakout_pct", 1, ("close", "high"), ("window",), _breakout_pct))
