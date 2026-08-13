# AAsource

A 股行情命令行工具，面向 Agent 和脚本，统一返回 JSON。

[![CI](https://github.com/The-R0/AAsource/actions/workflows/test.yml/badge.svg)](https://github.com/The-R0/AAsource/actions/workflows/test.yml)
[![Python](https://img.shields.io/badge/Python-3.11%20%7C%203.12-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

## 安装

需要 Python 3.11 或 3.12。下面这条命令不要求本机安装 Git：

```bash
python -m pip install --no-cache-dir https://github.com/The-R0/AAsource/archive/refs/heads/main.zip
```

如果使用 `pipx`：

```bash
pipx install --pip-args=--no-cache-dir https://github.com/The-R0/AAsource/archive/refs/heads/main.zip
```

安装完成后检查：

```bash
aasource --version
aasource health --pretty
```

如果系统找不到 `aasource`，可以直接使用模块入口：

```bash
python -m ashare_data --version
python -m ashare_data health --pretty
```

## 使用

```bash
# 实时行情
aasource quotes SH600519 SZ000001 --pretty

# 最近 5 根日 K
aasource bars SH600036 --tf 1d --limit 5 --pretty

# 市场涨跌分布
aasource market breadth --pretty
```

股票代码使用 `SH600519`、`SZ000001`，板块代码使用 `BK0475`。

## 可用数据

### 行情与证券

| 数据 | 命令示例 | 主要内容 | 来源 |
| --- | --- | --- | --- |
| 证券信息 | `aasource securities SH600519` | 代码、名称、市场、证券类型等当前信息 | 通达信 |
| 实时行情 | `aasource quotes SH600519 SZ000001` | 最新价、开高低、昨收、涨跌幅、成交量、成交额、换手率 | 腾讯 |
| 开盘集合竞价 | `aasource auction SH600519` | 09:15–09:25 当前竞价快照和盘口 | 腾讯；不提供历史序列 |
| 单只 K 线 | `aasource bars SH600036 --tf 1d --limit 120` | OHLCV、成交额；支持 `1m/5m/15m/30m/60m/1d` | 股票和指数：通达信；板块：东方财富 |
| 批量 K 线 | `aasource bars-batch --symbols SH600036,SH600050 --tf 1d` | 多只证券 K 线，逐项返回成功或错误 | 通达信 |
| 板块 K 线 | `aasource bars BK0475 --tf 1d --limit 120` | 板块日线或分钟线 | 东方财富 |
| 分笔成交 | `aasource trades SH600036 --trade-date 2026-08-07` | 指定交易日的逐笔成交 | 通达信 |
| 涨停历史 | `aasource limit-history SH600519 --limit 120` | 封板、炸板和连续涨停状态，由日线规则计算 | 通达信日线 |

K 线可以用 `--start`、`--end` 和 `--limit` 限制时间范围和返回量。当前只支持不复权数据。

### 市场数据

| 数据 | 命令示例 | 主要内容 | 来源 |
| --- | --- | --- | --- |
| 市场概览 | `aasource market snapshot` | 上涨、下跌、平盘数量，成交额和证券覆盖情况 | 通达信 + 腾讯 |
| 全市场截面 | `aasource market cross-section` | 全 A 股实时行情列表 | 通达信 + 腾讯 |
| 选股维度 | `aasource market stock-signals` | 涨跌、成交额、换手、量比、行业偏离、持续性及涨停活动等横截面排名 | 通达信 + 腾讯 + 东方财富 |
| 涨跌排行 | `aasource market movers --sort-by change_pct --limit 20` | 按涨跌幅、成交额或换手率排序 | 腾讯 |
| 市场宽度 | `aasource market breadth` | 上涨、下跌、平盘数量及成交额 | 通达信 + 腾讯 |
| 涨跌停池 | `aasource market limits --trade-date 2026-08-07` | 涨停、跌停、炸板、昨日涨停及连板统计 | 东方财富 |

### 板块数据

| 数据 | 命令示例 | 主要内容 | 来源 |
| --- | --- | --- | --- |
| 板块列表 | `aasource sectors list --kind all` | 行业板块和概念板块 | 东方财富 |
| 板块排行 | `aasource sectors rankings --kind industry` | 行业或概念板块涨跌排行 | 东方财富 |
| 板块成分股 | `aasource sectors members BK0475` | 指定板块的当前成分股 | 东方财富 |
| 个股所属板块 | `aasource sectors memberships SH600519` | 个股当前所属行业、概念和地域 | 东方财富 |
| 板块搜索 | `aasource sectors search 白酒` | 按名称或代码搜索板块 | 东方财富 |
| 板块解析 | `aasource sectors resolve 白酒` | 将名称解析为标准 `BK` 代码 | 东方财富 |
| 板块分钟走势 | `aasource sectors minute BK0475` | 板块 1 分钟走势 | 东方财富 |

### 参考数据

| 数据 | 命令示例 | 主要内容 | 来源 |
| --- | --- | --- | --- |
| 龙虎榜 | `aasource reference dragon-tiger --trade-date 20260807` | 指定交易日龙虎榜记录 | 东方财富 |
| 龙虎榜席位 | `aasource reference dragon-tiger-seats SH600519 --trade-date 20260807` | 个股龙虎榜营业部席位 | 东方财富 |
| 机构龙虎榜 | `aasource reference institutional-dragon-tiger --start-date 20260801 --end-date 20260807` | 日期范围内机构龙虎榜记录 | 东方财富 |
| 大宗交易 | `aasource reference block-trades --start-date 20260801 --end-date 20260807` | 日期范围内大宗交易记录 | 东方财富 |
| 资金流 | `aasource reference money-flow SH600519` | 个股主力资金流数据 | 东方财富 |
| 股东数据 | `aasource reference shareholders SH600519 --report-date 20260630` | 指定报告期股东数据 | 东方财富 |
| 基金持仓 | `aasource reference fund-holdings --report-date 20260630` | 指定报告期基金持仓 | 东方财富 |

### 计算特征

| 特征集合 | 命令示例 | 内容 |
| --- | --- | --- |
| `trend_core` | `aasource features SH600036 --set trend_core` | 均线、区间收益、滚动高低点、突破和距离 |
| `volume_core` | `aasource features SH600036 --set volume_core` | 均量、均额、量比、额比、换手率和分位数 |
| `volatility_core` | `aasource features SH600036 --set volatility_core` | ATR、波动率、振幅和波动分位数 |
| `intraday_core` | `aasource features SH600036 --set intraday_core --tf 1m` | VWAP、日内收益、日内高低点距离和分钟量比 |
| `relative_core` | `aasource features SH600036 --set relative_core` | 相对沪深 300 收益；部分板块相对指标暂不可用 |
| `technical_extended` | `aasource features SH600036 --set technical_extended` | EMA、MACD、RSI、布林带和 OBV |
| `agent_core` | `aasource features SH600036 --set agent_core` | 趋势、量价、波动和相对强弱的组合集合 |

多个集合可以逗号分隔，多个股票使用 `--symbols SH600036,SH600050`。

### 工具命令

| 命令 | 用途 |
| --- | --- |
| `aasource catalog --pretty` | 返回完整能力、数据源、单位和特征集合 |
| `aasource health --pretty` | 检查通达信、腾讯和东方财富是否可访问 |

查看全部命令和参数：

```bash
aasource --help
aasource bars --help
aasource catalog --pretty
```

## 返回结果

所有命令都向 stdout 输出同一种 JSON 结构。成功、部分成功和失败都可由程序直接判断。

```json
{
  "schema_version": "1.0",
  "command": "quotes",
  "status": "ok",
  "degraded": false,
  "sources": [{"provider": "tencent", "role": "realtime_quotes"}],
  "data": {},
  "error": null
}
```

批量命令会保留单个标的的状态；上游不可用时明确返回错误，不会静默换源。K 线支持 `--start`、`--end` 和 `--limit`，便于限制返回量。

## 数据说明

AAsource 不保存行情数据库，也不维护本地票池。上游不可用时会返回明确错误，不会静默切换数据源。

## 开发

```bash
git clone git@github.com:The-R0/AAsource.git
cd AAsource
python -m venv .venv
source .venv/bin/activate  # Windows: .\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pytest -q
```

## 许可

代码采用 [MIT License](LICENSE)。第三方接口和数据不在 MIT 授权范围内，使用时请遵守相应服务条款。本项目仅提供数据调用工具，不构成投资建议。
