"""Eastmoney board/sector facts, including reverse stock memberships."""

from __future__ import annotations

import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import requests

from ashare_data.domain.identifiers import canonicalize_symbol
from ashare_data.domain.sectors import canonicalize_sector_id, eastmoney_sector_secid
from ashare_data.providers.eastmoney import EastmoneyProviderError, UT, _get_json, _number

CLIST_URL = "https://push2.eastmoney.com/api/qt/clist/get"
CLIST_FALLBACK = "https://push2delay.eastmoney.com/api/qt/clist/get"
TRENDS_URL = "https://push2his.eastmoney.com/api/qt/stock/trends2/get"
KLINE_URL = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
CORE_CONCEPTION_URL = "https://emweb.securities.eastmoney.com/PC_HSF10/CoreConception/PageAjax"

BOARD_FIELDS = "f12,f14,f2,f3,f6,f8,f62,f104,f105,f128,f140"
MEMBER_FIELDS = "f12,f14,f2,f3,f6,f8,f10,f15,f16,f17,f18,f20,f21,f62"
STOCK_SIGNAL_FIELDS = "f12,f14,f3,f6,f8,f10,f22,f24,f25,f100,f109"
FULL_A_FS = "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23"

KIND_FS = {
    "industry": "m:90+t:2",
    "concept": "m:90+t:3",
}


def _clist_get(params: dict[str, Any]) -> dict[str, Any]:
    try:
        return _get_json(CLIST_URL, params, timeout=20)
    except (EastmoneyProviderError, requests.RequestException):
        return _get_json(CLIST_FALLBACK, params, timeout=20)


def _diff_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    diff = data.get("diff")
    if isinstance(diff, list):
        return [row for row in diff if isinstance(row, dict)]
    if isinstance(diff, dict):
        return [row for row in diff.values() if isinstance(row, dict)]
    return []


def _paged_clist(base_params: dict[str, Any], *, desired: int, page_size: int = 100) -> list[dict[str, Any]]:
    desired = max(1, min(int(desired), 10_000))
    page_size = max(1, min(page_size, 100))
    first_params = {**base_params, "pn": 1, "pz": page_size}
    first = _clist_get(first_params)
    rows = _diff_rows(first)
    data = first.get("data") if isinstance(first.get("data"), dict) else {}
    total = int(_number(data.get("total")) or len(rows))
    need = min(desired, total)
    if len(rows) >= need:
        return rows[:need]
    pages = math.ceil(need / page_size)
    out = list(rows)
    with ThreadPoolExecutor(max_workers=16) as pool:
        futures = {
            pool.submit(_clist_get, {**base_params, "pn": page, "pz": page_size}): page
            for page in range(2, pages + 1)
        }
        page_rows: dict[int, list[dict[str, Any]]] = {}
        for fut in as_completed(futures):
            page = futures[fut]
            page_rows[page] = _diff_rows(fut.result())
    for page in sorted(page_rows):
        out.extend(page_rows[page])
        if len(out) >= need:
            break
    return out[:need]


def _map_board(row: dict[str, Any], kind: str) -> dict[str, Any]:
    code = str(row.get("f12") or "").upper()
    up = int(_number(row.get("f104")) or 0)
    down = int(_number(row.get("f105")) or 0)
    breadth = (up / (up + down)) if (up + down) else None
    return {
        "sector_id": code,
        "board_code": code,
        "board_name": row.get("f14"),
        "name": row.get("f14"),
        "kind": kind,
        "change_pct": _number(row.get("f3")),
        "index": _number(row.get("f2")),
        "amount": _number(row.get("f6")),
        "turnover_rate": _number(row.get("f8")),
        "main_net_flow": _number(row.get("f62")),
        "up_count": up,
        "down_count": down,
        "breadth": round(breadth, 4) if breadth is not None else None,
        "leader_name": row.get("f128"),
        "leader_code": str(row.get("f140") or "") or None,
    }


def _map_member(row: dict[str, Any]) -> dict[str, Any]:
    code = str(row.get("f12") or "").zfill(6)[-6:]
    symbol = None
    try:
        symbol = canonicalize_symbol(code) if code else None
    except Exception:
        symbol = None
    return {
        "symbol": symbol,
        "code": code,
        "name": row.get("f14"),
        "price": _number(row.get("f2")),
        "last": _number(row.get("f2")),
        "change_pct": _number(row.get("f3")),
        "amount": _number(row.get("f6")),
        "turnover_rate": _number(row.get("f8")),
        "volume_ratio": _number(row.get("f10")),
        "high": _number(row.get("f15")),
        "low": _number(row.get("f16")),
        "open": _number(row.get("f17")),
        "previous_close": _number(row.get("f18")),
        "market_cap": _number(row.get("f20")),
        "float_market_cap": _number(row.get("f21")),
        "main_net_flow": _number(row.get("f62")),
    }


def fetch_board_rankings(kind: str = "industry", *, limit: int = 100) -> list[dict[str, Any]]:
    if kind not in KIND_FS:
        raise ValueError(f"unsupported board kind: {kind}")
    params = {
        "fs": KIND_FS[kind],
        "fields": BOARD_FIELDS,
        "po": 1,
        "fid": "f3",
        "fltt": 2,
        "np": 1,
        "ut": UT,
    }
    rows = _paged_clist(params, desired=limit)
    return [_map_board(row, kind) for row in rows]


def fetch_board_members(sector_id: str, *, limit: int = 500) -> list[dict[str, Any]]:
    sector_id = canonicalize_sector_id(sector_id)
    params = {
        "fs": f"b:{sector_id}+f:!50",
        "fields": MEMBER_FIELDS,
        "po": 1,
        "fid": "f3",
        "fltt": 2,
        "np": 1,
        "ut": UT,
    }
    rows = _paged_clist(params, desired=limit)
    return [_map_member(row) for row in rows]


def _membership_type(row: dict[str, Any]) -> str:
    rank = int(_number(row.get("BOARD_RANK")) or 0)
    name = str(row.get("BOARD_NAME") or "")
    if rank and rank <= 3:
        return "industry"
    if str(row.get("IS_PRECISE") or "") == "1":
        return "concept"
    if name.endswith("板块"):
        return "region"
    return "tag"


def fetch_stock_memberships(symbol: str) -> dict[str, Any]:
    """Return canonical current memberships for one stock without board fan-out."""
    canonical = canonicalize_symbol(symbol)
    payload = _get_json(CORE_CONCEPTION_URL, {"code": canonical}, timeout=20)
    rows = payload.get("ssbk")
    if not isinstance(rows, list):
        raise EastmoneyProviderError(f"core conception schema invalid for {canonical}")
    memberships: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("BOARD_NAME") or "").strip()
        board_code = str(row.get("BOARD_CODE") or "").strip()
        if not name or not board_code:
            continue
        memberships.append(
            {
                "name": name,
                "relation_type": _membership_type(row),
                "source_id": board_code,
                "rank": int(_number(row.get("BOARD_RANK")) or 0) or None,
                "precise": str(row.get("IS_PRECISE") or "") == "1",
            }
        )
    return {"symbol": canonical, "memberships": memberships}


def fetch_stock_signal_rows() -> list[dict[str, Any]]:
    """Fetch one full-A supplemental cross-section for deterministic discovery facts."""
    rows = _paged_clist(
        {
            "fs": FULL_A_FS,
            "fields": STOCK_SIGNAL_FIELDS,
            "po": 1,
            "fid": "f3",
            "fltt": 2,
            "invt": 2,
            "np": 1,
            "ut": UT,
        },
        desired=10_000,
    )
    out: list[dict[str, Any]] = []
    for row in rows:
        code = str(row.get("f12") or "").zfill(6)[-6:]
        try:
            symbol = canonicalize_symbol(code)
        except Exception:
            continue
        out.append(
            {
                "symbol": symbol,
                "name": row.get("f14"),
                "change_pct": _number(row.get("f3")),
                "amount": _number(row.get("f6")),
                "turnover_rate": _number(row.get("f8")),
                "volume_ratio": _number(row.get("f10")),
                "change_speed": _number(row.get("f22")),
                "change_pct_5d": _number(row.get("f109")),
                "change_pct_60d": _number(row.get("f24")),
                "change_pct_ytd": _number(row.get("f25")),
                "industry": row.get("f100"),
            }
        )
    return out


def fetch_minute_trends(secid: str, *, trading_date: str | None = None, ndays: int = 5) -> dict[str, Any]:
    ndays = max(1, min(int(ndays), 5))
    payload = _get_json(
        TRENDS_URL,
        {
            "fields1": "f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58",
            "ut": UT,
            "ndays": ndays,
            "iscr": 0,
            "secid": secid,
        },
        timeout=20,
    )
    data = payload.get("data") if isinstance(payload.get("data"), dict) else None
    if data is None:
        raise EastmoneyProviderError(f"trends2 empty for {secid}")
    rows: list[dict[str, Any]] = []
    for item in data.get("trends") or []:
        parts = str(item).split(",")
        if len(parts) < 8:
            continue
        day = parts[0][:10]
        if trading_date and day != trading_date:
            continue
        rows.append(
            {
                "ts": parts[0].replace(" ", "T") + "+08:00" if " " in parts[0] else parts[0],
                "time": parts[0],
                "open": _number(parts[1]),
                "close": _number(parts[2]),
                "high": _number(parts[3]),
                "low": _number(parts[4]),
                "volume": _number(parts[5]),
                "amount": _number(parts[6]),
                "average": _number(parts[7]),
            }
        )
    return {
        "secid": secid,
        "preclose": _number(data.get("prePrice")),
        "rows": rows,
        "provider": "eastmoney",
    }


def fetch_sector_minute(sector_id: str, *, trading_date: str | None = None, ndays: int = 5) -> dict[str, Any]:
    sector_id = canonicalize_sector_id(sector_id)
    payload = fetch_minute_trends(eastmoney_sector_secid(sector_id), trading_date=trading_date, ndays=ndays)
    payload["sector_id"] = sector_id
    return payload


def _map_sector_daily_kline(item: Any) -> dict[str, Any] | None:
    parts = str(item).split(",")
    if len(parts) < 7:
        return None
    trade_date = parts[0]
    return {
        "trade_date": trade_date,
        "ts": f"{trade_date}T15:00:00+08:00",
        "open": _number(parts[1]),
        "close": _number(parts[2]),
        "high": _number(parts[3]),
        "low": _number(parts[4]),
        "volume": int(value) if (value := _number(parts[5])) is not None else None,
        "amount": _number(parts[6]),
    }


def fetch_sector_daily(
    sector_id: str,
    *,
    start: str | None = None,
    end: str | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """Fetch unadjusted daily board OHLCV and keep vendor fields behind this adapter."""
    sector_id = canonicalize_sector_id(sector_id)
    payload = _get_json(
        KLINE_URL,
        {
            "secid": eastmoney_sector_secid(sector_id),
            "fields1": "f1,f2,f3,f4,f5,f6",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
            "klt": 101,
            "fqt": 0,
            "beg": (start or "19900101").replace("-", ""),
            "end": (end or "20500101").replace("-", ""),
            "lmt": max(1, min(int(limit or 10_000), 10_000)),
            "ut": UT,
        },
        timeout=20,
    )
    data = payload.get("data") if isinstance(payload.get("data"), dict) else None
    if data is None:
        raise EastmoneyProviderError(f"sector daily kline empty for {sector_id}")
    rows = [mapped for item in data.get("klines") or [] if (mapped := _map_sector_daily_kline(item))]
    if start:
        rows = [row for row in rows if row["trade_date"] >= start]
    if end:
        rows = [row for row in rows if row["trade_date"] <= end]
    if limit is not None and limit > 0:
        rows = rows[-limit:]
    return {
        "sector_id": sector_id,
        "name": data.get("name"),
        "rows": rows,
        "provider": "eastmoney",
    }
