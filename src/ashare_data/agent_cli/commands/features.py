from __future__ import annotations

from ashare_data.agent_cli.envelope import ok
from ashare_data.domain.identifiers import canonicalize_symbol
from ashare_data.domain.models import SourceRef, WarningItem
from ashare_data.features.compute import compute_feature_set, compute_feature_sets, compute_features_batch


def run_features(
    symbols: list[str],
    *,
    set_name: str,
    timeframe: str,
    include_provisional: bool = False,
):
    warnings: list[WarningItem] = []
    names = [p.strip() for p in set_name.split(",") if p.strip()]
    if include_provisional:
        warnings.append(
            WarningItem(
                code="PROVISIONAL_NOT_MERGED",
                message="include_provisional accepted but v1 still uses final daily / live minute bars without hybrid merge",
            )
        )
    if len(symbols) == 1:
        symbol = canonicalize_symbol(symbols[0])
        if len(names) == 1:
            data = compute_feature_set(
                symbol, names[0], timeframe=timeframe, include_provisional=include_provisional
            )
        else:
            data = compute_feature_sets(
                symbol, names, timeframe=timeframe, include_provisional=include_provisional
            )
        degraded = False
    else:
        items, degraded = compute_features_batch(
            symbols, names, timeframe=timeframe, include_provisional=include_provisional
        )
        data = {
            "items": items,
            "count": len(items),
            "ok_count": sum(1 for i in items if i.get("status") == "ok"),
            "error_count": sum(1 for i in items if i.get("status") != "ok"),
        }
    return ok(
        "features",
        data,
        sources=[SourceRef(provider="tdx", role="canonical_daily"), SourceRef(provider="internal", role="features")],
        warnings=warnings,
        degraded=degraded,
    )
