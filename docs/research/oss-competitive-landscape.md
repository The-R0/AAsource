# AAsource 开源许可与竞争格局

更新时间：2026-08-12

## 结论

AKShare 的代码采用标准 MIT License，可以使用、修改、分发和商业使用，但必须保留版权和许可声明；该许可只覆盖 AKShare 代码，不自动授予东方财富、腾讯、通达信等上游数据的使用或再分发权。[AKShare LICENSE](https://github.com/akfamily/akshare/blob/main/LICENSE) [AKShare 官方仓库](https://github.com/akfamily/akshare)

AAsource 不适合定位成“AKShare 替代品”或“首个多源 A 股库”。更准确且有区分度的定位是：**面向 Agent 与自动化脚本的无状态、provider-explicit、可审计 A 股事实层，以稳定 JSON CLI 提供规范化事实，而不是提供宽泛的 DataFrame 接口或本地数据库。**

## 直接或邻近项目

| 项目 | 主要定位 | 与本项目的重叠 | 主要区别 |
|---|---|---|---|
| [AKShare](https://github.com/akfamily/akshare) | 覆盖面很广的 Python 财经数据接口库 | 多种公开财经数据接口 | 以 Python/DataFrame 和接口广度为核心，社区规模远大于本项目 |
| [finshare](https://github.com/finvfamily/finshare) | 东方财富、Yahoo、腾讯、新浪、TDX、BaoStock 等多源统一库 | 多源、统一格式、自动故障切换 | 面向 Python 用户和多市场；本项目可在稳定 JSON 契约、来源语义和无状态方面区分 |
| [pyqauto](https://pypi.org/project/pyqauto/1.0.0rc2/) | 本地 A 股多源路由器 | 字段标准化、健康检查、fallback、熔断、缓存、审计 | 这是概念上最接近的项目之一，但更强调自动路由和本地运行控制；本项目应强调 provider-explicit 和跨进程 JSON 契约 |
| [mootdx](https://github.com/mootdx/mootdx) | TDX 在线/离线数据封装 | TDX 行情和 CLI | 单一 TDX 体系，且包含本地数据读取，不是无状态多源事实层 |
| [eltdx](https://github.com/electkismet/eltdx) | TDX 协议客户端及 MCP | Agent、JSON、行情、逐笔、K 线 | 功能更贴近 TDX 与短线研究，README 明确限制商业使用；其后续 AxData 还包含数据库能力 |
| [AKTools](https://github.com/akfamily/aktools) | 将 AKShare 暴露为 HTTP API | 机器可调用的数据出口 | 本质是 AKShare 的传输包装，不负责多源 canonical contract |

此外，2026 年仍有 [stock-gateway](https://pypi.org/project/stock-gateway/)、[stockdata-hub](https://pypi.org/project/stockdata-hub/0.1.3/) 等新项目做统一模型和多源故障切换，因此“多源”和“统一字段”本身已不是独占卖点。

## 当前竞争力

已有的强项：

- 只有一个稳定 JSON CLI，适合 Agent、Shell、Node、Go 等跨语言进程调用。
- canonical symbol、字段和单位由本项目定义，不把上游原始列直接暴露给使用者。
- 明确返回 provenance、freshness、degraded、warning 和批量 item-level error，便于自动化系统判断数据可信度。
- 无本地数据库、无历史票池、无静默本地 fallback，部署边界简单。
- 特征可复算，不输出交易建议或自动下单结论。

目前的短板：

- 数据覆盖面远小于 AKShare 和 finshare，不能以接口数量竞争。
- 缺少公开用户、长期运行记录、兼容性承诺、性能基准和真实源稳定性报告。
- 只有 CLI、暂时没有 Python public API、HTTP 或 MCP；这既是聚焦，也会缩小早期用户面。
- GitHub 发布基础已补齐 LICENSE、CI、版本一致性与真实仓库 URL；贡献说明和安全说明可在社区形成后继续补充。
- 当前直接依赖 `pytdx==1.72`。其[官方仓库](https://github.com/rainx/pytdx)已于 2020 年归档，仓库没有清晰的标准 LICENSE，README 还明确要求不要商业使用。这不会阻止本项目公开自己的源代码，但会使“整个工具链可自由商用”的声明存在明显风险。发布前应替换、重写 TDX 适配层，或至少把该限制明确写进第三方声明和使用边界。

## 建议定位

推荐一句话：

> A stateless, auditable A-share fact layer for agents and scripts, exposing canonical market facts through a stable JSON CLI with explicit provenance, freshness and partial-failure semantics.

不建议使用“比 AKShare 更全”“自动找到最好的数据源”“生产级无风险”等表述。项目当前最有竞争力的不是数据数量，而是**机器契约的确定性、可追溯性和无状态边界**。

## 许可证建议

本项目自己的原创代码可以选择 MIT，和 AKShare、finshare 等生态项目的使用习惯一致。但在加入 LICENSE 之前，应先完成依赖许可清单，尤其处理 pytdx；同时在 README 中分开说明“代码许可证”和“第三方数据源条款”。MIT 许可证不是上游数据授权，也不是投资或数据质量保证。
