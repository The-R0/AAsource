from __future__ import annotations

from aasource.agent_cli.envelope import ok
from aasource.services import market as market_service


def run_market(
    subcommand: str,
    *,
    sort_by: str = "change_pct",
    limit: int = 50,
    descending: bool = True,
    trade_date: str | None = None,
):
    if subcommand == "snapshot":
        data, sources, warnings, degraded = market_service.market_snapshot()
    elif subcommand == "cross-section":
        data, sources, warnings, degraded = market_service.market_cross_section()
    elif subcommand == "stock-signals":
        data, sources, warnings, degraded = market_service.market_stock_signals()
    elif subcommand == "movers":
        data, sources, warnings, degraded = market_service.market_movers(sort_by, limit, descending)
    elif subcommand == "breadth":
        data, sources, warnings, degraded = market_service.market_breadth()
    elif subcommand == "limits":
        data, sources, warnings, degraded = market_service.market_limits(trade_date=trade_date)
    else:
        from aasource.domain.errors import AshareDataError, ErrorCode

        raise AshareDataError(ErrorCode.INVALID_REQUEST, f"Unknown market subcommand: {subcommand}")
    return ok(
        f"market.{subcommand}",
        data,
        sources=sources,
        warnings=warnings,
        degraded=degraded,
    )
