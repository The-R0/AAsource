"""Point-in-Time Security Master and Universe fact service."""

from __future__ import annotations

import datetime
from typing import Any

from aasource.domain.errors import AshareDataError, ErrorCode
from aasource.domain.identifiers import canonicalize_symbol
from aasource.domain.models import SourceRef, WarningItem
from aasource.pit.auditor import MainBoardAuditor
from aasource.pit.master import get_pit_master
from aasource.pit.pipeline import IngestionPipeline


def query_pit_security(
    symbol: str,
    as_of: str | None = None,
) -> tuple[dict[str, Any], list[SourceRef], list[WarningItem], bool]:
    """Query a security's Point-in-Time attributes on as_of trade date."""
    canonical = canonicalize_symbol(symbol)
    as_of_date = as_of or datetime.date.today().isoformat()
    master = get_pit_master()
    
    sec = master.get_security_at(canonical, as_of_date)
    is_st_val = master.is_st(canonical, as_of_date)
    
    warnings: list[WarningItem] = []
    degraded = False
    if is_st_val is None and sec.is_listed:
        degraded = True
        warnings.append(WarningItem(code="ST_STATUS_UNCONFIRMED_DEGRADED", message=f"Historical ST status for {canonical} on {as_of_date} is unconfirmed; coverage downgraded."))

    payload = {
        "security": sec.to_dict(),
        "query_as_of": as_of_date,
        "is_st_pit": is_st_val,
        "is_tradable_pit": sec.tradable,
    }
    sources = [SourceRef(provider=sec.source, role="pit_security_master")]
    return payload, sources, warnings, degraded


def query_tradable_universe(
    as_of: str,
) -> tuple[dict[str, Any], list[SourceRef], list[WarningItem], bool]:
    """Reconstruct the exact tradable Main Board universe as of a Point-in-Time date."""
    master = get_pit_master()
    securities = master.get_tradable_mainboard_universe(as_of)
    payload = {
        "as_of": as_of,
        "universe_size": len(securities),
        "board_filter": "MAIN_BOARD_ONLY",
        "excluded_boards": ["CHINEXT", "STAR", "BSE", "ETF", "INDEX"],
        "securities": [s.to_dict() for s in securities],
    }
    sources = [SourceRef(provider="tdx", role="pit_universe_reconstruction")]
    return payload, sources, [], False


def validate_order_execution(
    symbol: str,
    as_of: str | None = None,
) -> tuple[dict[str, Any], list[SourceRef], list[WarningItem], bool]:
    """Strict gatekeeper verifying order execution permission against Main Board rules."""
    master = get_pit_master()
    permitted, reason = master.validate_order(symbol, as_of)
    payload = {
        "symbol": canonicalize_symbol(symbol),
        "as_of": as_of,
        "order_permitted": permitted,
        "reason_code": reason,
        "rule": "MAIN_BOARD_ONLY_NO_ST_NO_SUSPENSION",
    }
    sources = [SourceRef(provider="internal", role="permission_gatekeeper")]
    return payload, sources, [], not permitted


def run_pit_quality_audit() -> tuple[dict[str, Any], list[SourceRef], list[WarningItem], bool]:
    """Execute the 14-point Main Board quality audit and produce MAIN_BOARD_DAILY_PIT_READY."""
    auditor = MainBoardAuditor()
    report = auditor.run_full_audit()
    sources = [SourceRef(provider="internal", role="quality_auditor")]
    is_ready = report.get("status") == "MAIN_BOARD_DAILY_PIT_READY"
    return report, sources, [], not is_ready
