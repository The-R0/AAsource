from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from ashare_data.features.registry import FeatureDefinition, register

SHANGHAI = ZoneInfo("Asia/Shanghai")
_SECTOR_FIELDS = {
    "sector_return_rank": "change_pct",
    "sector_amount_rank": "amount",
    "sector_turnover_rank": "turnover_rate",
}


def _frame_return_pct(frame: pd.DataFrame, window: int) -> float | None:
    if len(frame) <= window:
        return None
    last = float(frame["close"].iloc[-1])
    prev = float(frame["close"].iloc[-1 - window])
    if prev == 0:
        return None
    return (last / prev - 1.0) * 100.0


def _relative_return_index(frame: pd.DataFrame, params: dict[str, Any]) -> float | None:
    window = int(params.get("window", 5))
    benchmark = str(params.get("benchmark", "SH000300"))
    stock_ret = _frame_return_pct(frame, window)
    if stock_ret is None:
        return None
    from ashare_data.services.bars import get_bars

    try:
        rows, _sources, _warnings, _degraded, _provenance = get_bars(
            benchmark,
            timeframe="1d",
            limit=max(window + 5, 80),
            adjust="none",
        )
    except Exception:
        return None
    bench = pd.DataFrame(rows)
    bench_ret = _frame_return_pct(bench, window)
    if bench_ret is None:
        return None
    return stock_ret - bench_ret


def _trade_date_frame(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    if "trade_date" in out.columns:
        out["trade_date"] = pd.to_datetime(out["trade_date"]).dt.strftime("%Y-%m-%d")
    elif "ts" in out.columns:
        out["trade_date"] = pd.to_datetime(out["ts"]).dt.strftime("%Y-%m-%d")
    else:
        return pd.DataFrame(columns=["trade_date", "close"])
    return out.dropna(subset=["trade_date", "close"]).drop_duplicates("trade_date", keep="last")


def _aligned_relative_return(
    stock_frame: pd.DataFrame, sector_rows: list[dict[str, Any]], window: int
) -> dict[str, Any] | None:
    stock = _trade_date_frame(stock_frame)[["trade_date", "close"]].rename(columns={"close": "stock_close"})
    sector = _trade_date_frame(pd.DataFrame(sector_rows))[["trade_date", "close"]].rename(
        columns={"close": "sector_close"}
    )
    aligned = stock.merge(sector, on="trade_date", how="inner").sort_values("trade_date")
    if len(aligned) <= window:
        return None
    sample = aligned.iloc[-(window + 1) :]
    stock_base = float(sample["stock_close"].iloc[0])
    sector_base = float(sample["sector_close"].iloc[0])
    if stock_base == 0 or sector_base == 0:
        return None
    stock_return = (float(sample["stock_close"].iloc[-1]) / stock_base - 1.0) * 100.0
    sector_return = (float(sample["sector_close"].iloc[-1]) / sector_base - 1.0) * 100.0
    return {
        "value": round(stock_return - sector_return, 4),
        "stock_return_pct": round(stock_return, 4),
        "sector_return_pct": round(sector_return, 4),
        "period_start": str(sample["trade_date"].iloc[0]),
        "period_end": str(sample["trade_date"].iloc[-1]),
        "aligned_observations": len(sample),
    }


def _rank_fact(rows: list[dict[str, Any]], symbol: str, field: str) -> dict[str, Any] | None:
    observed = [row for row in rows if row.get("symbol") and row.get(field) is not None]
    target = next((row for row in observed if str(row["symbol"]) == symbol), None)
    if target is None:
        return None
    value = float(target[field])
    return {
        "value": value,
        "rank": 1 + sum(float(row[field]) > value for row in observed),
        "observed_members": len(observed),
        "sector_member_count": len(rows),
        "order": "descending",
    }


def build_sector_relative_context(
    symbol: str,
    stock_frame: pd.DataFrame,
    *,
    membership_fetcher=None,
    sector_bars_fetcher=None,
    member_fetcher=None,
    retrieved_at: str | None = None,
) -> dict[str, Any]:
    """Resolve all current industry/concept memberships and fetch each sector once."""
    if membership_fetcher is None:
        from ashare_data.services.sectors import stock_memberships

        def membership_fetcher(target: str):
            data, _sources, _warnings, _degraded = stock_memberships([target])
            items = data.get("items") or []
            return items[0] if items else {"symbol": target, "memberships": []}
    if sector_bars_fetcher is None:
        from ashare_data.services.bars import get_bars

        sector_bars_fetcher = get_bars
    if member_fetcher is None:
        from ashare_data.services.sectors import sector_members

        def member_fetcher(sector_id: str, *, limit: int):
            data, _sources, _warnings, _degraded = sector_members(sector_id, limit=limit)
            return list(data.get("members") or [])
    retrieved_at = retrieved_at or datetime.now(SHANGHAI).isoformat(timespec="seconds")
    try:
        payload = membership_fetcher(symbol)
    except Exception as exc:  # noqa: BLE001
        return {"status": "unavailable", "reason": f"sector_membership_failed:{exc}", "items": []}
    memberships = []
    seen: set[str] = set()
    for item in payload.get("memberships") or []:
        sector_id = str(item.get("source_id") or "").upper()
        if sector_id.isdigit():
            sector_id = f"BK{int(sector_id):04d}"
        if item.get("relation_type") not in {"industry", "concept"} or not sector_id or sector_id in seen:
            continue
        seen.add(sector_id)
        memberships.append(
            {
                "sector_id": sector_id,
                "sector_name": item.get("name"),
                "relation_type": item.get("relation_type"),
                "membership_rank": item.get("rank"),
                "membership_precise": bool(item.get("precise")),
            }
        )
    if not memberships:
        return {"status": "unavailable", "reason": "no_current_industry_or_concept_membership", "items": []}

    def fetch(item: dict[str, Any]) -> dict[str, Any]:
        local_errors: dict[str, str] = {}
        try:
            members = member_fetcher(item["sector_id"], limit=500)
        except Exception as exc:  # noqa: BLE001
            members = []
            local_errors["members"] = str(exc)
        try:
            bars, _sources, _warnings, _degraded, _provenance = sector_bars_fetcher(
                item["sector_id"], timeframe="1d", limit=80, adjust="none"
            )
            bars = [row for row in bars if row.get("status", "final") == "final"]
        except Exception as exc:  # noqa: BLE001
            bars = []
            local_errors["bars"] = str(exc)
        return {"membership": item, "bars": bars, "members": members, "errors": local_errors}

    sector_data: dict[str, dict[str, Any]] = {}
    errors: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=min(4, len(memberships))) as pool:
        futures = {pool.submit(fetch, item): item for item in memberships}
        for future in as_completed(futures):
            item = futures[future]
            try:
                result = future.result()
                sector_data[item["sector_id"]] = result
                for kind, message in result["errors"].items():
                    errors[f"{item['sector_id']}:{kind}"] = message
            except Exception as exc:  # noqa: BLE001
                errors[item["sector_id"]] = str(exc)
    return {
        "status": "ok" if sector_data else "unavailable",
        "reason": None if sector_data else "sector_data_unavailable",
        "symbol": symbol,
        "retrieved_at": retrieved_at,
        "membership_temporal_scope": "current_snapshot",
        "historical_membership_asserted": False,
        "requested_memberships": len(memberships),
        "sector_data": sector_data,
        "errors": errors,
    }


def _base_item(context: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    membership = data["membership"]
    return {
        **membership,
        "membership_as_of": context.get("retrieved_at"),
        "membership_temporal_scope": "current_snapshot",
        "historical_membership_asserted": False,
    }


def _sector_relative_return(frame: pd.DataFrame, params: dict[str, Any]) -> dict[str, Any]:
    context = frame.attrs.get("sector_relative_context") or {}
    window = int(params.get("window", 5))
    items = []
    for data in context.get("sector_data", {}).values():
        fact = _aligned_relative_return(frame, data["bars"], window)
        if fact is not None:
            items.append({**_base_item(context, data), **fact})
    return {
        "items": items,
        "count": len(items),
        "requested_memberships": context.get("requested_memberships", 0),
        "temporal_basis": "aligned_final_daily_bars",
        "sources": ["tdx_stock_daily", "eastmoney_sector_daily", "eastmoney_current_membership"],
        "errors": context.get("errors", {}),
    }


def _sector_rank(frame: pd.DataFrame, params: dict[str, Any]) -> dict[str, Any]:
    context = frame.attrs.get("sector_relative_context") or {}
    feature_id = str(params.get("feature_id"))
    field = _SECTOR_FIELDS[feature_id]
    items = []
    for data in context.get("sector_data", {}).values():
        fact = _rank_fact(data["members"], str(context.get("symbol")), field)
        if fact is not None:
            items.append({**_base_item(context, data), **fact})
    return {
        "items": items,
        "count": len(items),
        "requested_memberships": context.get("requested_memberships", 0),
        "temporal_basis": "current_member_cross_section",
        "sources": ["eastmoney_current_membership", "eastmoney_current_sector_members"],
        "field": field,
        "errors": context.get("errors", {}),
    }


def _rank_compute(feature_id: str):
    return lambda frame, params: _sector_rank(frame, {**params, "feature_id": feature_id})


def register_relative_features() -> None:
    register(
        FeatureDefinition(
            "relative_return_index",
            1,
            ("close",),
            ("window", "benchmark"),
            _relative_return_index,
        )
    )
    register(FeatureDefinition("relative_return_sector", 2, ("close",), ("window",), _sector_relative_return))
    register(FeatureDefinition("sector_return_rank", 2, (), (), _rank_compute("sector_return_rank")))
    register(FeatureDefinition("sector_amount_rank", 2, (), (), _rank_compute("sector_amount_rank")))
    register(FeatureDefinition("sector_turnover_rank", 2, (), (), _rank_compute("sector_turnover_rank")))
