from __future__ import annotations

from ashare_data.services import bars as bars_service


def test_daily_bars_use_tdx_without_local_release_or_universe(monkeypatch, tmp_path) -> None:
    class FakeTdx:
        def fetch_daily_raw(self, symbol: str, count: int):
            assert symbol == "SH600036"
            assert count >= 2
            rows = [
                {
                    "datetime": "2026-08-07",
                    "open": 10.0,
                    "high": 10.5,
                    "low": 9.8,
                    "close": 10.2,
                    "vol": 1000,
                    "amount": 10200,
                },
                {
                    "datetime": "2026-08-10",
                    "open": 10.2,
                    "high": 10.8,
                    "low": 10.1,
                    "close": 10.6,
                    "vol": 1200,
                    "amount": 12720,
                },
            ]
            return rows, [], "fake-tdx", False

    monkeypatch.setenv("ASHARE_DATA_HOME", str(tmp_path / "empty-data-home"))
    monkeypatch.setattr(bars_service, "get_tdx_provider", lambda: FakeTdx())

    bars, sources, warnings, degraded, provenance = bars_service.get_bars(
        "SH600036", timeframe="1d", limit=2
    )

    assert len(bars) == 2
    assert {bar["status"] for bar in bars} == {"final"}
    assert [source.provider for source in sources] == ["tdx"]
    assert warnings == []
    assert degraded is False
    assert provenance["dataset"] == "daily_bars"
    assert "release_id" not in provenance
