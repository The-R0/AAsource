from __future__ import annotations

from typing import Any, Callable, Iterable

from ashare_data.domain.errors import AshareDataError, ErrorCode
from ashare_data.domain.identifiers import canonicalize_symbol


def resolve_inputs(raw_symbols: Iterable[str]) -> list[dict[str, Any]]:
    """Preserve input order and duplicates; attach canonical symbol or item error."""
    items: list[dict[str, Any]] = []
    for raw in raw_symbols:
        text = str(raw)
        try:
            symbol = canonicalize_symbol(text)
            items.append({"input": text, "symbol": symbol, "status": "pending"})
        except AshareDataError as exc:
            items.append(
                {
                    "input": text,
                    "symbol": None,
                    "status": "error",
                    "error": exc.to_dict(),
                }
            )
    return items


def unique_symbols(items: list[dict[str, Any]]) -> list[str]:
    seen: list[str] = []
    for item in items:
        sym = item.get("symbol")
        if sym and sym not in seen:
            seen.append(sym)
    return seen


def map_results(
    items: list[dict[str, Any]],
    *,
    payload_key: str,
    fetch: Callable[[list[str]], dict[str, Any]],
    missing_error_code: ErrorCode = ErrorCode.UNAVAILABLE,
    missing_retryable: bool = True,
) -> tuple[list[dict[str, Any]], bool]:
    """fetch(symbols) -> {symbol: payload}. Aligns back to input order."""
    ok_symbols = unique_symbols(items)
    by_symbol: dict[str, Any] = {}
    fetch_error: AshareDataError | None = None
    if ok_symbols:
        try:
            by_symbol = fetch(ok_symbols)
        except AshareDataError as exc:
            fetch_error = exc
        except Exception as exc:  # noqa: BLE001
            fetch_error = AshareDataError(ErrorCode.PROVIDER_FAILURE, str(exc), retryable=True)

    out: list[dict[str, Any]] = []
    degraded = False
    for item in items:
        if item.get("status") == "error":
            degraded = True
            out.append(
                {
                    "input": item["input"],
                    "symbol": None,
                    "status": "error",
                    "error": item["error"],
                    payload_key: None,
                }
            )
            continue
        symbol = item["symbol"]
        if fetch_error is not None:
            degraded = True
            out.append(
                {
                    "input": item["input"],
                    "symbol": symbol,
                    "status": "error",
                    "error": fetch_error.to_dict(),
                    payload_key: None,
                }
            )
            continue
        payload = by_symbol.get(symbol)
        if payload is None:
            degraded = True
            out.append(
                {
                    "input": item["input"],
                    "symbol": symbol,
                    "status": "error",
                    "error": {
                        "code": missing_error_code,
                        "message": f"No data for {symbol}",
                        "retryable": missing_retryable,
                    },
                    payload_key: None,
                }
            )
            continue
        out.append(
            {
                "input": item["input"],
                "symbol": symbol,
                "status": "ok",
                "error": None,
                payload_key: payload,
            }
        )
    return out, degraded
