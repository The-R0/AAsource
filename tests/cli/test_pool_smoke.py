from __future__ import annotations

from ashare_data.features.compute import compute_features_batch


def test_feature_batch_preserves_large_input_contract(monkeypatch):
    symbols = [f"SH60{value:04d}" for value in range(130)]

    def fake_compute(symbol, *_args, **_kwargs):
        return {"symbol": symbol, "features": []}

    monkeypatch.setattr("ashare_data.features.compute.compute_feature_set", fake_compute)
    items, degraded = compute_features_batch(symbols, "trend_core")
    assert len(items) == len(symbols)
    assert all(i["status"] == "ok" for i in items)
    assert degraded is False
