from __future__ import annotations

import datetime
from aasource.domain.enums import CoverageGrade
from aasource.pit.master import get_pit_master


def test_st_point_in_time_transitions() -> None:
    """Historical ST must be determined strictly via is_st(as_of), never is_st(today)."""
    master = get_pit_master()

    # Case 1: 康美药业 (SH600518)
    # 2018: Normal trading (is_st=False)
    # 2021: ST / *ST risk alert (is_st=True)
    # 2025: Destatted back to normal (is_st=False)
    assert master.is_st("SH600518", "2018-05-10") is False
    assert master.is_st("SH600518", "2021-06-01") is True
    assert master.is_st("SH600518", "2023-01-01") is True
    assert master.is_st("SH600518", "2025-01-01") is False

    # PIT Tradability at different times
    assert master.is_tradable_at("SH600518", "2018-05-10") is True
    assert master.is_tradable_at("SH600518", "2021-06-01") is False  # Cannot trade when ST
    assert master.is_tradable_at("SH600518", "2025-01-01") is True   # Can trade when destatted

    # Case 2: 中核钛白 (SZ002145)
    # 2012: Historical ST period
    # 2024: Destatted normal
    assert master.is_st("SZ002145", "2012-05-01") is True
    assert master.is_st("SZ002145", "2024-01-01") is False
    assert master.is_tradable_at("SZ002145", "2012-05-01") is False
    assert master.is_tradable_at("SZ002145", "2024-01-01") is True


def test_delisted_and_unlisted_bounds() -> None:
    """Delisted stocks and pre-IPO stocks must NOT be tradable outside their active periods."""
    master = get_pit_master()

    # SH600001 (邯郸钢铁) listed 1998, delisted 2009-12-29
    assert master.is_listed_at("SH600001", "2005-05-01") is True
    assert master.is_listed_at("SH600001", "2024-01-01") is False
    assert master.is_tradable_at("SH600001", "2024-01-01") is False

    # SZ001201 (东瑞股份) listed 2021-04-28
    assert master.is_listed_at("SZ001201", "2020-01-01") is False
    assert master.is_tradable_at("SZ001201", "2020-01-01") is False
    assert master.is_listed_at("SZ001201", "2022-01-01") is True
    assert master.is_tradable_at("SZ001201", "2022-01-01") is True


def test_unconfirmed_st_status_degradation() -> None:
    """If ST status on as_of is unconfirmed, coverage is degraded and excluded from strict trading."""
    master = get_pit_master()
    # Non-existent or unknown stock
    st_val = master.is_st("SH609999", "2022-01-01")
    assert st_val is None
    assert master.is_tradable_at("SH609999", "2022-01-01") is False
