# Agent CLI Contract

## Version planes

| Plane | Field | v1 |
|---|---|---|
| CLI envelope | `schema_version` | `1.0` |
| Domain / bar | `domain_version` (catalog) | `2` |
| Feature defs | per feature / set `version` | see `feature_sets.yaml` |

Additive CLI fields → `1.x`. Breaking → `2.0`. Planes upgrade independently.

## Envelope

```json
{
  "schema_version": "1.0",
  "command": "bars",
  "request_id": "01J...",
  "as_of": "2026-08-08T16:30:12+08:00",
  "status": "ok",
  "degraded": false,
  "sources": [{"provider": "tdx", "role": "canonical_daily"}],
  "warnings": [],
  "freshness": {"age_seconds": 3, "stale": false},
  "provenance": {},
  "data": {},
  "error": null
}
```

- `status`: `ok` | `error`
- `degraded=true` with `status=ok`: partial success; exit code **0**
- Errors always JSON on stdout (`data=null`, `error={code,message,retryable,details?}`)

### Error codes (selected)

| Code | Meaning |
|---|---|
| `INVALID_REQUEST` | Bad args |
| `SYMBOL_NOT_FOUND` | Unknown / unparseable symbol |
| `UNSUPPORTED_ADJUST_MODE` | Adjust mode not supported |
| `UNSUPPORTED_TIMEFRAME` | Unknown timeframe token |
| `CAPABILITY_NOT_AVAILABLE` | Known feature not enabled in this build/phase |
| `UNAVAILABLE` | Data missing (e.g. no parquet) |
| `PROVIDER_FAILURE` | Upstream failed |
| `CONTRACT_ERROR` | Schema/contract violation |
| `INTERNAL_ERROR` | Bug |

### Exit codes

| Code | Meaning |
|---|---|
| 0 | Success or partial success (`degraded`) |
| 2 | Invalid request |
| 3 | Contract / schema error |
| 4 | Unavailable / capability not available |
| 5 | Provider failure |
| 6 | Internal error |

## Time semantics (never conflate)

| Field | Meaning |
|---|---|
| `trade_date` | Trading day the fact belongs to (`YYYY-MM-DD`) |
| `as_of` | Fact cutoff time when observed/served (ISO-8601 +08:00) |
| `source_time` | Vendor-reported event/print time |
| `retrieved_at` | Local retrieval timestamp |
| `bar.ts` | Bar **end** time |

Historical provider example: `trade_date=2026-08-07` with `as_of=2026-08-08T16:10:00+08:00` is valid.

## Trading sessions (SSE/SZSE)

| Window | Name |
|---|---|
| 09:15–09:25 | Call auction |
| 09:25–09:30 | Silent / prep (no continuous matching) |
| 09:30–11:30 | Continuous |
| 11:30–13:00 | Lunch (no bars invented) |
| 13:00–14:57 | Continuous |
| 14:57–15:00 | Closing call auction |

### Opening call-auction snapshot

`auction <symbols...>` is a current, provisional snapshot available only when Tencent's vendor timestamp is within `09:15:00–09:25:00` Asia/Shanghai. It is not a historical series.

- `indicative_price`: bid-1/ask-1 virtual opening reference price when both agree
- `matched_volume`: virtual matched quantity, canonical unit shares
- `unmatched_buy_volume`: bid-2 virtual unmatched quantity, shares
- `unmatched_sell_volume`: ask-2 virtual unmatched quantity, shares
- `unmatched_side`: `buy`, `sell`, `both`, or `none`
- `book_consistent`: bid-1 price/volume agrees with ask-1 price/volume
- Outside the opening auction window: item-level `CAPABILITY_NOT_AVAILABLE`
- Never interpret Tencent cumulative quote volume as auction matched volume

Intraday bar policy (v1):

- `ts` = bar end time
- **No trade ⇒ no bar** (do not fabricate OHLC=prev, volume=0)
- Lunch generates no empty bars
- Suspended names: omit bars (do not invent)
- Auction: include only if provider supplies a real print; else omit
- `11:30` bar ends morning continuous; `15:00` may include close auction print when present

## Units (project-wide)

| Field | Unit |
|---|---|
| price / OHLC | CNY per share |
| volume | shares (股) |
| amount | CNY |
| `change_pct` | percent points (e.g. `2.31` means 2.31%) |
| `turnover_rate` | percent points (e.g. `4.18` means 4.18%) |
| market_cap | CNY |
| shares | shares |

`volume_lots` only under `raw`.

## Identifiers

- Canonical: `SH600519`, `SZ000001`, `BJxxxxxx`, `SH000300`
- Inputs may be bare / mixed case; outputs always canonical

## Batch protocol

- Preserve **input order** in outputs
- Deduplicate provider work internally; **do not** reorder by provider
- Duplicate inputs: return one result per input occurrence (aligned to inputs)
- Request-level `status=ok` + `degraded=true` when any item fails and any succeeds
- Item-level:

```json
{
  "input": "BADCODE",
  "symbol": null,
  "status": "error",
  "error": {"code": "SYMBOL_NOT_FOUND", "message": "...", "retryable": false},
  "quote": null
}
```

Successful item: `"status":"ok"` plus payload field (`quote` / `security` / `features`…).

## null vs [] vs UNKNOWN

- `null`: unknown / not obtained
- `[]`: success and empty
- `UNKNOWN`: categorical unknown
- Never emit JSON `NaN` / `Infinity` / `-Infinity` — use `null` + warning/status

## Quote

- Canonical `volume` = shares
- `status`: `live` | `delayed` | `unavailable`
- Prefer carrying `source_time` + envelope/provenance `retrieved_at`

## Bar

- Timeframes: `1m` `5m` `15m` `30m` `60m` `1d`
- `status`: `final` | `provisional`
- `adjust`: `none` | `qfq` | `hfq` — v1 only `none`; else `UNSUPPORTED_ADJUST_MODE`
- Future adjust responses must include `adjustment_version` / `adjustment_as_of` (not implemented yet)
- Daily security bars are relayed directly from TDX; sector bars are relayed from Eastmoney.
- Daily bars may include `previous_close`; limit-history requires it and treats missing values as unavailable observations.

## Security / trading rules

Minimal Security fields plus optional:

```json
"trading_rules": {
  "price_limit_type": "standard",
  "price_limit_pct": 10.0,
  "price_tick": 0.01
}
```

`temporal_scope` on security-master payloads is `current` until PIT lands.

## Market subcommands

| Subcommand | Role |
|---|---|
| `snapshot` | Cheap compact overview (width, amount, brief breadth) — not a junk drawer |
| `breadth` | Dedicated breadth dataset (extend with above_ma*, new highs/lows later) |
| `limits` | Limit-up/down / board statistics |
| `movers` | Cross-sectional ranking (`--sort-by`, `--limit`) |

`cross-section` 和 `movers` 中的 quote 都使用 Quote canonical fields。Tencent `volume_lots`、原始数组和 vendor 字段不得出现。指数统一通过 `quotes SH000001 SH000300…` 查询。

## Reference facts

成功响应的 `data` 始终是对象，即使没有记录：

```json
{
  "data_class": "reference",
  "dataset": "block_trades",
  "reference_schema_version": "1.0",
  "query": {},
  "record_count": 0,
  "truncated": false,
  "records": [],
  "units": {
    "price": "CNY_per_share",
    "volume": "shares",
    "amount": "CNY",
    "market_cap": "CNY",
    "percent_fields": "percent_points"
  },
  "provenance": {}
}
```

- Records 只使用英文 canonical fields，不输出上游原始列。
- Provider ratio 必须在 Fact module 内转换为 percent points。
- Provider schema 不能映射到 required canonical fields 时：`degraded=true` + `REFERENCE_SCHEMA_DRIFT`。
- 进程内 Cache 只通过 provenance 的 `cache_hit` 暴露，不输出缓存控制。

## Main Board Point-in-Time (PIT) & Account Execution Universe

### 1. 唯一执行股票池 (Execution Universe)

- **正式执行范围**:
  - 沪市主板：`SH600/601/603/605`
  - 深市主板：`SZ000/001/002/003`
- **正式排除范围**:
  - 创业板：`SZ300/301`
  - 科创板：`SH688/689`
  - 北交所：`BJ`
  - ETF、基金、债券和指数
  - 当时处于 ST、停牌、退市或未上市状态的股票
- **硬拦截规则**:
  - `SH688*` -> 永远不能产生订单，无法进入 Alpha 候选池
  - `SH689*` -> 永远不能产生订单
  - `SZ300*` -> 永远不能产生订单，无法进入 Alpha 候选池
  - `SZ301*` -> 永远不能产生订单
  - `BJ*`    -> 永远不能产生订单
  - 过滤必须发生在因子排名和组合构建之前。

### 2. 非权限板块观察锚 (Market Observation Anchors)

- 观察标的：`SZ399006`（创业板指）、`SH000688`（科创50）及各行业/概念板块指数。
- 标记为 `NON_EXECUTABLE_MARKET_ANCHOR`。
- 仅用于宏观风险偏好、成长风格强弱与观察锚，不可交易、不进入个股排名、不产生目标仓位。

### 3. Point-in-Time ST 状态维护

- 必须基于 `is_st(as_of)` 计算时点状态，禁止使用 `is_st(today)`。
- 历史 ST 摘帽股票在过去 ST 阶段保持 ST；当前 ST 股票在过去正常阶段保持正常。
- 历史 ST 状态缺失时自动降级覆盖等级 (`DEGRADED`) 并排除在严格回测外。

### 4. 数据分层与质量验收

- 采用 `raw/`、`normalized/`、`manifests/`、`quality_reports/` 规范分层。
- 覆盖 3,195+ 沪深主板全部历史与退市证券，避免幸存者偏差。
- 质量验收命令：`AAsource quality-audit`，合格时输出 `MAIN_BOARD_DAILY_PIT_READY`。

## Limit history

`limit-history <symbol>` 从 canonical unadjusted daily bars 的 `previous_close`、high、close 与板块/日期标准涨跌幅限制识别 `sealed_limit_up`、`broken_limit_up` 和连续封板数。价格按 0.01 tick、`ROUND_HALF_UP` 计算。

历史 ST 身份未完成前，不推断主板 5% 涨停事件；响应使用 `degraded=true`，并在 `unavailable_dimensions` 中列出 `historical_st_status` 与 `five_pct_limit_events`。这类缺失不得用当前 ST 状态回填历史。

## No local database

- CLI 不提供 `admin`、`universes` 或 `--release`。
- CLI 与 Fact modules 不读取或写入本地数据库。
- security master 与 Reference fact 只允许进程内缓存。
- 外部 provider 失败时返回明确错误，不使用本地 fallback。

## Sectors

`sectors` owns identity/membership (`list` / `members` / `memberships` / `search`).
`sectors memberships <symbols...>` is the canonical reverse stock-to-sector current snapshot. It supports up to 100 symbols and preserves item-level partial failures.

### Classification sources

| Source | Provider | Scope | Access |
|---|---|---|---|
| `em` | eastmoney | quote-bearing industry/concept boards (`BK####`) + reverse board membership | `sectors list --kind industry\|concept\|all`, `sectors members BK####` |
| `ths` | ths (同花顺) | concept board list + per-stock concepts and company themes | `sectors list --kind ths_concept`, `sectors memberships ... --source ths\|all` |
| `sw` | legulegu | Shenwan 2021 formal industry ladder (L1/L2/L3) | `sectors list --kind sw [--level 1\|2\|3]`, `sectors members 801xxx.SI`, `sectors memberships ... --source sw\|all` |

- `sectors memberships` merges sources by default (`--source all`); each membership row carries a `source` field (`em` / `ths`) and Eastmoney rows use canonical `BK####` `source_id` values. The Shenwan ladder is emitted per item under `sw_industry` (`l1`/`l2`/`l3` with `industry_code` + `name`), not as a board membership.
- Per-source failures stay item-level and surface as distinct warnings (`STOCK_MEMBERSHIP_PARTIAL`, `THS_MEMBERSHIP_PARTIAL`, `SW_INDUSTRY_PARTIAL`) with `degraded=true`.
- `sectors list --kind ths_concept` returns identity rows (name/code/url, no quotes); board quote rankings remain Eastmoney-only under `sectors rankings`. The THS board list requires the optional `py_mini_racer` dependency and returns a clear `CAPABILITY_NOT_AVAILABLE` error when it is missing.
- Industry ladders are deliberately two-tier: Eastmoney boards are the market-facing (盘面) view; Shenwan 2021 is the formal (正式) classification. Neither is replayable historically — both are current snapshots.

`market stock-signals` joins the canonical realtime cross-section with deterministic discovery dimensions: return, amount, turnover, intraday activity expansion, stock-versus-industry divergence, prior-four-day persistence, and observed two-session limit activity. Every derived field exposes its basis or observation window; missing enrichment remains item-level `null` and is counted in `dimension_coverage`.
OHLCV for a sector id uses `bars <sector-id>` — **not** `sectors bars`. Sector bars support canonical `1d` and `1m`; daily bars are unadjusted final facts and minute bars are provisional.

## Generic fact composition

- `scan-stocks` filters and ranks the current market cross-section. Filters are a JSON list of `{field,op,value}`. Unsupported historical dimensions are reported in `skipped_filters`; a non-current requested date is rejected.
- `distance_20d_high` is a ratio (`-0.03` means 3% below the 20-day high). Other `*_pct` fields remain percent points.
- `relative-intraday <symbol> --sector <BK####> [--trade-date YYYY-MM-DD]` aligns stock and sector 1-minute observations without inventing missing minutes. Previous closes are resolved for the requested session from daily bars.
- A dated `relative-intraday` request requires an explicit sector because historical sector membership is not available. Current requests may use current-snapshot membership.
- `sector-context` is current-session only. It composes sector ranking, members, limit activity, 1/3/5/20-day windows, minute summary, internal return distribution, amount concentration, and factual member rankings.
- These commands never emit leader labels, strategy scores, predictions, or trade decisions.

## Features

- Sets are packaged presets in `aasource/resources/feature_sets.yaml`, not CLI subcommands
- Sets: `trend_core`, `volume_core`, `volatility_core`, `intraday_core`, `relative_core`, `technical_extended`, `agent_core` (includes)
- Multi-set: `--set trend_core,volume_core`
- Registry item: `{id, version, params, value, status, observations?, required_observations?, uses_provisional?, reason?}`
- `status`: `ok` | `insufficient_history` | `unavailable`
- Feature `return` / distances / amplitudes use **percent points**
- `include_provisional` (default false); v1 does not silently invent provisional merges
- Never invent `0`/`NaN` for insufficient windows
- Sector-relative ranks stay `unavailable` until the feature engine consumes canonical sector membership

## Freshness

See `aasource/resources/freshness.yaml`. Stale detection must use TradingCalendar for day-based rules.

## Health

Top-level `status` plus provider statuses under `components` (`tencent`, `tdx`, `reference`). Reference provider down ≠ whole fact layer dead.

## Catalog

Machine self-description: `contract_version`, `capabilities` (timeframes, adjust_modes, batch, security_types), feature sets. Capabilities reflect what is actually enabled.

## I/O hygiene

- stdout: protocol JSON only
- stderr: debug / traces
- `--pretty` indented; default compact
- `--stdin` batch JSON `{"symbols":[...]}`
- No Rich/colors/spinners on Agent path
