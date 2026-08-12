from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from ashare_data.domain.enums import (
    AdjustMode,
    BarStatus,
    DataQuality,
    EnvelopeStatus,
    ProviderName,
    QuoteStatus,
    SecurityType,
    Timeframe,
)


def _clean(d: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in d.items() if v is not None or k in {"data", "error", "degraded"}}


@dataclass
class SourceRef:
    provider: str
    role: str

    def to_dict(self) -> dict[str, Any]:
        return {"provider": self.provider, "role": self.role}


@dataclass
class WarningItem:
    code: str
    message: str = ""
    symbols: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"code": self.code}
        if self.message:
            out["message"] = self.message
        if self.symbols:
            out["symbols"] = list(self.symbols)
        return out


@dataclass
class Security:
    symbol: str
    code: str
    exchange: str
    name: str | None = None
    security_type: str = SecurityType.UNKNOWN
    board: str | None = None
    listed_date: str | None = None
    delisted_date: str | None = None
    is_st: bool | None = None
    is_suspended: bool | None = None
    price_limit_pct: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Quote:
    symbol: str
    as_of: str
    last: float | None
    open: float | None
    high: float | None
    low: float | None
    previous_close: float | None
    change: float | None
    change_pct: float | None
    volume: int | None
    amount: float | None
    turnover_rate: float | None
    source: str = ProviderName.TENCENT
    status: str = QuoteStatus.LIVE
    name: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if not d.get("raw"):
            d.pop("raw", None)
        return d


@dataclass
class Bar:
    symbol: str
    timeframe: str
    ts: str
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    volume: int | None
    amount: float | None
    previous_close: float | None = None
    status: str = BarStatus.FINAL
    source: str = ProviderName.TDX
    adjust: str = AdjustMode.NONE
    quality: str = DataQuality.COMPLETE
    missing_fields: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if not d["missing_fields"]:
            d.pop("missing_fields", None)
        return d


@dataclass
class Envelope:
    schema_version: str
    command: str
    request_id: str
    as_of: str
    status: str
    degraded: bool
    sources: list[SourceRef] = field(default_factory=list)
    warnings: list[WarningItem] = field(default_factory=list)
    data: Any = None
    error: dict[str, Any] | None = None
    freshness: dict[str, Any] | None = None
    provenance: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "command": self.command,
            "request_id": self.request_id,
            "as_of": self.as_of,
            "status": self.status,
            "degraded": self.degraded,
            "sources": [s.to_dict() for s in self.sources],
            "warnings": [w.to_dict() for w in self.warnings],
            "freshness": self.freshness,
            "provenance": self.provenance,
            "data": self.data,
            "error": self.error,
        }
