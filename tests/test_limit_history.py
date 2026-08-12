from __future__ import annotations

from ashare_data.services.limit_history import classify_limit_history


def _bar(day: str, previous: float, high: float, close: float):
    return {
        "trade_date": day,
        "previous_close": previous,
        "open": previous,
        "high": high,
        "low": previous,
        "close": close,
        "volume": 1000,
        "amount": 10000,
    }


def test_classifies_sealed_broken_and_streak_without_score() -> None:
    result = classify_limit_history(
        "SH600001",
        [
            _bar("2026-08-03", 10.0, 11.0, 11.0),
            _bar("2026-08-04", 11.0, 12.1, 12.1),
            _bar("2026-08-05", 12.1, 13.31, 12.8),
        ],
    )
    assert [event["state"] for event in result["events"]] == [
        "sealed_limit_up",
        "sealed_limit_up",
        "broken_limit_up",
    ]
    assert result["max_streak"] == 2
    assert result["events"][1]["streak"] == 2
    assert result["events"][2]["streak"] == 0
    assert result["unavailable_dimensions"] == ["historical_st_status", "five_pct_limit_events"]
    assert "score" not in result


def test_chinext_uses_20_pct_after_registration_reform() -> None:
    result = classify_limit_history("SZ300001", [_bar("2026-08-03", 10.0, 12.0, 12.0)])
    assert result["events"][0]["limit_pct"] == 20.0
    assert result["unavailable_dimensions"] == []


def test_rounds_limit_price_half_up_to_tick() -> None:
    result = classify_limit_history("SH600001", [_bar("2026-08-03", 10.05, 11.06, 11.06)])
    assert result["events"][0]["limit_price"] == 11.06


def test_lower_bound_only_applies_to_streak_touching_window_start() -> None:
    result = classify_limit_history(
        "SH600001",
        [
            _bar("2026-08-01", 10.0, 11.0, 11.0),
            _bar("2026-08-02", 11.0, 11.5, 11.4),
            _bar("2026-08-03", 11.4, 12.54, 12.54),
        ],
    )
    assert result["events"][0]["streak_is_lower_bound"] is True
    assert result["events"][1]["streak_is_lower_bound"] is False
