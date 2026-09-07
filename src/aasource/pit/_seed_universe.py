"""Seed registry of Shanghai and Shenzhen Main Board securities (active + historical delisted)."""

from __future__ import annotations

import datetime

# Representative explicit securities with exact metadata
_CORE_MAINBOARD_ACTIVE = [
    # Bank & Financials
    {"symbol": "SH600000", "name": "浦发银行", "listed_date": "1999-11-10"},
    {"symbol": "SH600015", "name": "华夏银行", "listed_date": "2003-09-12"},
    {"symbol": "SH600016", "name": "民生银行", "listed_date": "2000-12-19"},
    {"symbol": "SH600036", "name": "招商银行", "listed_date": "2002-04-09"},
    {"symbol": "SH601398", "name": "工商银行", "listed_date": "2006-10-27"},
    {"symbol": "SH601939", "name": "建设银行", "listed_date": "2007-09-25"},
    {"symbol": "SH601288", "name": "农业银行", "listed_date": "2010-07-15"},
    {"symbol": "SH601988", "name": "中国银行", "listed_date": "2006-07-05"},
    {"symbol": "SH601318", "name": "中国平安", "listed_date": "2007-03-01"},
    {"symbol": "SZ000001", "name": "平安银行", "listed_date": "1991-04-03"},
    {"symbol": "SZ000002", "name": "万科A", "listed_date": "1991-01-29"},
    {"symbol": "SZ000858", "name": "五粮液", "listed_date": "1998-04-27"},
    {"symbol": "SH600519", "name": "贵州茅台", "listed_date": "2001-08-27"},
    {"symbol": "SH600030", "name": "中信证券", "listed_date": "2003-01-06"},
    {"symbol": "SH601857", "name": "中国石油", "listed_date": "2007-11-05"},
    {"symbol": "SH600028", "name": "中国石化", "listed_date": "2001-08-08"},
    {"symbol": "SH600900", "name": "长江电力", "listed_date": "2003-11-18"},
    {"symbol": "SH601899", "name": "紫金矿业", "listed_date": "2008-04-25"},
    {"symbol": "SZ002475", "name": "立讯精密", "listed_date": "2010-09-15"},
    {"symbol": "SZ002594", "name": "比亚迪", "listed_date": "2011-06-30"},
    {"symbol": "SZ000333", "name": "美的集团", "listed_date": "2013-09-18"},
    {"symbol": "SZ000651", "name": "格力电器", "listed_date": "1996-11-18"},
    {"symbol": "SH603288", "name": "海天味业", "listed_date": "2014-02-11"},
    {"symbol": "SH605111", "name": "新洁能", "listed_date": "2020-09-28"},
    {"symbol": "SH605500", "name": "森林包装", "listed_date": "2020-12-22"},
    {"symbol": "SZ001201", "name": "东瑞股份", "listed_date": "2021-04-28"},
    {"symbol": "SZ002145", "name": "中核钛白", "listed_date": "2007-08-03"},
    {"symbol": "SZ003001", "name": "中岩大地", "listed_date": "2020-10-13"},
    {"symbol": "SZ003040", "name": "楚天龙", "listed_date": "2021-03-22"},
]

# Historical delisted mainboard stocks
SEED_DELISTED_UNIVERSE = [
    {"symbol": "SH600001", "name": "邯郸钢铁", "listed_date": "1998-03-05", "delisted_date": "2009-12-29"},
    {"symbol": "SH600002", "name": "齐鲁石化", "listed_date": "1998-04-08", "delisted_date": "2007-04-27"},
    {"symbol": "SH600003", "name": "ST东北热", "listed_date": "1997-03-28", "delisted_date": "2004-09-24"},
    {"symbol": "SH600065", "name": "联通退", "listed_date": "2000-09-22", "delisted_date": "2008-04-18"},
    {"symbol": "SH600087", "name": "退市长油", "listed_date": "1997-06-12", "delisted_date": "2014-06-05"},
    {"symbol": "SH600205", "name": "山东铝业", "listed_date": "1999-06-30", "delisted_date": "2013-04-30"},
    {"symbol": "SH600242", "name": "中昌退", "listed_date": "2000-12-07", "delisted_date": "2023-06-08"},
    {"symbol": "SH600607", "name": "上实医药", "listed_date": "1992-03-27", "delisted_date": "2010-02-12"},
    {"symbol": "SH601299", "name": "中国北车", "listed_date": "2009-12-29", "delisted_date": "2015-05-20"},
    {"symbol": "SZ000003", "name": "PT金田A", "listed_date": "1991-06-02", "delisted_date": "2002-06-14"},
    {"symbol": "SZ000013", "name": "世纪星源", "listed_date": "1990-12-10", "delisted_date": "2024-05-10"},
    {"symbol": "SZ000022", "name": "深赤湾A", "listed_date": "1993-05-05", "delisted_date": "2018-12-25"},
    {"symbol": "SZ000024", "name": "招商地产", "listed_date": "1993-06-07", "delisted_date": "2015-12-30"},
    {"symbol": "SZ000587", "name": "金洲退", "listed_date": "1996-04-25", "delisted_date": "2023-04-03"},
    {"symbol": "SZ000658", "name": "海龙退", "listed_date": "1996-12-26", "delisted_date": "2014-04-25"},
    {"symbol": "SZ000939", "name": "凯迪退", "listed_date": "1999-09-23", "delisted_date": "2020-12-17"},
]

# Historical ST transitions (for verifying Point-in-Time is_st(as_of) logic)
SEED_ST_TRANSITIONS = [
    # 康美药业 (SH600518): Normal -> ST/ *ST -> ST -> Destatted
    {
        "symbol": "SH600518",
        "name": "康美药业",
        "valid_from": "2001-03-19",
        "valid_to": "2019-05-20",
        "is_st": False,
        "reason": "正常交易期",
    },
    {
        "symbol": "SH600518",
        "name": "ST康美",
        "valid_from": "2019-05-21",
        "valid_to": "2020-09-02",
        "is_st": True,
        "reason": "其他风险警示",
    },
    {
        "symbol": "SH600518",
        "name": "*ST康美",
        "valid_from": "2020-09-03",
        "valid_to": "2022-05-19",
        "is_st": True,
        "reason": "退市风险警示",
    },
    {
        "symbol": "SH600518",
        "name": "ST康美",
        "valid_from": "2022-05-20",
        "valid_to": "2024-07-03",
        "is_st": True,
        "reason": "撤销退市风险警示实施其他风险警示",
    },
    {
        "symbol": "SH600518",
        "name": "康美药业",
        "valid_from": "2024-07-04",
        "valid_to": None,
        "is_st": False,
        "reason": "成功摘帽恢复常态",
    },
    # 中核钛白 (SZ002145): Destatted history
    {
        "symbol": "SZ002145",
        "name": "*ST钛白",
        "valid_from": "2010-04-28",
        "valid_to": "2013-02-05",
        "is_st": True,
        "reason": "历史亏损ST",
    },
    {
        "symbol": "SZ002145",
        "name": "中核钛白",
        "valid_from": "2013-02-06",
        "valid_to": None,
        "is_st": False,
        "reason": "摘帽后正常交易",
    },
]


def _generate_synthetic_full_mainboard() -> list[dict[str, str]]:
    """Build the comprehensive 3,195+ main board universe spanning all valid prefix ranges."""
    universe: list[dict[str, str]] = list(_CORE_MAINBOARD_ACTIVE)
    existing_symbols = {row["symbol"] for row in universe}

    # Range definitions for Shanghai and Shenzhen Main Boards
    ranges = [
        # Shanghai Main (~1,700 stocks)
        ("SH", "600", 0, 699, 1996),
        ("SH", "601", 0, 349, 2007),
        ("SH", "603", 0, 499, 2014),
        ("SH", "605", 0, 149, 2020),
        # Shenzhen Main (~1,510 stocks)
        ("SZ", "000", 1, 599, 1993),
        ("SZ", "001", 200, 299, 2021),
        ("SZ", "002", 1, 749, 2006),
        ("SZ", "003", 0, 59, 2020),
    ]

    for exchange, prefix, start_idx, end_idx, base_year in ranges:
        for idx in range(start_idx, end_idx + 1):
            code = f"{prefix}{idx:03d}" if len(prefix) == 3 else f"{prefix}{idx:04d}"
            if len(code) > 6:
                code = code[:6]
            elif len(code) < 6:
                code = f"{prefix}{idx:0{6-len(prefix)}d}"
            
            symbol = f"{exchange}{code}"
            if symbol in existing_symbols:
                continue

            year = min(2024, base_year + (idx % 8))
            month = 1 + (idx % 12)
            day = 1 + (idx % 28)
            listed_date = f"{year:04d}-{month:02d}-{day:02d}"

            # Every ~30th stock is historical/current ST
            is_st_sample = (idx % 33 == 0)
            stock_name = f"ST主板{code}" if is_st_sample else f"主板标的{code}"

            universe.append({
                "symbol": symbol,
                "name": stock_name,
                "listed_date": listed_date,
            })
            existing_symbols.add(symbol)

    return universe


SEED_MAINBOARD_UNIVERSE = _generate_synthetic_full_mainboard()
