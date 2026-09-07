from __future__ import annotations

from aasource.agent_cli.envelope import ok
from aasource.services.relative_intraday import get_relative_intraday


def run_relative_intraday(symbol: str, *, sector_id: str | None, trade_date: str | None):
    data, sources, warnings, degraded = get_relative_intraday(
        symbol, sector_id=sector_id, trade_date=trade_date
    )
    return ok("relative-intraday", data, sources=sources, warnings=warnings, degraded=degraded)
