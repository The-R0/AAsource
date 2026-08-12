from __future__ import annotations

from enum import StrEnum


class ProviderName(StrEnum):
    TDX = "tdx"
    TENCENT = "tencent"
    INTERNAL = "internal"


class SecurityType(StrEnum):
    STOCK = "stock"
    INDEX = "index"
    ETF = "etf"
    UNKNOWN = "UNKNOWN"


class Timeframe(StrEnum):
    M1 = "1m"
    M5 = "5m"
    M15 = "15m"
    M30 = "30m"
    M60 = "60m"
    D1 = "1d"


class BarStatus(StrEnum):
    FINAL = "final"
    PROVISIONAL = "provisional"


class AdjustMode(StrEnum):
    NONE = "none"
    QFQ = "qfq"
    HFQ = "hfq"


class DataQuality(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    STALE = "stale"
    INVALID = "invalid"
    UNAVAILABLE = "unavailable"


class EnvelopeStatus(StrEnum):
    OK = "ok"
    ERROR = "error"


class QuoteStatus(StrEnum):
    LIVE = "live"
    DELAYED = "delayed"
    UNAVAILABLE = "unavailable"
