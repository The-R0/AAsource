from __future__ import annotations

from typing import Any

import pandas as pd

from ashare_data.features.registry import FeatureDefinition, register


def _macd(frame: pd.DataFrame, params: dict[str, Any]) -> float | None:
    fast = int(params.get("fast", 12))
    slow = int(params.get("slow", 26))
    signal = int(params.get("signal", 9))
    field = str(params.get("field", "macd"))
    need = slow + signal
    if len(frame) < need:
        return None
    close = frame["close"]
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd = ema_fast - ema_slow
    macd_signal = macd.ewm(span=signal, adjust=False).mean()
    hist = macd - macd_signal
    mapping = {"macd": macd, "signal": macd_signal, "histogram": hist}
    series = mapping.get(field)
    if series is None:
        return None
    return float(series.iloc[-1])


def _rsi(frame: pd.DataFrame, params: dict[str, Any]) -> float | None:
    window = int(params.get("window", 14))
    if len(frame) < window + 1:
        return None
    delta = frame["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window).mean()
    avg_loss = loss.rolling(window).mean()
    rs = avg_gain / avg_loss.replace(0, pd.NA)
    rsi = 100 - (100 / (1 + rs))
    value = rsi.iloc[-1]
    if pd.isna(value):
        return None
    return float(value)


def _boll(frame: pd.DataFrame, params: dict[str, Any]) -> float | None:
    window = int(params.get("window", 20))
    n_std = float(params.get("n_std", 2.0))
    field = str(params.get("field", "mid"))
    if len(frame) < window:
        return None
    mid = frame["close"].rolling(window).mean()
    std = frame["close"].rolling(window).std(ddof=0)
    upper = mid + n_std * std
    lower = mid - n_std * std
    mapping = {"mid": mid, "upper": upper, "lower": lower}
    series = mapping.get(field)
    if series is None:
        return None
    value = series.iloc[-1]
    if pd.isna(value):
        return None
    return float(value)


def _obv(frame: pd.DataFrame, params: dict[str, Any]) -> float | None:
    if len(frame) < 2:
        return None
    direction = frame["close"].diff().fillna(0).apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))
    obv = (direction * frame["volume"]).cumsum()
    return float(obv.iloc[-1])


def register_technical_features() -> None:
    register(FeatureDefinition("macd", 1, ("close",), ("fast", "slow", "signal", "field"), _macd))
    register(FeatureDefinition("rsi", 1, ("close",), ("window",), _rsi))
    register(FeatureDefinition("boll", 1, ("close",), ("window", "field"), _boll))
    register(FeatureDefinition("obv", 1, ("close", "volume"), (), _obv))
