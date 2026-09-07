"""THS (同花顺 10jqka) concept boards: board list and per-stock concept themes.

The board list needs the hexin-v cookie that 同花顺's q.10jqka.com.cn pages
require; it is produced by executing the vendored obfuscated ``ths.js`` with
``py_mini_racer`` (optional dependency). Per-stock concept pages on
``basic.10jqka.com.cn`` are plain GBK HTML reachable without the cookie.
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any

import requests

from aasource.domain.errors import AshareDataError, ErrorCode
from aasource.domain.identifiers import canonicalize_symbol

THS_JS_PATH = Path(__file__).parent / "vendor" / "ths.js"
GN_CATEGORY_URL = "https://q.10jqka.com.cn/gn/detail/code/307822/"
STOCK_CONCEPT_URL = "https://basic.10jqka.com.cn/{code}/concept.html"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)
_CATE_HREF = re.compile(
    r'href="(?:https?://q\.10jqka\.com\.cn)?/gn/detail/code/(\d+)/"[^>]*>([^<]+)</a>'
)
_GBK_CELL_ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.DOTALL)
_GBK_CELL = re.compile(r"<td[^>]*>(.*?)</td>", re.DOTALL)
_TAG = re.compile(r"<[^>]+>")


class ThsProviderError(RuntimeError):
    pass


def _get_retry(url: str, *, tries: int = 3, headers: dict[str, str], timeout: float = 15.0) -> requests.Response:
    last: Exception | None = None
    for attempt in range(tries):
        try:
            response = requests.get(url, headers=headers, timeout=timeout)
            if response.status_code == 200:
                return response
            last = ThsProviderError(f"{url} -> HTTP {response.status_code}")
        except (requests.RequestException, OSError) as exc:
            last = exc
        time.sleep(1.0 + attempt)
    raise ThsProviderError(f"{url} failed after {tries} attempts: {last}") from last


def _hexin_v() -> str:
    try:
        from py_mini_racer import MiniRacer
    except ImportError as exc:  # pragma: no cover - depends on optional install
        raise AshareDataError(
            ErrorCode.CAPABILITY_NOT_AVAILABLE,
            "THS board list needs the optional 'py_mini_racer' dependency (pip install py_mini_racer); "
            "per-stock THS concepts and SW/EM sources work without it",
        ) from exc
    context = MiniRacer()
    context.eval(THS_JS_PATH.read_text(encoding="utf-8"))
    return str(context.call("v"))


def _concept_rows_from_table(table_html: str) -> list[str]:
    """Extract concept names from a THS F10 concept table.

    Data rows start with a numeric 序号 cell; the interleaved rows carry the
    long 概念解析 text and are skipped.
    """
    names: list[str] = []
    for row in _GBK_CELL_ROW.findall(table_html):
        cells = [_TAG.sub("", cell).strip() for cell in _GBK_CELL.findall(row)]
        if len(cells) >= 2 and cells[0].isdigit():
            name = cells[1].strip()
            if name and name not in names:
                names.append(name)
    return names


def fetch_ths_concept_boards() -> list[dict[str, Any]]:
    """Return the full THS concept board list [{board_code, name, source, url}]."""
    response = _get_retry(
        GN_CATEGORY_URL,
        headers={"User-Agent": USER_AGENT, "Cookie": f"v={_hexin_v()}", "Referer": "https://q.10jqka.com.cn/"},
        timeout=20,
    )
    response.encoding = "gbk"
    pairs = _CATE_HREF.findall(response.text)
    if not pairs:
        raise ThsProviderError("THS gn category page returned no concept links (schema changed?)")
    boards: dict[str, dict[str, Any]] = {}
    for code, name in pairs:
        name = name.strip()
        if not name or code in boards:
            continue
        boards[code] = {
            "board_code": code,
            "name": name,
            "source": "ths",
            "url": f"https://q.10jqka.com.cn/gn/detail/code/{code}/",
        }
    return list(boards.values())


def fetch_ths_stock_concepts(symbol: str) -> dict[str, Any]:
    """Return per-stock THS concept memberships plus company-specific themes."""
    code = canonicalize_symbol(symbol)
    response = _get_retry(
        STOCK_CONCEPT_URL.format(code=code[2:]),
        headers={"User-Agent": USER_AGENT, "Referer": "https://basic.10jqka.com.cn/"},
        timeout=20,
    )
    response.encoding = "gbk"
    tables = re.findall(r"<table[^>]*>(.*?)</table>", response.text, re.DOTALL)
    if not tables:
        raise ThsProviderError(f"THS concept page for {code} has no tables (blocked or schema changed)")
    concepts = _concept_rows_from_table(tables[0])
    company_themes = _concept_rows_from_table(tables[1]) if len(tables) > 1 else []
    if not concepts:
        raise ThsProviderError(f"THS concept page for {code} returned no concept rows")
    return {
        "symbol": code,
        "concepts": [{"name": name, "relation_type": "concept", "source": "ths"} for name in concepts],
        "company_themes": [
            {"name": name, "relation_type": "company_theme", "source": "ths"} for name in company_themes
        ],
    }
