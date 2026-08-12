from __future__ import annotations

from ashare_data.agent_cli.main import build_parser, dispatch
from ashare_data.providers import eastmoney_boards
from ashare_data.services import sectors


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
    assert not any("BOARD_" in key for item in result["memberships"] for key in item)


def test_service_preserves_partial_failure(monkeypatch) -> None:
    def fake(symbol: str):
        if symbol == "SZ000001":
            raise OSError("upstream unavailable")
        return {"symbol": symbol, "memberships": []}

    monkeypatch.setattr(sectors, "fetch_stock_memberships", fake)
    data, _sources, warnings, degraded = sectors.stock_memberships(["600519", "000001"])

    assert degraded is True
    assert data["requested"] == 2
    assert data["count"] == 1
    assert list(data["errors"]) == ["SZ000001"]
    assert warnings[0].code == "STOCK_MEMBERSHIP_PARTIAL"


def test_cli_exposes_memberships(monkeypatch) -> None:
    monkeypatch.setattr(
        sectors,
        "stock_memberships",
        lambda symbols: ({"items": [{"symbol": symbols[0]}]}, [], [], False),
    )
    args = build_parser().parse_args(["sectors", "memberships", "600519"])
    payload, code = dispatch(args)

    assert code == 0
    assert payload["command"] == "sectors.memberships"
    assert payload["data"]["items"][0]["symbol"] == "600519"
