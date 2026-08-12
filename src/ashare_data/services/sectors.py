"""Sector identity / membership / rankings facts."""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import requests

from ashare_data.domain.errors import AshareDataError, ErrorCode
from ashare_data.domain.models import SourceRef, WarningItem
from ashare_data.domain.sectors import canonicalize_sector_id, is_sector_id
from ashare_data.providers.eastmoney import EastmoneyProviderError
from ashare_data.providers.eastmoney_boards import (
    fetch_board_members,
    fetch_board_rankings,
    fetch_sector_minute,
    fetch_stock_memberships,
)
from ashare_data.domain.identifiers import parse_symbol_input

_BK = re.compile(r"^BK\d+$", re.IGNORECASE)


def _sources() -> list[SourceRef]:
    return [SourceRef(provider="eastmoney", role="sector_boards")]


def list_sectors(*, kind: str = "all", limit: int = 200) -> tuple[dict[str, Any], list[SourceRef], list[WarningItem], bool]:
    """List/rank sectors. kind: industry | concept | all."""
    warnings: list[WarningItem] = []
    degraded = False
    kinds = ["industry", "concept"] if kind == "all" else [kind]
    if any(k not in {"industry", "concept"} for k in kinds):
        raise AshareDataError(ErrorCode.INVALID_REQUEST, f"unsupported kind: {kind}")
    sectors: list[dict[str, Any]] = []
    errors: dict[str, str] = {}
    per = max(1, int(limit) if kind != "all" else max(1, int(limit) // 2))
    for k in kinds:
        try:
            sectors.extend(fetch_board_rankings(k, limit=per))
        except (EastmoneyProviderError, requests.RequestException, OSError, ValueError) as exc:
            errors[k] = str(exc)
            degraded = True
            warnings.append(WarningItem(code="SECTOR_LIST_FAILED", message=f"{k}: {exc}"))
    sectors.sort(key=lambda row: float(row.get("change_pct") or -999), reverse=True)
    return (
        {
            "sectors": sectors[:limit],
            "count": min(len(sectors), limit),
            "kind": kind,
            "types": ["industry", "concept"],
            "errors": errors,
            "subcommands": ["list", "rankings", "members", "memberships", "search", "resolve"],
        },
        _sources(),
        warnings,
        degraded,
    )


def sector_rankings(*, kind: str = "industry", limit: int = 50) -> tuple[dict[str, Any], list[SourceRef], list[WarningItem], bool]:
    data, sources, warnings, degraded = list_sectors(kind=kind, limit=limit)
    return (
        {
            "rankings": data["sectors"],
            "count": data["count"],
            "kind": kind,
            "errors": data.get("errors") or {},
        },
        sources,
        warnings,
        degraded,
    )


def sector_members(
    sector_id: str,
    *,
    limit: int = 500,
) -> tuple[dict[str, Any], list[SourceRef], list[WarningItem], bool]:
    sector_id = canonicalize_sector_id(sector_id)
    try:
        members = fetch_board_members(sector_id, limit=limit)
    except (EastmoneyProviderError, requests.RequestException, OSError, ValueError) as exc:
        raise AshareDataError(ErrorCode.PROVIDER_FAILURE, str(exc), retryable=True) from exc
    return (
        {
            "sector_id": sector_id,
            "members": members,
            "count": len(members),
        },
        _sources(),
        [],
        False,
    )


def stock_memberships(
    symbols: list[str],
) -> tuple[dict[str, Any], list[SourceRef], list[WarningItem], bool]:
    """Resolve current industry/concept/tag relations for a bounded stock batch."""
    canonical = parse_symbol_input(symbols)
    if len(canonical) > 100:
        raise AshareDataError(ErrorCode.INVALID_REQUEST, "at most 100 symbols per membership request")
    items: dict[str, dict[str, Any]] = {}
    errors: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=min(8, max(1, len(canonical)))) as pool:
        futures = {pool.submit(fetch_stock_memberships, symbol): symbol for symbol in canonical}
        for future in as_completed(futures):
            symbol = futures[future]
            try:
                items[symbol] = future.result()
            except (EastmoneyProviderError, requests.RequestException, OSError, ValueError) as exc:
                errors[symbol] = str(exc)
    ordered = [items[symbol] for symbol in canonical if symbol in items]
    warnings = []
    if errors:
        warnings.append(
            WarningItem(
                code="STOCK_MEMBERSHIP_PARTIAL",
                message=f"{len(errors)} of {len(canonical)} symbols failed",
                symbols=list(errors),
            )
        )
    return (
        {
            "items": ordered,
            "count": len(ordered),
            "requested": len(canonical),
            "errors": errors,
            "membership_type": "current_snapshot",
        },
        _sources(),
        warnings,
        bool(errors),
    )


def sector_search(
    query: str,
    *,
    limit: int = 20,
) -> tuple[dict[str, Any], list[SourceRef], list[WarningItem], bool]:
    needle = str(query or "").strip()
    if not needle:
        raise AshareDataError(ErrorCode.INVALID_REQUEST, "sector search query required")
    if is_sector_id(needle) or _BK.fullmatch(needle):
        sector_id = canonicalize_sector_id(needle)
        return (
            {
                "query": needle,
                "matches": [
                    {
                        "sector_id": sector_id,
                        "board_code": sector_id,
                        "board_name": sector_id,
                        "name": sector_id,
                        "kind": "unknown",
                        "match": "id",
                    }
                ],
                "count": 1,
            },
            _sources(),
            [],
            False,
        )
    sectors: list[dict[str, Any]] = []
    warnings: list[WarningItem] = []
    degraded = False
    for kind in ("industry", "concept"):
        data, _kind_sources, kind_warnings, kind_degraded = list_sectors(kind=kind, limit=500)
        sectors.extend(data["sectors"])
        warnings.extend(kind_warnings)
        degraded = degraded or kind_degraded
    sources = _sources()
    exact = [row for row in sectors if str(row.get("name") or "") == needle]
    partial = [
        row
        for row in sectors
        if needle in str(row.get("name") or "") and str(row.get("name") or "") != needle
    ]
    matches = (exact + partial)[:limit]
    if not matches:
        raise AshareDataError(ErrorCode.SYMBOL_NOT_FOUND, f"sector not found: {needle}")
    return (
        {"query": needle, "matches": matches, "count": len(matches)},
        sources,
        warnings,
        degraded,
    )


def sector_resolve(query: str) -> tuple[dict[str, Any], list[SourceRef], list[WarningItem], bool]:
    data, sources, warnings, degraded = sector_search(query, limit=5)
    matches = data.get("matches") or []
    return (
        {
            "query": query,
            "sector": matches[0] if matches else None,
            "alternates": matches[1:],
        },
        sources,
        warnings,
        degraded,
    )


def sector_minute(
    sector_id: str,
    *,
    trading_date: str | None = None,
) -> tuple[dict[str, Any], list[SourceRef], list[WarningItem], bool]:
    sector_id = canonicalize_sector_id(sector_id)
    try:
        payload = fetch_sector_minute(sector_id, trading_date=trading_date)
    except (EastmoneyProviderError, requests.RequestException, OSError, ValueError) as exc:
        raise AshareDataError(ErrorCode.PROVIDER_FAILURE, str(exc), retryable=True) from exc
    degraded = not bool(payload.get("rows"))
    warnings = [WarningItem(code="SECTOR_MINUTE_EMPTY")] if degraded else []
    return payload, [SourceRef(provider="eastmoney", role="sector_minute")], warnings, degraded


def sector_bars(sector_id: str, **_: Any) -> dict[str, Any]:
    raise AshareDataError(
        ErrorCode.CAPABILITY_NOT_AVAILABLE,
        "sectors bars removed — use `bars <sector-id> --tf 1m` for OHLCV",
        details={"replacement": f"bars {sector_id}", "sector_id": sector_id},
        retryable=False,
    )
