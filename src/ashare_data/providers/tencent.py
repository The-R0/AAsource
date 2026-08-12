from __future__ import annotations

import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import requests
from requests.adapters import HTTPAdapter

from ashare_data.domain.identifiers import canonicalize_symbol, tencent_symbol

SHANGHAI = ZoneInfo("Asia/Shanghai")
QUOTE_URL = "https://qt.gtimg.cn/q="
QUOTE_BATCH_SIZE = 350
MAX_DIRECT_SYMBOLS = 500
INDEX_SYMBOLS = {
    "上证指数": "SH000001",
    "深证成指": "SZ399001",
    "创业板指": "SZ399006",
    "科创50": "SH000688",
    "沪深300": "SH000300",
}

_session_state = threading.local()
_quote_executor = ThreadPoolExecutor(max_workers=6, thread_name_prefix="ashare-quote")


class TencentProviderError(RuntimeError):
    pass


def _now_iso() -> str:
    return datetime.now(SHANGHAI).isoformat(timespec="seconds")


def _number(value: Any) -> float | None:
    if value in (None, "", "-"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_tencent_quotes(text: str) -> list[dict[str, Any]]:
    quotes: list[dict[str, Any]] = []
    for record in text.split(";"):
        if '="' not in record:
            continue
        payload = record.split('="', 1)[1].rstrip('"\r\n')
        cells = payload.split("~")
        if len(cells) < 39 or not re.fullmatch(r"\d{6}", cells[2] or ""):
            continue
        amount_wan = _number(cells[37])
        source_time = cells[30] if re.fullmatch(r"\d{14}", cells[30] or "") else None
        bid_levels = [
            {"price": _number(cells[9 + index * 2]), "volume_lots": _number(cells[10 + index * 2])}
            for index in range(5)
        ]
        ask_levels = [
            {"price": _number(cells[19 + index * 2]), "volume_lots": _number(cells[20 + index * 2])}
            for index in range(5)
        ]
        quotes.append(
            {
                "code": cells[2],
                "name": cells[1],
                "price": _number(cells[3]),
                "previous_close": _number(cells[4]),
                "open": _number(cells[5]),
                "change": _number(cells[31]),
                "change_pct": _number(cells[32]),
                "high": _number(cells[33]),
                "low": _number(cells[34]),
                "volume_lots": _number(cells[36]),
                "amount": amount_wan * 10_000 if amount_wan is not None else None,
                "turnover_rate": _number(cells[38]),
                "source_time": source_time,
                "bid_levels": bid_levels,
                "ask_levels": ask_levels,
            }
        )
    return quotes


def _quote_session() -> requests.Session:
    session = getattr(_session_state, "session", None)
    if session is None:
        session = requests.Session()
        session.trust_env = False
        session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AShareDataHub/1.0",
                "Referer": "https://stockapp.finance.qq.com/",
            }
        )
        session.mount("https://", HTTPAdapter(pool_connections=8, pool_maxsize=8, max_retries=0))
        _session_state.session = session
    return session


def _fetch_quote_batch(symbols: list[str], timeout: float = 8.0) -> list[dict[str, Any]]:
    response = _quote_session().get(QUOTE_URL + ",".join(symbols), timeout=timeout)
    response.raise_for_status()
    response.encoding = "gbk"
    return parse_tencent_quotes(response.text)


def _source_time(quotes: list[dict[str, Any]]) -> str | None:
    values = [str(row["source_time"]) for row in quotes if row.get("source_time")]
    return max(values) if values else None


class TencentProvider:
    """Deep adapter for Tencent quote transport and vendor parsing."""

    name = "tencent"

    def fetch_quote_rows(self, symbols: list[str]) -> list[dict[str, Any]]:
        canonical = list(dict.fromkeys(canonicalize_symbol(symbol) for symbol in symbols))
        if not canonical:
            return []
        vendor_symbols = [tencent_symbol(symbol) for symbol in canonical]
        batches = [
            vendor_symbols[index : index + QUOTE_BATCH_SIZE]
            for index in range(0, len(vendor_symbols), QUOTE_BATCH_SIZE)
        ]
        if len(batches) == 1:
            return _fetch_quote_batch(batches[0])
        rows: list[dict[str, Any]] = []
        errors: list[str] = []
        futures = [_quote_executor.submit(_fetch_quote_batch, batch) for batch in batches]
        for future in as_completed(futures):
            try:
                rows.extend(future.result())
            except requests.RequestException as exc:
                errors.append(str(exc))
        if not rows:
            raise TencentProviderError(errors[0] if errors else "Tencent returned no valid quotes")
        return rows

    def fetch_quotes_raw(self, symbols: list[str]) -> dict[str, Any]:
        rows = self.fetch_quote_rows(symbols)
        requested = [canonicalize_symbol(symbol) for symbol in symbols]
        found = {str(row.get("code")) for row in rows}
        missing = [symbol for symbol in requested if symbol[2:] not in found]
        return {
            "status": "DEGRADED" if missing else "OK",
            "updated_at": _now_iso(),
            "data": {
                "quotes": rows,
                "requested": len(requested),
                "returned": len(rows),
                "missing": missing,
                "source_time": _source_time(rows),
            },
        }

    def fetch_indices_raw(self) -> dict[str, Any]:
        rows = self.fetch_quote_rows(list(INDEX_SYMBOLS.values()))
        by_code = {str(row.get("code")): row for row in rows}
        ordered: list[dict[str, Any]] = []
        for name, symbol in INDEX_SYMBOLS.items():
            row = by_code.get(symbol[2:])
            if row:
                ordered.append({**row, "name": name, "symbol": symbol})
        return {
            "status": "OK" if len(ordered) == len(INDEX_SYMBOLS) else "DEGRADED",
            "updated_at": _now_iso(),
            "data": {"indices": ordered, "source_time": _source_time(ordered)},
        }

    def status(self) -> dict[str, Any]:
        try:
            result = self.fetch_indices_raw()
            return {"provider": self.name, "status": "ok" if result["status"] == "OK" else "degraded"}
        except Exception as exc:
            return {"provider": self.name, "status": "degraded", "error": str(exc)}


_provider: TencentProvider | None = None
_provider_lock = threading.Lock()


def get_tencent_provider() -> TencentProvider:
    global _provider
    with _provider_lock:
        if _provider is None:
            _provider = TencentProvider()
        return _provider
