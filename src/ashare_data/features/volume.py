from __future__ import annotations

from typing import Any

import pandas as pd

from ashare_data.features.registry import FeatureDefinition, register


def _avg_volume(frame: pd.DataFrame, params: dict[str, Any]) -> float | None:
    window = int(params.get("window", 20))
    if len(frame) < window:
        return None
    return float(frame["volume"].tail(window).mean())


def _avg_amount(frame: pd.DataFrame, params: dict[str, Any]) -> float | None:
    window = int(params.get("window", 20))
    if len(frame) < window:
        return None
    return float(frame["amount"].tail(window).mean())


def _volume_ratio(frame: pd.DataFrame, params: dict[str, Any]) -> float | None:
    window = int(params.get("window", 5))
    if len(frame) < window + 1:
        return None
    today = float(frame["volume"].iloc[-1])
    base = float(frame["volume"].iloc[-(window + 1) : -1].mean())
    if base == 0:
        return None
    return today / base


def _amount_ratio(frame: pd.DataFrame, params: dict[str, Any]) -> float | None:
    window = int(params.get("window", 5))
    if len(frame) < window + 1:
        return None
    today = float(frame["amount"].iloc[-1])
    base = float(frame["amount"].iloc[-(window + 1) : -1].mean())
    if base == 0:
        return None
    return today / base


def _vwap(frame: pd.DataFrame, params: dict[str, Any]) -> float | None:
    window = int(params.get("window", 20))
    if len(frame) < 1:
        return None
    part = frame.tail(window) if len(frame) >= window else frame
    vol = part["volume"].sum()
    if vol == 0:
        return None
    return float((part["close"] * part["volume"]).sum() / vol)


def _turnover_rate(frame: pd.DataFrame, params: dict[str, Any]) -> float | None:
    if "turnover_rate" not in frame.columns:
        return None
    value = frame["turnover_rate"].iloc[-1]
    if pd.isna(value):
        return None
    return float(value)


def _average_turnover(frame: pd.DataFrame, params: dict[str, Any]) -> float | None:
    if "turnover_rate" not in frame.columns:
        return None
    window = int(params.get("window", 20))
    if len(frame) < window:
        return None
    series = frame["turnover_rate"].tail(window)
    if series.isna().all():
        return None
    return float(series.mean())


def _percentile(series: pd.Series, value: float) -> float | None:
    clean = series.dropna()
    if clean.empty:
        return None
    return float((clean <= value).mean() * 100.0)


def _amount_percentile(frame: pd.DataFrame, params: dict[str, Any]) -> float | None:
    window = int(params.get("window", 20))
    if len(frame) < window:
        return None
    part = frame["amount"].tail(window)
    return _percentile(part, float(part.iloc[-1]))


def _turnover_percentile(frame: pd.DataFrame, params: dict[str, Any]) -> float | None:
    if "turnover_rate" not in frame.columns:
        return None
    window = int(params.get("window", 20))
    if len(frame) < window:
        return None
    part = frame["turnover_rate"].tail(window)
    return _percentile(part, float(part.iloc[-1]))


def register_volume_features() -> None:
    register(FeatureDefinition("average_volume", 1, ("volume",), ("window",), _avg_volume))
    register(FeatureDefinition("average_amount", 1, ("amount",), ("window",), _avg_amount))
    register(FeatureDefinition("volume_ratio", 1, ("volume",), ("window",), _volume_ratio))
    register(FeatureDefinition("amount_ratio", 1, ("amount",), ("window",), _amount_ratio))
    register(FeatureDefinition("vwap", 1, ("close", "volume"), ("window",), _vwap))
    register(FeatureDefinition("turnover_rate", 1, (), (), _turnover_rate))
    register(FeatureDefinition("average_turnover", 1, (), ("window",), _average_turnover))
    register(FeatureDefinition("amount_percentile", 1, ("amount",), ("window",), _amount_percentile))
    register(FeatureDefinition("turnover_percentile", 1, (), ("window",), _turnover_percentile))
