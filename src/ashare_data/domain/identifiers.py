from __future__ import annotations

import re
from typing import Iterable

from ashare_data.domain.errors import AshareDataError, ErrorCode

_BARE = re.compile(r"^\d{6}$")
_PREFIXED = re.compile(r"^(SH|SZ|BJ)(\d{6})$", re.IGNORECASE)
_DOT = re.compile(r"^(?:sh|sz|bj)?(\d{6})$", re.IGNORECASE)


def exchange_for_code(code: str) -> str:
    """Infer exchange for a bare 6-digit code (stocks/funds). Indexes must be prefixed."""
    if not _BARE.fullmatch(code):
        raise AshareDataError(ErrorCode.INVALID_REQUEST, f"Invalid bare code: {code}")
    if code.startswith(("4", "8")):
        return "BJ"
    if code.startswith(("5", "6", "9")):
        return "SH"
    if code.startswith(("0", "3")):
        return "SZ"
    raise AshareDataError(ErrorCode.SYMBOL_NOT_FOUND, f"Cannot infer exchange for {code}")


def canonicalize_symbol(raw: str) -> str:
    value = str(raw).strip()
    if not value:
        raise AshareDataError(ErrorCode.INVALID_REQUEST, "Empty symbol")
    m = _PREFIXED.fullmatch(value)
    if m:
        return f"{m.group(1).upper()}{m.group(2)}"
    lower = value.lower()
    if lower.startswith(("sh", "sz", "bj")) and _BARE.fullmatch(lower[2:]):
        return f"{lower[:2].upper()}{lower[2:]}"
    # Eastmoney-style 1.600519 / 0.000001
    if "." in value:
        parts = value.split(".", 1)
        if len(parts) == 2 and _BARE.fullmatch(parts[1]):
            code = parts[1]
            prefix = parts[0]
            if prefix in {"1", "sh", "SH"}:
                return f"SH{code}"
            if prefix in {"0", "sz", "SZ"}:
                return f"SZ{code}"
            if prefix in {"2", "bj", "BJ"}:
                return f"BJ{code}"
            return f"{exchange_for_code(code)}{code}"
    if _BARE.fullmatch(value):
        return f"{exchange_for_code(value)}{value}"
    raise AshareDataError(ErrorCode.SYMBOL_NOT_FOUND, f"Unknown symbol: {raw}")


def parse_symbol_input(symbols: Iterable[str]) -> list[str]:
    out = [canonicalize_symbol(item) for item in symbols]
    return list(dict.fromkeys(out))


def bare_code(symbol: str) -> str:
    return canonicalize_symbol(symbol)[2:]


def tencent_symbol(symbol: str) -> str:
    symbol = canonicalize_symbol(symbol)
    return f"{symbol[:2].lower()}{symbol[2:]}"
