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


def _extreme_time(frame: pd.DataFrame, field: str, mode: str) -> str | None:
    if frame.empty or "ts" not in frame.columns or field not in frame.columns:
        return None
    values = pd.to_numeric(frame[field], errors="coerce")
    if values.notna().sum() == 0:
        return None
    index = values.idxmax() if mode == "high" else values.idxmin()
    return str(frame.loc[index, "ts"])


def _intraday_high_time(frame: pd.DataFrame, params: dict[str, Any]) -> str | None:
    """First minute in the frame that reached the session high."""
    return _extreme_time(frame, "high", "high")


def _intraday_low_time(frame: pd.DataFrame, params: dict[str, Any]) -> str | None:
    """First minute in the frame that reached the session low."""
    return _extreme_time(frame, "low", "low")


def _max_drawdown_from_high(frame: pd.DataFrame, params: dict[str, Any]) -> float | None:
    """Largest close-to-running-close-peak drawdown, expressed as a negative percent."""
    closes = pd.to_numeric(frame.get("close"), errors="coerce").dropna()
    if closes.empty:
        return None
    peaks = closes.cummax()
    valid = peaks != 0
    if not valid.any():
        return None
    return float(((closes[valid] / peaks[valid]) - 1.0).min() * 100.0)


def _last_30m_return(frame: pd.DataFrame, params: dict[str, Any]) -> float | None:
    """Return over the final 30 one-minute intervals: last close vs close 30 bars earlier."""
    closes = pd.to_numeric(frame.get("close"), errors="coerce").dropna()
    if len(closes) < 31:
        return None
    base = float(closes.iloc[-31])
    if base == 0:
        return None
    return (float(closes.iloc[-1]) / base - 1.0) * 100.0


def register_intraday_features() -> None:
    register(FeatureDefinition("distance_to_vwap", 1, ("close", "volume"), ("window",), _distance_to_vwap))
    register(FeatureDefinition("intradaily_return", 1, ("open", "close"), (), _intradaily_return))
    register(FeatureDefinition("distance_to_intraday_high", 1, ("high", "close"), (), _distance_to_intraday_high))
    register(FeatureDefinition("distance_to_intraday_low", 1, ("low", "close"), (), _distance_to_intraday_low))
    register(FeatureDefinition("intradaily_volume_ratio", 1, ("volume",), ("window",), _intradaily_volume_ratio))
    register(FeatureDefinition("intraday_high_time", 1, ("ts", "high"), (), _intraday_high_time))
    register(FeatureDefinition("intraday_low_time", 1, ("ts", "low"), (), _intraday_low_time))
    register(FeatureDefinition("max_drawdown_from_high", 1, ("close",), (), _max_drawdown_from_high))
    register(FeatureDefinition("last_30m_return", 1, ("close",), (), _last_30m_return))
