from __future__ import annotations

from ashare_data.providers.tencent import parse_tencent_quotes
from ashare_data.services import auction as auction_service


def _tencent_auction_text(*, source_time: str = "20260812092235") -> str:
    cells = [""] * 39
    cells[1] = "测试股份"
    cells[2] = "600000"
    cells[3] = "10.12"
    cells[4] = "10.00"
    cells[5] = "0"
    cells[9], cells[10] = "10.08", "123"
    cells[11], cells[12] = "10.08", "45"
    cells[19], cells[20] = "10.08", "123"
    cells[21], cells[22] = "10.08", "0"
    cells[30] = source_time
    cells[36] = "0"
    cells[37] = "0"
    return f'v_sh600000="{"~".join(cells)}";'


def test_tencent_parser_preserves_level_one_and_two_book() -> None:
    row = parse_tencent_quotes(_tencent_auction_text())[0]

    assert row["bid_levels"][0] == {"price": 10.08, "volume_lots": 123.0}
    assert row["bid_levels"][1] == {"price": 10.08, "volume_lots": 45.0}
    assert row["ask_levels"][0] == {"price": 10.08, "volume_lots": 123.0}
    assert row["ask_levels"][1] == {"price": 10.08, "volume_lots": 0.0}


def test_auction_snapshot_maps_exchange_auction_book_semantics(monkeypatch) -> None:
    row = parse_tencent_quotes(_tencent_auction_text())[0]

    class FakeTencent:
        def fetch_quotes_raw(self, _symbols):
            return {"status": "OK", "data": {"quotes": [row], "source_time": row["source_time"]}}

    monkeypatch.setattr(auction_service, "get_tencent_provider", lambda: FakeTencent())
    monkeypatch.setattr(
        auction_service,
        "quote_freshness",
        lambda *_args, **_kwargs: {"stale": False, "threshold_seconds": 30, "age_seconds": 0},
    )
    items, _sources, warnings, degraded, freshness = auction_service.get_auction_snapshots(["SH600000"])

    assert degraded is False
    assert warnings == []
    assert freshness["stale"] is False
    snapshot = items[0]["auction"]
    assert snapshot["phase"] == "call_auction"
    assert snapshot["indicative_price"] == 10.08
    assert snapshot["matched_volume"] == 12_300
    assert snapshot["unmatched_buy_volume"] == 4_500
    assert snapshot["unmatched_sell_volume"] == 0
    assert snapshot["unmatched_side"] == "buy"
    assert snapshot["provisional"] is True
    assert snapshot["source"] == "tencent"


def test_auction_snapshot_rejects_non_auction_source_time(monkeypatch) -> None:
    row = parse_tencent_quotes(_tencent_auction_text(source_time="20260812093001"))[0]

    class FakeTencent:
        def fetch_quotes_raw(self, _symbols):
            return {"status": "OK", "data": {"quotes": [row], "source_time": row["source_time"]}}

    monkeypatch.setattr(auction_service, "get_tencent_provider", lambda: FakeTencent())
    items, _sources, _warnings, degraded, _freshness = auction_service.get_auction_snapshots(["SH600000"])

    assert degraded is True
    assert items[0]["status"] == "error"
    assert items[0]["error"]["code"] == "CAPABILITY_NOT_AVAILABLE"
    assert items[0]["auction"] is None
