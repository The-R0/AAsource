from __future__ import annotations

import re
from datetime import datetime, time
from typing import Iterable
from zoneinfo import ZoneInfo

from ashare_data.settings import load_yaml_resource

SHANGHAI = ZoneInfo("Asia/Shanghai")
_DURATION = re.compile(r"^(\d+)(s|m|h|d)$")


def duration_seconds(value: str) -> int:
    match = _DURATION.fullmatch(str(value).strip())
    if not match:
        raise ValueError(f"invalid duration: {value}")
    amount = int(match.group(1))
    return amount * {"s": 1, "m": 60, "h": 3600, "d": 86400}[match.group(2)]


def parse_provider_time(value: str | None) -> datetime | None:
    text = str(value or "")
    if re.fullmatch(r"\d{14}", text):
        try:
            return datetime.strptime(text, "%Y%m%d%H%M%S").replace(tzinfo=SHANGHAI)
        except ValueError:
            return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed.replace(tzinfo=SHANGHAI) if parsed.tzinfo is None else parsed.astimezone(SHANGHAI)


def quote_freshness(
    source_times: Iterable[str | None],
    *,
    retrieved_at: datetime | None = None,
) -> dict[str, object]:
    observed = retrieved_at or datetime.now(SHANGHAI)
    observed = observed.astimezone(SHANGHAI)
    parsed = [value for value in (parse_provider_time(item) for item in source_times) if value is not None]
    latest = max(parsed) if parsed else None
    session_active = observed.weekday() < 5 and time(9, 15) <= observed.time() <= time(15, 5)
    policy = load_yaml_resource("freshness.yaml").get("quotes") or {}
    threshold_text = policy.get("trading_hours" if session_active else "outside_trading_hours", "10s")
    threshold = duration_seconds(str(threshold_text))
    age = max(0, int((observed - latest).total_seconds())) if latest else None
    return {
        "source_time": latest.isoformat(timespec="seconds") if latest else None,
        "retrieved_at": observed.isoformat(timespec="milliseconds"),
        "age_seconds": age,
        "stale": True if age is None else age > threshold,
        "threshold_seconds": threshold,
        "policy": "trading_hours" if session_active else "outside_trading_hours",
    }
