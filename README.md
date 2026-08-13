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

常用命令：

| 命令 | 数据 |
| --- | --- |
| `quotes` | 实时行情 |
| `bars` / `bars-batch` | 日线、分钟线 |
| `trades` | 分笔成交 |
| `auction` | 09:15–09:25 开盘集合竞价快照 |
| `securities` | 证券列表与基础信息 |
| `market` | 市场截面、涨跌分布、排行、涨跌停 |
| `sectors` | 板块、成分股与排行 |
| `reference` | 龙虎榜、大宗交易、股东、资金流等参考数据 |
| `features` | 基于 K 线计算的技术特征 |

查看全部命令和参数：

```bash
aasource --help
aasource bars --help
```

如果系统找不到 `aasource` 命令，使用 `python -m ashare_data`，参数完全相同。

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

## 数据源

- 通达信：证券信息、K 线、分笔成交
- 腾讯：实时行情、开盘集合竞价快照
- 东方财富：板块、市场排行及参考数据

AAsource 不保存行情数据库，也不维护本地票池。

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
