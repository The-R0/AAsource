from __future__ import annotations

from aasource.agent_cli.envelope import ok
from aasource.services.quotes import get_quotes


def run_quotes(symbols: list[str]):
    items, sources, warnings, degraded, freshness = get_quotes(symbols)
    return ok(
        "quotes",
        {
            "items": items,
            "count": len(items),
            "ok_count": sum(1 for i in items if i.get("status") == "ok"),
            "error_count": sum(1 for i in items if i.get("status") != "ok"),
        },
        sources=sources,
        warnings=warnings,
        degraded=degraded,
        freshness=freshness,
    )
