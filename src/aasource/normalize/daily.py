from __future__ import annotations

from collections import defaultdict
from datetime import date
import math
from typing import Any

import pandas as pd


def _bar_date(row: dict[str, Any]) -> date:
    if row.get("year") and row.get("month") and row.get("day"):
        return date(int(row["year"]), int(row["month"]), int(row["day"]))
    return date.fromisoformat(str(row.get("datetime") or row.get("date") or "")[:10])


def _number(value: Any, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if math.isfinite(parsed) else default


def ex_reference(previous_close: float, actions: list[dict[str, Any]]) -> float:
    cash = sum(_number(item.get("fenhong")) for item in actions) / 10
    rights = sum(_number(item.get("peigu")) for item in actions) / 10
    rights_value = sum(_number(item.get("peigu")) * _number(item.get("peigujia")) for item in actions) / 10
    bonus = sum(_number(item.get("songzhuangu")) for item in actions) / 10
    denominator = 1 + rights + bonus
    if previous_close <= 0 or denominator <= 0:
        raise ValueError("invalid corporate action inputs")
    return (previous_close - cash + rights_value) / denominator


def normalize_daily(code: str, rows: list[dict[str, Any]], actions: list[dict[str, Any]]) -> pd.DataFrame:
    records = []
    for row in rows:
        records.append(
            {
                "code": code,
                "trade_date": pd.Timestamp(_bar_date(row)),
                "open": _number(row.get("open")),
                "high": _number(row.get("high")),
                "low": _number(row.get("low")),
                "close": _number(row.get("close")),
                "volume": _number(row.get("vol") or row.get("volume")),
                "amount": _number(row.get("amount")),
            }
        )
    frame = pd.DataFrame(records).drop_duplicates("trade_date", keep="last").sort_values("trade_date")
    if frame.empty:
        return frame
    invalid = (frame[["open", "high", "low", "close"]] <= 0).any(axis=1)
    invalid |= frame["high"] < frame[["open", "low", "close"]].max(axis=1)
    invalid |= frame["low"] > frame[["open", "high", "close"]].min(axis=1)
    if invalid.any():
        raise ValueError(f"invalid OHLC rows: {int(invalid.sum())}")
    action_map: dict[date, list[dict[str, Any]]] = defaultdict(list)
    for action in actions:
        if int(action.get("category", 0) or 0) != 1:
            continue
        try:
            key = date(int(action["year"]), int(action["month"]), int(action["day"]))
        except (KeyError, TypeError, ValueError):
            continue
        action_map[key].append(action)
    factors = [1.0] * len(frame)
    cumulative = 1.0
    closes = frame["close"].tolist()
    dates = frame["trade_date"].dt.date.tolist()
    for index in range(len(frame) - 1, 0, -1):
        current_actions = action_map.get(dates[index], [])
        if current_actions:
            ratio = ex_reference(closes[index - 1], current_actions) / closes[index - 1]
            if 0.01 < ratio < 10:
                cumulative *= ratio
        factors[index - 1] = cumulative
    frame["pre_close"] = frame["close"].shift(1)
    frame["adjust_factor"] = factors
    for field in ("open", "high", "low", "close"):
        frame[f"adj_{field}"] = frame[field] * frame["adjust_factor"]
    frame["source"] = "pytdx"
    return frame.reset_index(drop=True)
