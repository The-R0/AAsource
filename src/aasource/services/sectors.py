"""Sector identity / membership / rankings facts."""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import requests

from aasource.domain.errors import AshareDataError, ErrorCode
from aasource.domain.models import SourceRef, WarningItem
from aasource.domain.sectors import canonicalize_sector_id, is_sector_id
from aasource.providers.eastmoney import EastmoneyProviderError
from aasource.providers.eastmoney_boards import (
    fetch_board_members,
    fetch_board_rankings,
    fetch_sector_minute,
    fetch_stock_memberships,
)
from aasource.providers.sw import (
    SwProviderError,
    fetch_sw_industry_members,
    fetch_sw_industry_tree,
    fetch_sw_stock_industry,
)
from aasource.providers.ths import (
    ThsProviderError,
    fetch_ths_concept_boards,
    fetch_ths_stock_concepts,
)
from aasource.domain.identifiers import parse_symbol_input

_BK = re.compile(r"^BK\d+$", re.IGNORECASE)
_SW_CODE = re.compile(r"^\d{6}\.SI$", re.IGNORECASE)
_MEMBERSHIP_SOURCES = ("all", "em", "ths", "sw")

LIST_KINDS = ("all", "industry", "concept", "ths_concept", "sw")


def _em_sources() -> list[SourceRef]:
    return [SourceRef(provider="eastmoney", role="sector_boards")]


def _ths_sources() -> list[SourceRef]:
    return [SourceRef(provider="ths", role="concept_boards"), SourceRef(provider="ths", role="stock_concepts")]


def _sw_sources() -> list[SourceRef]:
    return [SourceRef(provider="legulegu", role="sw_industry")]


def _sources() -> list[SourceRef]:
    return _em_sources()


def list_sectors(
    *, kind: str = "all", limit: int = 200, sw_level: int = 1
) -> tuple[dict[str, Any], list[SourceRef], list[WarningItem], bool]:
    """List sectors. kind: industry | concept | all (Eastmoney) | ths_concept | sw."""
    warnings: list[WarningItem] = []
    if kind not in LIST_KINDS:
        raise AshareDataError(ErrorCode.INVALID_REQUEST, f"unsupported kind: {kind}")
    if kind == "ths_concept":
        try:
            boards = fetch_ths_concept_boards()
        except (ThsProviderError, AshareDataError, requests.RequestException, OSError, ValueError) as exc:
            return (
                {"sectors": [], "count": 0, "kind": kind, "errors": {"ths_concept": str(exc)}},
                _ths_sources(),
                [WarningItem(code="SECTOR_LIST_FAILED", message=f"ths_concept: {exc}")],
                True,
            )
        boards.sort(key=lambda row: str(row.get("name") or ""))
        return (
            {
                "sectors": boards[:limit],
                "count": min(len(boards), limit),
                "kind": kind,
                "types": ["ths_concept"],
                "note": "THS concept boards are name/code identity rows without quotes; board-quote rankings stay Eastmoney-only.",
            },
            _ths_sources(),
            warnings,
            False,
        )
    if kind == "sw":
        level = int(sw_level) if int(sw_level) in (1, 2, 3) else 1
        try:
            tree = fetch_sw_industry_tree()
        except (SwProviderError, AshareDataError, requests.RequestException, OSError, ValueError) as exc:
            return (
                {"sectors": [], "count": 0, "kind": kind, "errors": {"sw": str(exc)}},
                _sw_sources(),
                [WarningItem(code="SECTOR_LIST_FAILED", message=f"sw: {exc}")],
                True,
            )
        rows = list(tree["levels"].get(f"l{level}") or [])
        return (
            {
                "sectors": rows[:limit],
                "count": min(len(rows), limit),
                "kind": kind,
                "level": level,
                "classification": tree.get("classification"),
                "types": [f"sw_industry_l{level}"],
            },
            _sw_sources(),
            warnings,
            False,
        )
    # Eastmoney quote-bearing kinds (all | industry | concept)
    kinds = ["industry", "concept"] if kind == "all" else [kind]
    if any(k not in {"industry", "concept"} for k in kinds):
        raise AshareDataError(ErrorCode.INVALID_REQUEST, f"unsupported kind: {kind}")
    sectors: list[dict[str, Any]] = []
    errors: dict[str, str] = {}
    degraded = False
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
    """Members for an Eastmoney board (BK####) or a Shenwan industry code (801xxx.SI)."""
    needle = str(sector_id or "").strip()
    if _SW_CODE.fullmatch(needle):
        try:
            members = fetch_sw_industry_members(needle, limit=limit)
        except (SwProviderError, AshareDataError, requests.RequestException, OSError, ValueError) as exc:
            raise AshareDataError(ErrorCode.PROVIDER_FAILURE, str(exc), retryable=True) from exc
        return (
            {
                "sector_id": needle.upper(),
                "classification": "SW2021",
                "members": members,
                "count": len(members),
            },
            _sw_sources(),
            [],
            False,
        )
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


def _fetch_per_symbol(
    symbols: list[str],
    worker,
    *,
    max_workers: int = 4,
) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    """Run a per-symbol fetch concurrently; return {symbol: payload} and {symbol: error}."""
    results: dict[str, dict[str, Any]] = {}
    errors: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=min(max_workers, max(1, len(symbols)))) as pool:
        futures = {pool.submit(worker, symbol): symbol for symbol in symbols}
        for future in as_completed(futures):
            symbol = futures[future]
            try:
                results[symbol] = future.result()
            except (EastmoneyProviderError, ThsProviderError, SwProviderError, AshareDataError, requests.RequestException, OSError, ValueError) as exc:
                errors[symbol] = str(exc)
    return results, errors


def stock_memberships(
    symbols: list[str],
    *,
    source: str = "all",
) -> tuple[dict[str, Any], list[SourceRef], list[WarningItem], bool]:
    """Resolve current industry/concept/tag relations for a bounded stock batch.

    source selects the classification stack: ``em`` (Eastmoney boards),
    ``ths`` (THS concepts and company themes), ``sw`` (Shenwan 2021 L1-L3),
    or ``all`` (default) to merge every source per item.
    """
    if source not in _MEMBERSHIP_SOURCES:
        raise AshareDataError(ErrorCode.INVALID_REQUEST, f"unsupported membership source: {source}")
    canonical = parse_symbol_input(symbols)
    if len(canonical) > 100:
        raise AshareDataError(ErrorCode.INVALID_REQUEST, "at most 100 symbols per membership request")
    items: dict[str, dict[str, Any]] = {}
    em_errors: dict[str, str] = {}
    ths_errors: dict[str, str] = {}
    sw_errors: dict[str, str] = {}

    if source in {"all", "em"}:
        em_rows, em_errors = _fetch_per_symbol(canonical, fetch_stock_memberships, max_workers=8)
        for symbol, row in em_rows.items():
            items.setdefault(symbol, {})["memberships"] = list(row.get("memberships") or [])
    if source in {"all", "ths"}:
        ths_rows, ths_errors = _fetch_per_symbol(canonical, fetch_ths_stock_concepts, max_workers=4)
        for symbol, row in ths_rows.items():
            item = items.setdefault(symbol, {})
            item.setdefault("memberships", []).extend(row.get("concepts") or [])
            item.setdefault("memberships", []).extend(row.get("company_themes") or [])
    if source in {"all", "sw"}:
        sw_rows, sw_errors = _fetch_per_symbol(canonical, fetch_sw_stock_industry, max_workers=4)
        for symbol, row in sw_rows.items():
            items.setdefault(symbol, {})["sw_industry"] = row.get("sw_industry")

    ordered = [items.get(symbol, {"memberships": []}) | {"symbol": symbol} for symbol in canonical]
    warnings: list[WarningItem] = []
    failed_sources = sum(bool(errs) for errs in (em_errors, ths_errors, sw_errors))
    if em_errors:
        warnings.append(
            WarningItem(
                code="STOCK_MEMBERSHIP_PARTIAL",
                message=f"eastmoney: {len(em_errors)} of {len(canonical)} symbols failed",
                symbols=list(em_errors),
            )
        )
    if ths_errors:
        warnings.append(
            WarningItem(
                code="THS_MEMBERSHIP_PARTIAL",
                message=f"ths: {len(ths_errors)} of {len(canonical)} symbols failed",
                symbols=list(ths_errors),
            )
        )
    if sw_errors:
        warnings.append(
            WarningItem(
                code="SW_INDUSTRY_PARTIAL",
                message=f"sw: {len(sw_errors)} of {len(canonical)} symbols failed",
                symbols=list(sw_errors),
            )
        )
    errors: dict[str, str] = {}
    for label, errs in (("em", em_errors), ("ths", ths_errors), ("sw", sw_errors)):
        for symbol, message in errs.items():
            errors[f"{label}:{symbol}"] = message
    sources: list[SourceRef] = []
    if source in {"all", "em"}:
        sources.append(SourceRef(provider="eastmoney", role="sector_boards"))
    if source in {"all", "ths"}:
        sources.extend(_ths_sources())
    if source in {"all", "sw"}:
        sources.extend(_sw_sources())
    return (
        {
            "items": ordered,
            "count": len(ordered),
            "requested": len(canonical),
            "source": source,
            "membership_type": "current_snapshot",
            "errors": errors,
            "sources_merged": [name for name, errs in (("em", em_errors), ("ths", ths_errors), ("sw", sw_errors)) if not errs],
        },
        sources,
        warnings,
        failed_sources > 0,
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
