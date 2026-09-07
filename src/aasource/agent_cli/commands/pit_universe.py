from __future__ import annotations

import datetime
from typing import Any

from aasource.agent_cli.envelope import ok
from aasource.domain.temporal import quote_freshness
from aasource.services.pit_master import query_tradable_universe


def run_pit_universe(as_of: str | None = None) -> tuple[dict[str, Any], int]:
    effective_as_of = as_of or datetime.date.today().isoformat()
    payload, sources, warnings, degraded = query_tradable_universe(effective_as_of)
    freshness = quote_freshness([])
    return ok(
        command="pit-universe",
        data=payload,
        sources=sources,
        warnings=warnings,
        degraded=degraded,
        freshness=freshness,
    )

