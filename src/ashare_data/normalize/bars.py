from __future__ import annotations

from datetime import datetime, time
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from ashare_data.domain.enums import AdjustMode, BarStatus, DataQuality, ProviderName, Timeframe
from ashare_data.domain.errors import AshareDataError, ErrorCode
from ashare_data.domain.identifiers import canonicalize_symbol
from ashare_data.domain.models import Bar

SHANGHAI = ZoneInfo("Asia/Shanghai")
LOT_SIZE = 100

RESAMPLE_RULES = {
    Timeframe.M5: "5min",
    Timeframe.M15: "15min",
    Timeframe.M30: "30min",
    Timeframe.M60: "60min",
}


def _daily_ts(trade_date: Any) -> str:
    if isinstance(trade_date, datetime):
        d = trade_date.date()
    else:
        d = pd.Timestamp(trade_date).date()
    return datetime.combine(d, time(15, 0), tzinfo=SHANGHAI).isoformat(timespec="seconds")


def _volume_shares(raw_volume: Any, *, security_is_index: bool) -> int | None:
    if raw_volume is None or (isinstance(raw_volume, float) and pd.isna(raw_volume)):
        return None
    value = float(raw_volume)
    # Canonical daily normalization already stores volume in shares. Do not
    # apply a second lot-size conversion; amount/price audits confirm the unit.
    return int(value)


def bars_from_daily_frame(
    frame: pd.DataFrame,
    *,
    symbol: str,
    status: str = BarStatus.FINAL,
    adjust: str = AdjustMode.NONE,
) -> list[Bar]:
    symbol = canonicalize_symbol(symbol)
    is_index = (symbol.startswith("SH") and symbol[2:].startswith("000")) or symbol.startswith("SZ399")
    if adjust != AdjustMode.NONE:
        raise AshareDataError(
            ErrorCode.UNSUPPORTED_ADJUST_MODE,
            f"adjust={adjust} is not supported in v1",
        )
    bars: list[Bar] = []
    for row in frame.to_dict(orient="records"):
        missing: list[str] = []
        for field in ("open", "high", "low", "close", "volume", "amount"):
            if row.get(field) is None or (isinstance(row.get(field), float) and pd.isna(row.get(field))):
                missing.append(field)
        quality = DataQuality.PARTIAL if missing else DataQuality.COMPLETE
        bars.append(
            Bar(
                symbol=symbol,
                timeframe=Timeframe.D1,
                ts=_daily_ts(row.get("trade_date")),
                open=_num(row.get("open")),
                high=_num(row.get("high")),
                low=_num(row.get("low")),
                close=_num(row.get("close")),
                volume=_volume_shares(row.get("volume"), security_is_index=is_index),
                amount=_num(row.get("amount")),
                previous_close=_num(row.get("pre_close")),
                status=status,
                source=ProviderName.TDX,
                adjust=AdjustMode.NONE,
                quality=quality,
                missing_fields=missing,
            )
        )
    return bars


def bars_from_minute_rows(
    rows: list[dict[str, Any]],
    *,
    symbol: str,
    timeframe: str = Timeframe.M1,
    status: str = BarStatus.PROVISIONAL,
) -> list[Bar]:
    symbol = canonicalize_symbol(symbol)
    bars: list[Bar] = []
    for row in rows:
        ts = row.get("ts") or row.get("time")
        if ts is None:
            continue
        if isinstance(ts, datetime):
            ts_text = ts.astimezone(SHANGHAI).isoformat(timespec="seconds")
        else:
            ts_text = str(ts)
        vol = row.get("volume")
        # provider minute volume assumed shares when already normalized; lots flagged in raw
        if row.get("volume_unit") == "lots" and vol is not None:
            vol = int(float(vol) * LOT_SIZE)
        elif vol is not None:
            vol = int(float(vol))
        bars.append(
            Bar(
                symbol=symbol,
                timeframe=timeframe,
                ts=ts_text,
                open=_num(row.get("open")),
                high=_num(row.get("high")),
                low=_num(row.get("low")),
                close=_num(row.get("close")),
                volume=vol,
                amount=_num(row.get("amount")),
                status=status,
                source=str(row.get("source") or ProviderName.TDX),
                adjust=AdjustMode.NONE,
            )
        )
    return bars


def resample_bars(bars: list[Bar], target: Timeframe) -> list[Bar]:
    if target == Timeframe.M1:
        return bars
    if target not in RESAMPLE_RULES:
        raise AshareDataError(ErrorCode.UNSUPPORTED_TIMEFRAME, f"Cannot resample to {target}")
    if not bars:
        return []
    frame = pd.DataFrame([b.to_dict() for b in bars])
    frame["ts"] = pd.to_datetime(frame["ts"])
    frame = frame.set_index("ts").sort_index()
    rule = RESAMPLE_RULES[target]
    agg = frame.resample(rule, label="right", closed="right").agg(
        {
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
            "amount": "sum",
        }
    )
    agg = agg.dropna(subset=["open", "close"], how="any")
    symbol = bars[0].symbol
    source = bars[0].source
    status = bars[0].status
    out: list[Bar] = []
    for ts, row in agg.iterrows():
        out.append(
            Bar(
                symbol=symbol,
                timeframe=target,
                ts=pd.Timestamp(ts).tz_convert(SHANGHAI).isoformat(timespec="seconds")
                if getattr(ts, "tzinfo", None)
                else pd.Timestamp(ts).tz_localize(SHANGHAI).isoformat(timespec="seconds"),
                open=_num(row["open"]),
                high=_num(row["high"]),
                low=_num(row["low"]),
                close=_num(row["close"]),
                volume=int(row["volume"]) if pd.notna(row["volume"]) else None,
                amount=_num(row["amount"]),
                status=status,
                source=source,
                adjust=AdjustMode.NONE,
            )
        )
    return out


def _num(value: Any) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
