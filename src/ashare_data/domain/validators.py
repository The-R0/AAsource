from __future__ import annotations

import math
from typing import Any

from ashare_data.domain.errors import AshareDataError, ErrorCode
from ashare_data.domain.identifiers import canonicalize_symbol


def is_finite_number(value: Any) -> bool:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(number)


def validate_ohlc(open_: Any, high: Any, low: Any, close: Any) -> list[str]:
    problems: list[str] = []
    for name, value in (("open", open_), ("high", high), ("low", low), ("close", close)):
        if value is None:
            continue
        if not is_finite_number(value) or float(value) <= 0:
            problems.append(f"{name}_invalid")
    nums = [float(v) for v in (open_, high, low, close) if v is not None and is_finite_number(v)]
    if len(nums) == 4:
        o, h, l, c = map(float, (open_, high, low, close))
        if h < max(o, c, l):
            problems.append("high_below_body")
        if l > min(o, c, h):
            problems.append("low_above_body")
    return problems


def validate_non_negative(name: str, value: Any) -> list[str]:
    if value is None:
        return []
    if not is_finite_number(value) or float(value) < 0:
        return [f"{name}_invalid"]
    return []


def validate_bar_dict(bar: dict[str, Any]) -> list[str]:
    problems = validate_ohlc(bar.get("open"), bar.get("high"), bar.get("low"), bar.get("close"))
    problems.extend(validate_non_negative("volume", bar.get("volume")))
    problems.extend(validate_non_negative("amount", bar.get("amount")))
    try:
        canonicalize_symbol(str(bar.get("symbol")))
    except AshareDataError:
        problems.append("symbol_invalid")
    return problems


def validate_quote_dict(quote: dict[str, Any]) -> list[str]:
    problems = validate_ohlc(quote.get("open"), quote.get("high"), quote.get("low"), quote.get("last"))
    problems.extend(validate_non_negative("volume", quote.get("volume")))
    problems.extend(validate_non_negative("amount", quote.get("amount")))
    return problems


def assert_supported_adjust(adjust: str) -> None:
    if adjust != "none":
        raise AshareDataError(
            ErrorCode.UNSUPPORTED_ADJUST_MODE,
            f"adjust={adjust} is not supported in v1",
            details={"supported": ["none"]},
        )
