from __future__ import annotations

import json

from ashare_data.agent_cli.main import main
from ashare_data.domain.schemas import BAR_REQUIRED, ENVELOPE_REQUIRED, assert_keys


def _run(argv, capsys):
    code = main(argv)
    out = capsys.readouterr().out
    payload = json.loads(out)
    return code, payload


def test_catalog_cli(capsys):
    code, payload = _run(["catalog"], capsys)
    assert code == 0
    data = payload["data"]
    assert "query_capabilities" in data
    assert "auction" in data["query_capabilities"]
    assert "admin_capabilities" not in data
    assert "admin" not in data["commands"]
    assert "universes" not in data["commands"]
    assert "agent_core" in data["feature_sets"]
    assert "volatility_core" in data["feature_sets"]
    assert "deprecated_subcommands" not in data["capabilities"]["market"]
    assert data["capabilities"]["sectors"]["bars"].startswith("use bars")
    assert data["capabilities"]["auction"]["history"] is False
    assert data["capabilities"]["bars"]["intraday_history"]["supported"] is True
    assert data["capabilities"]["bars"]["intraday_history"]["scope"] == "single_trade_date_within_provider_retention"
    assert assert_keys(payload, ENVELOPE_REQUIRED, "envelope") == []


def test_bars_daily_from_upstream_provider(capsys):
    code, payload = _run(["bars", "SH600036", "--tf", "1d", "--limit", "20"], capsys)
    assert code == 0
    bars = payload["data"]["bars"]
    assert len(bars) == 20
    assert assert_keys(bars[0], BAR_REQUIRED, "bar") == []


def test_bars_unsupported_adjust(capsys):
    code, payload = _run(["bars", "SH600036", "--tf", "1d", "--adjust", "qfq"], capsys)
    assert code == 2
    assert payload["error"]["code"] == "UNSUPPORTED_ADJUST_MODE"


def test_features_trend_core(capsys):
    code, payload = _run(["features", "SH600036", "--set", "trend_core"], capsys)
    assert code == 0
    feats = payload["data"]["features"]
    assert any(f["id"] == "ma" and f["params"]["window"] == 20 and f["status"] == "ok" for f in feats)


def test_features_multi_set(capsys):
    code, payload = _run(["features", "SH600036", "--set", "trend_core,volume_core"], capsys)
    assert code == 0
    assert payload["data"]["set_count"] == 2


def test_removed_sectors_bars_is_rejected(capsys):
    code, payload = _run(["sectors", "bars", "EM:BK0816"], capsys)
    assert code == 2
    assert payload["error"]["code"] == "INVALID_REQUEST"


def test_quotes_partial_failure(capsys):
    code, payload = _run(["quotes", "600519", "NOTACODE", "000001"], capsys)
    assert code == 0
    assert payload["degraded"] is True
    items = payload["data"]["items"]
    assert items[1]["error"]["code"] == "SYMBOL_NOT_FOUND"


def test_removed_legacy_alias_is_rejected(capsys):
    code, payload = _run(["market-snapshot"], capsys)
    assert code == 2
    assert payload["error"]["code"] == "INVALID_REQUEST"


def test_removed_market_indices_is_rejected(capsys):
    code, payload = _run(["market", "indices"], capsys)
    assert code == 2
    assert payload["error"]["code"] == "INVALID_REQUEST"


def test_local_universes_are_not_exposed_by_cli(capsys):
    code, payload = _run(["universes", "list"], capsys)
    assert code == 2
    assert payload["error"]["code"] == "INVALID_REQUEST"
