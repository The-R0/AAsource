from __future__ import annotations

import secrets
import time
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from ashare_data.domain.enums import EnvelopeStatus
from ashare_data.domain.errors import AshareDataError, exit_code_for
from ashare_data.domain.models import Envelope, SourceRef, WarningItem

SHANGHAI = ZoneInfo("Asia/Shanghai")
SCHEMA_VERSION = "1.0"


def new_request_id() -> str:
    # ulid-ish compact id without extra dependency
    return f"{int(time.time() * 1000):x}{secrets.token_hex(4)}"


def now_iso() -> str:
    return datetime.now(SHANGHAI).isoformat(timespec="seconds")


def ok(
    command: str,
    data: Any,
    *,
    sources: list[SourceRef] | None = None,
    warnings: list[WarningItem] | None = None,
    degraded: bool = False,
    freshness: dict[str, Any] | None = None,
    provenance: dict[str, Any] | None = None,
    request_id: str | None = None,
) -> tuple[dict[str, Any], int]:
    env = Envelope(
        schema_version=SCHEMA_VERSION,
        command=command,
        request_id=request_id or new_request_id(),
        as_of=now_iso(),
        status=EnvelopeStatus.OK,
        degraded=degraded,
        sources=sources or [],
        warnings=warnings or [],
        data=data,
        error=None,
        freshness=freshness,
        provenance=provenance,
    )
    return env.to_dict(), 0


def fail(
    command: str,
    error: AshareDataError | Exception,
    *,
    request_id: str | None = None,
) -> tuple[dict[str, Any], int]:
    if isinstance(error, AshareDataError):
        err = error
        code = exit_code_for(error)
    else:
        err = AshareDataError(
            code=__import__("ashare_data.domain.errors", fromlist=["ErrorCode"]).ErrorCode.INTERNAL_ERROR,
            message=str(error),
            retryable=False,
        )
        code = 6
    env = Envelope(
        schema_version=SCHEMA_VERSION,
        command=command,
        request_id=request_id or new_request_id(),
        as_of=now_iso(),
        status=EnvelopeStatus.ERROR,
        degraded=False,
        sources=[],
        warnings=[],
        data=None,
        error=err.to_dict(),
    )
    return env.to_dict(), code
