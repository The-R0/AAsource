from __future__ import annotations

from typing import Any

from aasource.agent_cli.envelope import ok
from aasource.domain.temporal import quote_freshness
from aasource.services.pit_master import validate_order_execution


def run_validate_order(symbol: str, as_of: str | None = None) -> tuple[dict[str, Any], int]:
    payload, sources, warnings, degraded = validate_order_execution(symbol, as_of)
    freshness = quote_freshness([])
    return ok(
        command="validate-order",
        data=payload,
        sources=sources,
        warnings=warnings,
        degraded=degraded,
        freshness=freshness,
    )

