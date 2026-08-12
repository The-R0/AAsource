from __future__ import annotations

from typing import Any

import pandas as pd

from ashare_data.domain.batch import map_results, resolve_inputs
from ashare_data.domain.errors import AshareDataError, ErrorCode
from ashare_data.domain.identifiers import canonicalize_symbol
from ashare_data.features import intraday, momentum, relative, trend, volatility, volume
from ashare_data.features.registry import get_feature
from ashare_data.services.bars import get_bars
from ashare_data.settings import load_yaml_resource

_REGISTERED = False

_REQUIRED = {
    "ma": lambda p: int(p.get("window", 20)),
    "ema": lambda p: int(p.get("window", 20)),
    "return": lambda p: int(p.get("window", 5)) + 1,
    "rolling_high": lambda p: int(p.get("window", 20)),
    "rolling_low": lambda p: int(p.get("window", 20)),
    "distance_to_ma": lambda p: int(p.get("window", 20)),
    "distance_to_high": lambda p: int(p.get("window", 20)),
    "breakout_pct": lambda p: int(p.get("window", 20)) + 1,
    "atr": lambda p: int(p.get("window", 14)) + 1,
    "volatility": lambda p: int(p.get("window", 20)) + 1,
    "amplitude": lambda p: 2,
    "average_amplitude": lambda p: int(p.get("window", 20)) + 1,
    "atr_percentile": lambda p: int(p.get("window", 60)) + 14,
    "average_volume": lambda p: int(p.get("window", 20)),
    "average_amount": lambda p: int(p.get("window", 20)),
    "volume_ratio": lambda p: int(p.get("window", 5)) + 1,
    "amount_ratio": lambda p: int(p.get("window", 5)) + 1,
    "amount_percentile": lambda p: int(p.get("window", 20)),
    "turnover_rate": lambda p: 1,
    "average_turnover": lambda p: int(p.get("window", 20)),
    "turnover_percentile": lambda p: int(p.get("window", 20)),
    "vwap": lambda p: 1,
    "distance_to_vwap": lambda p: 1,
    "intradaily_return": lambda p: 1,
    "distance_to_intraday_high": lambda p: 1,
    "distance_to_intraday_low": lambda p: 1,
    "intradaily_volume_ratio": lambda p: int(p.get("window", 5)) + 1,
    "relative_return_index": lambda p: int(p.get("window", 5)) + 1,
    "relative_return_sector": lambda p: 1,
    "sector_return_rank": lambda p: 1,
    "sector_amount_rank": lambda p: 1,
    "sector_turnover_rank": lambda p: 1,
    "macd": lambda p: int(p.get("slow", 26)) + int(p.get("signal", 9)),
    "rsi": lambda p: int(p.get("window", 14)) + 1,
    "boll": lambda p: int(p.get("window", 20)),
    "obv": lambda p: 2,
}

_SECTOR_PENDING = {
    "relative_return_sector",
    "sector_return_rank",
    "sector_amount_rank",
    "sector_turnover_rank",
}


def _ensure_registry() -> None:
    global _REGISTERED
    if _REGISTERED:
        return
    trend.register_trend_features()
    volatility.register_volatility_features()
    volume.register_volume_features()
    momentum.register_technical_features()
    relative.register_relative_features()
    intraday.register_intraday_features()
    _REGISTERED = True


def _load_sets() -> dict[str, Any]:
    return load_yaml_resource("feature_sets.yaml")


def _daily_frame(symbol: str, limit: int = 300) -> pd.DataFrame:
    rows, _sources, _warnings, _degraded, _provenance = get_bars(
        symbol, timeframe="1d", limit=limit, adjust="none"
    )
    return pd.DataFrame(rows)


def _minute_frame(symbol: str) -> pd.DataFrame:
    rows, _sources, _warnings, _degraded, _provenance = get_bars(
        symbol, timeframe="1m", limit=240, adjust="none"
    )
    if not rows:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume", "amount"])
    return pd.DataFrame(rows)


def _expand_set_names(raw: str | list[str], sets: dict[str, Any]) -> list[str]:
    names = raw if isinstance(raw, list) else [p.strip() for p in str(raw).split(",") if p.strip()]
    out: list[str] = []
    for name in names:
        if name == "schema_version" or name not in sets:
            raise AshareDataError(ErrorCode.INVALID_REQUEST, f"Unknown feature set: {name}")
        spec = sets[name]
        includes = spec.get("includes") or []
        if includes:
            for child in includes:
                if child not in out:
                    out.append(child)
        elif name not in out:
            out.append(name)
    return out


def _feature_result(defn, frame: pd.DataFrame, params: dict[str, Any], *, uses_provisional: bool) -> dict[str, Any]:
    if defn.id in _SECTOR_PENDING:
        return {
            "id": defn.id,
            "version": defn.version,
            "params": params,
            "value": None,
            "status": "unavailable",
            "reason": "sector_membership_not_ready",
            "uses_provisional": uses_provisional,
        }
    required_fn = _REQUIRED.get(defn.id)
    required = required_fn(params) if required_fn else int(params.get("window") or 1)
    observations = int(len(frame))
    # Field dependency soft-fail
    for field in defn.required_fields:
        if field and field not in frame.columns:
            return {
                "id": defn.id,
                "version": defn.version,
                "params": params,
                "value": None,
                "status": "unavailable",
                "reason": f"missing_field:{field}",
                "observations": observations,
                "required_observations": required,
                "uses_provisional": uses_provisional,
            }
    if observations < required:
        return {
            "id": defn.id,
            "version": defn.version,
            "params": params,
            "value": None,
            "status": "insufficient_history",
            "observations": observations,
            "required_observations": required,
            "uses_provisional": uses_provisional,
        }
    value = defn.compute(frame, params)
    if value is None and defn.id in {"turnover_rate", "average_turnover", "turnover_percentile"}:
        return {
            "id": defn.id,
            "version": defn.version,
            "params": params,
            "value": None,
            "status": "unavailable",
            "reason": "turnover_not_in_daily_release",
            "observations": observations,
            "required_observations": required,
            "uses_provisional": uses_provisional,
        }
    if value is None and defn.id == "relative_return_index":
        return {
            "id": defn.id,
            "version": defn.version,
            "params": params,
            "value": None,
            "status": "unavailable",
            "reason": "benchmark_bars_missing_or_short",
            "observations": observations,
            "required_observations": required,
            "uses_provisional": uses_provisional,
        }
    return {
        "id": defn.id,
        "version": defn.version,
        "params": params,
        "value": value,
        "status": "ok" if value is not None else "insufficient_history",
        "observations": observations,
        "required_observations": required,
        "uses_provisional": uses_provisional,
    }


def compute_feature_set(
    symbol: str,
    set_name: str,
    *,
    timeframe: str = "1d",
    include_provisional: bool = False,
) -> dict[str, Any]:
    result = compute_feature_sets(
        symbol, [set_name], timeframe=timeframe, include_provisional=include_provisional
    )
    # single-set convenience: flatten first set payload
    sets_out = result["sets"]
    if len(sets_out) == 1:
        only = sets_out[0]
        return {
            "symbol": result["symbol"],
            "timeframe": result["timeframe"],
            "set": only["set"],
            "set_version": only["set_version"],
            "availability": only.get("availability"),
            "include_provisional": include_provisional,
            "uses_provisional": only.get("uses_provisional", False),
            "features": only["features"],
        }
    return result


def compute_feature_sets(
    symbol: str,
    set_names: list[str],
    *,
    timeframe: str = "1d",
    include_provisional: bool = False,
) -> dict[str, Any]:
    _ensure_registry()
    symbol = canonicalize_symbol(symbol)
    sets = _load_sets()
    expanded = _expand_set_names(set_names, sets)
    uses_provisional = False
    if include_provisional:
        uses_provisional = False  # v1 honesty

    daily = None
    minute = None
    set_payloads = []
    for name in expanded:
        spec = sets[name]
        required_tf = spec.get("requires_timeframe") or "1d"
        if required_tf == "1m":
            if timeframe not in {"1m", "1d"}:
                raise AshareDataError(
                    ErrorCode.CAPABILITY_NOT_AVAILABLE,
                    f"set {name} requires intraday bars",
                    details={"set": name, "requires_timeframe": "1m"},
                )
            if minute is None:
                try:
                    minute = _minute_frame(symbol)
                except Exception as exc:  # noqa: BLE001
                    raise AshareDataError(ErrorCode.PROVIDER_FAILURE, str(exc), retryable=True) from exc
            frame = minute
            tf_used = "1m"
        else:
            if timeframe != "1d" and required_tf == "1d":
                # still allow explicit 1d compute
                pass
            if daily is None:
                daily = _daily_frame(symbol)
            frame = daily
            tf_used = "1d"
        features = []
        for item in spec.get("features") or []:
            defn = get_feature(item["id"])
            params = dict(item.get("params") or {})
            features.append(_feature_result(defn, frame, params, uses_provisional=uses_provisional))
        set_payloads.append(
            {
                "set": name,
                "set_version": spec.get("version"),
                "availability": spec.get("availability", "available"),
                "note": spec.get("note"),
                "timeframe": tf_used,
                "uses_provisional": uses_provisional,
                "features": features,
            }
        )
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "include_provisional": include_provisional,
        "sets": set_payloads,
        "set_count": len(set_payloads),
    }


def compute_features_batch(
    symbols: list[str],
    set_name: str | list[str],
    *,
    timeframe: str = "1d",
    include_provisional: bool = False,
) -> tuple[list[dict[str, Any]], bool]:
    items = resolve_inputs(symbols)
    names = set_name if isinstance(set_name, list) else [p.strip() for p in str(set_name).split(",") if p.strip()]

    def fetch(ok_symbols: list[str]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for symbol in ok_symbols:
            if len(names) == 1:
                out[symbol] = compute_feature_set(
                    symbol, names[0], timeframe=timeframe, include_provisional=include_provisional
                )
            else:
                out[symbol] = compute_feature_sets(
                    symbol, names, timeframe=timeframe, include_provisional=include_provisional
                )
        return out

    return map_results(items, payload_key="features", fetch=fetch)
