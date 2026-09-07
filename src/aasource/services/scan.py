"""Generic current-session stock filtering and ranking facts."""

from __future__ import annotations

import json
from typing import Any

from aasource.domain.errors import AshareDataError, ErrorCode
from aasource.domain.models import SourceRef, WarningItem
from aasource.services.bars import get_bars_batch
from aasource.services.market import market_stock_signals
from aasource.services.sectors import sector_rankings

OPS = {
    "=": lambda left, right: left == right,
    "==": lambda left, right: left == right,
    "eq": lambda left, right: left == right,
    "!=": lambda left, right: left != right,
    "ne": lambda left, right: left != right,
    ">": lambda left, right: left > right,
    "gt": lambda left, right: left > right,
    ">=": lambda left, right: left >= right,
    "gte": lambda left, right: left >= right,
    "<": lambda left, right: left < right,
    "lt": lambda left, right: left < right,
    "<=": lambda left, right: left <= right,
    "lte": lambda left, right: left <= right,
    "in": lambda left, right: left in right if isinstance(right, (list, tuple, set)) else left == right,
    "not_in": lambda left, right: left not in right if isinstance(right, (list, tuple, set)) else left != right,
}

BAR_FIELDS = {"distance_20d_high"}
MAX_BAR_ENRICH = 80
MAX_RESULT_LIMIT = 50
AVAILABLE_FIELDS = (
    "symbol",
    "name",
    "board",
    "industry",
    "amount",
    "change_pct",
    "open_change_pct",
    "change_pct_5d",
    "change_pct_60d",
    "turnover_rate",
    "volume_ratio",
    "sector_divergence_pct",
    "industry_change_pct",
    "sector_rank",
    "sector_rank_pct",
    "relative_sector_1d",
    "previous_limit_up",
    "today_state",
    "streak",
    "return_pctile",
    "amount_pctile",
    "distance_20d_high",
)
UNSUPPORTED_FIELDS = {
    "relative_sector_5d": "industry 5d return is unavailable on the current cross-section",
    "historical_st": "historical ST/listing status is unavailable",
    "distance_60d_high": "only distance_20d_high is implemented",
}
RANK_ALIASES = {
    "relative_sector_1d": "sector_divergence_pct",
    "rs": "sector_divergence_pct",
    "rs_1d": "sector_divergence_pct",
}
OUTPUT_FIELDS = (
    "symbol",
    "name",
    "board",
    "industry",
    "last",
    "change_pct",
    "open_change_pct",
    "amount",
    "turnover_rate",
    "volume_ratio",
    "change_pct_5d",
    "change_pct_60d",
    "sector_divergence_pct",
    "relative_sector_1d",
    "sector_rank",
    "sector_rank_pct",
    "previous_limit_up",
    "today_state",
    "streak",
    "return_pctile",
    "amount_pctile",
    "distance_20d_high",
)


def classify_board(symbol: str | None) -> str:
    value = str(symbol or "").upper()
    if value.startswith("SH688"):
        return "STAR"
    if value.startswith("SH6"):
        return "SH_MAIN"
    if value.startswith("SZ300"):
        return "CYB"
    if value.startswith(("SZ000", "SZ001")):
        return "SZ_MAIN"
    if value.startswith("SZ002"):
        return "SME"
    if value.startswith("BJ"):
        return "BJ"
    if value.startswith("SH"):
        return "SH"
    if value.startswith("SZ"):
        return "SZ"
    return "OTHER"


def parse_filters(raw: Any) -> list[dict[str, Any]]:
    if raw in (None, "", []):
        return []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise AshareDataError(ErrorCode.INVALID_REQUEST, f"filters must be valid JSON: {exc.msg}") from exc
    if not isinstance(raw, list):
        raise AshareDataError(ErrorCode.INVALID_REQUEST, "filters must be a JSON list of {field, op, value}")
    filters: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict) or not item.get("field"):
            raise AshareDataError(ErrorCode.INVALID_REQUEST, "each filter needs field, op, value")
        op = str(item.get("op") or "=")
        if op not in OPS:
            raise AshareDataError(ErrorCode.INVALID_REQUEST, f"unsupported filter operator: {op}")
        filters.append({"field": str(item["field"]), "op": op, "value": item.get("value")})
    return filters


def industry_ranks(industries: list[dict[str, Any]]) -> dict[str, tuple[int, float | None]]:
    ranked = [row for row in industries if row.get("name") and isinstance(row.get("change_pct"), (int, float))]
    ranked.sort(key=lambda row: float(row["change_pct"]), reverse=True)
    size = len(ranked)
    return {
        str(row["name"]): (index, round(index / size, 4) if size else None)
        for index, row in enumerate(ranked, 1)
    }


def _safe_pct(numerator: Any, denominator: Any) -> float | None:
    if not isinstance(numerator, (int, float)) or not isinstance(denominator, (int, float)) or denominator == 0:
        return None
    return round(float(numerator) / float(denominator) * 100, 4)


def _source_date(value: Any) -> str | None:
    digits = "".join(character for character in str(value or "")[:10] if character.isdigit())
    if len(digits) < 8:
        return None
    return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}"


def enrich_scan_row(row: dict[str, Any], ranks: dict[str, tuple[int, float | None]]) -> dict[str, Any]:
    activity = row.get("limit_activity") or {}
    industry = row.get("industry")
    rank = ranks.get(str(industry)) if industry else None
    previous_close = row.get("previous_close")
    open_change = _safe_pct(
        float(row["open"]) - float(previous_close)
        if isinstance(row.get("open"), (int, float)) and isinstance(previous_close, (int, float))
        else None,
        previous_close,
    )
    return {
        **row,
        "board": classify_board(str(row.get("symbol") or "")),
        "open_change_pct": open_change,
        "previous_limit_up": bool(activity.get("previous_limit_up")),
        "today_state": activity.get("today_state") or "none",
        "streak": int(activity.get("streak") or 0),
        "sector_rank": rank[0] if rank else None,
        "sector_rank_pct": rank[1] if rank else None,
        "relative_sector_1d": row.get("sector_divergence_pct"),
    }


def _matches(row: dict[str, Any], item: dict[str, Any]) -> bool:
    left = row.get(item["field"])
    if left is None:
        return False
    right = item.get("value")
    if isinstance(left, bool) and not isinstance(right, bool):
        right = str(right).lower() in {"1", "true", "yes"}
    if isinstance(left, (int, float)) and not isinstance(left, bool) and not isinstance(right, (list, tuple, set)):
        try:
            right = float(right)
        except (TypeError, ValueError):
            return False
    return bool(OPS[item["op"]](left, right))


def apply_filters(
    rows: list[dict[str, Any]], filters: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, str]], list[dict[str, Any]]]:
    skipped: list[dict[str, str]] = []
    active: list[dict[str, Any]] = []
    for item in filters:
        field = item["field"]
        if field in UNSUPPORTED_FIELDS:
            skipped.append({"field": field, "reason": UNSUPPORTED_FIELDS[field]})
        elif field not in AVAILABLE_FIELDS:
            skipped.append({"field": field, "reason": "unknown scan field"})
        else:
            active.append(item)
    matched = rows
    for item in (row for row in active if row["field"] not in BAR_FIELDS):
        matched = [row for row in matched if _matches(row, item)]
    return matched, skipped, [row for row in active if row["field"] in BAR_FIELDS]


def distance_20d_high(bars: list[dict[str, Any]]) -> float | None:
    highs = [float(row["high"]) for row in bars[-20:] if isinstance(row.get("high"), (int, float))]
    close = next((float(row["close"]) for row in reversed(bars) if isinstance(row.get("close"), (int, float))), None)
    if not highs or close is None or max(highs) <= 0:
        return None
    return round(close / max(highs) - 1.0, 4)


def slim_scan_row(row: dict[str, Any]) -> dict[str, Any]:
    return {field: row.get(field) for field in OUTPUT_FIELDS if row.get(field) is not None}


def _dedupe_sources(sources: list[SourceRef]) -> list[SourceRef]:
    seen: set[tuple[str, str]] = set()
    output: list[SourceRef] = []
    for source in sources:
        key = (source.provider, source.role)
        if key not in seen:
            seen.add(key)
            output.append(source)
    return output


def scan_stocks(
    *,
    filters: Any = None,
    rank_by: str = "amount",
    descending: bool = True,
    limit: int = 30,
    trade_date: str | None = None,
) -> tuple[dict[str, Any], list[SourceRef], list[WarningItem], bool]:
    parsed = parse_filters(filters)
    if not 1 <= int(limit) <= MAX_RESULT_LIMIT:
        raise AshareDataError(ErrorCode.INVALID_REQUEST, f"limit must be between 1 and {MAX_RESULT_LIMIT}")

    signals, signal_sources, signal_warnings, signal_degraded = market_stock_signals()
    industries, industry_sources, industry_warnings, industry_degraded = sector_rankings(kind="industry", limit=500)
    effective_date = _source_date(signals.get("source_time"))
    if trade_date and not effective_date:
        raise AshareDataError(
            ErrorCode.CAPABILITY_NOT_AVAILABLE,
            "scan-stocks could not establish the current session date",
            details={"date_requested": trade_date, "historical_replay": False},
        )
    if trade_date and effective_date and trade_date != effective_date:
        raise AshareDataError(
            ErrorCode.CAPABILITY_NOT_AVAILABLE,
            f"scan-stocks is current-session only (effective {effective_date})",
            details={
                "date_requested": trade_date,
                "date_effective": effective_date,
                "historical_replay": False,
                "missing": ["historical_st_status", "historical_sector_membership", "as_of_quotes"],
            },
        )

    ranks = industry_ranks(list(industries.get("rankings") or []))
    universe = [enrich_scan_row(row, ranks) for row in signals.get("stocks") or [] if isinstance(row, dict)]
    matched, skipped, bar_filters = apply_filters(universe, parsed)
    sources = signal_sources + industry_sources
    warnings = signal_warnings + industry_warnings
    degraded = signal_degraded or industry_degraded

    if bar_filters and len(matched) > MAX_BAR_ENRICH:
        skipped.append({
            "field": "distance_20d_high",
            "reason": f"{len(matched)} survivors exceed {MAX_BAR_ENRICH}; tighten cheap filters first",
        })
        bar_filters = []
        degraded = True
    if bar_filters and matched:
        batch, bar_sources, bar_warnings, bar_degraded, _ = get_bars_batch(
            [str(row["symbol"]) for row in matched if row.get("symbol")],
            timeframe="1d",
            limit=25,
        )
        sources.extend(bar_sources)
        warnings.extend(bar_warnings)
        degraded = degraded or bar_degraded
        by_symbol = {
            str(item.get("symbol")): item.get("bars") or []
            for item in batch.get("items") or []
            if item.get("status") == "ok"
        }
        for row in matched:
            row["distance_20d_high"] = distance_20d_high(by_symbol.get(str(row.get("symbol"))) or [])
        for item in bar_filters:
            matched = [row for row in matched if _matches(row, item)]

    requested_rank = str(rank_by)
    resolved_rank = RANK_ALIASES.get(requested_rank, requested_rank)
    if resolved_rank in UNSUPPORTED_FIELDS:
        skipped.append({"field": resolved_rank, "reason": UNSUPPORTED_FIELDS[resolved_rank]})
        resolved_rank = "sector_divergence_pct"
        degraded = True
    if resolved_rank not in AVAILABLE_FIELDS:
        raise AshareDataError(ErrorCode.INVALID_REQUEST, f"unsupported rank_by: {requested_rank}")
    ranked = [row for row in matched if row.get(resolved_rank) is not None]
    ranked.sort(key=lambda row: row[resolved_rank], reverse=bool(descending))
    omitted = {item["field"] for item in skipped}
    return (
        {
            "purpose": "generic_cross_section_query",
            "judgment_free": True,
            "temporal_scope": "current_session",
            "historical_replay": False,
            "date_requested": trade_date,
            "date_effective": effective_date,
            "scanned_count": len(universe),
            "matched_count": len(ranked),
            "rank_by": resolved_rank,
            "rank_by_requested": requested_rank,
            "descending": bool(descending),
            "applied_filters": [item for item in parsed if item["field"] not in omitted],
            "skipped_filters": skipped,
            "available_fields": list(AVAILABLE_FIELDS),
            "rows": [slim_scan_row(row) for row in ranked[:limit]],
            "truncated": len(ranked) > limit,
            "field_units": {"distance_20d_high": "ratio", "*_pct": "percent_points"},
            "note": "Generic current-session facts only; not a stock picker, score, or buy list.",
        },
        _dedupe_sources(sources),
        warnings,
        degraded,
    )
