from __future__ import annotations

from typing import Any

from aasource.settings import load_yaml_resource


def get_catalog() -> dict[str, Any]:
    feature_sets = load_yaml_resource("feature_sets.yaml")
    sources = load_yaml_resource("sources.yaml")
    set_meta = {
        name: {
            "version": spec.get("version"),
            "availability": spec.get("availability", "available"),
            "includes": spec.get("includes"),
            "note": spec.get("note"),
        }
        for name, spec in feature_sets.items()
        if name != "schema_version"
    }
    set_names = list(set_meta.keys())
    query_commands = [
        "catalog",
        "health",
        "securities",
        "quotes",
        "auction",
        "bars",
        "bars-batch",
        "limit-history",
        "trades",
        "features",
        "market",
        "sectors",
        "reference",
        "scan-stocks",
        "relative-intraday",
        "sector-context",
    ]
    return {
        "contract_version": "1.0",
        "domain_version": 2,
        "query_capabilities": query_commands,
        "commands": query_commands,
        "feature_sets": set_names,
        "feature_set_meta": set_meta,
        "canonical_providers": sources.get("canonical", {}),
        "reference_providers": sources.get("reference", {}),
        "schema_version": "1.0",
        "capabilities": {
            "bars": {
                "security_types": ["stock", "index", "sector"],
                "timeframes": ["1m", "5m", "15m", "30m", "60m", "1d"],
                "adjust_modes": ["none"],
                "batch": True,
                "batch_command": "bars-batch",
                "note": "Daily/intraday security bars are relayed from TDX; sector boards via BK#### use Eastmoney.",
            },
            "trades": {
                "provider": "tdx",
                "batch": False,
                "note": "History ticks for one trade_date",
            },
            "quotes": {"batch": True, "item_status": True},
            "auction": {
                "provider": "tencent",
                "batch": True,
                "item_status": True,
                "scope": "opening_call_auction_current_snapshot",
                "window": "09:15:00-09:25:00 Asia/Shanghai",
                "history": False,
            },
            "securities": {"batch": True, "item_status": True, "temporal_scope": "current"},
            "features": {
                "timeframes": ["1d", "1m"],
                "sets": set_names,
                "multi_set": True,
                "batch": True,
                "include_provisional": False,
                "item_status": True,
                "return_unit": "percent_points",
            },
            "market": {
                "subcommands": ["snapshot", "cross-section", "stock-signals", "movers", "breadth", "limits"],
                "snapshot": "cheap compact overview",
                "cross-section": "canonical full-A quotes for scan/context (hot cache)",
                "stock-signals": "full-A discovery dimensions with explicit basis and coverage",
                "breadth": "dedicated breadth dataset",
                "limits": "limit-up/down/broken pools + sealed/broken/max_streak summary",
                "movers": "cross-sectional ranking",
            },
            "sectors": {
                "implemented": True,
                "subcommands": ["list", "rankings", "members", "memberships", "search", "resolve", "minute"],
                "providers": {
                    "eastmoney": "quote-bearing industry/concept boards (BK####) and reverse board membership",
                    "ths": "THS concept board list and per-stock concepts/company themes (list --kind ths_concept; needs optional py_mini_racer for the board list)",
                    "legulegu": "Shenwan 2021 formal industry ladder (list --kind sw, members 801xxx.SI, memberships sw_industry)",
                },
                "membership_sources": ["all", "em", "ths", "sw"],
                "industry_classification": {
                    "market_facing": "eastmoney BK boards",
                    "formal": "shenwan_2021 (l1/l2/l3)",
                },
                "reverse_membership": "batch stock-to-sector current snapshot, merged across sources with per-item partial failures",
                "bars": "use bars <BK####> --tf 1d|1m — not sectors bars",
            },
            "reference": {
                "data_class": "reference",
                "schema_version": "1.0",
                "canonical": True,
                "provider": "eastmoney",
            },
            "limit_history": {
                "scope": "single_stock",
                "states": ["sealed_limit_up", "broken_limit_up"],
                "streak": True,
                "method": "canonical_daily_price_limit_match",
                "historical_st_status": "unavailable",
            },
            "point_in_time": {
                "security_master": "current",
                "sector_membership": "current_snapshot",
                "auction_history": False,
                "historical_st_status": "unavailable",
                "corporate_actions_adjust": "unsupported",
                "note": (
                    "Do not replay a past session with today's ST flag, listing status, "
                    "limit rule, membership, or unadjusted-as-adjusted prices."
                ),
            },
            "scan_stocks": {
                "temporal_scope": "current_session",
                "generic_query": True,
                "historical_replay": False,
                "note": "Generic filters and ranking; not a strategy, score, or recommendation.",
            },
            "relative_intraday": {
                "timeframe": "1m",
                "historical_explicit_sector": True,
                "historical_implicit_membership": False,
                "facts": ["relative_return", "delta_relative_return", "extrema_sync", "lead_lag", "divergence"],
            },
            "sector_context": {
                "temporal_scope": "current_session",
                "historical_replay": False,
                "judgment_free": True,
            },
        },
        "units": {
            "price": "CNY_per_share",
            "volume": "shares",
            "amount": "CNY",
            "change_pct": "percent_points",
            "turnover_rate": "percent_points",
            "feature_return": "percent_points",
        },
    }
