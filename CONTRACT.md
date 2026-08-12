# Agent CLI Contract

## Version planes

| Plane | Field | v1 |
|---|---|---|
| CLI envelope | `schema_version` | `1.0` |
| Domain / bar | `domain_version` (catalog) | `1` |
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

`market stock-signals` joins the canonical realtime cross-section with deterministic discovery dimensions: return, amount, turnover, intraday activity expansion, stock-versus-industry divergence, prior-four-day persistence, and observed two-session limit activity. Every derived field exposes its basis or observation window; missing enrichment remains item-level `null` and is counted in `dimension_coverage`.
OHLCV for a sector id uses `bars <sector-id>` — **not** `sectors bars`. Sector bars support canonical `1d` and `1m`; daily bars are unadjusted final facts and minute bars are provisional.

## Features

- Sets are packaged presets in `ashare_data/resources/feature_sets.yaml`, not CLI subcommands
- Sets: `trend_core`, `volume_core`, `volatility_core`, `intraday_core`, `relative_core`, `technical_extended`, `agent_core` (includes)
- Multi-set: `--set trend_core,volume_core`
- Registry item: `{id, version, params, value, status, observations?, required_observations?, uses_provisional?, reason?}`
- `status`: `ok` | `insufficient_history` | `unavailable`
- Feature `return` / distances / amplitudes use **percent points**
- `include_provisional` (default false); v1 does not silently invent provisional merges
- Never invent `0`/`NaN` for insufficient windows
- Sector-relative ranks stay `unavailable` until the feature engine consumes canonical sector membership

## Freshness

See `ashare_data/resources/freshness.yaml`. Stale detection must use TradingCalendar for day-based rules.

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
