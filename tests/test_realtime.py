from __future__ import annotations

import pytest

from ashare_data.domain.identifiers import parse_symbol_input
from ashare_data.providers.tencent import parse_tencent_quotes
from ashare_data.services.market import summarize_market


def test_normalize_symbols_accepts_common_formats() -> None:
    assert parse_symbol_input(["SH600000", "000001", "bj430047", "600000"]) == [
        "SH600000",
        "SZ000001",
        "BJ430047",
    ]


def test_normalize_symbols_rejects_names_and_invalid_codes() -> None:
    with pytest.raises(Exception, match="Unknown symbol"):
        parse_symbol_input(["风华高科", "123"])


def test_parse_tencent_quote_fields() -> None:
    cells = [""] * 39
    cells[1] = "浦发银行"
    cells[2] = "600000"
    cells[3] = "10.20"
    cells[4] = "10.00"
    cells[5] = "10.05"
    cells[30] = "20260806103000"
    cells[31] = "0.20"
    cells[32] = "2.00"
    cells[33] = "10.30"
    cells[34] = "9.98"
    cells[36] = "1234"
    cells[37] = "5678.9"
    cells[38] = "1.25"

    rows = parse_tencent_quotes('v_sh600000="' + "~".join(cells) + '";')

    assert rows[0]["code"] == "600000"
    assert rows[0]["price"] == 10.2
    assert rows[0]["amount"] == pytest.approx(56_789_000)
    assert rows[0]["source_time"] == "20260806103000"


def test_summarize_market() -> None:
    result = summarize_market(
        [
            {"change_pct": 1.0, "amount": 100},
            {"change_pct": -2.0, "amount": 200},
            {"change_pct": 0.0, "amount": None},
            {"change_pct": None, "amount": 999},
        ]
    )
    assert result == {"total": 3, "up": 1, "down": 1, "flat": 1, "up_ratio": 0.3333, "amount": 300.0}
