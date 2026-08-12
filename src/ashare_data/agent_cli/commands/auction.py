from __future__ import annotations

from ashare_data.agent_cli.envelope import ok
from ashare_data.services.auction import get_auction_snapshots


def run_auction(symbols: list[str]):
    items, sources, warnings, degraded, freshness = get_auction_snapshots(symbols)
    return ok(
        "auction",
        {
            "items": items,
            "count": len(items),
            "ok_count": sum(1 for item in items if item.get("status") == "ok"),
            "error_count": sum(1 for item in items if item.get("status") != "ok"),
        },
        sources=sources,
        warnings=warnings,
        degraded=degraded,
        freshness=freshness,
    )
