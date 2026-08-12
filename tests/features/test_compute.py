from __future__ import annotations

from ashare_data.features.compute import compute_feature_set, compute_features_batch


def test_batch_features():
    items, degraded = compute_features_batch(["SH600036", "SH600050", "BAD"], "volume_core")
    assert len(items) == 3
    assert items[0]["status"] == "ok"
    assert items[2]["status"] == "error"
    assert degraded is True
    feats = items[0]["features"]["features"]
    assert any(f["id"] == "volume_ratio" and "status" in f for f in feats)


def test_single_feature_set():
    row = compute_feature_set("SH600036", "trend_core")
    ma20 = next(f for f in row["features"] if f["id"] == "ma" and f["params"]["window"] == 20)
    assert ma20["status"] in {"ok", "insufficient_history"}
    assert ma20["value"] is None or isinstance(ma20["value"], float)
