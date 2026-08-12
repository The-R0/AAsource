from __future__ import annotations

from ashare_data.domain.errors import AshareDataError, ErrorCode
from ashare_data.domain.identifiers import canonicalize_symbol, parse_symbol_input
from ashare_data.domain.schemas import BAR_REQUIRED, ENVELOPE_REQUIRED, QUOTE_REQUIRED, assert_keys
from ashare_data.agent_cli.envelope import fail, ok
from ashare_data.domain.models import SourceRef


def test_canonicalize_symbol_variants():
    assert canonicalize_symbol("600519") == "SH600519"
    assert canonicalize_symbol("sh600519") == "SH600519"
    assert canonicalize_symbol("SH600519") == "SH600519"
    assert canonicalize_symbol("000001") == "SZ000001"
    assert canonicalize_symbol("SZ000001") == "SZ000001"
    assert canonicalize_symbol("SH000300") == "SH000300"


def test_parse_symbol_input_unique_order():
    assert parse_symbol_input(["600519", "SH600519", "000001"]) == ["SH600519", "SZ000001"]


def test_envelope_ok_contract_keys():
    payload, code = ok("catalog", {"commands": []}, sources=[SourceRef("internal", "catalog")])
    assert code == 0
    assert payload["status"] == "ok"
    assert assert_keys(payload, ENVELOPE_REQUIRED, "envelope") == []


def test_envelope_error_json():
    payload, code = fail("bars", AshareDataError(ErrorCode.SYMBOL_NOT_FOUND, "Unknown symbol"))
    assert code == 2
    assert payload["status"] == "error"
    assert payload["data"] is None
    assert payload["error"]["code"] == "SYMBOL_NOT_FOUND"


def test_quote_and_bar_required_lists_nonempty():
    assert "volume" in QUOTE_REQUIRED
    assert "adjust" in BAR_REQUIRED
