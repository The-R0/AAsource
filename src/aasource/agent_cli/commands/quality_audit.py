from __future__ import annotations

from typing import Any

from aasource.agent_cli.envelope import ok
from aasource.domain.temporal import quote_freshness
from aasource.services.pit_master import run_pit_quality_audit


def run_quality_audit() -> tuple[dict[str, Any], int]:
    payload, sources, warnings, degraded = run_pit_quality_audit()
    freshness = quote_freshness([])
    return ok(
        command="quality-audit",
        data=payload,
        sources=sources,
        warnings=warnings,
        degraded=degraded,
        freshness=freshness,
    )

