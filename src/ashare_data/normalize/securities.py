from __future__ import annotations

from typing import Any

from ashare_data.domain.enums import SecurityType
from ashare_data.domain.identifiers import canonicalize_symbol
from ashare_data.domain.models import Security


def _infer_type(symbol: str, name: str | None) -> str:
    code = symbol[2:]
    if symbol.startswith("SH") and code.startswith("000"):
        return SecurityType.INDEX
    if symbol.startswith("SZ") and code.startswith("399"):
        return SecurityType.INDEX
    if code.startswith(("51", "15", "56", "58")):
        return SecurityType.ETF
    return SecurityType.STOCK


def _infer_board(symbol: str) -> str | None:
    code = symbol[2:]
    if symbol.startswith("BJ"):
        return "bse"
    if code.startswith("688"):
        return "star"
    if code.startswith(("300", "301")):
        return "chinext"
    if code.startswith(("000", "001", "002", "003", "600", "601", "603", "605")):
        return "mainboard"
    return None


def _price_limit_pct(symbol: str, is_st: bool | None) -> float | None:
    if is_st:
        return 5.0
    code = symbol[2:]
    if code.startswith(("300", "301", "688")):
        return 20.0
    if symbol.startswith("BJ"):
        return 30.0
    if _infer_type(symbol, None) == SecurityType.INDEX:
        return None
    return 10.0


def security_from_master_row(row: dict[str, Any]) -> Security:
    raw_code = str(row.get("code") or row.get("symbol") or "")
    # master rows may already be SH/SZ or bare
    try:
        symbol = canonicalize_symbol(raw_code if len(raw_code) >= 6 else str(row.get("code")))
    except Exception:
        market = str(row.get("market") or row.get("exchange") or "").upper()
        code = str(row.get("code") or "")[-6:]
        if market in {"SH", "SZ", "BJ"}:
            symbol = f"{market}{code}"
        else:
            symbol = canonicalize_symbol(code)
    name = row.get("name")
    is_st = None
    if isinstance(name, str):
        is_st = "ST" in name.upper()
    return Security(
        symbol=symbol,
        code=symbol[2:],
        exchange=symbol[:2],
        name=name,
        security_type=_infer_type(symbol, name),
        board=_infer_board(symbol),
        is_st=is_st,
        is_suspended=row.get("is_suspended"),
        price_limit_pct=_price_limit_pct(symbol, is_st),
        listed_date=row.get("listed_date"),
        delisted_date=row.get("delisted_date"),
    )
