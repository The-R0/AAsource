# AAsource

给 Agent 和脚本用的 A 股事实 CLI。返回稳定 JSON：证券、行情、K 线、成交、市场截面、板块、可复算特征和参考数据。

不给交易建议，也不下单。

[![CI](https://github.com/The-R0/AAsource/actions/workflows/test.yml/badge.svg)](https://github.com/The-R0/AAsource/actions/workflows/test.yml)
[![Python 3.11–3.12](https://img.shields.io/badge/python-3.11%20%7C%203.12-blue)](https://github.com/The-R0/AAsource)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

```text
Agent / Script  →  AAsource  →  Canonical JSON Fact
```

## 安装

需要 Python 3.11 或 3.12。装的是包，不是整仓：

```bash
pip install git+https://github.com/The-R0/AAsource.git
```

只想要命令、不想进当前环境：

```bash
pipx install git+https://github.com/The-R0/AAsource.git
```

装完后命令是 `AAsource`。包名也是 `AAsource`。包里只有代码和不可变配置，不会创建数据目录，也不会写本地数据库。

PyPI 发布后可以改用 `pip install AAsource` 或 `pipx install AAsource`。

## 30 秒试用

```bash
AAsource health
AAsource quotes SH600519 SZ000001
AAsource bars SH600036 --tf 1d --limit 5
```

stdout 永远是同一套 JSON envelope，失败也是 JSON，不走 stderr 文本：

```json
{
  "schema_version": "1.0",
  "command": "quotes",
  "request_id": "01J...",
  "as_of": "2026-08-13T10:31:02+08:00",
  "status": "ok",
  "degraded": false,
  "sources": [{"provider": "tencent", "role": "realtime_quotes"}],
  "warnings": [],
  "freshness": {"age_seconds": 3, "stale": false},
  "data": {},
  "error": null
}
```

`status=ok` 且 `degraded=true` 表示部分成功，退出码仍是 0。

## 适合 / 不适合

**适合**

- Agent、Shell、Node、Go 等跨进程调用，要稳定 JSON 而不是 DataFrame
- 要看到来源、时效、降级和单票错误，不能“看起来有数就算成功”
- 不想维护本地行情库或票池

**不适合**

- 要 AKShare / finshare 那种宽接口面
- 要落盘多年历史（那是独立项目，不是本工具的 fallback）
- 要 Python 公共 API、HTTP 或 MCP（当前没有）
- 要自动换成“最好的数据源”（上游失败会明确报错，不静默切换）

## 命令

| 命令 | 做什么 |
|---|---|
| `catalog` | 能力与单位 |
| `health` | 上游是否可达 |
| `securities` | 证券主数据 |
| `quotes` | 实时行情 |
| `auction` | 开盘集合竞价当前快照（仅 09:15–09:25） |
| `bars` / `bars-batch` | K 线（股票/指数走 TDX，`BK####` 板块走东财） |
| `trades` | 某一交易日分笔 |
| `limit-history` | 单票涨停活动史（由日线规则推导） |
| `features` | 可复算特征，只消费 canonical bars |
| `market` | 市场截面、宽度、排行、涨跌停 |
| `sectors` | 板块身份、成分、排行 |
| `reference` | 龙虎榜、大宗、股东、基金持仓、资金流 |

```bash
AAsource catalog
AAsource securities SH600519 SZ000001
AAsource auction SH600519 SZ000001
AAsource bars BK0475 --tf 1d --limit 120
AAsource bars-batch --symbols SH600036,SH600050 --tf 1d
AAsource trades SH600036 --trade-date 2026-08-07
AAsource features SH600036 --set trend_core,volume_core
AAsource market movers --sort-by amount --limit 20
AAsource market breadth
AAsource sectors rankings --kind industry
AAsource reference dragon-tiger --trade-date 20260807
AAsource reference money-flow SH600519
```

代码用 `SH600519` / `SZ000001` / `BK0475`。价格是元/股，成交量是股，成交额是元，百分比是百分点。日线是 final，盘中线是 provisional。

`auction` 只给当前开盘集合竞价快照，不存也不补历史。窗口外逐项返回 `CAPABILITY_NOT_AVAILABLE`。

## 数据源

| 职责 | 来源 |
|---|---|
| 证券主数据、日线、分钟线、分笔、公司行为 | 通达信（TDX） |
| 实时行情、开盘集合竞价快照 | 腾讯 |
| 板块、涨跌停池、Reference facts | 东方财富 |

来源失败不会被另一个源悄悄顶替。`degraded=true` 必须出现在 JSON 里。

当前 v1 不提供前复权 / 后复权。

## 开发

clone 仓库只给改代码的人：

```bash
git clone git@github.com:The-R0/AAsource.git
cd AAsource
python -m venv .venv
source .venv/bin/activate          # Windows: .\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pytest -q
```

## 许可证与数据源

本项目原创代码采用 [MIT License](LICENSE)。该许可证不覆盖第三方行情、服务端点、商标、协议或内容。本项目与通达信、腾讯、东方财富及任何交易所不存在隶属、授权或背书关系。

运行时依赖 `pytdx==1.72`。它不是本仓库的一部分；上游未声明标准开源许可证，并写明仅供个人研究、不要商业使用。使用前请自行阅读其条款。

仓库和 wheel 都不分发行情数据库，也不保证第三方接口的准确性、连续性或可用性。本项目不构成投资建议。
