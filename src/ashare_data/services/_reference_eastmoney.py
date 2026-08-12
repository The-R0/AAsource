"""Private Eastmoney implementation for the Reference Fact module.

This module owns the complete request-to-record path for the seven reference
datasets used by the Agent CLI.  It deliberately does not expose vendor
column names or depend on a general-purpose market data package.
"""

from __future__ import annotations

import copy
import json
import math
import re
import threading
import time
from datetime import date, datetime
from typing import Any, Callable

import requests

from ashare_data.domain.identifiers import canonicalize_symbol
MAX_RETURN_ROWS = 500
MAX_DATE_RANGE_DAYS = 31
DATACENTER_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"
SHAREHOLDER_URL = "https://emweb.securities.eastmoney.com/PC_HSF10/ShareholderResearch/PageSDLTGD"
MONEY_FLOW_URL = "https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get"
FUND_HOLDING_URL = "https://data.eastmoney.com/dataapi/zlsj/list"
URL_QUERY_PATTERN = re.compile(r"((?:https?://|/)[^\s?'\"()]+)\?[^\s'\"()]+")


class _ReferenceSourceError(RuntimeError):
    """An upstream or response-contract failure in the reference module."""


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _safe_exception_text(exc: Exception) -> str:
    return URL_QUERY_PATTERN.sub(r"\1?<redacted>", str(exc))


def _validate_date(value: str, field: str) -> str:
    if not re.fullmatch(r"\d{8}", value):
        raise ValueError(f"{field}必须是YYYYMMDD")
    datetime.strptime(value, "%Y%m%d")
    return value


def _validate_range(start_date: str, end_date: str) -> tuple[str, str]:
    start = _validate_date(start_date, "start_date")
    end = _validate_date(end_date, "end_date")
    days = (datetime.strptime(end, "%Y%m%d") - datetime.strptime(start, "%Y%m%d")).days
    if days < 0:
        raise ValueError("end_date不能早于start_date")
    if days > MAX_DATE_RANGE_DAYS:
        raise ValueError(f"单次日期范围不能超过{MAX_DATE_RANGE_DAYS}天")
    return start, end


def _validate_limit(limit: int) -> int:
    if not 1 <= limit <= MAX_RETURN_ROWS:
        raise ValueError(f"limit必须在1到{MAX_RETURN_ROWS}之间")
    return limit


def _pick(row: dict[str, Any], *names: str) -> Any:
    for name in names:
        value = row.get(name)
        if value not in (None, "", "-"):
            return value
    return None


def _number(value: Any) -> float | None:
    if value in (None, "", "-"):
        return None
    try:
        result = float(str(value).replace(",", "").replace("%", "").strip())
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _integer(value: Any) -> int | None:
    number = _number(value)
    return int(round(number)) if number is not None else None


def _date_text(value: Any) -> str | None:
    if value in (None, "", "-"):
        return None
    text = str(value).strip()
    digits = re.sub(r"\D", "", text[:10])
    if len(digits) >= 8:
        try:
            return date(int(digits[:4]), int(digits[4:6]), int(digits[6:8])).isoformat()
        except ValueError:
            pass
    return text[:10]


def _text(value: Any) -> str | None:
    return None if value in (None, "", "-") else str(value).strip()


def _symbol(value: Any) -> str | None:
    if value in (None, "", "-"):
        return None
    text = str(value).strip().upper()
    match = re.search(r"(?:SH|SZ|BJ)?(\d{6})", text)
    if not match:
        return None
    try:
        return canonicalize_symbol(text if text[:2] in {"SH", "SZ", "BJ"} else match.group(1))
    except Exception:
        return None


def _compact(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if value is not None}


def _market_prefix(code: str) -> str:
    if code.startswith(("4", "8", "9")):
        return "bj"
    return "sh" if code.startswith("6") else "sz"


def _canonical_dragon(row: dict[str, Any], index: int, query: dict[str, Any]) -> dict[str, Any]:
    return _compact({
        "rank": index,
        "symbol": _symbol(_pick(row, "SECURITY_CODE", "代码")),
        "name": _text(_pick(row, "SECURITY_NAME_ABBR", "名称")),
        "trade_date": _date_text(_pick(row, "TRADE_DATE", "上榜日")) or query.get("trade_date"),
        "close": _number(_pick(row, "CLOSE_PRICE", "收盘价")),
        "change_pct": _number(_pick(row, "CHANGE_RATE", "涨跌幅")),
        "net_buy_amount": _number(_pick(row, "BILLBOARD_NET_AMT", "龙虎榜净买额")),
        "buy_amount": _number(_pick(row, "BILLBOARD_BUY_AMT", "龙虎榜买入额")),
        "sell_amount": _number(_pick(row, "BILLBOARD_SELL_AMT", "龙虎榜卖出额")),
        "listed_trade_amount": _number(_pick(row, "BILLBOARD_DEAL_AMT", "龙虎榜成交额")),
        "market_amount": _number(_pick(row, "ACCUM_AMOUNT", "市场总成交额")),
        "net_buy_to_market_pct": _number(_pick(row, "DEAL_NET_RATIO", "净买额占总成交比")),
        "listed_trade_to_market_pct": _number(_pick(row, "DEAL_AMOUNT_RATIO", "成交额占总成交比")),
        "turnover_rate": _number(_pick(row, "TURNOVERRATE", "换手率")),
        "float_market_cap": _number(_pick(row, "FREE_MARKET_CAP", "流通市值")),
        "reason": _text(_pick(row, "EXPLANATION", "上榜原因")),
        "interpretation": _text(_pick(row, "EXPLAIN", "解读")),
        "post_return_1d_pct": _number(_pick(row, "D1_CLOSE_ADJCHRATE", "上榜后1日")),
        "post_return_2d_pct": _number(_pick(row, "D2_CLOSE_ADJCHRATE", "上榜后2日")),
        "post_return_5d_pct": _number(_pick(row, "D5_CLOSE_ADJCHRATE", "上榜后5日")),
        "post_return_10d_pct": _number(_pick(row, "D10_CLOSE_ADJCHRATE", "上榜后10日")),
    })


def _canonical_institution(row: dict[str, Any], index: int, query: dict[str, Any]) -> dict[str, Any]:
    freecap = _number(row.get("FREECAP"))
    float_cap = round(freecap * 1e8, 2) if freecap is not None else _number(_pick(row, "FREE_MARKET_CAP", "流通市值"))
    return _compact({
        "rank": index,
        "symbol": _symbol(_pick(row, "SECURITY_CODE", "代码")),
        "name": _text(_pick(row, "SECURITY_NAME_ABBR", "名称")),
        "trade_date": _date_text(_pick(row, "TRADE_DATE", "上榜日期")),
        "close": _number(_pick(row, "CLOSE_PRICE", "收盘价")),
        "change_pct": _number(_pick(row, "CHANGE_RATE", "涨跌幅")),
        "buyer_institution_count": _integer(_pick(row, "BUY_TIMES", "BUY_ORG_NUM", "BUYER_ORG_NUM", "买方机构数")),
        "seller_institution_count": _integer(_pick(row, "SELL_TIMES", "SELL_ORG_NUM", "SELLER_ORG_NUM", "卖方机构数")),
        "institution_buy_amount": _number(_pick(row, "BUY_AMT", "机构买入总额")),
        "institution_sell_amount": _number(_pick(row, "SELL_AMT", "机构卖出总额")),
        "institution_net_amount": _number(_pick(row, "NET_BUY_AMT", "机构买入净额")),
        "market_amount": _number(_pick(row, "ACCUM_AMOUNT", "AMOUNT", "市场总成交额")),
        "institution_net_to_market_pct": _number(_pick(row, "RATIO", "NET_BUY_RATIO", "机构净买额占总成交额比")),
        "turnover_rate": _number(_pick(row, "TURNOVERRATE", "换手率")),
        "float_market_cap": float_cap,
        "reason": _text(_pick(row, "EXPLANATION", "上榜原因")),
    })


def _canonical_block(row: dict[str, Any], index: int, query: dict[str, Any]) -> dict[str, Any]:
    return _compact({
        "rank": index,
        "symbol": _symbol(_pick(row, "SECURITY_CODE", "证券代码")),
        "name": _text(_pick(row, "SECURITY_NAME_ABBR", "证券简称")),
        "trade_date": _date_text(_pick(row, "TRADE_DATE", "交易日期")),
        "close": _number(_pick(row, "CLOSE_PRICE", "收盘价")),
        "change_pct": _number(_pick(row, "CHANGE_RATE", "涨跌幅")),
        "trade_price": _number(_pick(row, "DEAL_PRICE", "成交价")),
        "premium_discount_pct": _number(_pick(row, "PREMIUM_RATIO", "折溢率")),
        "volume": _integer(_pick(row, "DEAL_VOLUME", "成交量")),
        "amount": _number(_pick(row, "DEAL_AMT", "成交额")),
        "amount_to_float_market_cap_pct": _number(_pick(row, "TURNOVER_RATE", "成交额/流通市值")),
        "buyer": _text(_pick(row, "BUYER_NAME", "买方营业部")),
        "seller": _text(_pick(row, "SELLER_NAME", "卖方营业部")),
    })


def _canonical_shareholder(row: dict[str, Any], index: int, query: dict[str, Any]) -> dict[str, Any]:
    return _compact({
        "rank": _integer(_pick(row, "HOLDER_RANK", "RANK", "名次")) or index,
        "symbol": query.get("symbol"),
        "report_date": query.get("report_date"),
        "shareholder_name": _text(_pick(row, "HOLDER_NAME", "SHAREHOLDER_NAME", "股东名称")),
        "shareholder_type": _text(_pick(row, "HOLDER_TYPE", "SHAREHOLDER_TYPE", "股东性质")),
        "share_type": _text(_pick(row, "SHARES_TYPE", "HOLD_TYPE", "股份类型")),
        "held_shares": _integer(_pick(row, "HOLD_NUM", "HOLD_SHARES", "持股数")),
        "holding_pct": _number(_pick(row, "FREE_HOLDNUM_RATIO", "HOLD_RATIO", "占总流通股本持股比例")),
        "change_label": _text(_pick(row, "HOLD_NUM_CHANGE", "HOLD_CHANGE", "增减")),
        "change_pct": _number(_pick(row, "CHANGE_RATIO", "HOLD_CHANGE_RATIO", "变动比率")),
    })


def _canonical_fund(row: dict[str, Any], index: int, query: dict[str, Any]) -> dict[str, Any]:
    return _compact({
        "rank": _integer(_pick(row, "RANK", "序号")) or index,
        "symbol": _symbol(_pick(row, "SECUCODE", "SECURITY_CODE", "股票代码")),
        "name": _text(_pick(row, "SECURITY_NAME_ABBR", "股票简称")),
        "report_date": query.get("report_date"),
        "fund_count": _integer(_pick(row, "HOULD_NUM", "FUND_NUM", "HOLD_FUND_NUM", "持有基金家数")),
        "held_shares": _integer(_pick(row, "TOTAL_SHARES", "HOLD_NUM", "持股总数")),
        "market_value": _number(_pick(row, "HOLD_VALUE", "HOLD_MARKET_CAP", "持股市值")),
        "change_label": _text(_pick(row, "HOLDCHA", "HOLD_CHANGE", "持股变化")),
        "change_shares": _integer(_pick(row, "HOLDCHA_NUM", "HOLD_CHANGE_NUM", "持股变动数值")),
        "change_pct": _number(_pick(row, "HOLDCHA_RATIO", "HOLD_CHANGE_RATIO", "持股变动比例")),
    })


class _EastmoneyReferenceSource:
    name = "eastmoney"
    adapter_version = "1"

    def __init__(self, get: Callable[..., Any] = requests.get):
        self._get = get
        self._lock = threading.Lock()
        self._cache: dict[str, tuple[float, dict[str, Any]]] = {}

    def status(self) -> dict[str, Any]:
        return {
            "status": "READY",
            "provider": self.name,
            "adapter_version": self.adapter_version,
            "capabilities": {
                "dragon_tiger": True,
                "dragon_tiger_seats": True,
                "institutional_dragon_tiger": True,
                "block_trades": True,
                "shareholders": True,
                "fund_holdings": True,
                "money_flow": True,
            },
            "cache_scope": "process",
            "limitations": ["公开网页数据可能随上游接口变化", "席位或资金标签属于数据商口径"],
        }

    @staticmethod
    def _cache_key(dataset: str, params: dict[str, Any]) -> str:
        return json.dumps({"dataset": dataset, "params": params}, ensure_ascii=False, sort_keys=True)

    def _fetch(self, dataset: str, url: str, params: dict[str, Any], *, ttl_seconds: int, page_key: str = "pageNumber") -> dict[str, Any]:
        key = self._cache_key(dataset, params)
        with self._lock:
            entry = self._cache.get(key)
            if entry is not None and time.time() - entry[0] <= ttl_seconds:
                cached = copy.deepcopy(entry[1])
                cached["cache"] = {"hit": True, "ttl_seconds": ttl_seconds}
                return cached
            started = time.perf_counter()
            try:
                response = self._get(url, params={**params, page_key: 1}, timeout=20)
                response.raise_for_status()
                first = response.json()
                if not isinstance(first, dict):
                    raise _ReferenceSourceError("上游返回非对象 JSON")
                rows, pages = self._extract(first)
                for page in range(2, pages + 1):
                    response = self._get(url, params={**params, page_key: page}, timeout=20)
                    response.raise_for_status()
                    payload = response.json()
                    if not isinstance(payload, dict):
                        raise _ReferenceSourceError("上游分页返回非对象 JSON")
                    page_rows, _ = self._extract(payload)
                    rows.extend(page_rows)
            except Exception as exc:  # noqa: BLE001
                raise _ReferenceSourceError(f"{dataset}请求失败: {_safe_exception_text(exc)}") from exc
            payload = {
                "provider": self.name,
                "adapter_version": self.adapter_version,
                "dataset": dataset,
                "endpoint": url,
                "query": params,
                "fetched_at": _now_iso(),
                "latency_ms": round((time.perf_counter() - started) * 1_000, 1),
                "row_count": len(rows),
                "records": rows,
                "cache": {"hit": False, "ttl_seconds": ttl_seconds},
            }
            self._cache[key] = (time.time(), copy.deepcopy(payload))
            return payload

    @staticmethod
    def _extract(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], int]:
        result = payload.get("result")
        if isinstance(result, dict):
            rows = result.get("data") or []
            return [row for row in rows if isinstance(row, dict)], int(result.get("pages") or 1)
        rows = payload.get("sdltgd") or payload.get("data") or []
        if isinstance(rows, dict) and isinstance(rows.get("klines"), list):
            return [{"_kline": item} for item in rows["klines"]], 1
        return ([row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []), int(payload.get("pages") or 1)

    @staticmethod
    def _result(payload: dict[str, Any], records: list[dict[str, Any]], limit: int) -> dict[str, Any]:
        return {
            "status": "OK",
            "updated_at": _now_iso(),
            "source": {
                "provider": payload["provider"],
                "adapter_version": payload["adapter_version"],
                "endpoint": payload["endpoint"],
                "dataset": payload["dataset"],
                "fetched_at": payload["fetched_at"],
                "cache": payload["cache"],
            },
            "query": payload["query"],
            "row_count": len(records),
            "total_provider_rows": payload["row_count"],
            "truncated": len(records) > limit,
            "records": records[:limit],
        }

    def dragon_tiger_list(self, trade_date: str, symbol: str | None = None, limit: int = 100) -> dict[str, Any]:
        trade_date = _validate_date(trade_date, "trade_date")
        limit = _validate_limit(limit)
        day = f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:]}"
        params = {"reportName": "RPT_DAILYBILLBOARD_DETAILSNEW", "columns": "ALL", "source": "WEB", "client": "WEB", "pageSize": 5000, "filter": f"(TRADE_DATE='{day}')"}
        payload = self._fetch("dragon_tiger", DATACENTER_URL, params, ttl_seconds=21_600)
        records = [_canonical_dragon(row, i, {"trade_date": day}) for i, row in enumerate(payload["records"], 1)]
        if symbol:
            code = canonicalize_symbol(symbol)
            records = [row for row in records if row.get("symbol") == code]
        return self._result(payload, records, limit)

    def dragon_tiger_seats(self, symbol: str, trade_date: str, limit: int = 20) -> dict[str, Any]:
        code = canonicalize_symbol(symbol)
        trade_date = _validate_date(trade_date, "trade_date")
        limit = _validate_limit(limit)
        day = f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:]}"
        records: list[dict[str, Any]] = []
        calls: list[dict[str, Any]] = []
        for side, report in (("buy", "RPT_BILLBOARD_DAILYDETAILSBUY"), ("sell", "RPT_BILLBOARD_DAILYDETAILSSELL")):
            params = {"reportName": report, "columns": "ALL", "source": "WEB", "client": "WEB", "pageSize": 500, "filter": f"(TRADE_DATE='{day}')(SECURITY_CODE=\"{code[2:]}\")"}
            payload = self._fetch("dragon_tiger_seats", DATACENTER_URL, params, ttl_seconds=86_400)
            for i, row in enumerate(payload["records"], 1):
                records.append(_compact({
                    "rank": i,
                    "symbol": code,
                    "trade_date": day,
                    "side": side,
                    "seat_name": _text(_pick(row, "OPERATEDEPT_NAME", "OPERATEDEPT_NAME_ABBR", "交易营业部名称")),
                    "buy_amount": _number(_pick(row, "BUY_AMT", "BUY", "买入金额")),
                    "buy_share_pct": _number(_pick(row, "BUY_RATE", "TOTAL_BUYRIO", "买入金额-占总成交比例")),
                    "sell_amount": _number(_pick(row, "SELL_AMT", "SELL", "卖出金额")),
                    "sell_share_pct": _number(_pick(row, "SELL_RATE", "TOTAL_SELLRIO", "卖出金额-占总成交比例")),
                    "net_amount": _number(_pick(row, "NET_AMT", "NET", "净额")),
                    "reason": _text(_pick(row, "EXPLAIN", "TYPE", "类型")),
                }))
            calls.append({"side": side, "cache": payload["cache"], "fetched_at": payload["fetched_at"]})
        result = self._result({"provider": self.name, "adapter_version": self.adapter_version, "endpoint": DATACENTER_URL, "dataset": "dragon_tiger_seats", "fetched_at": _now_iso(), "cache": {"calls": calls}, "query": {"symbol": code, "trade_date": day}, "row_count": len(records)}, records, limit)
        result["source"]["calls"] = calls
        return result

    def institutional_dragon_tiger(self, start_date: str, end_date: str, symbol: str | None = None, limit: int = 100) -> dict[str, Any]:
        start_date, end_date = _validate_range(start_date, end_date)
        limit = _validate_limit(limit)
        start = f"{start_date[:4]}-{start_date[4:6]}-{start_date[6:]}"
        end = f"{end_date[:4]}-{end_date[4:6]}-{end_date[6:]}"
        params = {"reportName": "RPT_ORGANIZATION_TRADE_DETAILS", "columns": "ALL", "source": "WEB", "client": "WEB", "pageSize": 500, "filter": f"(TRADE_DATE>='{start}')(TRADE_DATE<='{end}')"}
        payload = self._fetch("institutional_dragon_tiger", DATACENTER_URL, params, ttl_seconds=21_600)
        records = [_canonical_institution(row, i, {}) for i, row in enumerate(payload["records"], 1)]
        if symbol:
            code = canonicalize_symbol(symbol)
            records = [row for row in records if row.get("symbol") == code]
        return self._result(payload, records, limit)

    def block_trades(self, start_date: str, end_date: str, category: str = "A股", symbol: str | None = None, limit: int = 100) -> dict[str, Any]:
        start_date, end_date = _validate_range(start_date, end_date)
        limit = _validate_limit(limit)
        category_map = {"A股": 1, "B股": 2, "基金": 3, "债券": 4}
        if category not in category_map:
            raise ValueError("category必须是A股、B股、基金或债券")
        start = f"{start_date[:4]}-{start_date[4:6]}-{start_date[6:]}"
        end = f"{end_date[:4]}-{end_date[4:6]}-{end_date[6:]}"
        params = {"reportName": "RPT_DATA_BLOCKTRADE", "columns": "ALL", "source": "WEB", "client": "WEB", "pageSize": 5000, "filter": f"(SECURITY_TYPE_WEB={category_map[category]})(TRADE_DATE>='{start}')(TRADE_DATE<='{end}')"}
        payload = self._fetch("block_trades", DATACENTER_URL, params, ttl_seconds=21_600)
        records = [_canonical_block(row, i, {}) for i, row in enumerate(payload["records"], 1)]
        if symbol:
            code = canonicalize_symbol(symbol)
            records = [row for row in records if row.get("symbol") == code]
        return self._result(payload, records, limit)

    def top_float_shareholders(self, symbol: str, report_date: str, limit: int = 20) -> dict[str, Any]:
        code = canonicalize_symbol(symbol)
        report_date = _validate_date(report_date, "report_date")
        limit = _validate_limit(limit)
        params = {"code": f"{_market_prefix(code[2:]).upper()}{code[2:]}", "date": f"{report_date[:4]}-{report_date[4:6]}-{report_date[6:]}"}
        payload = self._fetch("shareholders", SHAREHOLDER_URL, params, ttl_seconds=86_400, page_key="page")
        records = [_canonical_shareholder(row, i, {"symbol": code, "report_date": report_date}) for i, row in enumerate(payload["records"], 1)]
        return self._result(payload, records, limit)

    def fund_holdings(self, report_date: str, symbol: str | None = None, limit: int = 100) -> dict[str, Any]:
        report_date = _validate_date(report_date, "report_date")
        limit = _validate_limit(limit)
        date_text = f"{report_date[:4]}-{report_date[4:6]}-{report_date[6:]}"
        params = {"date": date_text, "type": 1, "zjc": 0, "sortField": "HOULD_NUM", "sortDirec": 1, "pageSize": 500}
        payload = self._fetch("fund_holdings", FUND_HOLDING_URL, params, ttl_seconds=86_400, page_key="pageNum")
        records = [_canonical_fund(row, i, {"report_date": report_date}) for i, row in enumerate(payload["records"], 1)]
        if symbol:
            code = canonicalize_symbol(symbol)
            records = [row for row in records if row.get("symbol") == code]
        return self._result(payload, records, limit)

    def money_flow(self, symbol: str, limit: int = 100) -> dict[str, Any]:
        code = canonicalize_symbol(symbol)
        limit = _validate_limit(limit)
        market = _market_prefix(code[2:])
        params = {"lmt": 0, "klt": 101, "secid": f"{1 if market == 'sh' else 0}.{code[2:]}", "fields1": "f1,f2,f3,f7", "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65"}
        payload = self._fetch("money_flow", MONEY_FLOW_URL, params, ttl_seconds=300)
        records: list[dict[str, Any]] = []
        for raw in payload["records"]:
            values = str(raw.get("_kline") or "").split(",")
            if len(values) < 13:
                continue
            records.append(_compact({
                "symbol": code,
                "trade_date": _date_text(values[0]),
                "close": _number(values[11]),
                "change_pct": _number(values[12]),
                "main_net_amount": _number(values[1]), "main_net_pct": _number(values[6]),
                "super_large_net_amount": _number(values[5]), "super_large_net_pct": _number(values[10]),
                "large_net_amount": _number(values[4]), "large_net_pct": _number(values[9]),
                "medium_net_amount": _number(values[3]), "medium_net_pct": _number(values[8]),
                "small_net_amount": _number(values[2]), "small_net_pct": _number(values[7]),
            }))
        return self._result(payload, records, limit)


_source: _EastmoneyReferenceSource | None = None
_source_lock = threading.Lock()


def _get_reference_source() -> _EastmoneyReferenceSource:
    global _source
    with _source_lock:
        if _source is None:
            _source = _EastmoneyReferenceSource()
        return _source
