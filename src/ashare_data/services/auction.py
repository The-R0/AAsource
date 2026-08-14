from __future__ import annotations

from datetime import datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from ashare_data.domain.batch import resolve_inputs, unique_symbols
from ashare_data.domain.errors import AshareDataError, ErrorCode
from ashare_data.domain.identifiers import canonicalize_symbol
from ashare_data.domain.models import SourceRef, WarningItem
from ashare_data.domain.temporal import quote_freshness
from ashare_data.providers.tencent import get_tencent_provider

SHANGHAI = ZoneInfo("Asia/Shanghai")
CALL_AUCTION_START = time(9, 15)
CALL_AUCTION_END = time(9, 25)


def _source_datetime(value: Any) -> datetime | None:
    text = str(value or "")
    if len(text) != 14 or not text.isdigit():
        return None
    try:
        return datetime.strptime(text, "%Y%m%d%H%M%S").replace(tzinfo=SHANGHAI)
    except ValueError:
        return None


def _shares(level: dict[str, Any]) -> int | None:
    lots = level.get("volume_lots")
    return int(round(float(lots) * 100)) if lots is not None else None


def _auction_snapshot(symbol: str, row: dict[str, Any], retrieved_at: str) -> tuple[dict[str, Any], bool]:
    source_dt = _source_datetime(row.get("source_time"))
    if source_dt is None:
        raise AshareDataError(
            ErrorCode.UNAVAILABLE,
            f"Tencent source time unavailable for {symbol}",
            retryable=True,
        )
    source_clock = source_dt.timetz().replace(tzinfo=None)
    if not CALL_AUCTION_START <= source_clock <= CALL_AUCTION_END:
        raise AshareDataError(
            ErrorCode.CAPABILITY_NOT_AVAILABLE,
            f"Tencent snapshot for {symbol} is outside opening call auction",
            details={"source_time": source_dt.isoformat(timespec="seconds"), "supported_window": "09:15:00-09:25:00"},
        )

    bids = list(row.get("bid_levels") or [])
    asks = list(row.get("ask_levels") or [])
    if len(bids) < 2 or len(asks) < 2:
        raise AshareDataError(ErrorCode.UNAVAILABLE, f"Tencent auction book incomplete for {symbol}", retryable=True)

    bid_price = bids[0].get("price")
    ask_price = asks[0].get("price")
    bid_match = _shares(bids[0])
    ask_match = _shares(asks[0])
    if bid_price is None or ask_price is None or bid_match is None or ask_match is None:
        raise AshareDataError(ErrorCode.UNAVAILABLE, f"Tencent auction match fields unavailable for {symbol}", retryable=True)

    book_consistent = bid_price == ask_price and bid_match == ask_match
    matched_volume = min(bid_match, ask_match)
    unmatched_buy = _shares(bids[1])
    unmatched_sell = _shares(asks[1])
    buy = unmatched_buy or 0
    sell = unmatched_sell or 0
    unmatched_side = "buy" if buy > 0 and sell == 0 else "sell" if sell > 0 and buy == 0 else "both" if buy > 0 and sell > 0 else "none"

    return (
        {
            "symbol": symbol,
            "trade_date": source_dt.date().isoformat(),
            "phase": "call_auction",
            "source_time": source_dt.isoformat(timespec="seconds"),
            "retrieved_at": retrieved_at,
            "indicative_price": bid_price if bid_price == ask_price else None,
            "matched_volume": matched_volume,
            "unmatched_buy_volume": unmatched_buy,
            "unmatched_sell_volume": unmatched_sell,
            "unmatched_side": unmatched_side,
            "provisional": True,
            "source": "tencent",
            "book_consistent": book_consistent,
            "units": {"price": "CNY_per_share", "volume": "shares"},
        },
        not book_consistent,
    )


def get_auction_snapshots(
    symbols: list[str],
) -> tuple[list[dict[str, Any]], list[SourceRef], list[WarningItem], bool, dict[str, Any]]:
    retrieved_at = datetime.now(SHANGHAI).isoformat(timespec="milliseconds")
    inputs = resolve_inputs(symbols)
    valid_symbols = unique_symbols(inputs)
    rows_by_symbol: dict[str, dict[str, Any]] = {}
    fetch_error: AshareDataError | None = None
    if valid_symbols:
        try:
            raw = get_tencent_provider().fetch_quotes_raw(valid_symbols)
            for row in (raw.get("data") or {}).get("quotes") or []:
                raw_symbol = row.get("symbol") or row.get("tencent_symbol")
                if raw_symbol:
                    rows_by_symbol[canonicalize_symbol(str(raw_symbol))] = row
        except Exception as exc:  # noqa: BLE001
            fetch_error = AshareDataError(ErrorCode.PROVIDER_FAILURE, str(exc), retryable=True)

    results: list[dict[str, Any]] = []
    warnings: list[WarningItem] = []
    degraded = False
    for item in inputs:
        symbol = item.get("symbol")
        error = None
        snapshot = None
        inconsistent = False
        if item.get("status") == "error":
            error = item["error"]
        elif fetch_error is not None:
            error = fetch_error.to_dict()
        else:
            row = rows_by_symbol.get(str(symbol))
            if row is None:
                error = AshareDataError(ErrorCode.UNAVAILABLE, f"No Tencent quote for {symbol}", retryable=True).to_dict()
            else:
                try:
                    snapshot, inconsistent = _auction_snapshot(str(symbol), row, retrieved_at)
                except AshareDataError as exc:
                    error = exc.to_dict()
        if error is not None:
            degraded = True
            results.append({"input": item["input"], "symbol": symbol, "status": "error", "error": error, "auction": None})
        else:
            if inconsistent:
                degraded = True
                warnings.append(WarningItem(code="AUCTION_BOOK_INCONSISTENT", symbols=[str(symbol)]))
            results.append({"input": item["input"], "symbol": symbol, "status": "ok", "error": None, "auction": snapshot})

    source_times = [
        (item.get("auction") or {}).get("source_time")
        for item in results
        if item.get("status") == "ok"
    ]
    freshness = quote_freshness(source_times, retrieved_at=datetime.fromisoformat(retrieved_at))
    if source_times and freshness["stale"]:
        degraded = True
        warnings.append(WarningItem(code="AUCTION_STALE", message="auction snapshot exceeds realtime freshness threshold"))
    return results, [SourceRef(provider="tencent", role="opening_call_auction_snapshot")], warnings, degraded, freshness
