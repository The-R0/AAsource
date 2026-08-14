from __future__ import annotations

from typing import Any

from ashare_data.domain.batch import map_results, resolve_inputs
from ashare_data.domain.errors import ErrorCode
from ashare_data.domain.identifiers import canonicalize_symbol
from ashare_data.domain.models import Security, SourceRef, WarningItem
from ashare_data.normalize.securities import security_from_master_row
from ashare_data.providers.tdx import get_tdx_provider


def get_securities(
    symbols: list[str],
) -> tuple[list[dict[str, Any]], list[SourceRef], list[WarningItem], bool]:
    items = resolve_inputs(symbols)
    by_symbol: dict[str, dict[str, Any]] = {}
    master_error: str | None = None
    try:
        master = get_tdx_provider().fetch_security_master()
        for row in master.get("symbols") or []:
            code = str(row.get("code") or "")
            exchange = str(row.get("exchange") or "").upper()
            raw_symbol = row.get("symbol") or (f"{exchange}{code}" if exchange and len(code) == 6 else code)
            try:
                by_symbol[canonicalize_symbol(str(raw_symbol))] = row
            except Exception:
                continue
    except Exception as exc:  # noqa: BLE001
        master_error = str(exc)

    def fetch(ok_symbols: list[str]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for symbol in ok_symbols:
            row = by_symbol.get(symbol)
            if row:
                sec = security_from_master_row({**row, "symbol": symbol, "code": symbol[2:], "exchange": symbol[:2]})
            else:
                continue
            payload = sec.to_dict()
            if payload.get("symbol") != symbol:
                continue
            payload["temporal_scope"] = "current"
            payload["trading_rules"] = {
                "price_limit_type": "standard",
                "price_limit_pct": payload.get("price_limit_pct"),
                "price_tick": 0.01,
            }
            out[symbol] = payload
        return out

    results, degraded = map_results(
        items,
        payload_key="security",
        fetch=fetch,
        missing_error_code=ErrorCode.SYMBOL_NOT_FOUND,
        missing_retryable=False,
    )
    warnings: list[WarningItem] = []
    if master_error:
        degraded = True
        warnings.append(WarningItem(code="SECURITY_MASTER_UNAVAILABLE", message=master_error))
    if degraded:
        warnings.append(WarningItem(code="BATCH_PARTIAL"))
    sources = [SourceRef(provider="tdx", role="security_master")]
    return results, sources, warnings, degraded
