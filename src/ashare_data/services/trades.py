from __future__ import annotations

from typing import Any

from ashare_data.domain.identifiers import canonicalize_symbol
from ashare_data.domain.models import SourceRef, WarningItem
from ashare_data.providers.tdx import get_tdx_provider


def get_trades(
    symbol: str,
    trade_date: str,
    *,
    limit: int = 2000,
) -> tuple[dict[str, Any], list[SourceRef], list[WarningItem], bool]:
    symbol = canonicalize_symbol(symbol)
    rows = get_tdx_provider().fetch_transactions(symbol, trade_date, limit=limit)
    degraded = len(rows) < min(limit, 20)
    warnings = [WarningItem(code="TRADES_SPARSE", symbols=[symbol])] if degraded else []
    return (
        {
            "symbol": symbol,
            "trade_date": trade_date,
            "count": len(rows),
            "rows": rows,
            "provider": "tdx",
        },
        [SourceRef(provider="tdx", role="transactions")],
        warnings,
        degraded,
    )
