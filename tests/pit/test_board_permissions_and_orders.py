from __future__ import annotations

import pytest
from aasource.domain.identifiers import (
    check_execution_permission,
    classify_board,
    is_mainboard_executable,
    is_non_executable_board,
)
from aasource.pit.master import get_pit_master


def test_mainboard_executable_whitelist() -> None:
    """Only SH600/601/603/605 and SZ000/001/002/003 are valid main board executables."""
    assert is_mainboard_executable("SH600519") is True
    assert is_mainboard_executable("SH601398") is True
    assert is_mainboard_executable("SH603288") is True
    assert is_mainboard_executable("SH605111") is True
    assert is_mainboard_executable("SZ000001") is True
    assert is_mainboard_executable("SZ000002") is True
    assert is_mainboard_executable("SZ001201") is True
    assert is_mainboard_executable("SZ002475") is True
    assert is_mainboard_executable("SZ003001") is True


def test_forbidden_boards_hard_rejection() -> None:
    """Non-executable boards (STAR, ChiNext, BSE, ETF, Index) must be strictly rejected."""
    forbidden_symbols = [
        # STAR (SH688/SH689)
        "SH688981", "SH688001", "SH688111", "SH689009",
        # ChiNext (SZ300/SZ301)
        "SZ300750", "SZ300059", "SZ301001", "SZ301123",
        # BSE (BJ)
        "BJ830946", "BJ430047", "BJ871981", "BJ920002",
        # ETF & Funds
        "SH510300", "SH510500", "SZ159915", "SZ161725",
        # Index
        "SH000001", "SH000300", "SZ399001", "SZ399006", "SH000688",
    ]

    master = get_pit_master()
    for sym in forbidden_symbols:
        assert is_mainboard_executable(sym) is False
        assert is_non_executable_board(sym) is True

        permitted, reason = check_execution_permission(sym)
        assert permitted is False, f"Symbol {sym} should not be permitted"

        # Hard test: can never produce orders
        valid_order, order_reason = master.validate_order(sym, "2024-01-02")
        assert valid_order is False, f"Symbol {sym} produced valid order unexpectedly"
        assert "FORBIDDEN" in order_reason or "NON_MAINBOARD" in order_reason or "REJECTED" in order_reason


def test_filter_candidates_before_alpha() -> None:
    """Candidate filtering must purge non-executable boards BEFORE Alpha ranking and portfolio building."""
    master = get_pit_master()
    raw_candidates = [
        {"symbol": "SH688981", "alpha_score": 0.99},  # STAR - MUST BE PURGED
        {"symbol": "SH600519", "alpha_score": 0.85},  # Mainboard - KEEP
        {"symbol": "SZ300750", "alpha_score": 0.95},  # ChiNext - MUST BE PURGED
        {"symbol": "SZ000001", "alpha_score": 0.70},  # Mainboard - KEEP
        {"symbol": "BJ830946", "alpha_score": 0.98},  # BSE - MUST BE PURGED
        {"symbol": "SH510300", "alpha_score": 0.90},  # ETF - MUST BE PURGED
    ]

    filtered = master.filter_candidates_before_alpha(raw_candidates, "2024-01-02")
    filtered_symbols = [item["symbol"] for item in filtered]

    assert filtered_symbols == ["SH600519", "SZ000001"]
    assert "SH688981" not in filtered_symbols
    assert "SZ300750" not in filtered_symbols
    assert "BJ830946" not in filtered_symbols
    assert "SH510300" not in filtered_symbols
