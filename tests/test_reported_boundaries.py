from __future__ import annotations

from datetime import datetime
from io import StringIO
import os
from pathlib import Path
import subprocess
import sys

import pytest

from ashare_data.features import compute as feature_compute
from ashare_data.agent_cli import main as cli_main
from ashare_data.providers.tencent import parse_tencent_quotes
from ashare_data.services import auction as auction_service
from ashare_data.services import bars as bars_service
from ashare_data.services import quotes as quotes_service
from ashare_data.services import securities as securities_service
from ashare_data.services.limit_history import classify_limit_history


def _tencent_record(
    vendor_symbol: str, name: str, *, price: str = "10.20", source_time: str = "20260814092000"
) -> str:
    cells = [""] * 39
    cells[1] = name
    cells[2] = vendor_symbol[2:]
    cells[3] = price
    cells[4] = "10.00"
    cells[5] = "10.05"
    cells[9:13] = [price, "10", "10.19", "2"]
    cells[19:23] = [price, "10", "10.21", "0"]
    cells[30] = source_time
    cells[31] = "0.20"
    cells[32] = "2.00"
    cells[33] = "10.30"
    cells[34] = "9.98"
    cells[36] = "1234"
    cells[37] = "5678.9"
    cells[38] = "1.25"
    return f'v_{vendor_symbol.lower()}="' + "~".join(cells) + '";'


def test_same_code_quotes_keep_exchange_identity(monkeypatch) -> None:
    rows = parse_tencent_quotes(
        _tencent_record("SH000001", "上证指数", price="8.88")
        + _tencent_record("SZ000001", "平安银行", price="10.20")
    )

    class FakeTencent:
        def fetch_quotes_raw(self, symbols):
            return {"status": "OK", "data": {"quotes": rows, "source_time": "20260814092000"}}

    monkeypatch.setattr(quotes_service, "get_tencent_provider", lambda: FakeTencent())
    items, *_ = quotes_service.get_quotes(["SH000001", "SZ000001"])

    assert [(item["symbol"], item["quote"]["symbol"], item["quote"]["name"]) for item in items] == [
        ("SH000001", "SH000001", "上证指数"),
        ("SZ000001", "SZ000001", "平安银行"),
    ]


def test_same_code_security_master_keeps_exchange_identity(monkeypatch) -> None:
    class FakeTdx:
        def fetch_security_master(self):
            return {
                "symbols": [
                    {"code": "000001", "exchange": "SH", "name": "上证指数"},
                    {"code": "000001", "exchange": "SZ", "name": "平安银行"},
                ]
            }

    monkeypatch.setattr(securities_service, "get_tdx_provider", lambda: FakeTdx())
    items, *_ = securities_service.get_securities(["SH000001", "SZ000001"])

    assert [(item["security"]["symbol"], item["security"]["name"]) for item in items] == [
        ("SH000001", "上证指数"),
        ("SZ000001", "平安银行"),
    ]


def test_same_code_auction_keeps_exchange_identity(monkeypatch) -> None:
    rows = parse_tencent_quotes(
        _tencent_record("SH000001", "上证指数", price="8.88")
        + _tencent_record("SZ000001", "平安银行", price="10.20")
    )

    class FakeTencent:
        def fetch_quotes_raw(self, symbols):
            return {"status": "OK", "data": {"quotes": rows}}

    monkeypatch.setattr(auction_service, "get_tencent_provider", lambda: FakeTencent())
    items, *_ = auction_service.get_auction_snapshots(["SH000001", "SZ000001"])

    assert [(item["auction"]["symbol"], item["auction"]["indicative_price"]) for item in items] == [
        ("SH000001", 8.88),
        ("SZ000001", 10.20),
    ]


class _Morning(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 8, 14, 10, 56, tzinfo=tz)


def test_current_daily_bar_is_provisional_before_close_confirmation(monkeypatch) -> None:
    class FakeTdx:
        def fetch_daily_raw(self, symbol, count):
            return ([{"datetime": "2026-08-14", "open": 10, "high": 11, "low": 9, "close": 10.5, "vol": 1}], [], "fake", False)

    monkeypatch.setattr(bars_service, "datetime", _Morning)
    monkeypatch.setattr(bars_service, "get_tdx_provider", lambda: FakeTdx())
    bars, _sources, warnings, degraded, _provenance = bars_service.get_bars("SH603887", timeframe="1d")

    assert bars[0]["status"] == "provisional"
    assert bars[0]["quality"] == "partial"
    assert degraded is True
    assert [warning.code for warning in warnings] == ["DAILY_BAR_PROVISIONAL"]


def test_old_date_range_fetch_depth_accounts_for_distance_from_today(monkeypatch) -> None:
    requested = []

    class FakeTdx:
        def fetch_daily_raw(self, symbol, count):
            requested.append(count)
            return ([{"datetime": "2024-02-01", "open": 10, "high": 11, "low": 9, "close": 10.5, "vol": 1}], [], "fake", False)

    monkeypatch.setattr(bars_service, "datetime", _Morning)
    monkeypatch.setattr(bars_service, "get_tdx_provider", lambda: FakeTdx())
    bars, *_ = bars_service.get_bars(
        "SH600088", timeframe="1d", start="2024-01-26", end="2024-02-07", limit=120
    )

    assert requested[0] >= 650
    assert [bar["trade_date"] for bar in bars] == ["2024-02-01"]


def test_features_exclude_provisional_by_default_and_report_actual_use(monkeypatch) -> None:
    rows = [
        {"trade_date": "2026-08-12", "close": 10.0, "status": "final"},
        {"trade_date": "2026-08-13", "close": 11.0, "status": "final"},
        {"trade_date": "2026-08-14", "close": 9.0, "status": "provisional"},
    ]
    monkeypatch.setattr(feature_compute, "get_bars", lambda *args, **kwargs: (rows, [], [], False, {}))

    final_only = feature_compute.compute_feature_set("SH603887", "trend_core")
    with_live = feature_compute.compute_feature_set("SH603887", "trend_core", include_provisional=True)
    final_return = next(item for item in final_only["features"] if item["id"] == "return")
    live_return = next(item for item in with_live["features"] if item["id"] == "return")

    assert final_return["observations"] == 2
    assert final_return["uses_provisional"] is False
    assert live_return["observations"] == 3
    assert live_return["uses_provisional"] is True


def test_limit_history_excludes_provisional_event_from_history_stats() -> None:
    bars = [
        {"trade_date": "2026-08-13", "previous_close": 10, "open": 10, "high": 11, "low": 10, "close": 11, "status": "final"},
        {"trade_date": "2026-08-14", "previous_close": 11, "open": 11, "high": 12.1, "low": 11, "close": 11.8, "status": "provisional"},
    ]

    result = classify_limit_history("SZ002437", bars)

    assert result["event_count"] == 1
    assert result["broken_count"] == 0
    assert result["provisional_current_event"]["state"] == "broken_limit_up"


def test_bars_batch_accepts_stdin_symbols(monkeypatch) -> None:
    captured = {}

    def fake_run(symbols, **kwargs):
        captured["symbols"] = symbols
        return {"status": "ok"}, 0

    monkeypatch.setattr(cli_main.bars_batch_cmd, "run_bars_batch", fake_run)
    monkeypatch.setattr(sys, "stdin", StringIO('{"symbols":["SH600036","SZ000001"]}'))
    args = cli_main.build_parser().parse_args(["bars-batch", "--stdin", "--tf", "1d"])

    cli_main.dispatch(args)

    assert captured["symbols"] == ["SH600036", "SZ000001"]


def test_help_is_utf8_in_a_fresh_windows_process() -> None:
    source_root = str(Path(__file__).parents[1] / "src")
    env = {**os.environ, "PYTHONPATH": source_root, "PYTHONUTF8": "0"}
    result = subprocess.run(
        [sys.executable, "-m", "ashare_data.agent_cli.main", "--help"],
        check=True,
        capture_output=True,
        env=env,
    )

    help_text = result.stdout.decode("utf-8")
    assert "A 股行情 JSON CLI" in help_text
    assert "�" not in help_text
