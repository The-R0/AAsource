# A-share Data Hub

面向 Agent 与脚本的确定性 A 股事实层。项目只提供证券、行情、K 线、成交、市场集合、参考数据、可复算特征、来源和时效，不输出交易判断或自动下单指令。

公共进程只有一个：`ashare-data` JSON CLI；当前不提供 MCP 进程。它只转接和规范化 TDX、Tencent、Eastmoney 等外部数据源。

```text
Agent / Script → ashare-data CLI → Fact modules → Canonical Fact
                              ├─ request normalization
                              ├─ provider adapters
                              └─ fact normalization
```

`ashare-data` 不读取或写入本地数据库，也不暴露 `admin`、`universes`、`--release`。缓存只存在于当前进程；外部数据源失败时返回明确错误。

## 安装

```powershell
git clone git@github.com:The-R0/AAsource.git ashare-data-hub
cd ashare-data-hub
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

wheel 只携带 `ashare_data/resources` 中的 immutable 配置，不创建数据目录或持久化缓存。

## 查询

```powershell
$ad = ".\.venv\Scripts\ashare-data.exe"

& $ad catalog
& $ad health
& $ad securities SH600519 SZ000001
& $ad quotes SH600519 SZ000001
& $ad auction SH600519 SZ000001
& $ad bars SH600036 --tf 1d --limit 100
& $ad bars BK0475 --tf 1d --limit 120
& $ad limit-history SH600519 --start 2022-01-01 --limit 1200
& $ad bars-batch --symbols SH600036,SH600050 --tf 1d
& $ad trades SH600036 --trade-date 2026-08-07
& $ad features SH600036 --set trend_core,volume_core
& $ad market snapshot
& $ad market cross-section
& $ad market stock-signals
& $ad market movers --sort-by amount --limit 20
& $ad market breadth
& $ad market limits
& $ad sectors rankings --kind industry
& $ad sectors memberships 600519 000858
```

`auction` 只返回交易日 09:15–09:25 的当前开盘集合竞价快照。它根据腾讯盘口映射虚拟撮合价、虚拟匹配量以及买卖方虚拟未匹配量；不保存也不补造历史竞价序列。竞价窗口外逐项返回 `CAPABILITY_NOT_AVAILABLE`。

Reference facts 是可选数据面。输出使用稳定英文 canonical fields；上游原始列只保留在事实模块内部：

```powershell
& $ad reference dragon-tiger --trade-date 20260807
& $ad reference dragon-tiger-seats SH600519 --trade-date 20260807
& $ad reference institutional-dragon-tiger --start-date 20260801 --end-date 20260808
& $ad reference block-trades --start-date 20260801 --end-date 20260808 --category A股
& $ad reference money-flow SH600519
& $ad reference shareholders SH600519 --report-date 20260630
& $ad reference fund-holdings --report-date 20260630
```

## 持久化

本项目无本地持久化。长期历史数据库是独立项目，不是 ashare 的 module、fallback 或运行依赖。

## 开发

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pip wheel --no-deps .
```

公开接口以 CLI 的 `--help` 输出、JSON 响应中的 `schema_version` 及自动化测试为准。

## 许可证与数据源

本项目原创代码采用 [MIT License](LICENSE)。该许可证不适用于第三方行情、服务端点、商标、协议实现或内容。本项目与通达信、腾讯、东方财富及任何交易所不存在隶属、授权或背书关系；使用者应自行确认并遵守适用的数据源与交易所条款。

本项目不随仓库或软件包分发行情数据库，也不保证第三方接口的准确性、连续性或可用性。第三方依赖及数据源分别受其各自许可证和服务条款约束；MIT License 仅授权本仓库的原创代码。本项目不构成投资建议。
