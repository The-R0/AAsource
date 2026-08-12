from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from ashare_data.domain.batch import map_results, resolve_inputs
from ashare_data.domain.errors import AshareDataError, ErrorCode
from ashare_data.domain.models import SourceRef, WarningItem
from ashare_data.domain.temporal import quote_freshness
from ashare_data.normalize.quotes import quote_from_tencent_row
from ashare_data.normalize.validation import annotate_quote_warnings
from ashare_data.providers.tencent import get_tencent_provider

SHANGHAI = ZoneInfo("Asia/Shanghai")


def get_quotes(
    symbols: list[str],
) -> tuple[list[dict[str, Any]], list[SourceRef], list[WarningItem], bool, dict[str, Any]]:
    retrieved_at = datetime.now(SHANGHAI).isoformat(timespec="milliseconds")
    items = resolve_inputs(symbols)

    def fetch(ok_symbols: list[str]) -> dict[str, Any]:
        provider = get_tencent_provider()
        try:
            raw = provider.fetch_quotes_raw(ok_symbols)
        except Exception as exc:  # noqa: BLE001
            raise AshareDataError(ErrorCode.PROVIDER_FAILURE, str(exc), retryable=True) from exc
        if str(raw.get("status") or "").upper() == "ERROR":
            raise AshareDataError(
                ErrorCode.PROVIDER_FAILURE,
                str(raw.get("error") or "tencent quotes failed"),
                retryable=True,
            )
        data = raw.get("data") or {}
        rows = data.get("quotes") or []
        by_code = {str(r.get("code")): r for r in rows}
        out: dict[str, Any] = {}
        for symbol in ok_symbols:
            row = by_code.get(symbol[2:])
            if not row:
                continue
            quote = quote_from_tencent_row(row, as_of=retrieved_at).to_dict()
            quote["retrieved_at"] = retrieved_at
            quote["source_time"] = quote.get("raw", {}).get("source_time") or data.get("source_time")
            quote.pop("raw", None)
            quote, problems = annotate_quote_warnings(quote)
            if problems:
                quote["quality_warnings"] = problems
            out[symbol] = quote
        return out

    results, degraded = map_results(items, payload_key="quote", fetch=fetch)
    warnings: list[WarningItem] = []
    if degraded:
        bad = [r["input"] for r in results if r["status"] != "ok"]
        warnings.append(WarningItem(code="BATCH_PARTIAL", symbols=[str(x) for x in bad[:20]]))
    source_times = [
        (item.get("quote") or {}).get("source_time")
        for item in results
        if item.get("status") == "ok"
    ]
    freshness = quote_freshness(source_times, retrieved_at=datetime.fromisoformat(retrieved_at))
    if freshness["stale"]:
        degraded = True
        warnings.append(
            WarningItem(
                code="QUOTE_STALE",
                message=f"quote age exceeds {freshness['threshold_seconds']} seconds",
            )
        )
    sources = [SourceRef(provider="tencent", role="realtime_quotes")]
    return results, sources, warnings, degraded, freshness
