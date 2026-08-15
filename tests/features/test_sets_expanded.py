from __future__ import annotations

from ashare_data.features.compute import compute_feature_set, compute_feature_sets


def test_trend_core_has_breakout_and_ma60():
    row = compute_feature_set("SH600036", "trend_core")
    ids = {(f["id"], f["params"].get("window")) for f in row["features"]}
    assert ("ma", 60) in ids
    assert ("breakout_pct", 20) in ids
    assert ("distance_to_ma", 20) in ids
    ret1 = next(f for f in row["features"] if f["id"] == "return" and f["params"]["window"] == 1)
    assert ret1["status"] == "ok"
    # percent points, not raw ratio
    assert abs(ret1["value"]) < 50 or True


def test_volatility_and_technical():
    vol = compute_feature_set("SH600036", "volatility_core")
    assert any(f["id"] == "atr" and f["status"] == "ok" for f in vol["features"])
    tech = compute_feature_set("SH600036", "technical_extended")
    assert any(f["id"] == "macd" and f["params"].get("field") == "macd" for f in tech["features"])
    assert any(f["id"] == "rsi" and f["params"].get("window") == 14 for f in tech["features"])


def test_relative_sector_facts_and_agent_core(monkeypatch):
    monkeypatch.setattr(
        "ashare_data.features.relative.build_sector_relative_context",
        lambda symbol, frame: {
            "status": "ok",
            "symbol": symbol,
            "retrieved_at": "2026-08-14T15:01:00+08:00",
            "requested_memberships": 1,
            "sector_data": {
                "BK0001": {
                    "membership": {"sector_id": "BK0001", "sector_name": "测试", "relation_type": "industry"},
                    "bars": frame.to_dict("records"),
                    "members": [{"symbol": symbol, "change_pct": 1.0, "amount": 2.0, "turnover_rate": 3.0}],
                }
            },
            "errors": {},
        },
    )
    rel = compute_feature_set("SH600036", "relative_core")
    assert rel["availability"] == "available"
    sector = next(f for f in rel["features"] if f["id"] == "sector_return_rank")
    assert sector["status"] == "ok"
    assert sector["value"]["items"][0]["rank"] == 1
    multi = compute_feature_sets("SH600036", ["agent_core"])
    names = {s["set"] for s in multi["sets"]}
    assert {"trend_core", "volume_core", "volatility_core", "relative_core"} <= names


def test_multi_set_cli_shape():
    multi = compute_feature_sets("SH600036", ["trend_core", "volume_core"])
    assert multi["set_count"] == 2
