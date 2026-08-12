from __future__ import annotations

import json

import pandas as pd
import pytest

from ashare_data.agent_cli.main import build_parser, main
from ashare_data.domain.errors import AshareDataError, ErrorCode
from ashare_data.normalize.bars import bars_from_daily_frame
from ashare_data.services import bars as bars_service
from ashare_data.services import market as market_service
from ashare_data.services import reference as reference_service
from ashare_data.services._reference_eastmoney import _EastmoneyReferenceSource


def test_canonical_daily_volume_is_already_shares() -> None:
    frame = pd.DataFrame(
        [
            {
                "trade_date": pd.Timestamp("2026-08-07"),
                "open": 7.5,
                "high": 7.7,
                "low": 7.4,
                "close": 7.58,
                "volume": 9_747_980,
                "amount": 73_883_128,
            }
        ]
    )
    bar = bars_from_daily_frame(frame, symbol="SH600004")[0]
    assert bar.volume == 9_747_980


def test_reference_block_trades_uses_valid_default_and_empty_list(monkeypatch) -> None:
    class FakeProvider:
        def block_trades(self, start_date, end_date, category, symbol, limit):
            assert category == "A股"
            return {"status": "OK", "records": []}

    monkeypatch.setattr(reference_service, "_get_reference_source", lambda: FakeProvider())
    data, _sources, warnings, degraded = reference_service.block_trades(
        start_date="20260801", end_date="20260808"
    )
    assert data["dataset"] == "block_trades"
    assert data["records"] == []
    assert data["record_count"] == 0
    assert data["units"]["volume"] == "shares"
    assert warnings == []
    assert degraded is False


def test_bars_batch_deduplicates_provider_work_and_returns_canonical_symbol(monkeypatch) -> None:
    calls: list[str] = []

    def fake_get_bars(symbol, **_kwargs):
        calls.append(symbol)
        return [], [], [], False, {"provider": "fake"}

    monkeypatch.setattr(bars_service, "get_bars", fake_get_bars)
    payload, _sources, _warnings, degraded, _provenance = bars_service.get_bars_batch(
        ["600000", "SH600000"]
    )
    assert calls == ["SH600000"]
    assert [item["symbol"] for item in payload["items"]] == ["SH600000", "SH600000"]
    assert degraded is False


def test_cli_parse_error_is_json(capsys) -> None:
    code = main(["bars"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert code == 2
    assert payload["status"] == "error"
    assert payload["error"]["code"] == "INVALID_REQUEST"


def test_local_release_admin_is_not_exposed_by_cli() -> None:
    parser = build_parser()
    with pytest.raises(AshareDataError) as exc_info:
        parser.parse_args(["admin", "backfill", "--symbols", "symbols.csv", "--version", "release-v1"])
    assert exc_info.value.code == ErrorCode.INVALID_REQUEST


def test_runtime_snapshot_never_exposes_vendor_quote_rows(monkeypatch) -> None:
    class FakeTdx:
        def fetch_security_master(self):
            return {
                "status": "PASS",
                "source": "fake",
                "scope": "test",
                "count": 1,
                "symbols": [{"exchange": "SH", "code": "600000"}],
            }

    class FakeTencent:
        def fetch_quote_rows(self, symbols):
            assert symbols == ["SH600000"]
            return [
                {
                    "code": "600000",
                    "name": "浦发银行",
                    "price": 10.2,
                    "previous_close": 10.0,
                    "open": 10.05,
                    "high": 10.3,
                    "low": 9.98,
                    "change": 0.2,
                    "change_pct": 2.0,
                    "volume_lots": 1234,
                    "amount": 56_789_000,
                    "turnover_rate": 1.25,
                    "source_time": "20260806103000",
                }
            ]

    monkeypatch.setattr(market_service, "get_tdx_provider", lambda: FakeTdx())
    monkeypatch.setattr(market_service, "get_tencent_provider", lambda: FakeTencent())
    market_service.reset_runtime_snapshot()
    data, _sources, _warnings, degraded = market_service.market_cross_section()
    quote = data["quotes"][0]
    assert degraded is False
    assert quote["symbol"] == "SH600000"
    assert quote["volume"] == 123_400
    assert quote["source_time"] == "2026-08-06T10:30:00+08:00"
    assert "volume_lots" not in quote
    assert "raw" not in quote
    market_service.reset_runtime_snapshot()


def test_reference_block_trade_maps_fields_and_units(monkeypatch) -> None:
    class FakeProvider:
        def block_trades(self, *_args):
            return {
                "status": "OK",
                "source": {
                    "provider": "eastmoney",
                    "adapter_version": "test",
                    "endpoint": "https://example.test/reference",
                    "fetched_at": "2026-08-09T10:00:00+08:00",
                    "cache": {"hit": True},
                },
                "records": [
                    {
                        "symbol": "SZ000725",
                        "name": "京东方A",
                        "trade_date": "2024-04-03",
                        "trade_price": 4.34,
                        "volume": 460900,
                        "amount": 2000300,
                        "amount_to_float_market_cap_pct": 0.125,
                    }
                ],
            }

    monkeypatch.setattr(reference_service, "_get_reference_source", lambda: FakeProvider())
    data, _sources, warnings, degraded = reference_service.block_trades(
        start_date="20240403", end_date="20240403"
    )
    record = data["records"][0]
    assert degraded is False
    assert warnings == []
    assert record["symbol"] == "SZ000725"
    assert record["volume"] == 460_900
    assert record["amount_to_float_market_cap_pct"] == 0.125
    assert not any(any("\u4e00" <= char <= "\u9fff" for char in key) for key in record)
    assert data["provenance"]["cache_hit"] is True


def test_all_reference_datasets_use_canonical_record_keys(monkeypatch) -> None:
    class FakeProvider:
        @staticmethod
        def _payload(record):
            return {"status": "OK", "source": {"provider": "eastmoney", "adapter_version": "test"}, "records": [record]}

        def dragon_tiger_list(self, *_args):
            return self._payload({"symbol": "SH600000", "trade_date": "2024-04-03", "net_buy_amount": 100})

        def dragon_tiger_seats(self, *_args):
            return self._payload({"symbol": "SH600000", "side": "buy", "seat_name": "机构专用", "buy_share_pct": 4.6})

        def institutional_dragon_tiger(self, *_args):
            return self._payload({"symbol": "SH600000", "trade_date": "2024-04-03", "institution_net_amount": 100})

        def money_flow(self, *_args):
            return self._payload({"symbol": "SH600000", "trade_date": "2024-04-03", "main_net_amount": 100, "main_net_pct": 1.5})

        def top_float_shareholders(self, *_args):
            return self._payload({"symbol": "SH600000", "shareholder_name": "示例股东", "held_shares": 1000, "holding_pct": 2.5})

        def fund_holdings(self, *_args):
            return self._payload({"symbol": "SH600000", "name": "浦发银行", "held_shares": 15000})

    monkeypatch.setattr(reference_service, "_get_reference_source", lambda: FakeProvider())
    results = [
        reference_service.dragon_tiger(trade_date="20240403")[0],
        reference_service.dragon_tiger_seats("SH600000", "20240403")[0],
        reference_service.institutional_dragon_tiger("20240403", "20240403")[0],
        reference_service.money_flow("SH600000")[0],
        reference_service.shareholders("SH600000", "20240331")[0],
        reference_service.fund_holdings("20240331")[0],
    ]
    for data in results:
        record = data["records"][0]
        assert not any(any("\u4e00" <= char <= "\u9fff" for char in key) for key in record)
    assert results[1]["records"][0]["buy_share_pct"] == 4.6
    assert results[4]["records"][0]["symbol"] == "SH600000"
    assert results[5]["records"][0]["held_shares"] == 15_000


class _JsonResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def test_reference_adapter_cache_is_process_local() -> None:
    calls = 0

    def fake_get(_url, **_kwargs):
        nonlocal calls
        calls += 1
        return _JsonResponse({"result": {"data": []}})

    provider = _EastmoneyReferenceSource(fake_get)
    first = provider._fetch("sample", "https://example.test", {}, ttl_seconds=60)
    second = provider._fetch("sample", "https://example.test", {}, ttl_seconds=60)

    assert calls == 1
    assert first["cache"]["hit"] is False
    assert second["cache"]["hit"] is True
    assert provider.status()["cache_scope"] == "process"


def test_reference_adapter_maps_shareholder_response_without_vendor_keys() -> None:
    def fake_get(_url, **_kwargs):
        return _JsonResponse({"sdltgd": [{"HOLDER_RANK": 1, "HOLDER_NAME": "示例股东", "SHARES_TYPE": "流通A股", "HOLD_NUM": 1000, "FREE_HOLDNUM_RATIO": 2.5}]})

    provider = _EastmoneyReferenceSource(fake_get)
    result = provider.top_float_shareholders("SH600000", "20240331")
    record = result["records"][0]
    assert record["symbol"] == "SH600000"
    assert record["shareholder_name"] == "示例股东"
    assert record["holding_pct"] == 2.5
    assert not any("HOLDER_" in key for key in record)


def test_reference_adapter_maps_fund_holding_units() -> None:
    def fake_get(_url, **_kwargs):
        return _JsonResponse({"pages": 1, "data": [{"SECUCODE": "600000", "SECURITY_NAME_ABBR": "浦发银行", "HOULD_NUM": 15, "TOTAL_SHARES": 15000, "HOLD_VALUE": 250000, "HOLDCHA_NUM": 100, "HOLDCHA_RATIO": 1.2}]})

    provider = _EastmoneyReferenceSource(fake_get)
    result = provider.fund_holdings("20240331")
    record = result["records"][0]
    assert record["symbol"] == "SH600000"
    assert record["fund_count"] == 15
    assert record["held_shares"] == 15000
    assert record["market_value"] == 250000
    assert record["change_pct"] == 1.2


def test_reference_adapter_converts_institution_market_cap_from_yi() -> None:
    def fake_get(_url, **_kwargs):
        return _JsonResponse({"result": {"pages": 1, "data": [{"SECURITY_CODE": "600595", "BUY_TIMES": 2, "SELL_TIMES": 1, "FREECAP": 156.2, "RATIO": 3.5}]}})

    provider = _EastmoneyReferenceSource(fake_get)
    result = provider.institutional_dragon_tiger("20240403", "20240403")
    record = result["records"][0]
    assert record["symbol"] == "SH600595"
    assert record["buyer_institution_count"] == 2
    assert record["float_market_cap"] == 15_620_000_000
    assert record["institution_net_to_market_pct"] == 3.5
