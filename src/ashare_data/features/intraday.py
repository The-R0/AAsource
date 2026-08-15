from __future__ import annotations

from typing import Any

import pandas as pd

from ashare_data.features.registry import FeatureDefinition, register
from ashare_data.features.volume import _vwap


def _distance_to_vwap(frame: pd.DataFrame, params: dict[str, Any]) -> float | None:
    vwap = _vwap(frame, params)
    if vwap is None or vwap == 0:
        return None
    return (float(frame["close"].iloc[-1]) / vwap - 1.0) * 100.0


def _intradaily_return(frame: pd.DataFrame, params: dict[str, Any]) -> float | None:
    if len(frame) < 1:
        return None
    first = float(frame["open"].iloc[0])
    last = float(frame["close"].iloc[-1])
    if first == 0:
        return None
    return (last / first - 1.0) * 100.0


def _distance_to_intraday_high(frame: pd.DataFrame, params: dict[str, Any]) -> float | None:
    if len(frame) < 1:
        return None
    high = float(frame["high"].max())
    if high == 0:
        return None
    return (float(frame["close"].iloc[-1]) / high - 1.0) * 100.0


def _distance_to_intraday_low(frame: pd.DataFrame, params: dict[str, Any]) -> float | None:
    if len(frame) < 1:
        return None
    low = float(frame["low"].min())
    if low == 0:
        return None
    return (float(frame["close"].iloc[-1]) / low - 1.0) * 100.0


def _intradaily_volume_ratio(frame: pd.DataFrame, params: dict[str, Any]) -> float | None:
    """Last bar volume vs mean of prior bars in the same session frame."""
    window = int(params.get("window", 5))
    if len(frame) < window + 1:
        return None
    today = float(frame["volume"].iloc[-1])
    base = float(frame["volume"].iloc[-(window + 1) : -1].mean())
    if base == 0:
        return None
    return today / base


def register_intraday_features() -> None:
    register(FeatureDefinition("distance_to_vwap", 1, ("close", "volume"), ("window",), _distance_to_vwap))
    register(FeatureDefinition("intradaily_return", 1, ("open", "close"), (), _intradaily_return))
    register(FeatureDefinition("distance_to_intraday_high", 1, ("high", "close"), (), _distance_to_intraday_high))
    register(FeatureDefinition("distance_to_intraday_low", 1, ("low", "close"), (), _distance_to_intraday_low))
    register(FeatureDefinition("intradaily_volume_ratio", 1, ("volume",), ("window",), _intradaily_volume_ratio))
