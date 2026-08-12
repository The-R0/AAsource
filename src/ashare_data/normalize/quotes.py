from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from ashare_data.domain.enums import ProviderName, QuoteStatus
from ashare_data.domain.identifiers import canonicalize_symbol
from ashare_data.domain.models import Quote

SHANGHAI = ZoneInfo("Asia/Shanghai")


def _parse_source_time(source_time: str | None, fallback: str) -> str:
    if source_time and len(source_time) == 14 and source_time.isdigit():
        dt = datetime.strptime(source_time, "%Y%m%d%H%M%S").replace(tzinfo=SHANGHAI)
        return dt.isoformat(timespec="seconds")
    return fallback


def quote_from_tencent_row(row: dict[str, Any], *, as_of: str) -> Quote:
    code = str(row.get("code") or "")
    # Prefer explicit prefixed symbol (indexes: SH000001 ≠ stock SZ000001).
    preferred = row.get("symbol") or row.get("tencent_symbol")
    if preferred:
        symbol = canonicalize_symbol(str(preferred))
    else:
        symbol = canonicalize_symbol(code)
    lots = row.get("volume_lots")
    volume = int(lots * 100) if lots is not None else None
    return Quote(
        symbol=symbol,
        as_of=_parse_source_time(row.get("source_time"), as_of),
        last=row.get("price") if row.get("price") is not None else row.get("last"),
        open=row.get("open"),
        high=row.get("high"),
        low=row.get("low"),
        previous_close=row.get("previous_close"),
        change=row.get("change"),
        change_pct=row.get("change_pct"),
        volume=volume,
        amount=row.get("amount"),
        turnover_rate=row.get("turnover_rate"),
        source=ProviderName.TENCENT,
        status=QuoteStatus.LIVE,
        name=row.get("name"),
        raw={"volume_lots": lots, "source_time": row.get("source_time")},
    )
