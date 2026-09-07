from __future__ import annotations

from aasource.agent_cli.main import build_parser, dispatch
from aasource.providers import eastmoney_boards
from aasource.services import sectors


def test_provider_normalizes_reverse_membership(monkeypatch) -> None:
    monkeypatch.setattr(
        eastmoney_boards,
        "_get_json",
        lambda *_args, **_kwargs: {
            "ssbk": [
                {"BOARD_CODE": "438", "BOARD_NAME": "食品饮料", "BOARD_RANK": 1, "IS_PRECISE": "0"},
                {"BOARD_CODE": "896", "BOARD_NAME": "白酒", "BOARD_RANK": 8, "IS_PRECISE": "1"},
                {"BOARD_CODE": "173", "BOARD_NAME": "贵州板块", "BOARD_RANK": 4, "IS_PRECISE": "0"},
            ]
        },
    )

    result = eastmoney_boards.fetch_stock_memberships("600519")

    assert result["symbol"] == "SH600519"
    assert [item["relation_type"] for item in result["memberships"]] == ["industry", "concept", "region"]
    assert [item["source_id"] for item in result["memberships"]] == ["BK0438", "BK0896", "BK0173"]
    assert all(item["source"] == "em" for item in result["memberships"])
    assert not any("BOARD_" in key for item in result["memberships"] for key in item)


def test_service_preserves_partial_failure(monkeypatch) -> None:
    def fake(symbol: str):
        if symbol == "SZ000001":
            raise OSError("upstream unavailable")
        return {"symbol": symbol, "memberships": []}

    monkeypatch.setattr(sectors, "fetch_stock_memberships", fake)
    data, _sources, warnings, degraded = sectors.stock_memberships(["600519", "000001"], source="em")

    assert degraded is True
    assert data["requested"] == 2
    assert data["count"] == 2  # failed symbols stay item-level with empty memberships
    assert list(data["errors"]) == ["em:SZ000001"]
    assert warnings[0].code == "STOCK_MEMBERSHIP_PARTIAL"
    failed_item = next(item for item in data["items"] if item["symbol"] == "SZ000001")
    assert failed_item["memberships"] == []


def test_cli_exposes_memberships(monkeypatch) -> None:
    monkeypatch.setattr(
        sectors,
        "stock_memberships",
        lambda symbols, **_kwargs: ({"items": [{"symbol": symbols[0]}]}, [], [], False),
    )
    args = build_parser().parse_args(["sectors", "memberships", "600519"])
    payload, code = dispatch(args)

    assert code == 0
    assert payload["command"] == "sectors.memberships"
    assert payload["data"]["items"][0]["symbol"] == "600519"
