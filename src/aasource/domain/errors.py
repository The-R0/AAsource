from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class ErrorCode(StrEnum):
    INVALID_REQUEST = "INVALID_REQUEST"
    SYMBOL_NOT_FOUND = "SYMBOL_NOT_FOUND"
    UNSUPPORTED_ADJUST_MODE = "UNSUPPORTED_ADJUST_MODE"
    UNSUPPORTED_TIMEFRAME = "UNSUPPORTED_TIMEFRAME"
    CAPABILITY_NOT_AVAILABLE = "CAPABILITY_NOT_AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    PROVIDER_FAILURE = "PROVIDER_FAILURE"
    CONTRACT_ERROR = "CONTRACT_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"


@dataclass
class AshareDataError(Exception):
    code: ErrorCode
    message: str
    retryable: bool = False
    details: dict[str, Any] | None = None

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "code": str(self.code),
            "message": self.message,
            "retryable": self.retryable,
        }
        if self.details:
            payload["details"] = self.details
        return payload


def exit_code_for(error: AshareDataError) -> int:
    mapping = {
        ErrorCode.INVALID_REQUEST: 2,
        ErrorCode.SYMBOL_NOT_FOUND: 2,
        ErrorCode.UNSUPPORTED_ADJUST_MODE: 2,
        ErrorCode.UNSUPPORTED_TIMEFRAME: 2,
        ErrorCode.CAPABILITY_NOT_AVAILABLE: 4,
        ErrorCode.CONTRACT_ERROR: 3,
        ErrorCode.UNAVAILABLE: 4,
        ErrorCode.NOT_IMPLEMENTED: 4,
        ErrorCode.PROVIDER_FAILURE: 5,
        ErrorCode.INTERNAL_ERROR: 6,
    }
    return mapping.get(error.code, 6)
