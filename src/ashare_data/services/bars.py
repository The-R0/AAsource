from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from ashare_data.domain.batch import resolve_inputs, unique_symbols
from ashare_data.domain.enums import AdjustMode, BarStatus, Timeframe
from ashare_data.domain.errors import AshareDataError, ErrorCode
from ashare_data.domain.identifiers import canonicalize_symbol
from ashare_data.domain.models import SourceRef, WarningItem
from ashare_data.domain.validators import assert_supported_adjust
from ashare_data.normalize.bars import bars_from_daily_frame, bars_from_minute_rows, resample_bars
from ashare_data.normalize.daily import normalize_daily
from ashare_data.normalize.validation import annotate_bar_quality
from ashare_data.providers.tdx import get_tdx_provider

SHANGHAI = ZoneInfo("Asia/Shanghai")
INTRADAY = {Timeframe.M1, Timeframe.M5, Timeframe.M15, Timeframe.M30, Timeframe.M60}


def _tdx_daily_bars(
    symbol: str,
    *,
    start: str | None,
    end: str | None,
    limit: int | None,
    retrieved_at: str,
) -> tuple[list[dict[str, Any]], list[SourceRef], list[WarningItem], bool, dict[str, Any]]:
    """Fetch canonical daily bars directly from the authoritative TDX adapter."""
    want = 2000
    if limit is not None and limit > 0:
        want = max(limit + 5, limit)
    if start and end:
        # rough calendar span → trading-day overshoot
        try:
            days = (datetime.fromisoformat(end) - datetime.fromisoformat(start)).days
            want = max(want, min(days + 40, 4000))
        except ValueError:
            pass
    try:
        rows, actions, host, _exhausted = get_tdx_provider().fetch_daily_raw(symbol, want)
        frame = normalize_daily(symbol, rows, actions)
    except Exception as exc:  # noqa: BLE001
        raise AshareDataError(
            ErrorCode.PROVIDER_FAILURE,
            f"live daily bars failed for {symbol}: {exc}",
            retryable=True,
        ) from exc
    if frame.empty:
        raise AshareDataError(ErrorCode.UNAVAILABLE, f"No live daily bars for {symbol}")
    if start:
        frame = frame[frame["trade_date"] >= pd.Timestamp(start)]
    if end:
        frame = frame[frame["trade_date"] <= pd.Timestamp(end)]
    if limit is not None and limit > 0:
        frame = frame.tail(limit)
    bars = bars_from_daily_frame(frame, symbol=symbol, status=BarStatus.FINAL, adjust=AdjustMode.NONE)
    out = []
    for bar in bars:
        payload = annotate_bar_quality(bar.to_dict())
        payload["trade_date"] = payload["ts"][:10]
        out.append(payload)
    provenance = {
        "provider": "tdx",
        "dataset": "daily_bars",
        "host": host,
        "retrieved_at": retrieved_at,
    }
    return out, [SourceRef(provider="tdx", role="canonical_daily")], [], False, provenance


def get_bars_batch(
    symbols: list[str],
    *,
    timeframe: str = "1m",
    limit: int | None = 240,
    start: str | None = None,
    end: str | None = None,
    adjust: str = "none",
) -> tuple[dict[str, Any], list[SourceRef], list[WarningItem], bool, dict[str, Any]]:
    """Fetch each canonical symbol once, then align results to input order."""
    resolved = resolve_inputs(symbols)
    fetched: dict[str, dict[str, Any]] = {}
    sources: list[SourceRef] = []
    warnings: list[WarningItem] = []
    for symbol in unique_symbols(resolved):
        try:
            bars, srcs, warns, degraded, provenance = get_bars(
                symbol,
                timeframe=timeframe,
                limit=limit,
                start=start,
                end=end,
                adjust=adjust,
            )
            fetched[symbol] = {
                "status": "ok",
                "error": None,
                "degraded": degraded,
                "bars": bars,
                "count": len(bars),
                "provenance": provenance,
            }
            sources.extend(srcs)
            warnings.extend(warns)
        except AshareDataError as exc:
            fetched[symbol] = {
                "status": "error",
                "error": exc.to_dict(),
                "degraded": True,
                "bars": [],
                "count": 0,
            }
            warnings.append(WarningItem(code="BARS_ITEM_FAILED", message=str(exc), symbols=[symbol]))
        except Exception as exc:  # noqa: BLE001
            error = AshareDataError(ErrorCode.PROVIDER_FAILURE, str(exc), retryable=True)
            fetched[symbol] = {
                "status": "error",
                "error": error.to_dict(),
                "degraded": True,
                "bars": [],
                "count": 0,
            }
            warnings.append(WarningItem(code="BARS_ITEM_FAILED", message=str(exc), symbols=[symbol]))

    items: list[dict[str, Any]] = []
    for item in resolved:
        symbol = item.get("symbol")
        if item.get("status") == "error":
            payload = {
                "status": "error",
                "error": item["error"],
                "degraded": True,
                "bars": [],
                "count": 0,
            }
        else:
            payload = fetched[symbol]
        items.append({"input": item["input"], "symbol": symbol, **payload})
    any_ok = any(item.get("status") == "ok" for item in items)
    degraded = (not any_ok) or any(item.get("status") != "ok" or item.get("degraded") for item in items)
    return (
        {"items": items, "count": len(items), "timeframe": timeframe},
        sources,
        warnings,
        degraded,
        {"batch": True, "timeframe": timeframe},
    )


def get_bars(
    symbol: str,
    *,
    timeframe: str = "1d",
    limit: int | None = 120,
    start: str | None = None,
    end: str | None = None,
    adjust: str = "none",
) -> tuple[list[dict[str, Any]], list[SourceRef], list[WarningItem], bool, dict[str, Any]]:
    from ashare_data.domain.sectors import canonicalize_sector_id, is_sector_id

    warnings: list[WarningItem] = []
    degraded = False
    retrieved_at = datetime.now(SHANGHAI).isoformat(timespec="milliseconds")

    # Sector boards (BK####): canonical daily and 1m facts from Eastmoney.
    if is_sector_id(symbol):
        sector_id = canonicalize_sector_id(symbol)
        try:
            tf = Timeframe(timeframe)
        except ValueError as exc:
            raise AshareDataError(
                ErrorCode.UNSUPPORTED_TIMEFRAME,
                f"Unsupported timeframe: {timeframe}",
                details={"supported": [t.value for t in Timeframe]},
            ) from exc
        if tf == Timeframe.D1:
            from ashare_data.providers.eastmoney_boards import fetch_sector_daily

            try:
                payload = fetch_sector_daily(sector_id, start=start, end=end, limit=limit)
            except Exception as exc:  # noqa: BLE001
                raise AshareDataError(
                    ErrorCode.PROVIDER_FAILURE,
                    f"sector daily bars failed for {sector_id}: {exc}",
                    retryable=True,
                ) from exc
            out = []
            for row in payload.get("rows") or []:
                bar = {
                    "symbol": sector_id,
                    "timeframe": "1d",
                    "ts": row.get("ts"),
                    "trade_date": row.get("trade_date"),
                    "open": row.get("open"),
                    "high": row.get("high"),
                    "low": row.get("low"),
                    "close": row.get("close"),
                    "volume": row.get("volume"),
                    "amount": row.get("amount"),
                    "previous_close": row.get("previous_close"),
                    "status": "final",
                    "source": "eastmoney",
                    "adjust": "none",
                    "quality": "complete",
                }
                out.append(annotate_bar_quality(bar))
            if not out:
                raise AshareDataError(ErrorCode.UNAVAILABLE, f"No sector daily bars for {sector_id}")
            provenance = {
                "provider": "eastmoney",
                "dataset": "sector_daily_kline",
                "sector_id": sector_id,
                "sector_name": payload.get("name"),
                "retrieved_at": retrieved_at,
            }
            return out, [SourceRef(provider="eastmoney", role="sector_daily")], warnings, degraded, provenance
        if tf != Timeframe.M1:
            raise AshareDataError(
                ErrorCode.CAPABILITY_NOT_AVAILABLE,
                f"sector bars support 1d and 1m (got {timeframe})",
                details={"sector_id": sector_id, "supported": ["1d", "1m"]},
            )
        from ashare_data.services.sectors import sector_minute

        payload, sources, swarnings, sdegraded = sector_minute(sector_id, trading_date=end)
        rows = list(payload.get("rows") or [])
        if start:
            rows = [r for r in rows if str(r.get("time") or r.get("ts") or "")[:10] >= start]
        if end:
            rows = [r for r in rows if str(r.get("time") or r.get("ts") or "")[:10] <= end]
        if limit:
            rows = rows[-limit:]
        out = []
        for row in rows:
            out.append(
                {
                    "symbol": sector_id,
                    "ts": row.get("ts") or row.get("time"),
                    "trade_date": str(row.get("time") or row.get("ts") or "")[:10],
                    "open": row.get("open"),
                    "high": row.get("high"),
                    "low": row.get("low"),
                    "close": row.get("close"),
                    "volume": row.get("volume"),
                    "amount": row.get("amount"),
                    "average": row.get("average"),
                    "preclose": payload.get("preclose"),
                    "timeframe": "1m",
                    "status": "provisional",
                }
            )
        provenance = {
            "provider": "eastmoney",
            "dataset": "sector_trends2",
            "sector_id": sector_id,
            "retrieved_at": retrieved_at,
            "preclose": payload.get("preclose"),
        }
        return out, sources, list(swarnings) + warnings, sdegraded or degraded, provenance

    symbol = canonicalize_symbol(symbol)
    try:
        tf = Timeframe(timeframe)
    except ValueError as exc:
        raise AshareDataError(
            ErrorCode.UNSUPPORTED_TIMEFRAME,
            f"Unsupported timeframe: {timeframe}",
            details={"supported": [t.value for t in Timeframe]},
        ) from exc
    assert_supported_adjust(adjust)

    if tf == Timeframe.D1:
        return _tdx_daily_bars(
            symbol,
            start=start,
            end=end,
            limit=limit,
            retrieved_at=retrieved_at,
        )

    if tf not in INTRADAY:
        raise AshareDataError(
            ErrorCode.CAPABILITY_NOT_AVAILABLE,
            f"timeframe {timeframe} not available",
            details={"timeframe": timeframe, "supported": ["1d", "1m", "5m", "15m", "30m", "60m"]},
        )

    provider = get_tdx_provider()
    try:
        rows = provider.fetch_minute_1m(symbol, trading_date=end)
    except AshareDataError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise AshareDataError(ErrorCode.PROVIDER_FAILURE, str(exc), retryable=True) from exc

    # No-trade minutes are absent from provider rows — do not fabricate.
    minute_bars = bars_from_minute_rows(rows, symbol=symbol, timeframe=Timeframe.M1, status=BarStatus.PROVISIONAL)
    if tf != Timeframe.M1:
        minute_bars = resample_bars(minute_bars, tf)
    if start:
        minute_bars = [b for b in minute_bars if b.ts[:10] >= start]
    if end:
        minute_bars = [b for b in minute_bars if b.ts[:10] <= end]
    if limit:
        minute_bars = minute_bars[-limit:]
    if not minute_bars:
        degraded = True
        warnings.append(WarningItem(code="INTRADAY_EMPTY", symbols=[symbol]))
    sources = [SourceRef(provider="tdx", role="intraday_1m")]
    provenance = {
        "provider": "tdx",
        "dataset": "intraday_1m",
        "retrieved_at": retrieved_at,
        "resampled_to": str(tf),
        "bar_policy": "no_trade_no_bar",
    }
    out = []
    for bar in minute_bars:
        payload = annotate_bar_quality(bar.to_dict())
        payload["trade_date"] = payload["ts"][:10]
        out.append(payload)
    return out, sources, warnings, degraded, provenance
