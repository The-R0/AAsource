from __future__ import annotations

from ashare_data.agent_cli.envelope import ok
from ashare_data.services.bars import get_bars


def run_bars(
    symbol: str,
    *,
    timeframe: str,
    limit: int | None,
    start: str | None,
    end: str | None,
    adjust: str,
):
    bars, sources, warnings, degraded, provenance = get_bars(
        symbol,
        timeframe=timeframe,
        limit=limit,
        start=start,
        end=end,
        adjust=adjust,
    )
    return ok(
        "bars",
        {"symbol": symbol, "timeframe": timeframe, "adjust": adjust, "bars": bars, "count": len(bars)},
        sources=sources,
        warnings=warnings,
        degraded=degraded,
        provenance=provenance,
    )
