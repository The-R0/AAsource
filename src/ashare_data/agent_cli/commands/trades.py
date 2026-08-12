from __future__ import annotations

from ashare_data.agent_cli.envelope import ok
from ashare_data.services.trades import get_trades


def run_trades(symbol: str, *, trade_date: str, limit: int = 2000):
    data, sources, warnings, degraded = get_trades(symbol, trade_date, limit=limit)
    return ok("trades", data, sources=sources, warnings=warnings, degraded=degraded)
