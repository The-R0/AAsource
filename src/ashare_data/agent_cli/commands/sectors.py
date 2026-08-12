from __future__ import annotations

from ashare_data.agent_cli.envelope import ok
from ashare_data.domain.errors import AshareDataError, ErrorCode
from ashare_data.services import sectors as sectors_service


def run_sectors(
    subcommand: str,
    *,
    sector_id: str | None = None,
    query: str | None = None,
    kind: str = "all",
    limit: int = 100,
    trade_date: str | None = None,
    symbols: list[str] | None = None,
):
    if subcommand == "list":
        data, sources, warnings, degraded = sectors_service.list_sectors(kind=kind, limit=limit)
        return ok("sectors.list", data, sources=sources, warnings=warnings, degraded=degraded)
    if subcommand == "rankings":
        data, sources, warnings, degraded = sectors_service.sector_rankings(kind=kind if kind != "all" else "industry", limit=limit)
        return ok("sectors.rankings", data, sources=sources, warnings=warnings, degraded=degraded)
    if subcommand == "members":
        data, sources, warnings, degraded = sectors_service.sector_members(sector_id or "", limit=limit)
        return ok("sectors.members", data, sources=sources, warnings=warnings, degraded=degraded)
    if subcommand == "memberships":
        data, sources, warnings, degraded = sectors_service.stock_memberships(symbols or [])
        return ok("sectors.memberships", data, sources=sources, warnings=warnings, degraded=degraded)
    if subcommand == "search":
        data, sources, warnings, degraded = sectors_service.sector_search(query or sector_id or "", limit=limit)
        return ok("sectors.search", data, sources=sources, warnings=warnings, degraded=degraded)
    if subcommand == "resolve":
        data, sources, warnings, degraded = sectors_service.sector_resolve(query or sector_id or "")
        return ok("sectors.resolve", data, sources=sources, warnings=warnings, degraded=degraded)
    if subcommand == "minute":
        data, sources, warnings, degraded = sectors_service.sector_minute(
            sector_id or query or "",
            trading_date=trade_date,
        )
        return ok("sectors.minute", data, sources=sources, warnings=warnings, degraded=degraded)
    raise AshareDataError(ErrorCode.INVALID_REQUEST, f"Unknown sectors subcommand: {subcommand}")
