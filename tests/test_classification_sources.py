"""Classification-source facts: Eastmoney board codes, THS concepts, Shenwan ladder."""

from __future__ import annotations

import pytest

from aasource.domain.errors import AshareDataError, ErrorCode
from aasource.domain.sectors import canonicalize_em_board_code
from aasource.providers.eastmoney import EastmoneyProviderError
from aasource.providers.sw import _BREADCRUMB_ANCHOR, _cells
from aasource.providers.ths import ThsProviderError, _concept_rows_from_table
from aasource.services import sectors as sectors_service


# --- Eastmoney board code canonicalization (task: memberships join safety) ---


def test_canonicalize_em_board_code_pads_and_passes_through() -> None:
    assert canonicalize_em_board_code("1432") == "BK1432"
    assert canonicalize_em_board_code("167") == "BK0167"
    assert canonicalize_em_board_code("bk172") == "BK172"
    assert canonicalize_em_board_code("BK0172") == "BK0172"
    with pytest.raises(AshareDataError):
        canonicalize_em_board_code("N/A")


# --- THS concept table parser ---


def test_ths_concept_rows_skip_analysis_rows_and_dedupe() -> None:
    table = (
        "<table><tr><th>序号</th><th>概念名称</th></tr>"
        "<tr><td>1</td><td>PCB概念</td><td>龙头股</td></tr>"
        "<tr><td>2025年1月22日互动易：公司子公司……提供PCB业务。</td></tr>"
        "<tr><td>2</td><td>先进封装</td><td>龙头股</td></tr>"
        "<tr><td>3</td><td>PCB概念</td><td>重复</td></tr>"
        "</table>"
    )
    rows = _concept_rows_from_table(table)
    assert rows == ["PCB概念", "先进封装"]


# --- Shenwan breadcrumb / composition parsing ---


def test_sw_stock_breadcrumb_parse() -> None:
    html = (
        '<span class="industry">'
        '<a class="industry-name" href="/stockdata/sw-industry-2021?industryCode=801080.SI" >I电子</a>'
        '<a class="industry-name" href="/stockdata/sw-industry-2021?industryCode=801086.SI" >II电子化学品Ⅱ</a>'
        '<a class="industry-name" href="/stockdata/sw-industry-2021?industryCode=850861.SI" >III电子化学品Ⅲ</a>'
        "</span>"
    )
    ladder: dict[str, dict[str, str] | None] = {"l1": None, "l2": None, "l3": None}
    for code, roman, name in _BREADCRUMB_ANCHOR.findall(html):
        ladder[f"l{len(roman)}"] = {"industry_code": code, "name": name.strip()}
    assert ladder["l1"] == {"industry_code": "801080.SI", "name": "电子"}
    assert ladder["l2"]["industry_code"] == "801086.SI"
    assert ladder["l3"]["name"] == "电子化学品Ⅲ"


def test_sw_composition_row_cells() -> None:
    row = "<tr><td>1</td><td>000019.SZ</td><td>深粮控股</td><td>2021-07-30</td><td>农林牧渔</td></tr>"
    cells = _cells(row)
    assert cells[1] == "000019.SZ" and cells[4] == "农林牧渔"


# --- Service merge: memberships across em/ths/sw ---


class _FakeEm:
    def __call__(self, symbol: str) -> dict:
        if symbol == "SH600000":
            raise EastmoneyProviderError("em down")
        return {
            "symbol": symbol,
            "memberships": [
                {"name": "银行", "relation_type": "industry", "source": "em", "source_id": "BK0475", "rank": 1, "precise": False}
            ],
        }


def _fake_ths(symbol: str) -> dict:
    return {
        "symbol": symbol,
        "concepts": [{"name": "跨境支付", "relation_type": "concept", "source": "ths"}],
        "company_themes": [{"name": "参股银行", "relation_type": "company_theme", "source": "ths"}],
    }


def _fake_sw(symbol: str) -> dict:
    return {
        "symbol": symbol,
        "sw_industry": {"l1": {"industry_code": "801780.SI", "name": "银行"}, "l2": None, "l3": None},
        "source": "sw",
        "classification": "SW2021",
    }


def test_memberships_merge_sources_and_partial_failures(monkeypatch) -> None:
    monkeypatch.setattr(sectors_service, "fetch_stock_memberships", _FakeEm())
    monkeypatch.setattr(sectors_service, "fetch_ths_stock_concepts", _fake_ths)
    monkeypatch.setattr(sectors_service, "fetch_sw_stock_industry", _fake_sw)

    data, sources, warnings, degraded = sectors_service.stock_memberships(["600000", "SH600036"])

    assert degraded is True  # SH600000 failed at the em source
    by_symbol = {item["symbol"]: item for item in data["items"]}
    sh = by_symbol["SH600036"]
    assert [m["source"] for m in sh["memberships"]] == ["em", "ths", "ths"]
    assert sh["sw_industry"]["l1"]["name"] == "银行"
    failed = by_symbol["SH600000"]
    assert [m["source"] for m in failed["memberships"]] == ["ths", "ths"]
    assert failed["sw_industry"]["l1"]["name"] == "银行"
    codes = {w.code for w in warnings}
    assert "STOCK_MEMBERSHIP_PARTIAL" in codes and "THS_MEMBERSHIP_PARTIAL" not in codes
    assert {s.provider for s in sources} >= {"eastmoney", "ths", "legulegu"}


def test_memberships_source_filter_em_only(monkeypatch) -> None:
    monkeypatch.setattr(sectors_service, "fetch_stock_memberships", _FakeEm())
    called = {"ths": False, "sw": False}

    def _no_ths(symbol):
        called["ths"] = True
        return _fake_ths(symbol)

    def _no_sw(symbol):
        called["sw"] = True
        return _fake_sw(symbol)

    monkeypatch.setattr(sectors_service, "fetch_ths_stock_concepts", _no_ths)
    monkeypatch.setattr(sectors_service, "fetch_sw_stock_industry", _no_sw)

    data, sources, _warnings, degraded = sectors_service.stock_memberships(["600036"], source="em")
    assert degraded is False
    assert called == {"ths": False, "sw": False}
    assert data["items"][0]["memberships"][0]["source_id"] == "BK0475"
    assert "sw_industry" not in data["items"][0]
    assert [s.provider for s in sources] == ["eastmoney"]


def test_memberships_rejects_unknown_source() -> None:
    with pytest.raises(AshareDataError):
        sectors_service.stock_memberships(["600036"], source="wind")


# --- members routing: SW industry codes vs Eastmoney boards ---


def test_sector_members_routes_sw_code(monkeypatch) -> None:
    def _fake_members(code: str, *, limit: int = 1000):
        assert code == "801086.SI"
        return [{"symbol": "SH688150", "name": "莱特光电", "industry_code": code, "source": "sw"}]

    monkeypatch.setattr(sectors_service, "fetch_sw_industry_members", _fake_members)
    data, sources, warnings, degraded = sectors_service.sector_members("801086.SI")
    assert data["classification"] == "SW2021" and data["count"] == 1
    assert degraded is False and warnings == []
    assert sources[0].provider == "legulegu"


def test_sector_members_rejects_bad_sw_code() -> None:
    with pytest.raises(AshareDataError):
        sectors_service.sector_members("99999999.SI")


# --- list kinds for ths/sw identity rows ---


def test_list_sectors_ths_concept_kind(monkeypatch) -> None:
    monkeypatch.setattr(
        sectors_service,
        "fetch_ths_concept_boards",
        lambda: [
            {"board_code": "309121", "name": "AI PC", "source": "ths", "url": "x"},
            {"board_code": "300843", "name": "5G", "source": "ths", "url": "y"},
        ],
    )
    data, sources, warnings, degraded = sectors_service.list_sectors(kind="ths_concept", limit=10)
    assert degraded is False and warnings == []
    assert [row["name"] for row in data["sectors"]] == ["5G", "AI PC"]  # sorted by name
    assert data["sectors"][0]["board_code"] == "300843"
    assert sources[0].provider == "ths"


def test_list_sectors_sw_kind_and_level(monkeypatch) -> None:
    tree = {
        "levels": {
            "l1": [{"industry_code": "801010.SI", "name": "农林牧渔", "member_count": 104, "level": 1, "source": "sw"}],
            "l2": [{"industry_code": "801016.SI", "name": "种植业", "member_count": 20, "level": 2, "source": "sw"}],
            "l3": [],
        },
        "classification": "SW2021",
    }
    monkeypatch.setattr(sectors_service, "fetch_sw_industry_tree", lambda: tree)
    data, _sources, _warnings, degraded = sectors_service.list_sectors(kind="sw", sw_level=2)
    assert degraded is False
    assert data["level"] == 2 and data["sectors"][0]["name"] == "种植业"


def test_list_sectors_degrades_when_ths_fails(monkeypatch) -> None:
    def _boom():
        raise ThsProviderError("ths blocked")

    monkeypatch.setattr(sectors_service, "fetch_ths_concept_boards", _boom)
    data, _sources, warnings, degraded = sectors_service.list_sectors(kind="ths_concept")
    assert degraded is True and data["count"] == 0
    assert warnings[0].code == "SECTOR_LIST_FAILED"


def test_ths_board_list_reports_missing_optional_dependency(monkeypatch) -> None:
    import sys

    import aasource.providers.ths as ths_provider

    monkeypatch.setitem(sys.modules, "py_mini_racer", None)
    with pytest.raises(AshareDataError) as caught:
        ths_provider.fetch_ths_concept_boards()
    assert caught.value.code == ErrorCode.CAPABILITY_NOT_AVAILABLE
    assert "py_mini_racer" in caught.value.message
