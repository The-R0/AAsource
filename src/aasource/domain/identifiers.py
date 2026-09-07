from __future__ import annotations

import re
from typing import Iterable

from aasource.domain.errors import AshareDataError, ErrorCode

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


# ---------------------------------------------------------------------------
# Board classification and Account Execution Permission (Main Board Only)
# ---------------------------------------------------------------------------

_MAINBOARD_SH_PREFIXES = ("600", "601", "603", "605")
_MAINBOARD_SZ_PREFIXES = ("000", "001", "002", "003")
_CHINEXT_PREFIXES = ("300", "301")
_STAR_PREFIXES = ("688", "689")

# Canonical observation anchor indices for non-executable markets and macro context
MARKET_OBSERVATION_ANCHORS = frozenset({
    "SZ399006",  # 创业板指
    "SH000688",  # 科创50
    "SH000001",  # 上证指数
    "SZ399001",  # 深证成指
    "SH000300",  # 沪深300
    "SH000905",  # 中证500
    "SH000852",  # 中证1000
    "SZ399106",  # 深证综指
})


def classify_board(symbol: str) -> str:
    """Classify instrument into standard board identifier."""
    canonical = canonicalize_symbol(symbol)
    exchange = canonical[:2]
    code = canonical[2:]

    if exchange == "BJ":
        return "BSE"
    if exchange == "SH":
        if code.startswith("000") or code.startswith("000"):
            return "INDEX"
        if code.startswith(("51", "56", "58", "50")):
            return "ETF"
        if code.startswith(_STAR_PREFIXES):
            return "STAR"
        if code.startswith(_MAINBOARD_SH_PREFIXES):
            return "SH_MAIN"
    elif exchange == "SZ":
        if code.startswith("399"):
            return "INDEX"
        if code.startswith(("15", "16")):
            return "ETF"
        if code.startswith(_CHINEXT_PREFIXES):
            return "CHINEXT"
        if code.startswith(_MAINBOARD_SZ_PREFIXES):
            return "SZ_MAIN"

    return "OTHER"


def is_mainboard_executable(symbol: str) -> bool:
    """Check if symbol belongs to the executable Shanghai/Shenzhen Main Board universe."""
    board = classify_board(symbol)
    return board in ("SH_MAIN", "SZ_MAIN")


def is_non_executable_board(symbol: str) -> bool:
    """Check if symbol is explicitly non-executable (STAR, ChiNext, BSE, ETF, Index, etc.)."""
    return not is_mainboard_executable(symbol)


def is_market_observation_anchor(symbol: str) -> bool:
    """Check if symbol is a designated non-executable market observation anchor."""
    try:
        canonical = canonicalize_symbol(symbol)
        if canonical in MARKET_OBSERVATION_ANCHORS:
            return True
        board = classify_board(canonical)
        return board == "INDEX"
    except Exception:
        return False


def check_execution_permission(symbol: str) -> tuple[bool, str]:
    """Strict execution permission gatekeeper.

    Returns:
        (True, "ACCESSIBLE") for main board stocks.
        (False, reason_code) for all non-executable instruments.
    """
    try:
        canonical = canonicalize_symbol(symbol)
    except Exception as exc:
        return False, f"INVALID_SYMBOL: {exc}"

    exchange = canonical[:2]
    code = canonical[2:]

    if exchange == "BJ":
        return False, "EXCLUDED_BOARD_BSE"
    if code.startswith(_STAR_PREFIXES):
        return False, "EXCLUDED_BOARD_STAR"
    if code.startswith(_CHINEXT_PREFIXES):
        return False, "EXCLUDED_BOARD_CHINEXT"
    if code.startswith(("51", "56", "58", "50", "15", "16")):
        return False, "EXCLUDED_TYPE_ETF_OR_FUND"
    if exchange == "SH" and code.startswith("000") or exchange == "SZ" and code.startswith("399"):
        return False, "EXCLUDED_TYPE_INDEX"

    if is_mainboard_executable(canonical):
        return True, "ACCESSIBLE"

    return False, "EXCLUDED_NON_MAINBOARD"

