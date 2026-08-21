from __future__ import annotations

from aasource.agent_cli.envelope import ok
from aasource.services.limit_history import get_limit_history


def run_limit_history(symbol: str, *, start: str | None, end: str | None, limit: int):
    data, sources, warnings, degraded, provenance = get_limit_history(
        symbol, start=start, end=end, limit=limit
    )
    return ok(
        "limit-history",
        data,
        sources=sources,
        warnings=warnings,
        degraded=degraded,
        provenance=provenance,
    )
