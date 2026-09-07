from __future__ import annotations

from typing import Any

from aasource.agent_cli.envelope import ok
from aasource.services.scan import scan_stocks


def run_scan_stocks(
    *,
    filters: Any,
    rank_by: str,
    descending: bool,
    limit: int,
    trade_date: str | None,
):
    data, sources, warnings, degraded = scan_stocks(
        filters=filters,
        rank_by=rank_by,
        descending=descending,
        limit=limit,
        trade_date=trade_date,
    )
    return ok("scan-stocks", data, sources=sources, warnings=warnings, degraded=degraded)
