# Domain context

## Fact

经过 canonical identifier、单位、时间、来源与缺失语义处理后，可由 Agent 直接消费的数据。Fact 不包含市场主线、龙头、买卖或仓位判断。

## Fact module

从请求到 Fact 的完整责任主体。它规范化请求，调用事实来源，把来源响应规范化为 Fact，并披露时效、来源和降级。其内部数据来源、缓存和转换步骤不是 Agent 可选择的能力。

## Agent CLI

本项目唯一公共 interface。stdout 始终是固定 JSON envelope；查询失败也通过 JSON 与稳定 exit code 表达。

## Canonical bars

统一 OHLCV 事实。price 为 CNY/share，volume 为 shares，amount 为 CNY；日线是 final，盘中线是 provisional。Features 只能消费 canonical bars。

## Runtime snapshot

可重建、可过期的 canonical 当前行情截面。它只存在于进程内，不得包含数据商原始行情行。

## Reference fact

龙虎榜、大宗交易、股东、基金持仓、资金流等非价格 Fact。它使用稳定字段、canonical identifier 和统一单位；数据商原始字段不是 Reference fact。

## Cache

进程内可重建的短期数据副本，用于降低来源压力和延迟。进程结束即消失；Agent 只能观察由它造成的时效与来源证据。
