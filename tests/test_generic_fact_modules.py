from __future__ import annotations

import pytest

from aasource.agent_cli.main import build_parser, dispatch
from aasource.domain.errors import AshareDataError, ErrorCode
from aasource.services.relative_intraday import (
    align_relative_points,
    compute_relative_intraday,
    get_relative_intraday,
    previous_close_for_session,
)
from aasource.services.scan import apply_filters, distance_20d_high, enrich_scan_row, parse_filters
from aasource.services.sector_context import member_fact_pools, relative_windows, return_distribution, window_returns


def _bar(minute: str, close: float) -> dict:
    return {"ts": f"2026-08-21T{minute}:00+08:00", "close": close}


def test_relative_intraday_compresses_alignment_without_decision() -> None:
    stock = [_bar("09:30", 100), _bar("09:47", 99), _bar("10:16", 99.9), _bar("10:48", 100.2)]
    sector = [_bar("09:30", 100), _bar("09:47", 99), _bar("10:16", 99.3), _bar("10:48", 100.4)]

    points = align_relative_points(stock, sector, 100, 100)
    facts = compute_relative_intraday(
        stock, sector, stock_previous_close=100, sector_previous_close=100
    )

    assert points[-1]["relative_return_pct"] == -0.2
    assert facts["status"] == "available"
    assert facts["sync"]["low"] is True
    assert "buy" not in facts and "sell" not in facts


def test_previous_close_is_point_in_time() -> None:
    bars = [
        {"trade_date": "2026-08-20", "close": 10.0, "previous_close": 9.8},
        {"trade_date": "2026-08-21", "close": 10.5, "previous_close": 10.0},
    ]
    assert previous_close_for_session(bars, "2026-08-21") == 10.0
    assert previous_close_for_session(bars[:1], "2026-08-21") == 10.0


def test_dated_relative_request_rejects_implicit_current_membership() -> None:
    with pytest.raises(AshareDataError) as caught:
        get_relative_intraday("SH600036", trade_date="2023-05-10")
    assert caught.value.code == ErrorCode.CAPABILITY_NOT_AVAILABLE


def test_scan_filters_and_bar_enrichment_are_generic() -> None:
    row = enrich_scan_row(
        {
            "symbol": "SH600036",
            "industry": "银行",
            "amount": 2e9,
            "change_pct": 3.0,
            "sector_divergence_pct": 1.0,
            "open": 10.2,
            "previous_close": 10.0,
            "limit_activity": {"previous_limit_up": True},
        },
        {"银行": (2, 0.1)},
    )
    filters = parse_filters('[{"field":"amount","op":">","value":1000000000}]')
    matched, skipped, bar_filters = apply_filters([row], filters)

    assert matched[0]["board"] == "SH_MAIN"
    assert matched[0]["previous_limit_up"] is True
    assert skipped == [] and bar_filters == []
    assert distance_20d_high([{"high": 10}, {"high": 12, "close": 11.4}]) == -0.05


def test_sector_context_helpers_are_facts_not_roles() -> None:
    windows = window_returns([{"close": 100}, {"close": 101}, {"close": 102}, {"close": 108}], (1, 3))
    assert windows["1d"]["change_pct"] == 5.8824
    assert relative_windows(windows, {"1d": {"change_pct": 1.0}})["1d"] == 4.8824
    assert return_distribution([3, 1, -1, 0])["median"] == 0.5

    pools = member_fact_pools(
        [
            {"symbol": "SZ300308", "change_pct": 4.0, "amount": 9e9, "last": 100, "high": 100},
            {"symbol": "SZ300502", "change_pct": -1.5, "amount": 2e9, "last": 80, "high": 85},
        ],
        1.0,
    )
    assert pools["amount_front"][0]["symbol"] == "SZ300308"
    assert "leader" not in pools


def test_cli_exposes_new_fact_commands(monkeypatch) -> None:
    from aasource.agent_cli.commands import relative_intraday, scan, sector_context

    monkeypatch.setattr(scan, "scan_stocks", lambda **_: ({"rows": []}, [], [], False))
    monkeypatch.setattr(
        relative_intraday,
        "get_relative_intraday",
        lambda *_args, **_kwargs: ({"status": "available"}, [], [], False),
    )
    monkeypatch.setattr(
        sector_context,
        "get_sector_context",
        lambda *_args, **_kwargs: ({"sector_id": "BK1128"}, [], [], False),
    )

    scan_payload, _ = dispatch(build_parser().parse_args(["scan-stocks", "--limit", "5"]))
    relative_payload, _ = dispatch(
        build_parser().parse_args(["relative-intraday", "SH600036", "--sector", "BK1128"])
    )
    sector_payload, _ = dispatch(build_parser().parse_args(["sector-context", "BK1128"]))

    assert scan_payload["command"] == "scan-stocks"
    assert relative_payload["command"] == "relative-intraday"
    assert sector_payload["command"] == "sector-context"
