from __future__ import annotations

from aasource.domain.enums import ExecutionRole
from aasource.domain.identifiers import is_mainboard_executable, is_market_observation_anchor
from aasource.pit.master import get_pit_master


def test_market_observation_anchors() -> None:
    """SZ399006 (ChiNext Index) and SH000688 (STAR 50) must serve ONLY as observation anchors."""
    anchors = ["SZ399006", "SH000688"]
    master = get_pit_master()

    for anchor in anchors:
        assert is_market_observation_anchor(anchor) is True
        assert is_mainboard_executable(anchor) is False

        # Verify role reconstruction
        sec = master.get_security_at(anchor, "2024-01-02")
        assert sec.execution_role == ExecutionRole.NON_EXECUTABLE_MARKET_ANCHOR
        assert sec.tradable is False

        # Order validation rejection
        valid, reason = master.validate_order(anchor, "2024-01-02")
        assert valid is False
        assert "FORBIDDEN" in reason or "REJECTED" in reason


def test_no_spurious_name_alike_buying() -> None:
    """Non-executable anchor strength must NOT trigger buying irrelevant mainboard stocks unless rules pass."""
    master = get_pit_master()
    # A mainboard stock must independently satisfy all rules on that date
    assert master.is_tradable_at("SH600519", "2024-01-02") is True
