from __future__ import annotations

"""Lightweight structural schemas for contract tests (no external JSON Schema dep)."""

ENVELOPE_REQUIRED = (
    "schema_version",
    "command",
    "request_id",
    "as_of",
    "status",
    "degraded",
    "sources",
    "warnings",
    "data",
    "error",
)

QUOTE_REQUIRED = (
    "symbol",
    "as_of",
    "last",
    "open",
    "high",
    "low",
    "previous_close",
    "change",
    "change_pct",
    "volume",
    "amount",
    "turnover_rate",
    "source",
    "status",
)

BAR_REQUIRED = (
    "symbol",
    "timeframe",
    "ts",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "amount",
    "status",
    "source",
    "adjust",
)


def assert_keys(payload: dict, required: tuple[str, ...], label: str) -> list[str]:
    missing = [k for k in required if k not in payload]
    if missing:
        return [f"{label} missing keys: {missing}"]
    return []
