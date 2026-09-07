"""Shenwan (申万) 2021 industry classification, sourced from legulegu.com.

Provides the formal industry ladder (L1/L2/L3) as a counterpart to the
Eastmoney "market-facing" board taxonomy: per-stock L1-L3 assignment via the
stock page breadcrumb, the full three-level industry tree from the overview
page, and per-industry constituent lists.
"""

from __future__ import annotations

import re
import time
from typing import Any

import requests

from aasource.domain.errors import AshareDataError, ErrorCode
from aasource.domain.identifiers import canonicalize_symbol

SW_OVERVIEW_URL = "https://legulegu.com/stockdata/sw-industry-overview"
SW_STOCK_URL = "https://legulegu.com/s/{symbol}"
SW_COMPOSITION_URL = "https://legulegu.com/stockdata/index-composition?industryCode={code}"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)
_SW_CODE = re.compile(r"[\dA-Z]{6}\.SI")
_ITEM_TITLE = re.compile(r'lg-industries-item-chinese-title">\s*([^<]+?)\s*<')
_ITEM_NUMBER = re.compile(r'lg-industries-item-number">\s*([^<]+?)\s*<')
_BREADCRUMB_ANCHOR = re.compile(
    r'class="industry-name"[^>]*href="/stockdata/sw-industry-2021\?industryCode=([\dA-Z]+\.SI)"\s*>'
    r"\s*(III|II|I)\s*([^<]+?)\s*</a>",
    re.DOTALL,
)
_TABLE_ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.DOTALL)
_TABLE_CELL = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.DOTALL)
_TAG = re.compile(r"<[^>]+>")
_LEVEL_NAME = {"1": "l1", "2": "l2", "3": "l3"}


class SwProviderError(RuntimeError):
    pass


def _get_retry(url: str, *, tries: int = 3, timeout: float = 25.0) -> requests.Response:
    last: Exception | None = None
    for attempt in range(tries):
        try:
            response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
            if response.status_code == 200:
                return response
            last = SwProviderError(f"{url} -> HTTP {response.status_code}")
        except (requests.RequestException, OSError) as exc:
            last = exc
        time.sleep(1.0 + attempt)
    raise SwProviderError(f"{url} failed after {tries} attempts: {last}") from last


def _cells(row_html: str) -> list[str]:
    return [_TAG.sub("", cell).strip() for cell in _TABLE_CELL.findall(row_html)]


def fetch_sw_industry_tree() -> dict[str, Any]:
    """Return the full Shenwan 2021 tree: L1/L2/L3 [{industry_code, name, member_count}]."""
    response = _get_retry(SW_OVERVIEW_URL)
    response.encoding = "utf-8"
    text = response.text
    anchors = [(m.start(), level) for level in (1, 2, 3) if (m := re.search(rf'id="level{level}Items"', text))]
    if len(anchors) < 3:
        raise SwProviderError("SW overview page missing level item containers")
    slices: dict[int, str] = {}
    for index, (pos, level) in enumerate(anchors):
        end = anchors[index + 1][0] if index + 1 < len(anchors) else len(text)
        slices[level] = text[pos:end]
    levels: dict[str, list[dict[str, Any]]] = {}
    for level, chunk in slices.items():
        codes = _ITEM_TITLE.findall(chunk)
        numbers = _ITEM_NUMBER.findall(chunk)
        rows: list[dict[str, Any]] = []
        for code, number in zip(codes, numbers):
            code = code.strip()
            if not _SW_CODE.fullmatch(code):
                continue
            name, _, count = number.partition("(")
            rows.append(
                {
                    "industry_code": code,
                    "name": name.strip(),
                    "member_count": int(re.sub(r"\D", "", count) or 0) or None,
                    "level": int(level),
                    "source": "sw",
                }
            )
        if rows:
            levels[_LEVEL_NAME[str(level)]] = rows
    if not levels.get("l1"):
        raise SwProviderError("SW overview page returned no L1 industries (schema changed?)")
    return {"levels": levels, "source": "sw", "classification": "SW2021"}


def fetch_sw_stock_industry(symbol: str) -> dict[str, Any]:
    """Return per-stock Shenwan L1-L3 assignment from the stock page breadcrumb."""
    code = canonicalize_symbol(symbol)
    response = _get_retry(SW_STOCK_URL.format(symbol=code[2:]))
    response.encoding = "utf-8"
    ladder: dict[str, dict[str, Any] | None] = {"l1": None, "l2": None, "l3": None}
    for industry_code, roman, name in _BREADCRUMB_ANCHOR.findall(response.text):
        slot = _LEVEL_NAME[str(len(roman))]
        ladder[slot] = {"industry_code": industry_code, "name": name.strip()}
    if not ladder["l1"]:
        raise SwProviderError(f"SW stock page for {code} has no industry breadcrumb (blocked or new listing)")
    return {"symbol": code, "sw_industry": ladder, "source": "sw", "classification": "SW2021"}


def fetch_sw_industry_members(industry_code: str, *, limit: int = 1000) -> list[dict[str, Any]]:
    """Return constituents of one Shenwan industry code (801xxx.SI / 850xxx.SI)."""
    code = str(industry_code or "").strip().upper()
    if not _SW_CODE.fullmatch(code):
        raise AshareDataError(ErrorCode.INVALID_REQUEST, f"Invalid SW industry code: {industry_code!r}")
    response = _get_retry(SW_COMPOSITION_URL.format(code=code))
    response.encoding = "utf-8"
    members: list[dict[str, Any]] = []
    for row in _TABLE_ROW.findall(response.text):
        cells = _cells(row)
        if len(cells) < 5 or not re.fullmatch(r"\d{6}\.(SH|SZ|BJ)", cells[1] or ""):
            continue
        if len(members) >= limit:
            break
        bare = cells[1][:6]
        try:
            symbol = canonicalize_symbol(bare)
        except Exception:
            continue
        members.append(
            {
                "symbol": symbol,
                "name": cells[2],
                "inclusion_date": cells[3] or None,
                "industry_name": cells[4] or None,
                "industry_code": code,
                "source": "sw",
            }
        )
    if not members:
        raise SwProviderError(f"SW composition page for {code} returned no members")
    return members
