from __future__ import annotations

from aasource.agent_cli.envelope import ok
from aasource.services.sector_context import get_sector_context


def run_sector_context(sector: str, *, member_limit: int):
    data, sources, warnings, degraded = get_sector_context(sector, member_limit=member_limit)
    return ok("sector-context", data, sources=sources, warnings=warnings, degraded=degraded)
