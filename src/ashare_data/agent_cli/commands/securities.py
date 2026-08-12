from __future__ import annotations

from ashare_data.agent_cli.envelope import ok
from ashare_data.domain.models import SourceRef
from ashare_data.services.securities import get_securities


def run_securities(symbols: list[str]):
    items, sources, warnings, degraded = get_securities(symbols)
    return ok(
        "securities",
        {
            "items": items,
            "count": len(items),
            "ok_count": sum(1 for i in items if i.get("status") == "ok"),
            "error_count": sum(1 for i in items if i.get("status") != "ok"),
            "temporal_scope": "current",
        },
        sources=sources or [SourceRef(provider="tdx", role="security_master")],
        warnings=warnings,
        degraded=degraded,
    )
