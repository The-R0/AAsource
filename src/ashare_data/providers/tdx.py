from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from pytdx.hq import TdxHq_API
from pytdx.params import TDXParams

from ashare_data.domain.errors import AshareDataError, ErrorCode
from ashare_data.domain.identifiers import canonicalize_symbol
from ashare_data.settings import load_yaml_resource

SHANGHAI = ZoneInfo("Asia/Shanghai")
MIN_LIVE_UNIVERSE_SIZE = 4_000


@dataclass(frozen=True)
class TdxHost:
    host: str
    port: int = 7709

    @property
    def label(self) -> str:
        return f"{self.host}:{self.port}"


INDEX_CODES = frozenset(
    {
        "SH000001",
        "SH000300",
        "SH000688",
        "SH000905",
        "SH000852",
        "SH932000",
        "SZ399001",
        "SZ399006",
    }
)


def is_index_symbol(symbol: str) -> bool:
    symbol = symbol.upper()
    return symbol in INDEX_CODES or symbol.startswith("SZ399") or (
        symbol.startswith("SH") and len(symbol) == 8 and symbol[2:5] == "000"
    )


def split_code(code: str) -> tuple[int, str]:
    if not re.fullmatch(r"(?:SH|SZ)\d{6}", code):
        raise ValueError(f"invalid canonical symbol: {code}")
    return (1 if code.startswith("SH") else 0, code[2:])


def bar_date(row: dict[str, Any]) -> date:
    if row.get("year") and row.get("month") and row.get("day"):
        return date(int(row["year"]), int(row["month"]), int(row["day"]))
    return date.fromisoformat(str(row.get("datetime") or row.get("date") or "")[:10])


class TdxClient:
    def __init__(self, hosts: list[TdxHost], timeout: float = 8.0):
        if not hosts:
            raise ValueError("at least one TDX host is required")
        self.hosts = hosts
        self.timeout = timeout

    def fetch(self, code: str, count: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str, bool]:
        errors: list[str] = []
        for host in self.hosts:
            try:
                bars, actions, exhausted = self._fetch_host(host, code, count)
                if not bars:
                    raise RuntimeError("empty daily history")
                return bars, actions, host.label, exhausted
            except Exception as exc:  # explicit host failover
                errors.append(f"{host.label}:{type(exc).__name__}:{exc}")
        raise RuntimeError("all TDX hosts failed: " + " | ".join(errors))

    def _fetch_host(
        self, host: TdxHost, code: str, count: int
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], bool]:
        market, bare = split_code(code)
        index = is_index_symbol(code)
        rows: list[dict[str, Any]] = []
        api = TdxHq_API(heartbeat=True, multithread=True, raise_exception=True)
        exhausted = False
        with api.connect(host.host, host.port, time_out=self.timeout):
            offset = 0
            while len(rows) < count:
                page_size = min(800, count - len(rows))
                page = (
                    api.get_index_bars(TDXParams.KLINE_TYPE_DAILY, market, bare, offset, page_size)
                    if index
                    else api.get_security_bars(TDXParams.KLINE_TYPE_DAILY, market, bare, offset, page_size)
                )
                if not page:
                    exhausted = True
                    break
                rows.extend(dict(item) for item in page)
                if len(page) < page_size:
                    exhausted = True
                    break
                offset += len(page)
            actions = [] if index else [dict(item) for item in (api.get_xdxr_info(market, bare) or [])]
        unique = {bar_date(row): row for row in rows}
        return [unique[key] for key in sorted(unique)][-count:], actions, exhausted


def _load_hosts(config_path: Any = None) -> list[TdxHost]:
    if config_path:
        import yaml

        payload = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    else:
        payload = load_yaml_resource("sources.yaml")
    return [TdxHost(host=item["host"], port=int(item.get("port", 7709))) for item in payload["tdx_hosts"]]


class TdxProvider:
    name = "tdx"

    def __init__(self, hosts: list[TdxHost] | None = None, timeout: float = 8.0):
        self.hosts = hosts or _load_hosts()
        self.timeout = timeout
        self._client = TdxClient(self.hosts, timeout=timeout)
        self._master_lock = threading.Lock()
        self._master: dict[str, Any] | None = None
        self._master_cached_at: float | None = None

    def status(self) -> dict[str, Any]:
        last_error = None
        for host in self.hosts[:3]:
            api = TdxHq_API(heartbeat=False, multithread=False, raise_exception=True)
            try:
                with api.connect(host.host, host.port, time_out=self.timeout):
                    count = api.get_security_count(1)
                    return {"provider": self.name, "status": "ok", "host": host.label, "sh_count": count}
            except Exception as exc:  # noqa: BLE001 — probe
                last_error = str(exc)
        return {"provider": self.name, "status": "degraded", "error": last_error}

    def fetch_daily_raw(self, symbol: str, count: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str, bool]:
        symbol = canonicalize_symbol(symbol)
        return self._client.fetch(symbol, count)

    @staticmethod
    def _is_a_share_code(market: int, code: str) -> bool:
        if market == 1:
            return code.startswith(("600", "601", "603", "605", "688", "689"))
        return code.startswith(("000", "001", "002", "003", "300", "301", "4", "8", "9"))

    @staticmethod
    def _security_page(api: Any, market: int, start: int, attempts: int = 4) -> list[dict[str, Any]]:
        last_error: Exception | None = None
        for attempt in range(attempts):
            try:
                page = api.get_security_list(market, start)
                if page is not None:
                    return [dict(item) for item in page]
            except Exception as exc:  # public nodes are intermittently incomplete
                last_error = exc
            time.sleep(0.05 * (attempt + 1))
        if last_error:
            raise last_error
        raise RuntimeError(f"empty TDX security page: market={market}, start={start}")

    def _fetch_security_master_remote(self) -> dict[str, Any]:
        errors: list[str] = []
        for host in self.hosts:
            api = TdxHq_API(heartbeat=False, multithread=True, raise_exception=True)
            try:
                symbols: dict[str, dict[str, Any]] = {}
                page_errors: list[str] = []
                with api.connect(host.host, host.port, time_out=self.timeout):
                    for market in (0, 1):
                        total = int(api.get_security_count(market) or 0)
                        for start in range(0, total, 1_000):
                            try:
                                page = self._security_page(api, market, start)
                            except Exception as exc:
                                page_errors.append(f"market={market},start={start}:{type(exc).__name__}")
                                continue
                            for item in page:
                                code = str(item.get("code") or "")
                                if re.fullmatch(r"\d{6}", code) and self._is_a_share_code(market, code):
                                    symbols[code] = {
                                        "code": code,
                                        "name": str(item.get("name") or ""),
                                        "exchange": "SH" if market == 1 else (
                                            "BJ" if code.startswith(("4", "8", "9")) else "SZ"
                                        ),
                                    }
                if len(symbols) < MIN_LIVE_UNIVERSE_SIZE:
                    raise RuntimeError(f"TDX security master coverage too small: {len(symbols)}")
                return {
                    "status": "PASS",
                    "source": f"pytdx:{host.label}",
                    "scope": "TDX public A-share security master",
                    "exchanges": sorted({str(item["exchange"]) for item in symbols.values()}),
                    "generated_at": datetime.now(SHANGHAI).isoformat(timespec="seconds"),
                    "count": len(symbols),
                    "warnings": page_errors,
                    "symbols": [symbols[code] for code in sorted(symbols)],
                }
            except Exception as exc:
                errors.append(f"{host.label}:{type(exc).__name__}:{exc}")
        raise RuntimeError("all TDX security-master hosts failed: " + " | ".join(errors))

    def fetch_security_master(self, *, max_age_seconds: int = 86_400, force: bool = False) -> dict[str, Any]:
        with self._master_lock:
            cache_fresh = (
                self._master is not None
                and self._master_cached_at is not None
                and time.monotonic() - self._master_cached_at <= max_age_seconds
            )
            if cache_fresh and not force:
                return self._master
            payload = self._fetch_security_master_remote()
            self._master = payload
            self._master_cached_at = time.monotonic()
            return payload

    def fetch_minute_1m(self, symbol: str, trading_date: str | None = None) -> list[dict[str, Any]]:
        """Fetch today's (or recent) 1-minute bars from TDX. Volume unit: lots."""
        symbol = canonicalize_symbol(symbol)
        market, code = split_code(symbol)
        is_index = symbol in INDEX_CODES or (symbol.startswith("SH") and code.startswith("000")) or symbol.startswith(
            "SZ399"
        )
        errors: list[str] = []
        for host in self.hosts:
            api = TdxHq_API(heartbeat=True, multithread=True, raise_exception=True)
            try:
                with api.connect(host.host, host.port, time_out=self.timeout):
                    # category 8 = 1-minute in pytdx
                    page = (
                        api.get_index_bars(TDXParams.KLINE_TYPE_1MIN, market, code, 0, 240)
                        if is_index
                        else api.get_security_bars(TDXParams.KLINE_TYPE_1MIN, market, code, 0, 240)
                    )
                if not page:
                    raise RuntimeError("empty 1m bars")
                rows: list[dict[str, Any]] = []
                for item in page:
                    row = dict(item)
                    year = int(row.get("year") or 0)
                    month = int(row.get("month") or 0)
                    day = int(row.get("day") or 0)
                    hour = int(row.get("hour") or 0)
                    minute = int(row.get("minute") or 0)
                    if not year:
                        # some nodes pack datetime
                        dt_text = str(row.get("datetime") or "")
                        if len(dt_text) >= 16:
                            ts = datetime.fromisoformat(dt_text.replace("/", "-"))
                            ts = ts.replace(tzinfo=SHANGHAI)
                        else:
                            continue
                    else:
                        ts = datetime(year, month, day, hour, minute, tzinfo=SHANGHAI)
                    if trading_date and ts.date().isoformat() != trading_date:
                        continue
                    # pytdx 1m `vol` matches amount/close (shares), unlike daily lots.
                    rows.append(
                        {
                            "ts": ts,
                            "open": float(row.get("open") or 0),
                            "high": float(row.get("high") or 0),
                            "low": float(row.get("low") or 0),
                            "close": float(row.get("close") or 0),
                            "volume": float(row.get("vol") or row.get("volume") or 0),
                            "amount": float(row.get("amount") or 0),
                            "volume_unit": "shares",
                            "source": "tdx",
                        }
                    )
                rows.sort(key=lambda r: r["ts"])
                return rows
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{host.label}:{exc}")
        raise AshareDataError(
            ErrorCode.PROVIDER_FAILURE,
            "TDX 1m fetch failed: " + " | ".join(errors[:3]),
            retryable=True,
        )


    def fetch_transactions(
        self,
        symbol: str,
        trade_date: str,
        *,
        limit: int = 2000,
    ) -> list[dict[str, Any]]:
        """History ticks for one trade date. lots = vol from TDX."""
        symbol = canonicalize_symbol(symbol)
        market, code = split_code(symbol)
        day = int(str(trade_date).replace("-", "")[:8])
        want = min(max(int(limit), 20), 2000)
        errors: list[str] = []
        for host in self.hosts:
            api = TdxHq_API(heartbeat=False, multithread=False, raise_exception=True)
            try:
                with api.connect(host.host, host.port, time_out=self.timeout):
                    raw = api.get_history_transaction_data(market, code, 0, want, day)
                if not raw:
                    raise RuntimeError("empty transactions")
                rows: list[dict[str, Any]] = []
                for item in raw:
                    price = float(item["price"]) if item.get("price") is not None else None
                    lots = float(item["vol"]) if item.get("vol") is not None else None
                    buyorsell = item.get("buyorsell")
                    direction = {
                        0: "buy",
                        1: "sell",
                        2: "neutral",
                    }.get(int(buyorsell) if buyorsell is not None else -1, f"raw({buyorsell})")
                    rows.append(
                        {
                            "time": item.get("time"),
                            "price": price,
                            "lots": lots,
                            "amount_estimate": (
                                price * lots * 100 if price is not None and lots is not None else None
                            ),
                            "buyorsell": buyorsell,
                            "direction": direction,
                        }
                    )
                return rows
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{host.label}:{exc}")
        raise AshareDataError(
            ErrorCode.PROVIDER_FAILURE,
            "TDX trades fetch failed: " + " | ".join(errors[:3]),
            retryable=True,
        )


_provider: TdxProvider | None = None
_provider_lock = threading.Lock()


def get_tdx_provider() -> TdxProvider:
    global _provider
    with _provider_lock:
        if _provider is None:
            _provider = TdxProvider()
        return _provider
