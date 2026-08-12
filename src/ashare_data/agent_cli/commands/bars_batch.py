from __future__ import annotations

from ashare_data.agent_cli.envelope import ok
from ashare_data.services.bars import get_bars_batch


def run_bars_batch(
    symbols: list[str],
    *,
    timeframe: str,
    limit: int | None,
    start: str | None,
    end: str | None,
    adjust: str,
):
    data, sources, warnings, degraded, provenance = get_bars_batch(
        symbols,
        timeframe=timeframe,
        limit=limit,
        start=start,
        end=end,
        adjust=adjust,
    )
    return ok(
        "bars-batch",
        data,
        sources=sources,
        warnings=warnings,
        degraded=degraded,
        provenance=provenance,
    )
